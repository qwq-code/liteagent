from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from jsonschema import Draft202012Validator

from .adapter_results import has_passed_verification
from .result_envelopes import iter_result_mappings


COMPLETION_ARGUMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reason": {"type": "string", "minLength": 1},
        "evidence": {
            "type": ["string", "array"],
            "minLength": 1,
            "items": {
                "oneOf": [
                    {
                        "type": "string",
                        "description": "One concise plain-text evidence statement.",
                    },
                    {
                        "type": "object",
                        "description": (
                            "One compact structured evidence record copied from a successful "
                            "model-visible tool result. This record is informational; the "
                            "completion gate still verifies the execution ledger."
                        ),
                        "maxProperties": 16,
                        "additionalProperties": True,
                    },
                ],
            },
            "minItems": 1,
            "description": (
                "One nonempty evidence statement, or a native JSON array of concise strings "
                "or compact structured evidence records. A string is treated as plain text, "
                "even when it looks like JSON. Refer to successful tool results; the "
                "execution ledger determines whether the work is complete."
            ),
        },
    },
    "required": ["reason", "evidence"],
    "additionalProperties": False,
}
_COMPLETION_ARGUMENT_VALIDATOR = Draft202012Validator(COMPLETION_ARGUMENT_SCHEMA)

READ_ONLY_ACTION_SUFFIXES = (
    ".find",
    ".inspect",
    ".read",
    ".read_file",
    ".read_text",
    ".extract_text_batch",
    ".query",
    ".list",
    ".snapshot",
    ".status",
    ".wait_for",
)
SAVE_ACTION_SUFFIXES = (".save", ".export")
READ_ONLY_ACTIONS = frozenset(
    {
        "clipboard.get",
        "mail.query_latest_messages",
        "mail.query_messages",
        "workspace.find_files",
    }
)

_CANONICAL_ACTION_ALIASES: dict[tuple[str, str], tuple[str, str]] = {
    ("libreoffice_impress", action): ("libreoffice_impress", "shape.set_geometry")
    for action in ("shape.align_to_slide", "shape.move", "shape.resize")
}
_CANONICAL_PUBLIC_ACTIONS: dict[tuple[str, str], tuple[str, ...]] = {
    ("libreoffice_impress", "shape.set_geometry"):
        ("shape.align_to_slide", "shape.move", "shape.resize"),
}

COMPLETION_RECOVERY_CLAIM_ONLY = "claim_only"
COMPLETION_RECOVERY_READBACK_ONLY = "readback_only"
COMPLETION_RECOVERY_TASK_STATE = "task_state"


def action_is_read_only(action: str) -> bool:
    return action in READ_ONLY_ACTIONS or action.endswith(READ_ONLY_ACTION_SUFFIXES)


def action_is_save(action: str) -> bool:
    return action.endswith(SAVE_ACTION_SUFFIXES)


def required_mutation_actions(
    state: Any,
    *,
    instruction_actions: Callable[[str, str], Iterable[str]],
    is_read_only_action: Callable[[str], bool],
    is_save_action: Callable[[str], bool],
) -> set[str]:
    """Return generic mutation names, preferring semantic facade actions."""
    required = {
        action
        for action in instruction_actions(state.domain, state.instruction)
        if not is_read_only_action(action) and not is_save_action(action)
    }
    replacements = required.intersection(
        {
            "range.fill_down",
            "range.text_transform",
        }
    )
    if replacements:
        return replacements
    return {
        action
        for action in [*state.recommended_actions, *required]
        if not is_read_only_action(action) and not is_save_action(action)
    }


def completion_claim_contract_errors(completion: Any) -> list[str]:
    """Return stable diagnostics when propose_done arguments violate its schema."""
    errors = sorted(
        _COMPLETION_ARGUMENT_VALIDATOR.iter_errors(completion),
        key=lambda error: (
            tuple(str(item) for item in error.absolute_path),
            error.message,
        ),
    )
    return [
        f"completion arguments do not satisfy the propose_done schema: {error.message}"
        for error in errors
    ]


