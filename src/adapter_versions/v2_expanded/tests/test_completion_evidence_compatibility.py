from __future__ import annotations

from copy import deepcopy
import json

import pytest

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.episode_control import (
    mark_tool_result_for_audit,
    record_model_audit,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


class NoAdapter:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("Completion must not execute an application action")


def _adapter_event(step, action, params, result=None):
    return ExecutionEvent(
        step=step,
        timestamp_utc="2032-06-07T00:00:00Z",
        proposed={
            "kind": "adapter",
            "tool": "adapter__adapter_call",
            "action": "adapter.call",
            "arguments": {
                "adapter": "libreoffice_calc",
                "action": action,
                "payload": {"params": params},
            },
        },
        parsed=True,
        validated=True,
        executed=True,
        result=result if result is not None else {"status": "ok"},
    )


def _workbook_events():
    return [
        _adapter_event(
            1, "range.write",
            {"sheet": "Observations", "range": "E8", "values": [[{"kind": "number", "value": 17}]]},
        ),
        _adapter_event(
            2, "workbook.save", {},
            {
                "status": "ok",
                "result": {"url": "file:///tmp/observations.xlsx", "size": 2048},
                "verification": {"passed": True},
            },
        ),
        _adapter_event(
            3, "workbook.inspect", {},
            {
                "status": "ok",
                "result": {"url": "file:///tmp/observations.xlsx", "modified": False},
                "verification": {"passed": True},
            },
        ),
    ]


def _workbook_state(events):
    return RuntimeState(
        task_id="synthetic-evidence-compatibility",
        domain="multi_apps",
        instruction="Update the current workbook and keep the change.",
        events=events,
    )


def _claim(evidence):
    return {"reason": "The workbook update is complete.", "evidence": evidence}


def test_string_and_array_evidence_require_the_same_recorded_work():
    statement = "The updated workbook was saved and inspected."
    state = _workbook_state([])

    def gate_for_both_forms():
        string_claim = _claim(statement)
        array_claim = _claim([statement])
        before = deepcopy((string_claim, array_claim, state.events))
        string_gate = CompletionMixin._generic_completion_gate(state, string_claim)
        array_gate = CompletionMixin._generic_completion_gate(state, array_claim)
        assert string_gate == array_gate
        assert (string_claim, array_claim, state.events) == before
        return string_gate

    assert not gate_for_both_forms()["passed"]
    mutation, save, readback = _workbook_events()
    state.events.append(mutation)
    missing = gate_for_both_forms()["missing"]
    assert any("save" in item for item in missing)
    assert any("read-back" in item for item in missing)

    state.events.append(save)
    gate = gate_for_both_forms()
    assert not gate["passed"]
    assert gate["missing"] == ["perform structural read-back after the final mutation"]

    state.events.append(readback)
    assert gate_for_both_forms() == {"passed": True, "missing": []}


def _audited_gui_state():
    event = ExecutionEvent(
        step=1,
        timestamp_utc="2032-06-07T00:00:00Z",
        proposed={
            "kind": "gui",
            "tool": "gui_request",
            "delegation": "planner_to_holo",
            "arguments": {"intent": "Click Save in the active document dialog"},
        },
        parsed=True,
        validated=True,
        executed=True,
        result={"environment_acknowledged": True},
        screenshot_after="synthetic-evidence-after.png",
    )
    state = RuntimeState(
        task_id="synthetic-gui-evidence-compatibility",
        domain="libreoffice_writer",
        instruction="Save the edited document.",
        events=[event],
        defer_terminal_audit=True,
    )
    mark_tool_result_for_audit(state, event)
    record_model_audit(state, {"tool": "propose_done"})
    return state


@pytest.mark.parametrize("gui", [False, True])
def test_string_evidence_alone_cannot_hide_an_incomplete_claim(gui):
    state = _audited_gui_state() if gui else _workbook_state(_workbook_events())
    assert CompletionMixin._generic_completion_gate(
        state, _claim("The requested changes were saved and inspected.")
    )["passed"]

    claim = _claim("The task is not complete.")
    before = deepcopy(claim)
    gate = CompletionMixin._generic_completion_gate(state, claim)

    assert not gate["passed"]
    assert "the completion claim says the task is not complete" in gate["missing"]
    assert claim == before

    agent = LiteAgent(LiteAgentConfig(base_url="http://unused/v1"), NoAdapter())
    raw = json.dumps(claim)
    proposal = {
        "tool": "propose_done", "arguments_raw": raw, "finish_reason": "tool_calls",
    }
    prior_events = deepcopy(state.events)
    event = agent.execute_proposal(state, proposal)

    assert not event.executed
    assert not state.done
    assert event.proposed["arguments_raw"] == raw
    assert event.proposed["arguments"] == before
    assert event.error["missing"] == gate["missing"]
    assert event.error["recovery"]["mode"] == "task_state"
    assert "unfinished task state" in event.error["recovery"]["guidance"]
    assert "state already satisfies" not in event.error["recovery"]["guidance"]
    assert state.events[:-1] == prior_events


def test_format_only_completion_recovery_still_requires_only_a_valid_claim():
    state = _workbook_state(_workbook_events())
    agent = LiteAgent(LiteAgentConfig(base_url="http://unused/v1"), NoAdapter())
    claim = _claim([])
    raw = json.dumps(claim)
    event = agent.execute_proposal(
        state,
        {"tool": "propose_done", "arguments_raw": raw, "finish_reason": "tool_calls"},
    )

    assert not event.executed
    assert not state.done
    assert event.proposed["arguments_raw"] == raw
    assert event.proposed["arguments"] == claim
    assert event.error["recovery"]["mode"] == "claim_only"


@pytest.mark.parametrize(
    "evidence",
    [
        "The saved workbook was inspected.",
        '[{"statement": "The saved workbook was inspected."}]',
        '["The saved workbook was inspected.",]',
    ],
)
def test_execution_preserves_opaque_evidence_and_raw_proposal(evidence):
    state = _workbook_state(_workbook_events())
    agent = LiteAgent(LiteAgentConfig(base_url="http://unused/v1"), NoAdapter())
    arguments = _claim(evidence)
    raw = json.dumps(arguments, indent=2)
    proposal = {
        "tool": "propose_done",
        "arguments_raw": raw,
        "finish_reason": "tool_calls",
    }
    original = deepcopy(proposal)
    prior_events = deepcopy(state.events)

    event = agent.execute_proposal(state, proposal)

    assert event.executed
    assert state.done
    assert event.proposed["arguments_raw"] == raw
    assert event.proposed["arguments"] == arguments
    assert isinstance(event.proposed["arguments"]["evidence"], str)
    assert event.proposed["arguments"]["evidence"] == evidence
    assert proposal == original
    assert state.events[:-1] == prior_events
