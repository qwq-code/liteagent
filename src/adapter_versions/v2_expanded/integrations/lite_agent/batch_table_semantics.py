"""Generic one-record-per-observed-input spreadsheet semantics.

The contract uses only the public instruction, successful batch-reader results,
and model-selected spreadsheet arguments.  It never supplies table values.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .adapter_results import (
    a1_geometry,
    column_label,
    column_number,
    _source_has_more_for_item,
    text_batch_context_for_model,
)
from .completion_policy import (
    action_is_read_only,
    canonical_action_request,
    effective_adapter_action,
    effective_canonical_action,
)


BATCH_READ_ACTIONS = ("pdf.extract_text_batch", "image.extract_text_batch")
# Source observations can remain incomplete after the model has inspected the
# target.  Permit a small, finite number of model-selected follow-up reads;
# the event ledger and the observed projection, rather than an instruction,
# decide when the lease ends.
MAX_BATCH_CONTINUATION_ATTEMPTS = 3
INSPECT_ACTION = "spreadsheet.inspect_current"
TARGET_INSPECTION_ACTIONS = frozenset({INSPECT_ACTION, "workbook.inspect"})
CREATE_ACTION = "spreadsheet.create_workbook"
WRITE_ACTION = "spreadsheet.write_range"
READ_ACTION = "spreadsheet.read_file"
SORT_ACTION = "table.sort"
SAVE_ACTION = "spreadsheet.save"

# A producer result does not imply that a new workbook is the consumer.  Keep
# the next consumer choices explicit and model-owned after the current Calc
# document has been inspected.
CONSUMER_ACTIONS = (WRITE_ACTION, READ_ACTION, SAVE_ACTION, CREATE_ACTION)
POST_MUTATION_ACTIONS = (READ_ACTION, WRITE_ACTION, SAVE_ACTION)
POST_MUTATION_ACTION_SET = frozenset({WRITE_ACTION, SORT_ACTION})
_CONSUMER_READ_ACTIONS = frozenset({READ_ACTION, "workbook.read_file"})
_CONSUMER_WRITE_ACTIONS = frozenset({WRITE_ACTION, "range.write"})
_CONSUMER_STAGE_ACTIONS = _CONSUMER_READ_ACTIONS | _CONSUMER_WRITE_ACTIONS

# Adapter responses wrap validation failures in several layers (for example,
# ``DOWNSTREAM_FAILED`` -> ``RANGE_INVALID``), while filesystem and transport
# failures use similarly shaped error objects.  Keep this classifier generic:
# it consumes only bounded error metadata and never examines model arguments.
_VALIDATION_ERROR_CODES = frozenset(
    {
        "ARGUMENT_ERROR",
        "ARGUMENT_INVALID",
        "DIMENSION_MISMATCH",
        "INVALID_ARGUMENT",
        "INVALID_RANGE",
        "INVALID_REQUEST",
        "JSONSCHEMA_VALIDATIONERROR",
        "RANGE_INVALID",
        "SCHEMA_ERROR",
        "SCHEMA_INVALID",
        "SHAPE_MISMATCH",
        "TYPE_MISMATCH",
        "VALIDATIONERROR",
        "VALUEERROR",
    }
)
_IO_ERROR_CODE_PARTS = (
    "CONNECTION",
    "FILE_NOT_FOUND",
    "IO_ERROR",
    "LOCKED",
    "NETWORK",
    "NOT_FOUND",
    "OS_ERROR",
    "PATH_NOT_FOUND",
    "PERMISSION",
    "TIMEOUT",
    "TRANSPORT",
    "UNAVAILABLE",
)
_VALIDATION_TEXT_RE = re.compile(
    r"(?i)(?:model-visible\s+schema|schema|validation|not valid under|"
    r"does not match|must be|rectangular|dimension\w*\s+(?:do|does)\s+not\s+match|"
    r"invalid\s+(?:argument|range|request|shape))"
)
_IO_TEXT_RE = re.compile(
    r"(?i)(?:no such file|file\s+not\s+found|path\s+not\s+found|"
    r"connection|timed?\s*out|permission\s+denied|i/o\s+error|transport)"
)

# Keep the cardinality signal local to the source noun.  A previous
# cross-sentence look-around treated unrelated phrases such as ``PDF reports
# ... for each year`` as a one-record-per-file request.  The model still owns
# the table values; this gate only decides whether a bounded batch-reader
# workflow is relevant.
_INPUT_NOUN_PATTERN = r"(?:papers?|pdfs?|files?|documents?|images?)"
_INPUT_QUALIFIER_PATTERN = (
    r"(?:(?:source|input|listed|provided|available|matching)\s+)?"
)
_EACH_INPUT_RE = re.compile(
    rf"(?ix)\b(?:for\s+)?(?:each|every|all)\s+"
    rf"(?:of\s+(?:the|these|those)\s+)?"
    rf"{_INPUT_QUALIFIER_PATTERN}{_INPUT_NOUN_PATTERN}\b"
)
_ROW_PER_INPUT_RE = re.compile(
    rf"(?ix)\b(?:one|a|an)\s+(?:data\s+)?(?:rows?|records?)\s+per\s+"
    rf"(?:(?:the|each|every|all)\s+)?"
    rf"{_INPUT_QUALIFIER_PATTERN}{_INPUT_NOUN_PATTERN}\b|"
    rf"\b(?:rows?|records?)\s+for\s+(?:each|every|all)\s+"
    rf"(?:of\s+(?:the|these|those)\s+)?"
    rf"{_INPUT_QUALIFIER_PATTERN}{_INPUT_NOUN_PATTERN}\b"
)
_TABLE_ACTION_RE = re.compile(
    r"(?i)\b(?:analy[sz]e|build|collect|convert|copy|create|enter|extract|"
    r"fill|gather|list|look\s+up|make|place|populate|process|put|read|"
    r"record|retrieve|save|summari[sz]e|transfer|organize)\b"
)
_TABLE_OUTPUT_RE = re.compile(
    r"(?i)\b(?:spreadsheet|workbook|excel|xlsx|ods|table|rows?|records?)\b"
)
_SORT_RE = re.compile(r"(?i)\bsort(?:ed|ing)?\b")


def _error_metadata(error: Any) -> tuple[set[str], str]:
    """Collect bounded public error codes and messages from nested responses."""
    codes: set[str] = set()
    texts: list[str] = []
    pending: list[tuple[Any, int]] = [(error, 0)]
    seen: set[int] = set()
    while pending:
        current, depth = pending.pop()
        if not isinstance(current, dict) or id(current) in seen or depth > 5:
            continue
        seen.add(id(current))
        for key, value in current.items():
            folded_key = str(key).casefold()
            if folded_key in {"type", "code", "error_code"} and isinstance(value, str):
                token = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").upper()
                if token:
                    codes.add(token)
            elif folded_key in {"detail", "message", "error"} and isinstance(
                value, str
            ):
                texts.append(value[:512])
            if isinstance(value, dict):
                pending.append((value, depth + 1))
    return codes, " ".join(texts[:24])


def _is_io_error_code(code: str) -> bool:
    return any(part in code for part in _IO_ERROR_CODE_PARTS)


def _is_consumer_validation_error(error: Any) -> bool:
    """Return whether an error is a retryable argument/schema failure.

    A failed consumer call is eligible for the stage lease only when its
    metadata indicates validation.  Explicit filesystem, transport, and
    availability markers take precedence so a nested ``DOWNSTREAM_FAILED``
    response cannot turn an I/O failure into a retry lease.
    """
    if not isinstance(error, dict) or not error:
        return False
    codes, text = _error_metadata(error)
    if "REPEATEDACTIONBLOCKED" in codes:
        return True
    if any(_is_io_error_code(code) for code in codes) or _IO_TEXT_RE.search(text):
        return False
    # A bare ValueError is not enough to establish that a downstream call was
    # rejected before mutation.  Require a schema/shape signal for that
    # generic wrapper; concrete validation codes remain sufficient on their
    # own (for example, RANGE_INVALID nested under DOWNSTREAM_FAILED).
    if "VALUEERROR" in codes and not _VALIDATION_TEXT_RE.search(text):
        codes.discard("VALUEERROR")
    if any(
        code in _VALIDATION_ERROR_CODES
        or code.startswith(("INVALID_", "SCHEMA_", "VALIDATION_"))
        or code.endswith(("_INVALID", "_MISMATCH"))
        for code in codes
    ):
        return True
    return bool(_VALIDATION_TEXT_RE.search(text) and not _IO_TEXT_RE.search(text))


def _error_claims_commit(error: Any) -> bool:
    """Return whether an error explicitly reports a partial mutation."""
    for mapping in _nested_mappings(error):
        for key in ("committed", "mutated", "changed", "applied"):
            value = mapping.get(key)
            if value is True or (
                isinstance(value, str) and value.strip().casefold() == "true"
            ):
                return True
    return False


def _retryable_consumer_failure(action: str, error: Any) -> bool:
    """Classify an unexecuted consumer event without inspecting its values."""
    if not isinstance(error, dict) or not error:
        return False
    if action in _CONSUMER_READ_ACTIONS:
        # Reads are non-mutating.  Keep the existing bounded recovery behavior
        # for adapter/schema/duplicate and ordinary read errors alike.
        return True
    if action in _CONSUMER_WRITE_ACTIONS:
        return not _error_claims_commit(error) and _is_consumer_validation_error(error)
    return False


def consumer_recovery_allows_search(state: Any) -> bool:
    """Whether a rejected consumer mutation may open bounded catalog search.

    Read failures stay on the narrow read surface because another search turn
    cannot repair a missing observation by itself.  A pre-mutation write
    contract error is different: the model may need to discover a reusable
    alternative route or its exact downstream schema.  This helper only
    exposes the control tool; it never selects a route or supplies arguments.
    """
    if not pending_consumer_recovery_actions(state, ()):
        return False
    events = list(getattr(state, "events", ()) or ())
    if not events:
        return False
    latest = events[-1]
    if getattr(latest, "executed", False):
        return False
    proposed = getattr(latest, "proposed", None)
    if not isinstance(proposed, dict) or proposed.get("kind") != "adapter":
        return False
    try:
        _domain, action, _arguments = effective_adapter_action(latest, state.domain)
    except (AttributeError, TypeError, ValueError):
        return False
    return action in _CONSUMER_WRITE_ACTIONS and _retryable_consumer_failure(
        action, getattr(latest, "error", None)
    )


def requests_one_record_per_input(instruction: str) -> bool:
    """Return whether the instruction explicitly requests exhaustive tabulation."""
    if not _TABLE_OUTPUT_RE.search(instruction):
        return False
    if _ROW_PER_INPUT_RE.search(instruction):
        return True

    # A bare ``each PDF file`` often describes naming, conversion, or another
    # per-file operation rather than a table.  Require a table-producing verb
    # in the same instruction clause as the source quantifier so an unrelated
    # later ``Excel``/``workbook`` mention cannot activate the batch gate.
    for match in _EACH_INPUT_RE.finditer(instruction):
        start = max(
            instruction.rfind(delimiter, 0, match.start()) for delimiter in ".!?;\n"
        )
        end_candidates = [
            instruction.find(delimiter, match.end())
            for delimiter in ".!?;\n"
            if instruction.find(delimiter, match.end()) >= 0
        ]
        end = min(end_candidates, default=len(instruction))
        clause = instruction[start + 1 : end]
        if _TABLE_OUTPUT_RE.search(clause) and _TABLE_ACTION_RE.search(clause):
            return True
    return False


def _instruction_batch_actions(instruction: str) -> list[str]:
    """Return public batch producers suggested by the source nouns in an instruction."""
    actions: list[str] = []
    if re.search(r"(?i)\b(?:papers?|pdfs?)\b", instruction):
        actions.append("pdf.extract_text_batch")
    if re.search(r"(?i)\bimages?\b", instruction):
        actions.append("image.extract_text_batch")
    return actions


def _event_batch_action(event: Any, default_domain: str = "multi_apps") -> str | None:
    proposed = getattr(event, "proposed", None)
    if not isinstance(proposed, dict):
        return None
    if proposed.get("kind") not in {None, "adapter"}:
        return None
    action = proposed.get("action")
    if action in BATCH_READ_ACTIONS:
        return str(action)
    if action == "adapter.call":
        # A searched multi-app route may wrap the same public producer.  Use
        # only the model-selected downstream action; never infer its payload.
        try:
            _domain, downstream_action, _arguments = effective_adapter_action(
                event, default_domain
            )
        except (AttributeError, TypeError, ValueError):
            downstream_action = ""
        if downstream_action in BATCH_READ_ACTIONS:
            return downstream_action
    # Older traces sometimes only retained the generated public tool name.
    tool = proposed.get("tool")
    if isinstance(tool, str) and proposed.get("kind") in {None, "adapter"}:
        for candidate in BATCH_READ_ACTIONS:
            if tool.rsplit("__", 1)[-1] == candidate.replace(".", "_"):
                return candidate
    return None


def _event_matches_action(event: Any, state: Any, action: str) -> bool:
    """Compare a direct facade and an ``adapter.call`` by one identity."""
    try:
        observed = effective_canonical_action(
            event, getattr(state, "domain", "multi_apps")
        )[:2]
        expected = canonical_action_request(
            getattr(state, "domain", "multi_apps"), action, {}
        )[:2]
    except (AttributeError, TypeError, ValueError):
        return False
    return observed == expected


def pending_producer_actions(state: Any, actions: Any) -> tuple[str, ...]:
    """Return batch producers that must be attempted before GUI competition.

    The gate is a generic stage signal: it applies only to an explicit
    one-record-per-input table workflow, and it ends as soon as the model has
    attempted a producer (whether that attempt succeeds or fails).  No
    producer arguments are inferred here.
    """
    if (
        getattr(state, "domain", None) != "multi_apps"
        or not requests_one_record_per_input(str(getattr(state, "instruction", "")))
        or expected_record_count(state) is not None
    ):
        return ()
    if any(
        _event_batch_action(event) is not None for event in getattr(state, "events", ())
    ):
        return ()

    instruction_actions = _instruction_batch_actions(
        str(getattr(state, "instruction", ""))
    )
    selected = [action for action in list(actions) if action in BATCH_READ_ACTIONS]
    if instruction_actions:
        selected = [action for action in selected if action in instruction_actions]
        if not selected:
            selected = instruction_actions
    return tuple(dict.fromkeys(selected))


def _arguments(event: Any) -> dict[str, Any]:
    proposed = getattr(event, "proposed", None)
    arguments = proposed.get("arguments") if isinstance(proposed, dict) else None
    return arguments if isinstance(arguments, dict) else {}


def _nested_mappings(value: Any) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    pending = [value]
    for _depth in range(10):
        if not pending:
            break
        next_pending = []
        for item in pending:
            if isinstance(item, dict):
                mappings.append(item)
                next_pending.extend(item.values())
            elif isinstance(item, list):
                next_pending.extend(item)
        pending = next_pending
    return mappings


def _positive_int(value: Any) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else None
    )


def _successful_batch_events(state: Any) -> list[Any]:
    """Return successful direct or searched-wrapper batch observations."""
    events = [
        event
        for event in getattr(state, "events", ())
        if getattr(event, "executed", False)
        and _event_batch_action(event, getattr(state, "domain", "multi_apps"))
        is not None
    ]
    if events:
        return sorted(events, key=lambda event: event.step)
    # Keep compatibility with lightweight synthetic states that implement only
    # ``successful_action_events`` rather than exposing an event list.
    fallback: list[Any] = []
    for action in BATCH_READ_ACTIONS:
        fallback.extend(state.successful_action_events(action))
    return sorted(fallback, key=lambda event: event.step)


def _successful_action_events(state: Any, action: str) -> list[Any]:
    """Resolve successful direct actions and searched ``adapter.call`` routes."""
    events = []
    for event in getattr(state, "events", ()):
        if not getattr(event, "executed", False):
            continue
        proposed = getattr(event, "proposed", None)
        if not isinstance(proposed, dict) or proposed.get("kind") not in {
            None,
            "adapter",
        }:
            continue
        try:
            _domain, effective_action, _arguments = effective_adapter_action(
                event, getattr(state, "domain", "multi_apps")
            )
        except (AttributeError, TypeError, ValueError):
            continue
        if effective_action == action or (
            action == INSPECT_ACTION and effective_action in TARGET_INSPECTION_ACTIONS
        ):
            events.append(event)
    if events:
        return sorted(events, key=lambda event: event.step)
    return sorted(state.successful_action_events(action), key=lambda event: event.step)


def _batch_arguments(event: Any, state: Any) -> dict[str, Any]:
    """Return model-selected producer arguments, unmodified, for comparison."""
    proposed = getattr(event, "proposed", None)
    if not isinstance(proposed, dict):
        return {}
    action = proposed.get("action")
    if action == "adapter.call":
        try:
            _domain, _action, arguments = effective_adapter_action(
                event, getattr(state, "domain", "multi_apps")
            )
            return arguments
        except (AttributeError, TypeError, ValueError):
            return {}
    return _arguments(event)


def _batch_identity(event: Any, state: Any) -> tuple[str, str, dict[str, Any]]:
    """Return an internal route/argument identity for progress comparisons."""
    proposed = getattr(event, "proposed", None)
    if isinstance(proposed, dict) and proposed.get("action") == "adapter.call":
        try:
            domain, action, arguments = effective_adapter_action(
                event, getattr(state, "domain", "multi_apps")
            )
            return domain, action, arguments
        except (AttributeError, TypeError, ValueError):
            pass
    return (
        getattr(state, "domain", "multi_apps"),
        str(proposed.get("action", "")) if isinstance(proposed, dict) else "",
        _batch_arguments(event, state),
    )


def _latest_successful_batch_event(state: Any) -> Any | None:
    events = _successful_batch_events(state)
    return max(events, key=lambda event: event.step, default=None)


def _batch_model_projection(event: Any) -> dict[str, Any] | None:
    """Return the latest text-batch projection carried by a successful event.

    Adapter events keep the complete result for auditing, while the model sees
    a typed projection under ``context_hint``.  Multi-app facades may wrap that
    hint in ``downstream_context``; walking only the hint subtree keeps this
    helper tied to observed output and avoids deriving anything from task
    identity or instruction-specific state.
    """
    result = getattr(event, "result", None)
    if not isinstance(result, dict):
        return None
    hints: list[dict[str, Any]] = []
    for mapping in _nested_mappings(result):
        hint = mapping.get("context_hint")
        if isinstance(hint, dict):
            hints.append(hint)
    for hint in reversed(hints):
        for candidate in _nested_mappings(hint):
            if candidate.get("observation_type") == "text_batch":
                return candidate
            if _is_text_batch_mapping(candidate):
                return text_batch_context_for_model(candidate)
    # Synthetic/direct events and older traces may not have a separate
    # ``context_hint`` wrapper.  The raw observed result is still sufficient
    # to determine whether a bounded continuation is available.
    for candidate in reversed(_nested_mappings(result)):
        if _is_text_batch_mapping(candidate):
            return text_batch_context_for_model(candidate)
    return None


def _is_text_batch_mapping(value: Any) -> bool:
    files = value.get("files") if isinstance(value, dict) else None
    return isinstance(files, list) and any(
        isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and ("text" in item or "returned_chars" in item)
        for item in files
    )


def _source_continuation_pending(projection: dict[str, Any]) -> bool:
    """Distinguish incomplete source data from a compact model projection."""
    explicit = projection.get("source_has_more")
    if isinstance(explicit, bool):
        # ``files_omitted``/``context_files_omitted`` describe the model
        # projection, not the Adapter source.  They must not schedule an
        # identical producer request when all observed source files are done.
        return explicit
    files = projection.get("files")
    if not isinstance(files, list):
        return False
    for item in files:
        if not isinstance(item, dict):
            continue
        source_more = item.get("source_has_more")
        if isinstance(source_more, bool):
            if source_more:
                return True
            continue
        source_item = dict(item)
        metadata = item.get("metadata")
        if isinstance(metadata, dict):
            source_item.update(metadata)
        if _source_has_more_for_item(source_item):
            return True
    # Legacy projections used ``has_more`` for both meanings.  Only retain
    # that fallback when there is no explicit context-only marker.
    return bool(projection.get("has_more")) and not bool(
        projection.get("context_truncated")
    )


def batch_continuation_action(state: Any) -> str | None:
    """Return the observed batch reader when its model view has more content."""
    latest = _latest_successful_batch_event(state)
    if latest is None:
        return None
    # A source-only continuation does not change the target application.  Keep
    # the target probe valid while the latest observed source is incomplete;
    # the bounded attempt/progress checks below prevent an unbounded read loop.
    all_batches = _successful_batch_events(state)
    first_batch_step = min(event.step for event in all_batches)
    inspections = [
        event
        for event in _successful_action_events(state, INSPECT_ACTION)
        if event.step > first_batch_step
    ]
    # Anchor the lease to the first successful target probe.  A later repeated
    # inspect is useful observation, but must not reset the finite source cap.
    probe_anchor = min(inspections, key=lambda event: event.step, default=None)
    if probe_anchor is None:
        return None
    projection = _batch_model_projection(latest)
    if not isinstance(projection, dict):
        return None
    if not _source_continuation_pending(projection):
        return None
    batch_action = _event_batch_action(latest, getattr(state, "domain", "multi_apps"))
    if batch_action is None:
        return None

    # Count every producer attempt after the target probe, including rejected
    # attempts.  A model-selected changed argument can make progress, but a
    # finite lease must still terminate if the source remains incomplete.
    attempts_after_probe = [
        event
        for event in getattr(state, "events", ())
        if getattr(event, "step", -1) > probe_anchor.step
        and _event_batch_action(event, getattr(state, "domain", "multi_apps"))
        is not None
    ]
    if len(attempts_after_probe) >= MAX_BATCH_CONTINUATION_ATTEMPTS:
        return None

    # The first post-probe continuation must differ from the original producer
    # request; later continuations must likewise avoid replaying a successful
    # request.  Equality is used only inside the event ledger and is never
    # serialized into the model-facing surface.
    latest_identity = _batch_identity(latest, state)
    prior_batches = [event for event in all_batches if event.step < latest.step]
    if latest.step > probe_anchor.step and any(
        _batch_identity(event, state) == latest_identity for event in prior_batches
    ):
        return None

    # Do not keep a stale source action alive after a successful mutation.  A
    # successful read-only target observation is intentionally allowed between
    # source calls, preserving the probe/continuation handoff.
    for event in getattr(state, "events", ()):
        if getattr(event, "step", -1) <= latest.step or not getattr(
            event, "executed", False
        ):
            continue
        proposed = getattr(event, "proposed", None)
        if not isinstance(proposed, dict):
            continue
        # GUI execution can change the target without carrying an Adapter
        # action name. Once it follows the source observation, the source
        # continuation lease is no longer trustworthy.
        if proposed.get("kind") == "gui":
            return None
        if proposed.get("kind") != "adapter":
            continue
        try:
            _domain, action, _arguments = effective_adapter_action(
                event, getattr(state, "domain", "multi_apps")
            )
        except (AttributeError, TypeError, ValueError):
            return None
        if (
            action not in TARGET_INSPECTION_ACTIONS
            and action not in BATCH_READ_ACTIONS
            and not action_is_read_only(action)
        ):
            return None

    # A failed changed-argument attempt may still be retried, but an exact
    # replay of any already-successful request is never re-presented here.
    producer_attempts = [
        event
        for event in getattr(state, "events", ())
        if getattr(event, "step", -1) > probe_anchor.step
        and _event_batch_action(event, getattr(state, "domain", "multi_apps"))
        is not None
    ]
    if producer_attempts:
        last_attempt = max(producer_attempts, key=lambda event: event.step)
        if not getattr(last_attempt, "executed", False):
            attempt_identity = _batch_identity(last_attempt, state)
            if any(
                _batch_identity(event, state) == attempt_identity
                for event in all_batches
            ):
                return None
            return batch_action
    return batch_action


def _valid_target_inspection(state: Any) -> Any | None:
    """Find a target probe still valid after source-only continuation reads."""
    batches = _successful_batch_events(state)
    if not batches:
        return None
    first_batch_step = min(event.step for event in batches)
    latest_batch_step = max(event.step for event in batches)
    inspections = [
        event
        for event in _successful_action_events(state, INSPECT_ACTION)
        if first_batch_step < event.step
    ]
    if not inspections:
        return None
    candidate = max(inspections, key=lambda event: event.step)
    if candidate.step >= latest_batch_step:
        return candidate
    between = [
        event
        for event in getattr(state, "events", ())
        if candidate.step < getattr(event, "step", -1) <= latest_batch_step
    ]

    def is_non_mutating_observation(event: Any) -> bool:
        """Keep a target probe valid across successful read-only observations."""
        if not getattr(event, "executed", False):
            return False
        proposed = getattr(event, "proposed", None)
        if not isinstance(proposed, dict) or proposed.get("kind") != "adapter":
            return False
        _domain, action, _arguments = effective_adapter_action(event, state.domain)
        # Keep compatibility with old traces that retained only the generated
        # batch tool name, while resolving adapter.call to its observed route.
        return (
            _event_batch_action(event) is not None
            or action == INSPECT_ACTION
            or action in BATCH_READ_ACTIONS
            or action_is_read_only(action)
        )

    if all(is_non_mutating_observation(event) for event in between):
        return candidate
    return None


def _bounded_consumer_actions(
    state: Any,
    actions: Any,
    *,
    prefer_consumer: bool = False,
) -> list[str]:
    """Build the post-probe surface with an explicit continuation priority.

    A failed consumer call is a local contract problem.  Give the model a
    chance to correct that call before offering another source read, while
    retaining the source continuation as a bounded fallback when the source
    really is incomplete.
    """
    continuation = batch_continuation_action(state)
    bounded = []
    if continuation and not prefer_consumer:
        bounded.append(continuation)
    bounded.extend(CONSUMER_ACTIONS)
    if continuation and prefer_consumer:
        bounded.append(continuation)
    if SORT_ACTION in actions:
        bounded.append(SORT_ACTION)
    return list(dict.fromkeys(bounded))


def _current_create_events(state: Any) -> list[Any]:
    """Return create events belonging to the latest observed batch workflow."""
    # Multi-app routes normally arrive as a model-selected ``adapter.call``
    # carrying the downstream Calc action.  Resolve both that wrapper and the
    # direct facade so completion cannot miss a real create event and accept a
    # header-only workbook.
    creates = _successful_action_events(state, CREATE_ACTION)
    latest_batch = _latest_successful_batch_event(state)
    if latest_batch is None:
        return creates
    return [event for event in creates if event.step > latest_batch.step]


def expected_record_count(state: Any) -> int | None:
    """Return the largest observed source cardinality for this workflow.

    A narrowed continuation can legitimately match one file while filling in
    missing text from an initial multi-file batch.  Using the latest match
    count would silently shrink the required table and completion contract.
    """
    if getattr(
        state, "domain", None
    ) != "multi_apps" or not requests_one_record_per_input(
        str(getattr(state, "instruction", ""))
    ):
        return None
    batches = _successful_batch_events(state)
    if not batches:
        return None
    counts = []
    for event in batches:
        counts.extend(
            count
            for item in _nested_mappings(event.result)
            if (count := _positive_int(item.get("matched_count"))) is not None
        )
    return max(counts, default=None)


def _observed_string(result: Any, key: str) -> str | None:
    for item in _nested_mappings(result):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def pending_header_first_creation(state: Any) -> Any | None:
    creates = _current_create_events(state)
    if not creates:
        return None
    latest = creates[-1]
    arguments = _arguments(latest)
    if "headers" not in arguments or "rows" in arguments:
        return None
    return latest


def expected_header_first_write(state: Any) -> dict[str, Any] | None:
    """Return the table geometry implied by a model-selected header-only create."""
    create = pending_header_first_creation(state)
    count = expected_record_count(state)
    if create is None or count is None:
        return None
    headers = _arguments(create).get("headers")
    if not isinstance(headers, list) or not headers:
        return None
    end_column = column_label(len(headers))
    return {
        "sheet": _observed_string(create.result, "sheet"),
        "range": f"A2:{end_column}{count + 1}",
        "record_count": count,
        "column_count": len(headers),
        "headers": [str(value) for value in headers],
        "create_step": create.step,
    }


def stage_actions(state: Any, actions: Any) -> list[str]:
    """Stage a batch producer before exposing generic table consumers.

    A successful batch reader only establishes that source records are
    available.  It says nothing about whether the user wants to edit an
    already-open workbook or create a new one.  Require a model-selected
    inspection first, then expose the ordinary consumer actions together so
    the model can choose the workflow that matches the observed application
    state.  The old create-first behavior made an existing open workbook
    unreachable and implicitly selected a new-file workflow.
    """
    selected = list(actions)
    count = expected_record_count(state)
    if count is None:
        if getattr(
            state, "domain", None
        ) != "multi_apps" or not requests_one_record_per_input(
            str(getattr(state, "instruction", ""))
        ):
            return selected
        if getattr(state, "events", None):
            return selected
        instruction = str(state.instruction)
        instruction_actions = _instruction_batch_actions(instruction)
        if instruction_actions:
            return instruction_actions
        return selected

    # Ground the consumer against live application state.  A failed probe is
    # deliberately soft: keep the probe searchable while allowing a new
    # workbook attempt; the model still supplies every argument.
    latest_batch_step = _latest_successful_batch_event(state).step
    creates = _current_create_events(state)
    if creates:
        table = observed_created_table(state)
        if table is None:
            return [WRITE_ACTION]
        sort_events = [
            event
            for event in getattr(state, "events", ())
            if getattr(event, "executed", False)
            and _event_matches_action(event, state, SORT_ACTION)
        ]
        if _SORT_RE.search(str(state.instruction)) and not sort_events:
            return [SORT_ACTION]
        latest_mutation_step = max(
            table["source_step"],
            max((event.step for event in sort_events), default=0),
        )
        saves = [
            event
            for event in getattr(state, "events", ())
            if getattr(event, "executed", False)
            and event.step > latest_mutation_step
            and _event_matches_action(event, state, SAVE_ACTION)
        ]
        if not saves:
            return [SAVE_ACTION]
        if not any(
            event.step > saves[-1].step
            for event in getattr(state, "events", ())
            if getattr(event, "executed", False)
            and _event_matches_action(event, state, READ_ACTION)
        ):
            return [READ_ACTION]
        return selected

    valid_inspection = _valid_target_inspection(state)
    if valid_inspection is None:
        inspected_attempt = any(
            _event_matches_action(event, state, INSPECT_ACTION)
            and event.step > latest_batch_step
            for event in getattr(state, "events", ())
        )
        if inspected_attempt:
            return list(dict.fromkeys([INSPECT_ACTION, CREATE_ACTION]))
        return [INSPECT_ACTION]

    # Keep this handoff surface deliberately bounded.  A batch result should
    # not re-expose unrelated multi-app facades (some of which hide several
    # mutations behind one call).  Sorting remains available when the public
    # ranking explicitly found that atomic operation; everything else remains
    # discoverable through tools_search.
    return _bounded_consumer_actions(state, actions)


def inspection_pending(state: Any) -> bool:
    """Return whether a successful batch still needs a live target probe.

    The signal is intentionally derived from the current event ledger rather
    than from an instruction-specific plan.  Until the model has either
    completed or failed the zero-argument spreadsheet probe, unrelated GUI
    actions should not compete with that observation step.
    """
    if expected_record_count(state) is None:
        return False
    latest_batch = _latest_successful_batch_event(state)
    if latest_batch is None or _current_create_events(state):
        return False
    if _valid_target_inspection(state) is not None:
        # Source-only continuation reads do not invalidate a successful target
        # probe; keep the consumer surface available after the read.
        return False
    events_after_batch = [
        event
        for event in getattr(state, "events", ())
        if getattr(event, "step", -1) > latest_batch.step
    ]
    if any(
        _event_matches_action(event, state, INSPECT_ACTION)
        for event in events_after_batch
    ):
        # A rejected inspection is handled by ``stage_actions`` as a soft
        # create/recovery choice; it must not be hidden behind this gate.
        return False
    return True


def pending_consumer_actions(state: Any, actions: Any) -> tuple[str, ...]:
    """Return the bounded consumer surface after a successful target probe.

    The surface lasts until the model has selected a downstream mutation or a
    save.  A failed call or an explicit replan always releases the normal
    recovery surface, so this is a routing hint rather than a hidden workflow.
    """
    count = expected_record_count(state)
    if count is None or _current_create_events(state):
        return ()
    latest_batch = _latest_successful_batch_event(state)
    if latest_batch is None:
        return ()
    valid_inspection = _valid_target_inspection(state)
    if (
        valid_inspection is None
        or state.requires_replan()
        or state.active_request_blocks()
    ):
        return ()
    latest_inspect_step = valid_inspection.step
    for event in getattr(state, "events", ()):
        if getattr(event, "step", -1) <= latest_inspect_step:
            continue
        if not getattr(event, "executed", False):
            return ()
        if any(
            _event_matches_action(event, state, action)
            for action in (WRITE_ACTION, CREATE_ACTION, SAVE_ACTION, SORT_ACTION)
        ):
            return ()
    return tuple(_bounded_consumer_actions(state, actions))


def pending_consumer_recovery_actions(state: Any, actions: Any) -> tuple[str, ...]:
    """Retain the bounded consumer lease around recoverable consumer errors.

    A failed read is non-mutating, while a failed write is eligible only when
    the nested Adapter evidence identifies a pre-mutation schema/shape error.
    Releasing the workflow to the generic GUI/search recovery surface for those
    recoverable failures can make a small model retry unrelated clicks instead
    of choosing a corrected consumer request.  Filesystem, transport, target,
    and explicitly partial-commit failures still release the normal recovery
    surface.  This path is valid only after a live target probe and before any
    successful consumer mutation; it never infers or rewrites arguments.
    """
    if (
        getattr(state, "domain", None) != "multi_apps"
        or expected_record_count(state) is None
        or _current_create_events(state)
    ):
        return ()
    probe = _valid_target_inspection(state)
    if probe is None:
        return ()
    events = list(getattr(state, "events", ()) or ())
    if not events:
        return ()
    latest = events[-1]
    if getattr(latest, "step", -1) <= probe.step:
        return ()
    proposed = getattr(latest, "proposed", None)
    if not isinstance(proposed, dict) or proposed.get("kind") != "adapter":
        return ()
    _domain, latest_action, _arguments = effective_adapter_action(latest, state.domain)
    if latest_action not in _CONSUMER_STAGE_ACTIONS:
        return ()
    if getattr(latest, "executed", False):
        if latest_action not in _CONSUMER_READ_ACTIONS:
            return ()
        active_blocks = state.active_request_blocks()
        if not active_blocks:
            return ()
        for block in active_blocks.values():
            blocked_action = block.get("action")
            if blocked_action == "adapter.call":
                route = block.get("downstream_route")
                blocked_action = (
                    route.get("action") if isinstance(route, dict) else None
                )
            if (
                blocked_action not in _CONSUMER_READ_ACTIONS
                or not isinstance(block.get("blocked_at_step"), int)
                or block["blocked_at_step"] <= probe.step
            ):
                return ()
    else:
        error = getattr(latest, "error", None)
        if not _retryable_consumer_failure(latest_action, error):
            return ()

    for event in events:
        if getattr(event, "step", -1) <= probe.step:
            continue
        if event is latest:
            continue
        event_proposed = getattr(event, "proposed", None)
        if (
            not isinstance(event_proposed, dict)
            or event_proposed.get("kind") != "adapter"
        ):
            return ()
        _domain, action, _event_arguments = effective_adapter_action(
            event, state.domain
        )
        if not getattr(event, "executed", False):
            event_error = getattr(event, "error", None)
            if not _retryable_consumer_failure(action, event_error):
                return ()
            continue
        if any(
            _event_matches_action(event, state, candidate)
            for candidate in (WRITE_ACTION, SORT_ACTION, CREATE_ACTION, SAVE_ACTION)
        ):
            return ()

    return tuple(_bounded_consumer_actions(state, actions, prefer_consumer=True))


def pending_post_mutation_actions(state: Any, actions: Any) -> tuple[str, ...]:
    """Keep batch consumers focused until a successful mutation is verified.

    A successful write changes the target, but it does not prove that the
    model has finished the requested workflow.  Until a read and save occur
    after the latest consumer mutation, expose only the bounded consumer
    operations.  This prevents an unrelated GUI fallback from competing with
    the required read-back while leaving every mutation argument model-owned.
    """
    if (
        getattr(state, "domain", None) != "multi_apps"
        or expected_record_count(state) is None
        or _current_create_events(state)
    ):
        return ()
    probe = _valid_target_inspection(state)
    if probe is None:
        return ()

    relevant: list[tuple[Any, str]] = []
    for event in getattr(state, "events", ()):
        if getattr(event, "step", -1) <= probe.step or not getattr(
            event, "executed", False
        ):
            continue
        proposed = getattr(event, "proposed", None)
        if not isinstance(proposed, dict) or proposed.get("kind") != "adapter":
            continue
        _domain, action, _arguments = effective_adapter_action(event, state.domain)
        relevant.append((event, action))
    mutations = [
        (event, action)
        for event, action in relevant
        if any(
            _event_matches_action(event, state, candidate)
            for candidate in POST_MUTATION_ACTION_SET
        )
    ]
    if not mutations:
        return ()
    latest_mutation_step = max(event.step for event, _action in mutations)

    # Any rejected call after the mutation should use the ordinary recovery
    # surface, rather than silently forcing a verification action.
    if any(
        getattr(event, "step", -1) > latest_mutation_step
        and not getattr(event, "executed", False)
        for event in getattr(state, "events", ())
    ):
        return ()

    read_back = any(
        _event_matches_action(event, state, READ_ACTION)
        and event.step > latest_mutation_step
        for event, action in relevant
    )
    saved = any(
        _event_matches_action(event, state, SAVE_ACTION)
        and event.step > latest_mutation_step
        for event, action in relevant
    )
    if read_back and saved:
        return ()

    bounded: list[str] = []
    if not read_back:
        bounded.append(READ_ACTION)
    bounded.extend(action for action in POST_MUTATION_ACTIONS if action not in bounded)
    if SORT_ACTION in actions and not any(
        _event_matches_action(event, state, SORT_ACTION)
        and event.step > latest_mutation_step
        for event, action in relevant
    ):
        bounded.append(SORT_ACTION)
    return tuple(dict.fromkeys(bounded))


def observed_created_table(state: Any) -> dict[str, Any] | None:
    """Describe the latest table created from model-selected headers and rows."""
    creates = _current_create_events(state)
    if not creates:
        return None
    create = creates[-1]
    arguments = _arguments(create)
    headers = arguments.get("headers")
    if not isinstance(headers, list) or not headers:
        return None
    sheet = _observed_string(create.result, "sheet")
    if "rows" in arguments:
        rows = arguments.get("rows")
        if not isinstance(rows, list) or sheet is None:
            return None
        data_range = _observed_string(create.result, "data_range")
        if a1_geometry(str(data_range or "")) is None:
            data_range = f"A1:{column_label(len(headers))}{len(rows) + 1}"
        return {
            "sheet": sheet,
            "range": data_range,
            "headers": [str(value) for value in headers],
            "record_count": len(rows),
            "source_step": create.step,
        }

    writes = [
        event
        for event in _successful_action_events(state, WRITE_ACTION)
        if event.step > create.step
    ]
    if not writes:
        return None
    write = writes[-1]
    write_arguments = _arguments(write)
    geometry = a1_geometry(str(write_arguments.get("range", "")))
    values = write_arguments.get("values")
    if geometry is None or not isinstance(values, list) or not values:
        return None
    start_column, start_row, end_column, end_row = geometry
    if start_column.upper() != "A" or start_row != 2:
        return None
    width = column_number(end_column) - column_number(start_column) + 1
    if width != len(headers) or sheet is None:
        sheet = str(write_arguments.get("sheet", "")).strip() or sheet
    if width != len(headers) or sheet is None:
        return None
    return {
        "sheet": sheet,
        "range": f"A1:{end_column.upper()}{end_row}",
        "headers": [str(value) for value in headers],
        "record_count": end_row - start_row + 1,
        "source_step": write.step,
    }


def _matrix_shape(values: Any) -> tuple[int, int] | None:
    if (
        not isinstance(values, list)
        or not values
        or not all(isinstance(row, list) for row in values)
    ):
        return None
    widths = {len(row) for row in values}
    if len(widths) != 1:
        return None
    return len(values), widths.pop()


def argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    """Reject incomplete model-selected batch tables without changing arguments."""
    count = expected_record_count(state)
    if count is None:
        return []
    if action == CREATE_ACTION and "rows" in arguments:
        rows = arguments.get("rows")
        if not isinstance(rows, list) or len(rows) != count:
            return [
                f"the successful batch reader observed {count} inputs, so rows must contain "
                f"exactly {count} model-supplied records; no values are supplied by the Runner"
            ]
        return []
    if action != WRITE_ACTION:
        return []
    expected = expected_header_first_write(state)
    if expected is None:
        return []
    shape = _matrix_shape(arguments.get("values"))
    errors = []
    if shape != (expected["record_count"], expected["column_count"]):
        errors.append(
            "spreadsheet.write_range values must be a rectangular row matrix containing "
            f"exactly {expected['record_count']} model-supplied records and "
            f"{expected['column_count']} cells per record"
        )
    if str(arguments.get("range", "")).upper() != expected["range"]:
        errors.append(
            "spreadsheet.write_range must cover the data rows immediately below the observed "
            f"header without omission: {expected['range']}"
        )
    if expected["sheet"] and arguments.get("sheet") != expected["sheet"]:
        errors.append(
            "spreadsheet.write_range must target the worksheet returned by the header-only "
            f"create call: {expected['sheet']!r}"
        )
    return errors


def constrain_tool_schema(function: dict[str, Any], state: Any) -> None:
    """Expose observed cardinality while leaving every record value model-owned."""
    count = expected_record_count(state)
    if count is None:
        return
    name = function.get("name")
    parameters = function.get("parameters")
    properties = parameters.get("properties") if isinstance(parameters, dict) else None
    if not isinstance(properties, dict):
        return
    if name == "adapter__spreadsheet_create_workbook":
        rows = properties.get("rows")
        if isinstance(rows, dict):
            rows["minItems"] = count
            rows["maxItems"] = count
            rows["description"] = (
                f"The successful batch reader observed {count} inputs. If rows is supplied, "
                f"provide exactly {count} complete records. The Runner supplies no cell values."
            )
        function["description"] += (
            f" The current public batch result contains {count} inputs; a complete one-row-per-input "
            "table therefore needs that many model-supplied data rows."
        )
        return
    if name != "adapter__spreadsheet_write_range":
        return
    expected = expected_header_first_write(state)
    if expected is None:
        return
    values = properties.get("values")
    branches = values.get("oneOf") if isinstance(values, dict) else None
    matrix = (
        copy.deepcopy(branches[1])
        if isinstance(branches, list) and len(branches) > 1
        else None
    )
    if not isinstance(matrix, dict):
        return
    matrix["minItems"] = expected["record_count"]
    matrix["maxItems"] = expected["record_count"]
    item_schema = matrix.get("items")
    if isinstance(item_schema, dict):
        item_schema["minItems"] = expected["column_count"]
        item_schema["maxItems"] = expected["column_count"]
    matrix["description"] = (
        f"Exactly {expected['record_count']} model-supplied records with "
        f"{expected['column_count']} cells per record."
    )
    properties["values"] = matrix
    range_schema = properties.get("range")
    if isinstance(range_schema, dict):
        range_schema["enum"] = [expected["range"]]
        range_schema["description"] = (
            "Observed header geometry and batch cardinality require this contiguous data range."
        )
    sheet_schema = properties.get("sheet")
    if isinstance(sheet_schema, dict) and expected["sheet"]:
        sheet_schema["enum"] = [expected["sheet"]]
    function["description"] += (
        f" The header-only workbook and observed batch cardinality require "
        f"{expected['record_count']} data rows; every cell remains model-supplied."
    )


def _sheet_rows(value: Any, *, sheet: str, cell_range: str) -> list[list[str]]:
    for item in _nested_mappings(value):
        sheets = item.get("sheets")
        if not isinstance(sheets, list):
            continue
        for candidate in sheets:
            if not isinstance(candidate, dict) or candidate.get("name") != sheet:
                continue
            observed_range = candidate.get("used_range") or candidate.get(
                "source_range"
            )
            rows = candidate.get("display_text")
            if (
                str(observed_range).upper() == cell_range.upper()
                and isinstance(rows, list)
                and all(isinstance(row, list) for row in rows)
            ):
                return [[str(value) for value in row] for row in rows]
    return []


def latest_readback_rows(
    state: Any, *, sheet: str, cell_range: str, after_step: int = 0
) -> list[list[str]]:
    for event in reversed(_successful_action_events(state, READ_ACTION)):
        if event.step <= after_step:
            continue
        rows = _sheet_rows(event.result, sheet=sheet, cell_range=cell_range)
        if rows:
            return rows
    return []


def completion_errors(state: Any) -> list[str]:
    # Reading a batch is not itself a request to create a table.  Defer all
    # creation-specific cardinality and readback requirements until the model
    # has selected and successfully executed the public create action.
    if not _current_create_events(state):
        return []
    count = expected_record_count(state)
    if count is None:
        return []
    table = observed_created_table(state)
    if table is None or table["record_count"] != count:
        return [
            f"the batch reader observed {count} inputs, but no successful spreadsheet table "
            f"contains exactly {count} model-supplied data records"
        ]
    rows = latest_readback_rows(
        state,
        sheet=table["sheet"],
        cell_range=table["range"],
        after_step=table["source_step"],
    )
    if len(rows) != count + 1:
        return [
            f"structurally read back the final spreadsheet with one header row and all {count} "
            "observed-input data rows before completion"
        ]
    return []


__all__ = [
    "CONSUMER_ACTIONS",
    "CREATE_ACTION",
    "INSPECT_ACTION",
    "READ_ACTION",
    "SAVE_ACTION",
    "WRITE_ACTION",
    "argument_contract_errors",
    "batch_continuation_action",
    "completion_errors",
    "consumer_recovery_allows_search",
    "constrain_tool_schema",
    "expected_header_first_write",
    "expected_record_count",
    "inspection_pending",
    "latest_readback_rows",
    "pending_consumer_actions",
    "pending_consumer_recovery_actions",
    "pending_producer_actions",
    "observed_created_table",
    "requests_one_record_per_input",
    "stage_actions",
]