def completion_response_contract_errors(proposal: dict[str, Any]) -> list[str]:
    """Reject an explicitly incomplete model response even if it contains a tool name."""
    finish_reason = proposal.get("finish_reason")
    if finish_reason in {None, "tool_calls"}:
        return []
    return [
        "the model response was incomplete "
        f"(finish_reason={finish_reason!r}); issue a fresh action with a complete tool call"
    ]


def requires_readback_action(value: Any) -> bool:
    """Recognize a requested observation, not a mismatch in an existing one."""
    normalized = str(value).strip().casefold().replace("read-back", "read back")
    return bool(
        re.match(
            r"(?:(?:save|persist)\s+and\s+)?"
            r"(?:(?:perform\s+)?structural(?:ly)?\s+)?read\s?back\b",
            normalized,
        )
    )


def classify_completion_recovery(
    structural_missing: list[str],
    claim_errors: list[str],
    semantic_claim_errors: list[str] | None = None,
) -> str:
    """Select the least-permissive recovery that can make completion valid."""
    if semantic_claim_errors:
        return COMPLETION_RECOVERY_TASK_STATE
    if not structural_missing and claim_errors:
        return COMPLETION_RECOVERY_CLAIM_ONLY
    if structural_missing and all(
        requires_readback_action(item) for item in structural_missing
    ):
        return COMPLETION_RECOVERY_READBACK_ONLY
    return COMPLETION_RECOVERY_TASK_STATE


def completion_recovery_guidance(mode: str) -> str:
    """Return short model-facing guidance for a rejected completion claim."""
    if mode == COMPLETION_RECOVERY_CLAIM_ONLY:
        return (
            "The task state already satisfies the completion gate. Do not repeat a mutation, save, "
            "GUI action, or tool search. Retry propose_done with a short reason and evidence as one "
            "nonempty statement, or a native JSON array containing one to three short strings or "
            "compact structured records copied from successful tool results."
        )
    if mode == COMPLETION_RECOVERY_READBACK_ONLY:
        return (
            "The last mutation must not be repeated. Use one exposed read-only inspection to read back "
            "the final state, then retry propose_done."
        )
    return (
        "The completion gate reports unfinished task state. Address only the listed missing state, "
        "then read back the result before retrying propose_done."
    )


def requires_terminal_provenance(instruction: str) -> bool:
    """Return whether the instruction explicitly requires a terminal-originated action."""
    terminal = r"(?:command[ -]?line|terminal|shell)"
    return any(
        re.search(pattern.format(terminal=terminal), instruction, re.IGNORECASE)
        for pattern in (
            r"\b(?:run|execute|apply|complete|perform|do|convert|quit|kill|terminate|stop|close|remove|delete|rename|move|copy|create|install|uninstall)\b.{{0,80}}"
            r"\b(?:from|in|using|via|with)\s+(?:the\s+)?(?:current\s+)?{terminal}\b",
            r"\buse\s+(?:the\s+)?(?:current\s+)?{terminal}\s+to\b",
            r"\buse\s+(?:a\s+|the\s+)?(?:current\s+)?{terminal}\s+command\s+to\b",
            r"\bfrom\s+(?:the\s+)?(?:current\s+)?{terminal}\b.{{0,24}}"
            r"\b(?:commit|push|run|execute|apply|complete|perform|do|convert)\b",
            r"\b(?:using|via|through)\s+(?:the\s+)?(?:current\s+)?{terminal}\b",
            r"\bwith\s+(?:a\s+)?{terminal}\s+command\b",
        )
    )


def command_is_read_only(action: str, arguments: dict[str, Any]) -> bool:
    """Classify common inspection-only command lines used through command.run."""
    if action != "command.run" or arguments.get("stdout_path"):
        return False
    argv = arguments.get("argv")
    if not isinstance(argv, list) or not argv:
        return False
    command = str(argv[0]).rsplit("/", 1)[-1].casefold()
    operands = [str(item).casefold() for item in argv[1:]]
    if command == "gsettings":
        return bool(
            operands
            and (
                operands[0]
                in {
                    "get",
                    "range",
                    "list-recursively",
                    "list-schemas",
                    "list-relocatable-schemas",
                }
                or operands[0].startswith("list-")
            )
        )
    if command == "git":
        return bool(
            operands
            and operands[0]
            in {"status", "diff", "log", "show", "rev-parse", "remote", "ls-files"}
        )
    return command in {
        "cat",
        "find",
        "head",
        "ls",
        "pgrep",
        "printenv",
        "ps",
        "pwd",
        "stat",
        "tail",
        "test",
        "which",
    }


