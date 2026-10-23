"""Bounded, model-choice-preserving surfaces for structured-error recovery.

Recovery is a routing concern, not an application workflow.  The helpers in
this module only carry public action names and coarse failure metadata.  They
never infer a target, replace model arguments, or expose evaluator state.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from integrations.openapa_osworld.tool_catalog import public_actions
from multi_apps_adapter.route_utils import contains_route, is_route, normalize_route

from .generic_routing import recovery_blocked_actions
from .context_projection import is_hidden_key, sanitize
from .tool_catalog import (
    FORBIDDEN_DATASET_ACTIONS,
    INSPECT_ACTIONS,
    action_from_tool_name,
)


_CONTROL_TOOL_NAMES = frozenset(
    {"tools_search", "propose_done", "fail_task", "gui_action", "gui_request"}
)
_SAFE_LABEL = re.compile(r"[^A-Za-z0-9_.-]+")
_SAFE_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,119}$")
_UUID = re.compile(
    r"(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])"
)
_UUID_PREFIX = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{8}(?![0-9a-f])")
_SENSITIVE_TEXT_MARKERS = (
    "answer",
    "expected",
    "evaluator",
    "golden",
    "reference",
    "dataset",
    "task_manifest",
    "task.execute",
    "task.inspect",
    "artifact.materialize",
    "assessment.grade_multiple_choice_documents",
    "assessment_grade_multiple_choice_documents",
)
_SENSITIVE_TEXT_MARKERS_NORMALIZED = frozenset(
    normalize_route(item) for item in _SENSITIVE_TEXT_MARKERS
)
_GENERIC_ERROR_CODES = frozenset(
    {
        "error",
        "internal_error",
        "adapter_error",
        "http_error",
        "request_error",
        "operation_failed",
        "validation_error",
        "downstream_failed",
    }
)
_GENERIC_ERROR_MESSAGES = frozenset(
    {
        "command failed",
        "operation failed",
        "request failed",
        "adapter call failed",
        "downstream adapter call failed",
    }
)
_ERROR_HINT_MAX_CHARS = 320
_PATH_LIKE = re.compile(r"(?:(?:file://|https?://|~/|/)[^\s,;)]{2,})")


def _normalized_action(value: Any) -> str:
    return normalize_route(value)


def _is_forbidden_action(value: Any) -> bool:
    return is_route(value, FORBIDDEN_DATASET_ACTIONS)


def _nested_error(error: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("error", "previous_error"):
        nested = error.get(key)
        if isinstance(nested, dict):
            return nested
    details = error.get("details")
    response = details.get("response") if isinstance(details, dict) else None
    nested = response.get("error") if isinstance(response, dict) else None
    return nested if isinstance(nested, dict) else None


def _error_type(error: Any) -> str:
    """Extract only a bounded public error code from nested Adapter errors."""
    current = error
    fallback: str | None = None
    for _ in range(4):
        if not isinstance(current, dict):
            break
        code = current.get("code") or current.get("error_code")
        if isinstance(code, str) and code.strip():
            normalized_code = _safe_label(code)
            if (
                normalized_code != "unknown"
                and normalized_code.casefold() not in _GENERIC_ERROR_CODES
            ):
                return normalized_code
            if normalized_code != "unknown" and fallback is None:
                fallback = normalized_code
        for key in ("type", "status"):
            value = current.get(key)
            if isinstance(value, str) and value.strip():
                candidate = _safe_label(value)
                # A generic transport status is less useful than a nested
                # Adapter code, so retain it only as a fallback.
                if candidate != "unknown" and fallback is None:
                    fallback = candidate
        nested = _nested_error(current)
        if not isinstance(nested, dict):
            break
        current = nested
    return fallback or "unknown"


def _safe_error_hint(error: Any) -> str | None:
    """Keep an actionable Adapter rule while removing values and sensitive text."""
    current = error
    for _ in range(4):
        if not isinstance(current, dict):
            break
        # Adapter command failures commonly put the useful diagnosis in
        # ``details.stderr`` while the outer message remains only
        # ``command failed``.  Project that bounded diagnostic as well so a
        # recovery turn can correct a stale handle/argument instead of
        # guessing from the generic wrapper message.
        sources: list[dict[str, Any]] = [current]
        details = current.get("details")
        if isinstance(details, dict):
            sources.append(details)
        for source in sources:
            for key in (
                "recovery",
                "guidance",
                "message",
                "detail",
                "stderr",
                "stdout",
            ):
                value = source.get(key)
                if not isinstance(value, str) or not value.strip():
                    continue
                # Keep the first meaningful diagnostic lines.  Joining lines
                # avoids spending the hint budget on indentation/newlines,
                # while the final bound still protects the model context.
                text = " ".join(line.strip() for line in value.splitlines() if line.strip())
                text = _UUID.sub("<id>", text)
                text = _UUID_PREFIX.sub("<id>", text)
                text = _PATH_LIKE.sub("<path>", text)
                # Prefer a concrete stderr/recovery rule over an outer wrapper
                # such as ``command failed`` when both are present.
                if (
                    key in {"message", "detail"}
                    and text.casefold().rstrip(".") in _GENERIC_ERROR_MESSAGES
                ):
                    continue
                if sanitize(text, sensitive_context=True) != text:
                    continue
                text = text[:_ERROR_HINT_MAX_CHARS].strip()
                if text:
                    return text
        nested = _nested_error(current)
        if not isinstance(nested, dict):
            break
        current = nested
    return None


def bounded_recovery_actions(
    state: Any,
    *,
    selected_actions: Iterable[str] = (),
    required_actions: Iterable[str] = (),
    searched_actions: Iterable[str] = (),
    limit: int = 7,
) -> list[str]:
    """Return a small public action set without selecting the next action.

    Required and recently searched actions are retained so a recovery turn does
    not collapse to the last failed route. ``selected_actions`` is the normal
    semantic Top-K for the current state; ``searched_actions`` is capped by the
    same final limit and therefore cannot make the tool surface unbounded.
    """
    if limit <= 0:
        return []
    domain = str(getattr(state, "domain", ""))
    try:
        public = set(public_actions(domain))
    except (ImportError, ValueError):
        public = set()
    blocked = recovery_blocked_actions(state)
    active_blocks = getattr(state, "active_request_blocks", None)
    active_action_names = {
        str(item.get("action"))
        for item in (active_blocks().values() if callable(active_blocks) else ())
        if isinstance(item, dict) and item.get("action")
    }
    failed_action_names: set[str] = set(active_action_names)
    for event in reversed(list(getattr(state, "events", ()) or ())):
        proposed = getattr(event, "proposed", None)
        if not isinstance(proposed, dict):
            continue
        if getattr(event, "executed", False):
            # A catalog lookup is observational and should not hide a failure
            # immediately before it.  A successful application mutation does
            # establish a new state, so failures before it are stale.
            if proposed.get("kind") in {"adapter", "gui"}:
                break
            continue
        if proposed.get("kind") not in {"adapter", "gui"}:
            continue
        action = proposed.get("action") or proposed.get("tool")
        if isinstance(action, str) and action:
            failed_action_names.add(action)
    ordered = [*required_actions, *searched_actions, *selected_actions]
    # Keep a failed action available for a model-authored parameter change, but
    # put it after alternatives so recovery does not deterministically replay
    # the same bad request.  Fully blocked actions are removed below.
    ordered = [
        *[
            candidate
            for candidate in ordered
            if str(candidate) not in failed_action_names
        ],
        *[candidate for candidate in ordered if str(candidate) in failed_action_names],
    ]
    result: list[str] = []
    for candidate in ordered:
        action = str(candidate)
        if (
            not action
            or action not in public
            or _is_forbidden_action(action)
            or action in _CONTROL_TOOL_NAMES
            or action in blocked
            or any(
                _normalized_action(item) == _normalized_action(action)
                for item in blocked
            )
            or action in result
        ):
            continue
        result.append(action)
        if len(result) >= limit:
            break
    if not result:
        # A fully blocked mutation should still leave the model one generic
        # observation route.  This is a bounded, domain-level fallback: it
        # does not choose a target or synthesize arguments.
        for candidate in INSPECT_ACTIONS.get(domain, ()):
            if (
                candidate in public
                and candidate not in blocked
                and not _is_forbidden_action(candidate)
            ):
                result.append(candidate)
                break
    return result


def _safe_label(
    value: Any,
    default: str = "unknown",
    *,
    sensitive_replacement: str | None = None,
) -> str:
    text = str(value or default)
    normalized = _normalized_action(text)
    if (_UUID.search(text) or _UUID_PREFIX.search(text)) or any(
        marker in normalized for marker in _SENSITIVE_TEXT_MARKERS_NORMALIZED
    ):
        return sensitive_replacement or default
    text = _SAFE_LABEL.sub("_", text).strip("_")
    if not _SAFE_TOKEN.fullmatch(text):
        return default
    return text[:80] or default


def last_failure_summary(state: Any) -> dict[str, Any] | None:
    """Extract coarse, non-sensitive failure metadata from the event ledger.

    Values, paths, URLs, task identifiers, and nested error bodies are omitted.
    The summary is useful to lexical retrieval and recovery guidance while
    remaining independent of a particular task or expected answer.
    """
    for event in reversed(list(getattr(state, "events", ()) or ())):
        if getattr(event, "executed", False):
            proposed = getattr(event, "proposed", {})
            # A later successful application action establishes a new state;
            # failures before it are no longer the active recovery context.
            if isinstance(proposed, dict) and proposed.get("kind") in {
                "adapter",
                "gui",
            }:
                break
            continue
        error = getattr(event, "error", None)
        if not isinstance(error, dict):
            continue
        proposed = getattr(event, "proposed", None)
        proposed = proposed if isinstance(proposed, dict) else {}
        action = proposed.get("action") or proposed.get("tool")
        arguments = proposed.get("arguments")
        fields = (
            sorted(
                str(key)
                for key in arguments
                if isinstance(key, str) and not is_hidden_key(key)
            )
            if isinstance(arguments, dict)
            else []
        )
        underlying = error
        if error.get("type") == "RepeatedActionBlocked":
            previous = error.get("previous_error")
            if isinstance(previous, dict):
                underlying = previous
        action_label = _safe_label(action, sensitive_replacement="public_action")
        if _is_forbidden_action(action) or contains_route(
            action, FORBIDDEN_DATASET_ACTIONS
        ):
            action_label = "public_action"
        return {
            "action": action_label,
            "error_type": _error_type(underlying),
            "argument_fields": fields[:16],
            **({"error_hint": hint} if (hint := _safe_error_hint(underlying)) else {}),
        }
    return None


def latest_unexecuted_public_failures(state: Any) -> tuple[str, ...]:
    """Return public actions from the immediately preceding failed call.

    This deliberately considers only the latest event and only a
    model-selected Adapter call.  Older failures are already handled by the
    bounded repeated-error/search surfaces; carrying them into the normal
    surface would reorder unrelated later work.  ``RepeatedActionBlocked`` is
    excluded because the explicit replan surface owns that state.
    """
    events = list(getattr(state, "events", ()) or ())
    if not events:
        return ()
    event = events[-1]
    if getattr(event, "executed", False):
        return ()
    error = getattr(event, "error", None)
    if not isinstance(error, dict) or not error:
        return ()
    if error.get("type") == "RepeatedActionBlocked":
        return ()
    proposed = getattr(event, "proposed", None)
    if not isinstance(proposed, dict) or proposed.get("kind") not in {
        "adapter",
        "gui",
    }:
        return ()
    domain = str(getattr(state, "domain", ""))
    try:
        public = set(public_actions(domain))
    except (ImportError, KeyError, ValueError):
        public = set()
    candidates: list[str] = []
    for value in (proposed.get("action"), proposed.get("tool")):
        if not isinstance(value, str) or not value:
            continue
        if value in public:
            candidates.append(value)
        mapped = action_from_tool_name(domain, value)
        if mapped is not None:
            candidates.append(mapped)
    return tuple(dict.fromkeys(candidates))


def soft_recovery_tools(
    tools: list[dict[str, Any]], state: Any
) -> list[dict[str, Any]]:
    """Tail-place the immediately failed public action without shrinking the surface.

    The model keeps every currently visible action, including GUI and control
    tools.  Only the relative order of Adapter slots changes: alternatives are
    presented first and the failed action remains available for a
    model-authored, materially different retry.  No arguments or route
    schemas are inferred here.
    """
    failed_actions = set(latest_unexecuted_public_failures(state))
    if not failed_actions:
        return tools
    domain = str(getattr(state, "domain", ""))
    adapter_positions: list[int] = []
    failed_tools: list[dict[str, Any]] = []
    other_adapter_tools: list[dict[str, Any]] = []
    for index, tool in enumerate(tools):
        function = tool.get("function")
        name = function.get("name") if isinstance(function, dict) else None
        action = action_from_tool_name(domain, str(name)) if name else None
        if action is None:
            continue
        adapter_positions.append(index)
        if action in failed_actions:
            failed_tools.append(tool)
        else:
            other_adapter_tools.append(tool)
    if not failed_tools:
        return tools

    reordered = [*other_adapter_tools, *failed_tools]
    result = list(tools)
    for index, tool in zip(adapter_positions, reordered):
        result[index] = tool

    # Give the model a stable, value-free recovery cue on the normal surface.
    # Keep this separate from ``decorate_recovery_tools`` so repeated-error
    # descriptions do not accumulate when a caller composes both helpers.
    for tool in result:
        function = tool.get("function")
        if not isinstance(function, dict) or function.get("name") != "tools_search":
            continue
        description = str(function.get("description", ""))
        cue = (
            " A prior model-selected public action returned a structured error. "
            "This is soft recovery: the normal public tools remain available; "
            "re-observe or choose an alternative before retrying, and never "
            "repeat identical arguments."
        )
        if cue not in description:
            function["description"] = description + cue
        break
    return result


def decorate_recovery_tools(
    tools: list[dict[str, Any]], state: Any, *, mode: str
) -> list[dict[str, Any]]:
    """Add generic recovery guidance without changing schemas or arguments."""
    summary = last_failure_summary(state)
    blocked = recovery_blocked_actions(state)
    failed_action = summary.get("action") if summary else None
    for tool in tools:
        function = tool.get("function")
        if not isinstance(function, dict):
            continue
        name = str(function.get("name", ""))
        action = action_from_tool_name(str(getattr(state, "domain", "")), name)
        if name == "tools_search":
            function["description"] = str(function.get("description", "")) + (
                " Recovery is advisory: search for a public action, then choose the next "
                "tool yourself. Re-observe an exact target or handle after a structured "
                "error; do not repeat the identical request."
            )
        elif action and failed_action and action == failed_action:
            # Keep the failed route available for a model-authored correction,
            # but put the usage contract directly beside it on the recovery
            # turn.  This is advisory text only: it never fills an argument or
            # changes the schema exposed to the model.
            cue = (
                " Recovery for this action: read the parameter descriptions above, "
                "supply every required field in the documented placement, and use a "
                "freshly observed identifier/handle when the prior error names one; "
                "do not replay the rejected arguments."
            )
            hint = summary.get("error_hint") if summary else None
            if isinstance(hint, str) and hint:
                cue += f" Last safe diagnostic: {hint[:_ERROR_HINT_MAX_CHARS]}."
            function["description"] = str(function.get("description", "")) + cue
        elif name == "propose_done":
            function["description"] = str(function.get("description", "")) + (
                " Recovery does not imply completion; use this only after every requested "
                "clause has structural read-back evidence."
            )
        elif name == "fail_task":
            function["description"] = str(function.get("description", "")) + (
                " Recovery does not imply infeasibility; use this only after a concrete "
                "alternative or re-observation is genuinely unavailable."
            )
        elif action == failed_action or action in blocked:
            function["description"] = str(function.get("description", "")) + (
                " An earlier argument variant for this public action failed. Supply a "
                "materially different model-authored argument set; the Runner will reject "
                "an exact duplicate."
            )
    if summary:
        mode_label = _safe_label(mode)
        # Keep this short: the full error remains in the immutable trace, while
        # the model only needs the category and argument-field names to replan.
        suffix = (
            f" Last failure ({mode_label}): action={summary['action']}, "
            f"error_type={summary['error_type']}, "
            f"argument_fields={summary['argument_fields']}"
            + (
                f", error_hint={summary['error_hint']}"
                if summary.get("error_hint")
                else ""
            )
            + "."
        )
        for tool in tools:
            function = tool.get("function")
            if isinstance(function, dict) and function.get("name") == "tools_search":
                function["description"] = str(function.get("description", "")) + suffix
                break
    return tools


__all__ = [
    "bounded_recovery_actions",
    "decorate_recovery_tools",
    "last_failure_summary",
    "latest_unexecuted_public_failures",
    "soft_recovery_tools",
]
