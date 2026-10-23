from __future__ import annotations

import json

import pytest

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.episode_control import (
    consume_terminal_audit,
    mark_tool_result_for_audit,
    record_model_audit,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


CLAIM = {"reason": "The document was saved.", "evidence": ["The save dialog closed."]}


class NoAdapter:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("A completion claim must not execute an Adapter")


def gui_state() -> RuntimeState:
    event = ExecutionEvent(
        step=1,
        timestamp_utc="2026-09-05T00:00:00Z",
        proposed={
            "kind": "gui",
            "tool": "gui_request",
            "delegation": "qwen_to_holo",
            "arguments": {"intent": "Click Save in the current dialog"},
            "gui_arguments": {"action": "click", "x": 200, "y": 300},
        },
        parsed=True,
        validated=True,
        executed=True,
        result={"environment_acknowledged": True},
        screenshot_after="synthetic_after.png",
    )
    state = RuntimeState(
        task_id="synthetic-gui-completion",
        domain="libreoffice_writer",
        instruction="Save the edited document.",
        events=[event],
        defer_terminal_audit=True,
    )
    mark_tool_result_for_audit(state, event)
    record_model_audit(state, {"tool": "propose_done"})
    return state


def adapter_event(action, arguments, *, domain="os") -> ExecutionEvent:
    return ExecutionEvent(
        step=2,
        timestamp_utc="2026-09-05T00:00:01Z",
        proposed={
            "kind": "adapter",
            "tool": "adapter__adapter_call",
            "action": "adapter.call",
            "arguments": {
                "adapter": domain,
                "action": action,
                "payload": {"params": arguments},
            },
        },
        executed=True,
        result={"status": "ok"},
    )


@pytest.mark.parametrize("review_tool", ["propose_done", "tools_search"])
@pytest.mark.parametrize("delegation", ["qwen_to_holo", "planner_to_holo"])
def test_audited_gui_claim_uses_existing_terminal_audit(review_tool, delegation) -> None:
    state = gui_state()
    state.events[0].proposed["delegation"] = delegation
    agent = LiteAgent(LiteAgentConfig(base_url="http://unused/v1"), NoAdapter())

    # Merely having a GUI result does not infer that task state is complete.
    assert not agent._generic_completion_gate(state)["passed"]
    event = agent.execute_proposal(
        state,
        {
            "tool": "propose_done",
            "arguments_raw": json.dumps(CLAIM),
            "finish_reason": "tool_calls",
        },
    )

    assert event.executed is True
    assert state.done is False
    assert state.pending_terminal["event_step"] == event.step
    assert len(state.events) == 2
    mark_tool_result_for_audit(state, event)
    resolution = consume_terminal_audit(state, {"tool": review_tool})
    assert resolution["confirmed"] is (review_tool == "propose_done")
    assert state.done is (review_tool == "propose_done")
    assert len(state.events) == 2


@pytest.mark.parametrize(
    ("action", "arguments"),
    [
        ("command.run", {"argv": ["ls", "/tmp/output.txt"]}),
        ("filesystem.find", {"roots": ["/tmp"], "name_patterns": ["output.txt"]}),
    ],
)
def test_read_only_adapter_verification_preserves_gui_completion(
    action, arguments
) -> None:
    state = gui_state()
    state.events.append(adapter_event(action, arguments))
    mark_tool_result_for_audit(state, state.events[-1])
    record_model_audit(state, {"tool": "propose_done"})

    assert CompletionMixin._generic_completion_gate(state, CLAIM)["passed"] is True


def test_gui_save_after_adapter_edit_does_not_require_an_api_save() -> None:
    state = gui_state()
    gui = state.events[0]
    edit = adapter_event(
        "filesystem.copy", {"source": "/tmp/a", "destination": "/tmp/b"}
    )
    edit.step = 1
    gui.step = 2
    state.events = [edit, gui]
    mark_tool_result_for_audit(state, gui)
    record_model_audit(state, {"tool": "propose_done"})

    assert CompletionMixin._generic_completion_gate(state, CLAIM)["passed"] is True


@pytest.mark.parametrize(
    ("domain", "action"),
    [
        ("libreoffice_writer", "document.save"),
        ("libreoffice_impress", "presentation.save"),
        ("libreoffice_calc", "workbook.save"),
    ],
)
@pytest.mark.parametrize("routed", [False, True])
def test_api_save_preserves_audited_gui_work(domain, action, routed) -> None:
    state = gui_state()
    state.domain = "multi_apps" if routed else domain
    save = adapter_event(action, {})
    if routed:
        save.proposed["arguments"]["adapter"] = domain
    else:
        save.proposed = {"kind": "adapter", "action": action, "arguments": {}}
    state.events.append(save)
    mark_tool_result_for_audit(state, save)
    record_model_audit(state, {"tool": "propose_done"})

    assert CompletionMixin._generic_completion_gate(state, CLAIM) == {
        "passed": True,
        "missing": [],
        "evidence_source": "audited_holo_gui",
    }
    assert not state.done
    assert not CompletionMixin._generic_completion_gate(state)["passed"]
    state.events.pop(0)
    assert not CompletionMixin._generic_completion_gate(state, CLAIM)["passed"]


@pytest.mark.parametrize(
    ("domain", "action", "arguments"),
    [
        ("os", "filesystem.copy", {"source": "/tmp/a", "destination": "/tmp/b"}),
        ("os", "command.run", {"argv": ["cat", "/tmp/a"], "stdout_path": "/tmp/b"}),
        (
            "libreoffice_calc",
            "workbook.export",
            {"format": "pdf", "url": "file:///tmp/export.pdf"},
        ),
    ],
)
def test_later_adapter_write_keeps_normal_api_completion_checks(
    domain, action, arguments
) -> None:
    state = gui_state()
    state.events.append(adapter_event(action, arguments, domain=domain))
    with_gui = CompletionMixin._generic_completion_gate(state, CLAIM)
    state.events.pop(0)

    assert with_gui == CompletionMixin._generic_completion_gate(state, CLAIM)
    assert not with_gui["passed"]


@pytest.mark.parametrize(
    "unusable", ["unexecuted", "unaudited", "legacy_gui", "no_terminal_audit"]
)
def test_unusable_gui_record_does_not_replace_api_evidence(unusable) -> None:
    state = gui_state()
    if unusable == "unexecuted":
        state.events[0].executed = False
    elif unusable == "unaudited":
        mark_tool_result_for_audit(state, state.events[0])
    elif unusable == "legacy_gui":
        state.events[0].proposed.pop("delegation")
    else:
        state.defer_terminal_audit = False

    assert not CompletionMixin._generic_completion_gate(state, CLAIM)["passed"]


@pytest.mark.parametrize(
    "claim",
    [
        {"reason": "Saved"},
        {
            "reason": "The task is not complete.",
            "evidence": ["Unsaved changes remain."],
        },
    ],
)
def test_gui_completion_preserves_claim_validation(claim) -> None:
    assert not CompletionMixin._generic_completion_gate(gui_state(), claim)["passed"]


def test_gui_completion_preserves_incomplete_response_rejection() -> None:
    state = gui_state()
    agent = LiteAgent(LiteAgentConfig(base_url="http://unused/v1"), NoAdapter())
    event = agent.execute_proposal(
        state,
        {
            "tool": "propose_done",
            "arguments_raw": json.dumps(CLAIM),
            "finish_reason": "length",
        },
    )

    assert not event.executed
    assert state.pending_terminal is None
    assert not state.done


def test_hybrid_prompt_distinguishes_visual_readback_from_execution_acknowledgement() -> (
    None
):
    state = gui_state()
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        NoAdapter(),
        holo_grounder=lambda *_args: None,
    )
    hybrid = agent._system_message(state)
    agent.holo_grounder = None
    api = agent._system_message(state)

    assert "executed=true confirms the input ran, not that" in hybrid
    assert "Do not repeat a GUI change through an Adapter" in hybrid
    assert "non-active worksheet" in hybrid
    assert "one structural inspect call" in hybrid
    assert "call the inspection tool first" in hybrid
    assert "structurally inspect the result after the final mutation" in api
    assert "Do not repeat a GUI change through an Adapter" not in api


@pytest.mark.parametrize(
    ("domain", "instruction"),
    [
        ("libreoffice_impress", "Use the built-in Slide Sorter to review this deck."),
        ("thunderbird", "Use the built-in Message Filters to organize incoming mail."),
    ],
)
def test_named_native_feature_guidance_does_not_select_a_command(
    domain: str, instruction: str
) -> None:
    state = RuntimeState(
        task_id="synthetic-native-feature",
        domain=domain,
        instruction=instruction,
    )
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        NoAdapter(),
        holo_grounder=lambda *_args: None,
    )

    prompt = agent._system_message(state)

    assert "When the user explicitly names a built-in application feature" in prompt
    assert "not a similar-looking result assembled with unrelated edits" in prompt
    assert "use the GUI to find its native command" in prompt
    assert "GUI changes can invalidate earlier inspection results" in prompt
    assert "use an available structural inspection to read its current contents" in prompt
    assert "a placeholder does not mean the whole object is blank" in prompt
    assert "Slide Sorter" not in prompt
    assert "Message Filters" not in prompt
    assert state.events == []