_ROUTE_ARGUMENT_KEYS = frozenset(
    {
        "adapter",
        "action",
        "downstream_adapter",
        "downstream_action",
        "payload",
        "params",
    }
)


def _route_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return downstream parameters from nested and flattened route shapes."""
    payload = arguments.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("params"), dict):
        return payload["params"]
    params = arguments.get("params")
    if isinstance(params, dict):
        return params
    nested_arguments = arguments.get("arguments")
    if isinstance(nested_arguments, dict):
        return nested_arguments
    # A searched/flattened route may put downstream fields beside the route
    # identity. Remove only the transport keys; preserve model-selected values.
    return {
        key: value
        for key, value in arguments.items()
        if key not in _ROUTE_ARGUMENT_KEYS
    }


def _route_identity(arguments: dict[str, Any]) -> tuple[str, str] | None:
    """Resolve route identity stored inside an adapter.call argument object."""
    adapter = arguments.get("adapter")
    action = arguments.get("action")
    if (
        not isinstance(adapter, str)
        or not adapter.strip()
        or not isinstance(action, str)
        or not action.strip()
    ):
        adapter = arguments.get("downstream_adapter")
        action = arguments.get("downstream_action")
    if (
        not isinstance(adapter, str)
        or not adapter.strip()
        or not isinstance(action, str)
        or not action.strip()
    ):
        return None
    return adapter, action


def _flattened_adapter_route(
    proposed: dict[str, Any],
) -> tuple[str, str, dict[str, Any]] | None:
    """Read all persisted model-selected ``adapter.call`` route shapes.

    Runtime proposals can retain a nested ``arguments.adapter/action/payload``
    object or a searched route can place ``downstream_adapter`` and
    ``downstream_action`` beside direct downstream parameters.  Completion
    policy uses this representation only for semantic comparison; the raw
    proposal remains unchanged for execution and audit.
    """
    if proposed.get("action") != "adapter.call":
        return None
    arguments = proposed.get("arguments")
    if not isinstance(arguments, dict):
        return None
    route = _route_identity(arguments)
    if route is None:
        adapter = proposed.get("downstream_adapter")
        action = proposed.get("downstream_action")
        if (
            not isinstance(adapter, str)
            or not adapter.strip()
            or not isinstance(action, str)
            or not action.strip()
        ):
            return None
        route = (adapter, action)
    return route[0], route[1], _route_arguments(arguments)


def effective_adapter_action(
    event: Any,
    default_domain: str,
) -> tuple[str, str, dict[str, Any]]:
    """Resolve a direct action or the downstream action wrapped by adapter.call."""
    proposed = getattr(event, "proposed", None)
    if not isinstance(proposed, dict):
        return default_domain, "", {}
    action = str(proposed.get("action", ""))
    arguments = proposed.get("arguments", {})
    if not isinstance(arguments, dict):
        arguments = {}
    if action != "adapter.call":
        return default_domain, action, arguments
    flattened = _flattened_adapter_route(proposed)
    if flattened is not None:
        return flattened
    return "", "", {}


def canonical_action_identity(domain: str, action: str) -> tuple[str, str]:
    """Return the stable downstream identity for a public action facade."""
    return _CANONICAL_ACTION_ALIASES.get((domain, action), (domain, action))


def canonical_action_request(
    default_domain: str,
    action: str,
    arguments: Any,
) -> tuple[str, str, dict[str, Any]]:
    """Resolve a proposal to one domain/action/argument identity.

    This is for internal comparison only.  The original model proposal and
    arguments remain untouched in the event ledger and are still what the
    executor sends to the Adapter.
    """
    raw_arguments = arguments if isinstance(arguments, dict) else {}
    if action == "adapter.call":
        route = _route_identity(raw_arguments)
        if route is not None:
            domain, canonical = canonical_action_identity(*route)
            return domain, canonical, _route_arguments(raw_arguments)
    domain, canonical = canonical_action_identity(default_domain, action)
    return domain, canonical, raw_arguments


def effective_canonical_action(
    event: Any, default_domain: str
) -> tuple[str, str, dict[str, Any]]:
    """Resolve an adapter event to its canonical downstream identity."""
    proposed = getattr(event, "proposed", None)
    if not isinstance(proposed, dict):
        return default_domain, "", {}
    flattened = _flattened_adapter_route(proposed)
    if flattened is not None:
        domain, action, arguments = flattened
        domain, action = canonical_action_identity(domain, action)
        return domain, action, arguments
    return canonical_action_request(
        default_domain,
        str(proposed.get("action", "")),
        proposed.get("arguments", {}),
    )


def _is_model_selected_downstream_mutation(
    event: Any,
    state_domain: str,
    downstream_domain: str,
    downstream_action: str,
) -> bool:
    """Recognize an opaque Multi-Apps route as mutation evidence.

    Multi-Apps intentionally has no instruction-specific action list: the model
    discovers an owning Adapter route and selects the complete downstream call.
    Requiring lexical relevance here therefore drops valid mutations such as a
    generic ``range.write`` selected after a catalog search.  The route itself
    is already validated at execution time; this helper only classifies its
    successful event for persistence/read-back accounting and never supplies a
    route or argument.
    """
    proposed = getattr(event, "proposed", None)
    return bool(
        state_domain == "multi_apps"
        and isinstance(proposed, dict)
        and proposed.get("action") == "adapter.call"
        and isinstance(downstream_domain, str)
        and downstream_domain
        and downstream_domain != "multi_apps"
        and isinstance(downstream_action, str)
        and "." in downstream_action
        and not action_is_read_only(downstream_action)
        and not action_is_save(downstream_action)
    )


def inspection_identity_url(event: Any) -> str | None:
    """Return the local document identity exposed by a successful inspect."""
    pending: list[tuple[Any, int]] = [(getattr(event, "result", None), 0)]
    seen: set[int] = set()
    nested_keys = (
        "context_hint",
        "downstream_context",
        "adapter_response",
        "response",
        "result",
    )
    while pending:
        candidate, depth = pending.pop(0)
        if depth > 8 or not isinstance(candidate, dict) or id(candidate) in seen:
            continue
        seen.add(id(candidate))
        identity = candidate.get("identity")
        if isinstance(identity, dict):
            for key in ("url", "path"):
                location = identity.get(key)
                if isinstance(location, str) and location.strip():
                    return location
        # Calc workbook.inspect exposes its identity directly.  The caller
        # already proved this is an inspect event, so a direct URL here is not
        # confused with an arbitrary result artifact.
        for key in ("url", "path"):
            location = candidate.get(key)
            if isinstance(location, str) and location.strip():
                return location
        for key in nested_keys:
            child = candidate.get(key)
            if isinstance(child, dict):
                pending.append((child, depth + 1))
    return None


def _result_has_explicit_failure(value: Any, *, depth: int = 0) -> bool:
    """Reject a result that carries an explicit failure at any envelope level."""
    if depth > 8 or not isinstance(value, dict):
        return False
    if value.get("status") in {"error", "failed"}:
        return True
    if value.get("error") not in (None, False, "", {}):
        return True
    verification = value.get("verification")
    if isinstance(verification, dict) and verification.get("passed") is False:
        return True
    return any(
        _result_has_explicit_failure(value.get(key), depth=depth + 1)
        for key in (
            "context_hint",
            "downstream_context",
            "adapter_response",
            "response",
            "result",
        )
    )


def _local_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.startswith("file://"):
        parsed = urlparse(raw)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            return None
        raw = unquote(parsed.path)
    else:
        raw = unquote(raw)
    if raw.startswith("~/"):
        return str(PurePosixPath(raw))
    if raw.startswith("/"):
        return str(PurePosixPath(raw))
    return None


def local_document_paths_match(left: Any, right: Any) -> bool:
    """Compare absolute/file-URL paths and an active-user ``~/`` alias."""
    first = _local_path(left)
    second = _local_path(right)
    if first is None or second is None:
        return isinstance(left, str) and isinstance(right, str) and left == right
    if first == second:
        return True

    def tilde_tail(path: str) -> tuple[str, ...] | None:
        parts = PurePosixPath(path).parts
        return parts[1:] if parts and parts[0] == "~" else None

    def home_tail(path: str) -> tuple[str, ...] | None:
        parts = PurePosixPath(path).parts
        # The guest's ``~`` alias is /home/user (or /root), not every
        # arbitrary /home/<name>. Keep the username in the comparison.
        if len(parts) >= 4 and parts[:3] == ("/", "home", "user"):
            return parts[3:]
        if len(parts) >= 3 and parts[:2] == ("/", "root"):
            return parts[2:]
        return None

    first_tilde = tilde_tail(first)
    second_tilde = tilde_tail(second)
    if first_tilde is not None:
        return first_tilde == home_tail(second)
    if second_tilde is not None:
        return second_tilde == home_tail(first)
    return False


def _is_destination_changing_save(
    event: Any,
    events: Iterable[Any],
    default_domain: str,
) -> bool:
    """Recognize a model-selected Save As from immutable Adapter evidence."""
    domain, action, arguments = effective_canonical_action(event, default_domain)
    if not action.endswith(".save"):
        return False
    selected_location = arguments.get("url", arguments.get("output_path"))
    if not isinstance(selected_location, str) or not selected_location.strip():
        return False

    if _result_has_explicit_failure(getattr(event, "result", None)):
        return False
    result_mappings = list(iter_result_mappings(getattr(event, "result", None)))
    if not any(result.get("status") == "ok" for result in result_mappings):
        return False

    saved_location = None
    for result in result_mappings:
        size = result.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            continue
        for key in ("url", "path"):
            candidate = result.get(key)
            if local_document_paths_match(selected_location, candidate):
                saved_location = candidate
                break
        if saved_location is not None:
            break
    if saved_location is None:
        return False

    # Include failed/invalid attempts when selecting the latest probe.  A
    # later failed inspect must invalidate an older successful identity rather
    # than allowing stale evidence to classify a save as in-place.
    prior_inspections = [
        previous
        for previous in events
        if getattr(previous, "step", 0) < getattr(event, "step", 0)
        and getattr(previous, "proposed", {}).get("kind") == "adapter"
        and effective_canonical_action(previous, default_domain)[0] == domain
        and effective_canonical_action(previous, default_domain)[1].endswith(".inspect")
    ]
    if not prior_inspections:
        return False
    latest_inspection = max(
        prior_inspections, key=lambda item: getattr(item, "step", 0)
    )
    previous_url = inspection_identity_url(latest_inspection)
    # A later inspect with missing/failed identity invalidates older evidence;
    # conservatively treat this save as destination-changing so a fresh,
    # identity-bound post-save inspect is required.
    if (
        previous_url is None
        or not latest_inspection.executed
        or getattr(latest_inspection, "error", None) is not None
        or (
            domain == "libreoffice_calc"
            and not has_passed_verification(getattr(latest_inspection, "result", None))
        )
        or _result_has_explicit_failure(getattr(latest_inspection, "result", None))
    ):
        # Without a verified source identity the save cannot be promoted to a
        # task-changing evidence record.  The generic gate will remain
        # incomplete instead of treating an unbound destination as progress.
        return False
    return not local_document_paths_match(previous_url, saved_location)


def _verified_workbook_inspection_after(
    state: Any,
    step: int,
    expected_location: str | None = None,
    *,
    expected_domain: str | None = None,
) -> bool:
    """Require an identity-bound document inspection after a destination save."""
    state_domain = str(getattr(state, "domain", ""))
    document_domain = expected_domain or state_domain
    candidates = [
        event
        for event in state.events
        if getattr(event, "step", 0) > step
        and getattr(event, "proposed", {}).get("kind") == "adapter"
        and effective_canonical_action(event, state_domain)[0] == document_domain
        and effective_canonical_action(event, state_domain)[1].endswith(".inspect")
    ]
    if not candidates:
        return False
    latest = max(candidates, key=lambda item: getattr(item, "step", 0))
    identity = inspection_identity_url(latest)
    if (
        not getattr(latest, "executed", False)
        or getattr(latest, "error", None) is not None
        or identity is None
        or (
            document_domain == "libreoffice_calc"
            and not has_passed_verification(getattr(latest, "result", None))
        )
        or _result_has_explicit_failure(getattr(latest, "result", None))
    ):
        return False
    return expected_location is None or local_document_paths_match(
        identity, expected_location
    )


def cross_app_presentation_completion_status(
    state: Any, mutations: list[Any], successful: list[Any],
) -> tuple[bool, bool] | None:
    """Return persistence/read-back evidence for the last live Impress edit."""
    if state.domain != "multi_apps":
        return None
    edits = [
        event for event in mutations
        if effective_canonical_action(event, state.domain)[0] == "libreoffice_impress"
        and not effective_canonical_action(event, state.domain)[1].startswith("settings.")
        and effective_canonical_action(event, state.domain)[1] not in {
            "presentation.export", "shape.export_image",
        }
    ]
    if not edits:
        return None
    last_edit = edits[-1]
    later_actions = {
        effective_canonical_action(event, state.domain)[:2]
        for event in successful
        if event.step > last_edit.step and not _result_has_explicit_failure(event.result)
    }
    persisted = state.event_has_save_evidence(last_edit) or (
        "libreoffice_impress", "presentation.save"
    ) in later_actions
    inspected = ("libreoffice_impress", "presentation.inspect") in later_actions
    return persisted, inspected


def collect_initial_completion_evidence(
    state: Any,
    completion: dict[str, Any] | None,
    *,
    is_read_only_action: Callable[[str], bool],
    is_save_action: Callable[[str], bool],
    relevance_score: Callable[[str, str, str], int],
    required_mutations: Iterable[str] | None = None,
) -> tuple[list[Any], list[Any], list[str], set[str]]:
    """Collect generic mutation, save, and read-back evidence for completion.

    ``required_mutations`` is an optional strict-mode contract containing only
    public action names.  The legacy default deliberately keeps the historical
    ``RuntimeState.required_mutation_actions`` behavior for compatibility, while
    strict callers can avoid task-shaped state predicates entirely.
    """
    successful = state.successful_adapter_events()
    required_mutation_set = (
        set(required_mutations)
        if required_mutations is not None
        else set(state.required_mutation_actions())
    )
    required_mutation_ids = {
        canonical_action_request(state.domain, action, {})[:2]
        for action in required_mutation_set
    }
    mutations = []
    for event in successful:
        raw_domain, raw_action, raw_arguments = effective_adapter_action(
            event, state.domain
        )
        domain, action, arguments = effective_canonical_action(event, state.domain)
        destination_changing_save = _is_destination_changing_save(
            event, state.events, state.domain
        )
        if (
            is_read_only_action(action)
            # Export creates an output artifact as well as persisting it.
            or (
                is_save_action(action)
                and not action.endswith(".export")
                and not destination_changing_save
            )
            or command_is_read_only(raw_action, raw_arguments)
        ):
            continue
        alias_relevant = any(
            relevance_score(state.domain, facade, state.instruction) >= 2
            for facade in _CANONICAL_PUBLIC_ACTIONS.get((domain, action), ())
        )
        if (
            (domain, action) in required_mutation_ids
            or raw_action in required_mutation_set
            or action in required_mutation_set
            or relevance_score(raw_domain, raw_action, state.instruction) >= 2
            or relevance_score(domain, action, state.instruction) >= 2
            or alias_relevant
            or _is_model_selected_downstream_mutation(
                event, state.domain, raw_domain, raw_action
            )
        ):
            mutations.append(event)

    missing = (
        completion_claim_contract_errors(completion) if completion is not None else []
    )
    missing.extend(completion_claim_contradictions(completion))
    if not mutations:
        missing.extend(
            [
                "no successful task-changing Adapter action is recorded",
                "no successful instruction-relevant task-changing Adapter action is recorded",
            ]
        )
        return successful, mutations, missing, required_mutation_set

    last_mutation_step = mutations[-1].step
    if requires_terminal_provenance(state.instruction):
        command_events = [
            event
            for event in successful
            if effective_adapter_action(event, state.domain)[1]
            in {
                "command.run",
                "document.convert",
                "terminal.show_output",
            }
        ]
        if not any(
            (
                effective_adapter_action(event, state.domain)[2].get("provenance")
                == "shell_history"
                or effective_adapter_action(event, state.domain)[2].get(
                    "record_shell_history"
                )
                is True
            )
            for event in command_events
        ):
            missing.append(
                "record the successful command in shell history because the instruction "
                "explicitly requires command-line or terminal provenance"
            )
    last_rejected_completion_step = max(
        (
            event.step
            for event in state.events
            if event.proposed.get("kind") == "completion"
            and not event.executed
            and isinstance(event.error, dict)
            and event.error.get("status") == "rejected"
        ),
        default=0,
    )
    gui_after_rejection = any(
        event.step > last_rejected_completion_step
        and event.executed
        and event.proposed.get("kind") == "gui"
        for event in state.events
    )
    if last_rejected_completion_step >= last_mutation_step and gui_after_rejection:
        missing.append(
            "perform a new instruction-relevant Adapter mutation after the rejected "
            "completion claim"
        )
    # Completion policy must reason about the downstream operation, not the
    # facade spelling selected by the model.  A searched ``adapter.call`` for
    # ``libreoffice_calc/range.write`` is the same document mutation as the
    # direct ``spreadsheet.write_range`` facade and must require the same save.
    last_domain, last_action, _last_arguments = effective_canonical_action(
        mutations[-1], state.domain
    )
    spreadsheet_mutation = last_domain == "libreoffice_calc" and last_action in {
        "range.write",
        "table.sort",
        "workbook.create_new",
    }
    office_settings_only = state.domain.startswith("libreoffice_") and all(
        effective_canonical_action(event, state.domain)[1].startswith("settings.")
        for event in mutations
    )
    requires_document_save = (
        state.domain.startswith("libreoffice_") and not office_settings_only
    ) or (
        state.domain == "multi_apps" and spreadsheet_mutation
    )
    if requires_document_save and not is_save_action(last_action):
        explicit_save = any(
            is_save_action(effective_canonical_action(event, state.domain)[1])
            and event.step > last_mutation_step
            for event in successful
        )
        if not explicit_save and not state.event_has_save_evidence(mutations[-1]):
            missing.append(
                "save the LibreOffice document after the final mutation"
                if last_domain.startswith("libreoffice_")
                else "call workbook.save after the final spreadsheet mutation"
            )
    destination_save = _is_destination_changing_save(
        mutations[-1], state.events, state.domain
    )
    if destination_save:
        saved_location = None
        _save_domain, _save_action, save_arguments = effective_canonical_action(
            mutations[-1], state.domain
        )
        selected_location = save_arguments.get("url", save_arguments.get("output_path"))
        if isinstance(selected_location, str) and selected_location.strip():
            saved_location = selected_location
        has_post_mutation_read = _verified_workbook_inspection_after(
            state,
            last_mutation_step,
            saved_location,
            expected_domain=_save_domain,
        )
    else:
        has_post_mutation_read = any(
            is_read_only_action(effective_canonical_action(event, state.domain)[1])
            and event.step > last_mutation_step
            and event.executed
            for event in successful
        )
    settings_readback = office_settings_only and any(
        isinstance(verification := body.get("verification"), dict)
        and verification.get("scope") == "application_settings"
        and verification.get("passed") is True
        for body in iter_result_mappings(mutations[-1].result)
    )
    verifier_readback = (
        (not state.domain.startswith("libreoffice_") or settings_readback)
        and not _is_destination_changing_save(mutations[-1], state.events, state.domain)
        and state.event_has_verifier_evidence(mutations[-1])
    )
    if not has_post_mutation_read and not verifier_readback:
        missing.append("perform structural read-back after the final mutation")
    # Impress verifies live UNO mutations without implicitly saving them.
    # A later file/archive operation must not hide an unsaved presentation.
    presentation_status = cross_app_presentation_completion_status(state, mutations, successful)
    if presentation_status is not None:
        persisted, inspected = presentation_status
        if not persisted:
            missing.append("save the LibreOffice presentation after its final mutation")
        readback_message = "perform structural read-back after the final mutation"
        if not inspected and readback_message not in missing:
            missing.append(readback_message)
    return successful, mutations, missing, required_mutation_set


def completion_claim_contradictions(
    completion: dict[str, Any] | None,
) -> list[str]:
    """Return generic contradictions contained in a proposed success claim."""
    if not isinstance(completion, dict):
        return []
    reason = str(completion.get("reason", ""))
    evidence = completion.get("evidence")
    if isinstance(evidence, str):
        evidence_text = evidence
    elif isinstance(evidence, list):
        evidence_text = " ".join(str(item) for item in evidence)
    else:
        evidence_text = ""
    claim = " ".join((reason, evidence_text))
    patterns = {
        "the completion claim says the task is not complete": (
            r"(?i)\b(?:not|never)\s+(?:yet\s+)?(?:been\s+)?"
            r"(?:complete|completed|done|executed|finished|performed)\b",
            r"(?i)\btask\s+(?:has\s+)?not\s+been\s+completed\b",
            r"(?i)\btask\s+(?:is|was)\s+not\s+(?:yet\s+)?complete\b",
            r"(?i)\btask\s+(?:is|was)\s+not\s+(?:yet\s+)?fully\s+complete\b",
            r"(?i)\btask\s+(?:is|was)\s+incomplete\b",
            r"(?i)\btask\s+(?:is|was)\s+not\s+(?:yet\s+)?fully\s+completed\b",
            r"(?i)\b(?:request|requested\s+(?:change|operation))\s+(?:is|was|has)\s+not\s+"
            r"(?:yet\s+)?(?:complete|completed|done|performed)\b",
            r"(?i)\b(?:I|we)\s+(?:still\s+)?need\s+to\b",
        ),
        "the completion claim says the task cannot be completed": (
            r"(?i)\btask\s+(?:cannot|can't|could\s+not|couldn't)\s+be\s+completed\b",
            r"(?i)\b(?:unable|failed)\s+to\s+complete\s+(?:the\s+)?task\b",
            r"(?i)\b(?:I|we)\s+(?:cannot|can't|could\s+not|couldn't|am\s+unable\s+to|are\s+unable\s+to)\s+"
            r"(?:complete|finish|perform|do)\b",
            r"(?i)\bcannot\s+complete\s+(?:this|the)\s+task\b",
        ),
        "the completion claim describes work that still needs to happen": (
            r"(?i)\bthe\s+next(?:\s+(?:logical|required|necessary))?\s+step\s+"
            r"(?:is|would\s+be|will\s+be)\s+to\b",
            r"(?i)\b(?:I|we|the\s+user)\s+(?:still\s+)?(?:need|needs|will\s+need|would\s+need)\s+to\b",
            r"(?i)\b(?:should|must|need(?:s)?\s+to)\s+(?:now\s+)?(?:execute|run|click|open|set|change|save|verify)\b",
            r"(?i)\b(?:ready|prepared)\s+(?:for|to)\s+(?:command\s+input|execute|run|perform)\b",
        ),
        "the completion claim says no required action was taken": (
            r"(?i)\bno\s+action\s+has\s+been\s+taken\b",
            r"(?i)\b(?:requested|required)\s+(?:change|action|operation)\s+(?:was|has)\s+not\s+"
            r"(?:been\s+)?(?:made|performed|executed)\b",
            r"(?i)\b(?:previous|last|attempted)?\s*(?:change|action|update)\s+"
            r"(?:did\s+not|didn't)\s+(?:address|modify|change|complete)\b",
            r"(?i)\b(?:I|we)\s+(?:still\s+)?need\s+to\b",
        ),
        "the completion claim says the wrong target is active": (
            r"(?i)\bwrong\s+(?:slide|page|sheet|document|window)\b",
        ),
    }
    return [
        message
        for message, expressions in patterns.items()
        if any(re.search(expression, claim) for expression in expressions)
    ]
