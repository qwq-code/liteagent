from __future__ import annotations

import json
from typing import Any, Iterable

from .completion_policy import action_is_read_only, effective_canonical_action


def request_stall_replan(state: Any, stall: dict[str, Any], *, limit: int = 1) -> bool:
    """Grant one model-authored recovery turn before terminating a no-progress loop."""
    if limit < 0:
        raise ValueError("stall replan limit must be nonnegative")
    requested = int(getattr(state, "runner_replans_requested", 0))
    if requested >= limit:
        return False
    state.runner_replans_requested = requested + 1
    state.pending_runner_replan = {
        "type": "no_progress_replan",
        "reason": str(stall.get("reason", "no_progress")),
    }
    return True


def _proposal(event: Any) -> dict[str, Any]:
    value = getattr(event, "proposed", None)
    return value if isinstance(value, dict) else {}


def _effective_action(event: Any) -> str:
    proposed = _proposal(event)
    action = str(proposed.get("action") or proposed.get("tool") or "")
    if action != "adapter.call":
        return action
    arguments = proposed.get("arguments")
    if not isinstance(arguments, dict):
        return action
    nested = arguments.get("action")
    return str(nested) if isinstance(nested, str) else action


def _request_signature(event: Any) -> str:
    proposed = _proposal(event)
    payload = {
        "action": _effective_action(event),
        "arguments": proposed.get("arguments", {}),
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)


def _operation_signature(event: Any) -> str:
    """Describe the operation while ignoring non-semantic launch-mode churn."""
    proposed = _proposal(event)
    action = _effective_action(event)
    arguments = proposed.get("arguments", {})
    if not isinstance(arguments, dict):
        arguments = {}
    if action in {"command.run", "command.capture_output"}:
        _domain, _action, arguments = effective_canonical_action(event, "")
        arguments = {
            key: arguments[key] for key in ("argv", "stdout_path") if key in arguments
        }
    payload = {
        "kind": proposed.get("kind"),
        "action": action,
        "arguments": arguments,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)


def _result_signature(event: Any) -> str | None:
    value = getattr(event, "result", None)
    if not isinstance(value, dict):
        return None
    hint = value.get("context_hint")
    if not isinstance(hint, dict):
        return None
    if "downstream_context" in hint:
        downstream = hint.get("downstream_context")
        if not isinstance(downstream, dict):
            return None
        semantic = downstream
    else:
        semantic = hint
    if not semantic:
        return None
    payload = {"action": _effective_action(event), "context": semantic}
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)


def _changed_flag(value: Any) -> bool | None:
    if not isinstance(value, dict):
        return None
    changed = value.get("changed")
    if isinstance(changed, bool):
        return changed
    for key in (
        "context_hint",
        "downstream_context",
        "adapter_response",
        "result",
        "response",
    ):
        nested = _changed_flag(value.get(key))
        if nested is not None:
            return nested
    return None


def _is_meaningful_progress(
    event: Any,
    prior_request_signatures: set[str],
    prior_result_signatures: set[str],
    prior_operation_signatures: set[str],
) -> bool:
    if not bool(getattr(event, "executed", False)):
        return False
    proposed = _proposal(event)
    kind = proposed.get("kind")
    if kind == "gui":
        return _operation_signature(event) not in prior_operation_signatures
    if kind != "adapter":
        return False
    action = _effective_action(event)
    if not action_is_read_only(action):
        changed = _changed_flag(getattr(event, "result", None))
        if changed is not None:
            return changed
        return _operation_signature(event) not in prior_operation_signatures
    result_signature = _result_signature(event)
    if result_signature is not None:
        return result_signature not in prior_result_signatures
    return _request_signature(event) not in prior_request_signatures


