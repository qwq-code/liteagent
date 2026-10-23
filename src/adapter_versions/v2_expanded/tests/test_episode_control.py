from __future__ import annotations

from integrations.lite_agent.episode_control import (
    begin_same_vm_soft_restart,
    consume_terminal_audit,
    finalize_deferred_terminal,
    finalize_terminal_after_deadline,
    mark_tool_result_for_audit,
    record_model_audit,
    recovery_summary,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


def _state() -> RuntimeState:
    return RuntimeState(
        task_id="internal-task-id",
        domain="os",
        instruction="Inspect the current screen and complete the requested operation.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-30T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__filesystem_find",
                    "action": "filesystem.find",
                    "arguments": {"roots": ["/tmp"]},
                },
                executed=True,
                result={"context_hint": {"path": "/tmp/observed.txt"}},
            )
        ],
    )


def test_soft_restart_preserves_ledger_and_marks_same_vm_context() -> None:
    state = _state()
    events = state.events

    decision = begin_same_vm_soft_restart(
        state,
        "repeated_action_search_cycle",
        max_retries=1,
        trigger_step=1,
    )

    assert decision.accepted is True
    assert decision.preserve_vm is True
    assert decision.terminal is False
    assert state.events is events
    assert state.events[0].step == 1
    assert state.retry == 1
    assert state.local_step == 1
    assert state.pending_runner_replan == {
        "type": "same_vm_soft_restart",
        "reason": "repeated_action_search_cycle",
        "retry": 1,
        "preserve_vm": True,
    }
    assert state.recovery_context is not None
    assert state.recovery_context["preserved_vm"] is True
    assert "internal-task-id" not in str(state.recovery_context)


def test_soft_restart_is_bounded_without_mutating_state_on_exhaustion() -> None:
    state = _state()
    begin_same_vm_soft_restart(state, "first", max_retries=1)
    events = state.events
    second = begin_same_vm_soft_restart(state, "second", max_retries=1)

    assert second.accepted is False
    assert second.terminal is True
    assert second.retry == 1
    assert state.retry == 1
    assert state.events is events
    assert state.soft_restart_count == 1


def test_control_result_and_action_result_share_model_audit_transition() -> None:
    state = _state()
    control = ExecutionEvent(
        step=2,
        timestamp_utc="2026-08-30T00:00:00Z",
        proposed={
            "kind": "catalog",
            "tool": "tools_search",
            "arguments": {"query": "inspect"},
        },
        executed=True,
        result={"status": "ok", "matches": []},
    )
    state.events.append(control)

    pending = mark_tool_result_for_audit(state, control)
    assert pending["tool_class"] == "control"
    assert control.audit_required is True
    assert control.audit_completed is False
    assert state.pending_model_audit == pending

    audit = record_model_audit(state, {"tool": "adapter__filesystem_find"})
    assert audit is not None
    assert audit["event_step"] == 2
    assert control.audit_required is True
    assert control.audit_completed is True
    assert control.audit_tool == "adapter__filesystem_find"
    assert state.pending_model_audit is None

    action = ExecutionEvent(
        step=3,
        timestamp_utc="2026-08-30T00:00:00Z",
        proposed={
            "kind": "adapter",
            "tool": "adapter__filesystem_find",
            "action": "filesystem.find",
            "arguments": {},
        },
        executed=False,
        error={"type": "ValidationError"},
    )
    state.events.append(action)
    pending_action = mark_tool_result_for_audit(state, action)
    assert pending_action["tool_class"] == "action"
    assert record_model_audit(state, {"tool": "fail_task"})["event_step"] == 3


