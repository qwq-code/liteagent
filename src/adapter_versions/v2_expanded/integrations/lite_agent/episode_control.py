"""Generic episode control transitions for the LiteAgent Runner.

This module deliberately contains no VM or Adapter calls.  It records the
boundary between a model-selected Tool result and the next model audit, and
describes an in-episode recovery as a *soft* restart.  A soft restart only
rebuilds model-facing context; the VM, task goal, event ledger, and durable
observations remain untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .completion_policy import (
    action_is_read_only,
    action_is_save,
    effective_canonical_action,
)
from .recovery_surface import last_failure_summary


CONTROL_TOOL_NAMES = frozenset({"tools_search", "propose_done", "fail_task"})
_MUTATION_LEDGER_LIMIT = 32
_MUTATION_ARGUMENT_BUDGET = 900
# Keep the restart handoff for three model decisions after the first audited
# proposal.  The first proposal is the audit of the triggering event itself.
_RECOVERY_PROJECTION_FOLLOWUP_TURNS = 3


@dataclass(frozen=True)
class SoftRestartDecision:
    """Result of asking the episode controller for an in-place recovery."""

    accepted: bool
    reason: str
    retry: int
    local_step: int
    summary: dict[str, Any]
    preserve_vm: bool = True
    terminal: bool = False


def _proposal(event: Any) -> dict[str, Any]:
    value = getattr(event, "proposed", None)
    return value if isinstance(value, dict) else {}


def _tool_name(event: Any) -> str:
    proposed = _proposal(event)
    value = proposed.get("tool") or proposed.get("action")
    return str(value) if value is not None else "unknown"


def _bounded_reason(reason: Any) -> str:
    """Keep runner-generated labels short and independent of task identity."""
    text = str(reason or "no_progress").strip()
    # Reasons originate from the generic stall policy.  Do not carry free-form
    # exception text, paths, UUIDs, or model content into the recovery prompt.
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-"
    text = "".join(character if character in allowed else "_" for character in text)
    return text[:96] or "no_progress"


def _bounded_context(state: Any, *, limit: int) -> list[dict[str, Any]]:
    """Read only the existing strict model projection from RuntimeState."""
    if limit <= 0:
        return []
    summary = getattr(state, "context_summary", None)
    if not callable(summary):
        return []
    try:
        value = summary(limit=limit, strict_generic=True)
    except TypeError:
        # Keep the helper usable by small test doubles that expose the older
        # context_summary signature.
        value = summary(limit=limit)
    if not isinstance(value, list):
        return []
    return [_coarse_context_item(item) for item in value if isinstance(item, dict)]


def _coarse_context_item(value: dict[str, Any]) -> dict[str, Any]:
    """Remove raw failure text while retaining observed result structure."""
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key == "error":
            if isinstance(item, dict):
                result[key] = {
                    nested_key: item[nested_key]
                    for nested_key in ("type", "code", "status")
                    if nested_key in item
                }
            continue
        if isinstance(item, dict):
            result[key] = _coarse_context_item(item)
        elif isinstance(item, list):
            result[key] = [
                _coarse_context_item(nested) if isinstance(nested, dict) else nested
                for nested in item
            ]
        else:
            result[key] = item
    return result


def _recovery_projection_active(state: Any) -> bool:
    recovery = getattr(state, "recovery_context", None)
    remaining = getattr(state, "recovery_projection_turns_remaining", 0)
    return (
        isinstance(recovery, dict)
        and isinstance(remaining, int)
        and not isinstance(remaining, bool)
        and remaining > 0
    )


def _clear_recovery_projection(state: Any) -> None:
    setattr(state, "recovery_context", None)
    setattr(state, "recovery_projection_turns_remaining", 0)
    setattr(state, "recovery_projection_initial_audit_pending", False)


def _refresh_recovery_projection(state: Any) -> None:
    """Refresh only the bounded model-facing ledger after a new event."""
    if not _recovery_projection_active(state):
        return
    recovery = getattr(state, "recovery_context", None)
    if not isinstance(recovery, dict):
        return
    refreshed = dict(recovery)
    mutation_ledger = successful_mutation_ledger(state)
    if mutation_ledger:
        refreshed["successful_mutation_ledger"] = mutation_ledger
    else:
        refreshed.pop("successful_mutation_ledger", None)
    # Copy-on-write keeps the immutable recovery history/result snapshot intact.
    setattr(state, "recovery_context", refreshed)


def successful_mutation_ledger(
    state: Any, *, limit: int = _MUTATION_LEDGER_LIMIT
) -> list[dict[str, Any]]:
    """Project successful model-selected mutations for a recovery handoff.

    This is deliberately a *model-facing* projection.  The complete event
    ledger remains authoritative for completion and matching; this helper only
    keeps enough bounded action history for a replan after transient context
    compaction.  Read-only probes, persistence actions, GUI events, and failed
    calls are omitted so the projection cannot masquerade as task completion.
    """
    if limit <= 0:
        return []
    # Importing these helpers lazily keeps episode control independent from the
    # broader context projection module during RuntimeState construction.
    from .context_projection import _fit, safe_action, sanitize

    entries: list[dict[str, Any]] = []
    for event in list(getattr(state, "events", ()) or ()):
        if not bool(getattr(event, "executed", False)):
            continue
        proposed = _proposal(event)
        if proposed.get("kind") != "adapter":
            continue
        raw_action = proposed.get("action")
        if not isinstance(raw_action, str) or not raw_action:
            continue
        _canonical_domain, canonical_action, _canonical_arguments = (
            effective_canonical_action(event, getattr(state, "domain", ""))
        )
        if (
            not canonical_action
            or action_is_read_only(canonical_action)
            or action_is_save(canonical_action)
        ):
            continue
        arguments = _fit(
            sanitize(proposed.get("arguments", {})),
            _MUTATION_ARGUMENT_BUDGET,
        )
        if not isinstance(arguments, dict):
            arguments = {}
        entry: dict[str, Any] = {
            "action": safe_action(raw_action),
            "arguments": arguments,
        }
        step = getattr(event, "step", None)
        if isinstance(step, int) and not isinstance(step, bool):
            entry["step"] = step
        entries.append(entry)
    return entries[-limit:]


def recovery_summary(
    state: Any,
    reason: str,
    *,
    trigger_step: int | None = None,
    context_limit: int = 8,
) -> dict[str, Any]:
    """Build a bounded, task-independent summary for a soft restart.

    The summary reuses the same sanitized projection used in ordinary model
    messages.  It intentionally omits task IDs and raw errors while retaining
    successful action observations and a coarse latest failure category.
    """
    events = list(getattr(state, "events", ()) or ())
    successful = sum(1 for event in events if bool(getattr(event, "executed", False)))
    summary: dict[str, Any] = {
        "type": "same_vm_soft_restart",
        "reason": _bounded_reason(reason),
        "trigger_step": (
            int(trigger_step)
            if isinstance(trigger_step, int) and not isinstance(trigger_step, bool)
            else (int(getattr(events[-1], "step", 0)) if events else 0)
        ),
        "retained_event_count": len(events),
        "retained_executed_event_count": successful,
        "preserved_vm": True,
        "usable_observations": _bounded_context(state, limit=context_limit),
    }
    mutation_ledger = successful_mutation_ledger(state)
    if mutation_ledger:
        summary["successful_mutation_ledger"] = mutation_ledger
    failure = last_failure_summary(state)
    if isinstance(failure, dict):
        # ``last_failure_summary`` is already a strict coarse projection.  Keep
        # only stable fields so a nested Adapter body cannot leak through.
        summary["last_failure"] = {
            key: failure[key]
            for key in ("action", "error_type", "argument_fields")
            if key in failure
        }
    return summary


def mark_tool_result_for_audit(state: Any, event: Any) -> dict[str, Any]:
    """Mark every executed/rejected Tool result as awaiting model audit.

    Control Tools and application Tools share this transition.  The Runner
    must call :func:`record_model_audit` only after the next Qwen response has
    been accepted as one complete structured call.
    """
    step = getattr(event, "step", None)
    step_value = (
        int(step) if isinstance(step, int) and not isinstance(step, bool) else None
    )
    tool = _tool_name(event)
    is_control = tool in CONTROL_TOOL_NAMES
    if hasattr(event, "audit_required"):
        event.audit_required = True
    if hasattr(event, "audit_completed"):
        event.audit_completed = False
    if hasattr(event, "audit_tool"):
        event.audit_tool = None
    pending = {
        "event_step": step_value,
        "tool": tool,
        "tool_class": "control" if is_control else "action",
        "status": "pending",
    }
    setattr(state, "pending_model_audit", pending)
    _refresh_recovery_projection(state)
    return pending


def record_model_audit(state: Any, proposal: Any) -> dict[str, Any] | None:
    """Complete the pending audit when Qwen returns the next valid call.

    A transport/protocol failure does not consume the audit marker.  This
    lets the Runner retry with the same truthful result without pretending it
    was reviewed.
    """
    pending = getattr(state, "pending_model_audit", None)
    if not isinstance(pending, dict):
        return None
    tool = proposal.get("tool") if isinstance(proposal, dict) else None
    tool = str(tool) if tool is not None else "unknown"
    event_step = pending.get("event_step")
    event = next(
        (
            candidate
            for candidate in reversed(list(getattr(state, "events", ()) or ()))
            if getattr(candidate, "step", None) == event_step
        ),
        None,
    )
    if event is not None:
        if hasattr(event, "audit_required"):
            event.audit_required = True
        if hasattr(event, "audit_completed"):
            event.audit_completed = True
        if hasattr(event, "audit_tool"):
            event.audit_tool = tool
    audit = {
        "event_step": event_step,
        "review_tool": tool,
        "tool_class": pending.get("tool_class", "action"),
        "status": "completed",
    }
    setattr(state, "last_model_audit", audit)
    setattr(state, "pending_model_audit", None)
    recovery = getattr(state, "recovery_context", None)
    if isinstance(recovery, dict):
        # The first post-restart proposal audits the triggering event.  Keep
        # the handoff for the bounded follow-up window; transport failures do
        # not reach this function and therefore do not consume the window.
        initial_audit_pending = bool(
            getattr(state, "recovery_projection_initial_audit_pending", False)
        )
        if initial_audit_pending:
            setattr(state, "recovery_projection_initial_audit_pending", False)
        else:
            remaining = getattr(state, "recovery_projection_turns_remaining", 0)
            if (
                not isinstance(remaining, int)
                or isinstance(remaining, bool)
                or remaining <= 1
            ):
                _clear_recovery_projection(state)
            else:
                setattr(state, "recovery_projection_turns_remaining", remaining - 1)
    return audit


def finalize_deferred_terminal(state: Any) -> dict[str, Any] | None:
    """Commit a terminal control result after its model audit completed.

    The terminal Tool itself is executed exactly once by the normal Runner
    path.  This transition only changes episode bookkeeping; it never
    executes (or validates) the proposal returned by the audit turn.  A
    pending model audit therefore prevents accidental early termination.
    """
    pending = getattr(state, "pending_terminal", None)
    if not isinstance(pending, dict):
        return None
    if isinstance(getattr(state, "pending_model_audit", None), dict):
        return None
    status = pending.get("status")
    if status not in {"done", "failed"}:
        return None
    state.done = status == "done"
    state.failed = status == "failed"
    state.pending_terminal = None
    # This flag means the deferred result was reviewed, not that the audit
    # proposal selected the same control tool.
    state.terminal_confirmation = True
    return {
        "status": status,
        "tool": pending.get("tool"),
        "event_step": pending.get("event_step"),
        "audit_only": True,
    }


def finalize_terminal_after_deadline(state: Any) -> dict[str, Any] | None:
    """Commit an already accepted terminal result when its audit turn times out.

    This is a bounded Runner fallback for an episode that has no time left for
    another model request. It never accepts a new tool or changes arguments;
    it only prevents a passed terminal control from becoming a deadline failure
    because the redundant review call could not start or finish.
    """
    pending = getattr(state, "pending_terminal", None)
    if not isinstance(pending, dict):
        return None
    if pending.get("tool") not in {"propose_done", "fail_task"}:
        return None
    setattr(state, "pending_model_audit", None)
    terminal = finalize_deferred_terminal(state)
    if terminal is None:
        return None
    terminal["audit_only"] = True
    terminal["audit_skipped"] = True
    terminal["audit_skip_reason"] = "episode_deadline"
    return terminal


def resolve_terminal_audit(state: Any, proposal: Any) -> bool:
    """Resolve a deferred terminal result from the bounded audit turn.

    Selecting the same terminal control confirms the already-recorded result;
    the Runner can then finalize it without executing a second terminal Tool.
    Selecting a different Tool cancels the pending terminal marker and hands
    that model-selected proposal back to the ordinary execution path.  The
    helper never supplies or rewrites arguments.
    """
    pending = getattr(state, "pending_terminal", None)
    if not isinstance(pending, dict):
        return False
    selected = proposal.get("tool") if isinstance(proposal, dict) else None
    selected = str(selected) if selected is not None else "unknown"
    expected = str(pending.get("tool", ""))
    confirmed = selected == expected and expected in {"propose_done", "fail_task"}
    setattr(state, "terminal_confirmation", confirmed)
    setattr(state, "terminal_audit_tool", selected)
    if not confirmed:
        setattr(state, "pending_terminal", None)
    return confirmed


def consume_terminal_audit(state: Any, proposal: Any) -> dict[str, Any] | None:
    """Consume the one model turn reserved to audit a terminal Tool result.

    If the model confirms the same terminal control, the result is committed
    without a second terminal event.  If it selects a different Tool, the
    pending terminal is cancelled and the caller may execute that model-owned
    proposal through the normal one-tool-per-turn path.
    """
    if not isinstance(getattr(state, "pending_terminal", None), dict):
        return None
    audit = record_model_audit(state, proposal)
    if audit is None:
        # A pending terminal without its corresponding Tool-result marker is
        # an invariant violation.  Leave it untouched so the caller can fail
        # closed instead of silently terminating an unaudited episode.
        return None
    confirmed = resolve_terminal_audit(state, proposal)
    terminal = finalize_deferred_terminal(state) if confirmed else None
    return {
        "audit": audit,
        "confirmed": confirmed,
        "terminal": terminal,
    }


def begin_same_vm_soft_restart(
    state: Any,
    reason: str,
    *,
    max_retries: int = 1,
    trigger_step: int | None = None,
    context_limit: int = 8,
) -> SoftRestartDecision:
    """Request an in-place replan without resetting or recreating the VM."""
    if max_retries < 0:
        raise ValueError("max_retries must be nonnegative")
    retry = getattr(state, "retry", None)
    if not isinstance(retry, int) or isinstance(retry, bool):
        retry = int(getattr(state, "runner_replans_requested", 0) or 0)
    summary = recovery_summary(
        state,
        reason,
        trigger_step=trigger_step,
        context_limit=context_limit,
    )
    if retry >= max_retries:
        return SoftRestartDecision(
            accepted=False,
            reason=_bounded_reason(reason),
            retry=retry,
            local_step=int(getattr(state, "local_step", 1) or 1),
            summary=summary,
            terminal=True,
        )

    retry += 1
    setattr(state, "retry", retry)
    # Preserve the historical counter for old result readers and tests.
    setattr(state, "runner_replans_requested", retry)
    setattr(state, "local_step", 1)
    setattr(
        state,
        "soft_restart_count",
        int(getattr(state, "soft_restart_count", 0) or 0) + 1,
    )
    summary["retry"] = retry
    state.pending_runner_replan = {
        "type": "same_vm_soft_restart",
        "reason": summary["reason"],
        "retry": retry,
        "preserve_vm": True,
    }
    setattr(
        state,
        "recovery_projection_turns_remaining",
        _RECOVERY_PROJECTION_FOLLOWUP_TURNS,
    )
    setattr(state, "recovery_projection_initial_audit_pending", True)
    setattr(state, "recovery_context", summary)
    history = getattr(state, "recovery_history", None)
    if not isinstance(history, list):
        history = []
        setattr(state, "recovery_history", history)
    history.append(summary)
    # Keep the history itself bounded; the event ledger is the durable record.
    del history[:-8]
    return SoftRestartDecision(
        accepted=True,
        reason=summary["reason"],
        retry=retry,
        local_step=1,
        summary=summary,
    )


def advance_local_step(state: Any) -> int:
    """Advance the local turn counter while preserving the global event step."""
    current = getattr(state, "local_step", 1)
    if not isinstance(current, int) or isinstance(current, bool) or current < 1:
        current = 1
    current += 1
    setattr(state, "local_step", current)
    return current


__all__ = [
    "CONTROL_TOOL_NAMES",
    "SoftRestartDecision",
    "advance_local_step",
    "begin_same_vm_soft_restart",
    "mark_tool_result_for_audit",
    "record_model_audit",
    "finalize_deferred_terminal",
    "resolve_terminal_audit",
    "consume_terminal_audit",
    "recovery_summary",
    "successful_mutation_ledger",
]