def detect_no_progress_stall(
    events: Iterable[Any], *, window: int = 8
) -> dict[str, Any] | None:
    """Detect a no-progress loop within one retry, retaining earlier progress evidence."""
    if window < 4:
        raise ValueError("stall window must be at least 4 events")
    event_list = list(events)
    if len(event_list) < window:
        return None

    recent = event_list[-window:]
    retry = getattr(recent[-1], "retry", 0)
    # Past retries remain evidence, but cannot consume the restarted stall window.
    if any(getattr(event, "retry", 0) != retry for event in recent):
        return None
    prior_events = event_list[:-window]
    cycle_candidates = [
        event
        for event in recent
        if bool(getattr(event, "executed", False))
        and _proposal(event).get("kind") in {"adapter", "gui"}
        and (
            _proposal(event).get("kind") == "gui"
            or not action_is_read_only(_effective_action(event))
        )
        and _changed_flag(getattr(event, "result", None)) is not True
    ]
    cycle_operation_signatures = {
        _operation_signature(event) for event in cycle_candidates
    }
    repeated_successful_operation_cycle = (
        len(cycle_candidates) == window and 0 < len(cycle_operation_signatures) <= 2
    )
    prior_request_signatures = {
        _request_signature(event)
        for event in prior_events
        if bool(getattr(event, "executed", False))
        and _proposal(event).get("kind") == "adapter"
    }
    prior_result_signatures = {
        signature
        for event in prior_events
        if (signature := _result_signature(event)) is not None
    }
    prior_operation_signatures = {
        _operation_signature(event)
        for event in prior_events
        if bool(getattr(event, "executed", False))
        and _proposal(event).get("kind") in {"adapter", "gui"}
    }
    if not repeated_successful_operation_cycle and any(
        _is_meaningful_progress(
            event,
            prior_request_signatures,
            prior_result_signatures,
            prior_operation_signatures,
        )
        for event in recent
    ):
        return None

    searches = [event for event in recent if _proposal(event).get("kind") == "catalog"]
    failed_actions = [
        event
        for event in recent
        if _proposal(event).get("kind") in {"adapter", "gui"}
        and not bool(getattr(event, "executed", False))
    ]
    repeated_blocks = [
        event
        for event in failed_actions
        if isinstance(getattr(event, "error", None), dict)
        and getattr(event, "error").get("type") == "RepeatedActionBlocked"
    ]
    unchanged_mutations = [
        event
        for event in recent
        if bool(getattr(event, "executed", False))
        and _proposal(event).get("kind") == "adapter"
        and not action_is_read_only(_effective_action(event))
        and _changed_flag(getattr(event, "result", None)) is False
    ]
    search_signatures = {_request_signature(event) for event in searches}
    unchanged_signatures = {_request_signature(event) for event in unchanged_mutations}
    repeated_equivalent_reads = [
        event
        for event in recent
        if bool(getattr(event, "executed", False))
        and _proposal(event).get("kind") == "adapter"
        and action_is_read_only(_effective_action(event))
        and _result_signature(event) in prior_result_signatures
    ]
    equivalent_read_signatures = {
        signature
        for event in repeated_equivalent_reads
        if (signature := _result_signature(event)) is not None
    }
    repeated_successful_actions = [
        event
        for event in recent
        if bool(getattr(event, "executed", False))
        and _proposal(event).get("kind") in {"adapter", "gui"}
        and (
            _proposal(event).get("kind") == "gui"
            or not action_is_read_only(_effective_action(event))
        )
        and _changed_flag(getattr(event, "result", None)) is not True
        and _operation_signature(event) in prior_operation_signatures
    ]
    repeated_operation_signatures = {
        _operation_signature(event) for event in repeated_successful_actions
    }
    if repeated_successful_operation_cycle:
        repeated_successful_actions = cycle_candidates
        repeated_operation_signatures = cycle_operation_signatures

    reason = None
    if len(repeated_blocks) >= 3 and len(searches) >= 2:
        reason = "repeated_action_search_cycle"
    elif len(repeated_blocks) >= 4:
        reason = "repeated_action_rejection_cycle"
    elif (
        len(searches) >= 4 and len(search_signatures) <= 2 and len(failed_actions) >= 2
    ):
        reason = "repeated_catalog_search_cycle"
    elif len(unchanged_mutations) >= 4 and len(unchanged_signatures) <= 3:
        reason = "repeated_unchanged_mutation_cycle"
    elif len(repeated_equivalent_reads) >= 4 and len(equivalent_read_signatures) <= 3:
        reason = "repeated_equivalent_read_cycle"
    elif repeated_successful_operation_cycle or (
        len(repeated_successful_actions) >= 4
        and len(repeated_operation_signatures) <= 3
    ):
        reason = "repeated_successful_action_cycle"
    if reason is None:
        return None

    return {
        "type": "stalled_no_progress",
        "reason": reason,
        "window": window,
        "event_steps": [int(getattr(event, "step", 0)) for event in recent],
        "catalog_searches": len(searches),
        "distinct_catalog_searches": len(search_signatures),
        "failed_actions": len(failed_actions),
        "repeated_action_blocks": len(repeated_blocks),
        "unchanged_mutations": len(unchanged_mutations),
        "distinct_unchanged_mutations": len(unchanged_signatures),
        "repeated_equivalent_reads": len(repeated_equivalent_reads),
        "distinct_equivalent_read_results": len(equivalent_read_signatures),
        "repeated_successful_actions": len(repeated_successful_actions),
        "distinct_repeated_operations": len(repeated_operation_signatures),
    }