def test_deferred_terminal_commits_only_after_audit_and_never_executes_proposal() -> (
    None
):
    state = _state()
    terminal = ExecutionEvent(
        step=2,
        timestamp_utc="2026-08-30T00:00:00Z",
        proposed={
            "kind": "failure",
            "tool": "fail_task",
            "arguments": {"reason": "blocked"},
        },
        executed=True,
        result={"status": "failed", "executed": True},
    )
    state.events.append(terminal)
    state.defer_terminal_audit = True
    state.pending_terminal = {"status": "failed", "tool": "fail_task", "event_step": 2}
    mark_tool_result_for_audit(state, terminal)

    # A terminal result cannot be committed while its Qwen review is pending.
    assert finalize_deferred_terminal(state) is None
    assert state.done is False
    assert state.failed is False

    audit = record_model_audit(
        state, {"tool": "adapter__filesystem_find", "arguments": {"roots": ["/tmp"]}}
    )
    assert audit is not None
    finalized = finalize_deferred_terminal(state)
    assert finalized == {
        "status": "failed",
        "tool": "fail_task",
        "event_step": 2,
        "audit_only": True,
    }
    assert state.failed is True
    assert state.done is False
    assert state.pending_terminal is None
    # The audit proposal remains outside the event ledger and is never run.
    assert len(state.events) == 2


def test_terminal_deadline_fallback_commits_existing_control_without_new_tool() -> None:
    state = _state()
    terminal = ExecutionEvent(
        step=2,
        timestamp_utc="2026-08-30T00:00:00Z",
        proposed={"kind": "completion", "tool": "propose_done", "arguments": {}},
        executed=True,
        result={"status": "ok", "executed": True},
    )
    state.events.append(terminal)
    state.pending_terminal = {
        "status": "done",
        "tool": "propose_done",
        "event_step": terminal.step,
    }
    mark_tool_result_for_audit(state, terminal)

    result = finalize_terminal_after_deadline(state)

    assert result is not None
    assert result["audit_skipped"] is True
    assert state.done is True
    assert state.pending_terminal is None
    assert len(state.events) == 2


def test_consume_terminal_audit_confirms_without_creating_an_event() -> None:
    state = _state()
    terminal = ExecutionEvent(
        step=2,
        timestamp_utc="2026-08-30T00:00:00Z",
        proposed={"kind": "completion", "tool": "propose_done", "arguments": {}},
        executed=True,
        result={"status": "ok", "executed": True},
    )
    state.events.append(terminal)
    state.pending_terminal = {
        "status": "done",
        "tool": "propose_done",
        "event_step": terminal.step,
    }
    mark_tool_result_for_audit(state, terminal)
    event_count = len(state.events)

    result = consume_terminal_audit(state, {"tool": "propose_done"})

    assert result is not None
    assert result["confirmed"] is True
    assert result["terminal"]["audit_only"] is True
    assert state.done is True
    assert state.pending_terminal is None
    assert len(state.events) == event_count
    assert terminal.audit_completed is True


def test_consume_terminal_audit_allows_different_tool_to_continue() -> None:
    state = _state()
    terminal = ExecutionEvent(
        step=2,
        timestamp_utc="2026-08-30T00:00:00Z",
        proposed={"kind": "failure", "tool": "fail_task", "arguments": {}},
        executed=True,
        result={"status": "failed", "executed": True},
    )
    state.events.append(terminal)
    state.pending_terminal = {
        "status": "failed",
        "tool": "fail_task",
        "event_step": terminal.step,
    }
    mark_tool_result_for_audit(state, terminal)

    result = consume_terminal_audit(
        state,
        {"tool": "adapter__filesystem_find", "arguments": {"roots": ["~/tmp"]}},
    )

    assert result is not None
    assert result["confirmed"] is False
    assert result["terminal"] is None
    assert state.done is False
    assert state.failed is False
    assert state.pending_terminal is None
    assert terminal.audit_completed is True


def test_recovery_summary_uses_generic_projection_and_coarse_failure() -> None:
    state = _state()
    state.events.append(
        ExecutionEvent(
            step=2,
            timestamp_utc="2026-08-30T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__filesystem_find",
                "action": "filesystem.find",
                "arguments": {"roots": ["/secret"]},
            },
            executed=False,
            error={"type": "ValidationError", "detail": "secret details"},
        )
    )

    summary = recovery_summary(state, "repeated rejection", context_limit=2)

    assert summary["type"] == "same_vm_soft_restart"
    assert summary["preserved_vm"] is True
    assert summary["retained_event_count"] == 2
    assert len(summary["usable_observations"]) <= 2
    assert summary["last_failure"]["error_type"] == "ValidationError"
    assert "secret details" not in str(summary)
    assert "internal-task-id" not in str(summary)
