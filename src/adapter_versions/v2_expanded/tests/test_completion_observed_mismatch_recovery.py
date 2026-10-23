from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.completion_policy import (
    COMPLETION_RECOVERY_READBACK_ONLY,
    COMPLETION_RECOVERY_TASK_STATE,
    classify_completion_recovery,
)
from integrations.lite_agent.generic_completion import _requires_readback
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


@pytest.mark.parametrize(
    "requirement,expected",
    [
        ("perform structural read-back after the final mutation", True),
        ("read back the observed title formatting after saving the presentation", True),
        ("save and structurally read back the final document", True),
        (
            "the final structural read-back does not show every requested title "
            "format property on the observed title shape",
            False,
        ),
    ],
)
def test_missing_observation_and_observed_mismatch_choose_different_recovery(
    requirement, expected,
):
    assert _requires_readback(requirement) is expected
    assert classify_completion_recovery([requirement], []) == (
        COMPLETION_RECOVERY_READBACK_ONLY if expected else COMPLETION_RECOVERY_TASK_STATE
    )


def _event(step, action, arguments, result):
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-09-13T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": arguments},
        executed=True,
        result=result,
    )


def _inspection(weight):
    return {
        "context_hint": {
            "slides": [{
                "slide": 2,
                "text_shapes": [{
                    "path": [0],
                    "index": 0,
                    "name": "Heading",
                    "kind": "com.sun.star.presentation.TitleTextShape",
                    "lines": ["Research Overview"],
                    "text_style": {"bold_weight": weight},
                }],
            }],
        },
    }


class RecordingExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, domain, action, arguments, _metadata):
        self.calls.append((domain, action, deepcopy(arguments)))
        return {
            "executed": True,
            "result": {"properties": {"CharWeight": "150.0"}},
        }


def test_wrong_title_readback_restores_repair_and_identical_call_can_execute():
    arguments = {"slide": 2, "selector": {"path": [0]}, "bold": True}
    state = RuntimeState(
        task_id="synthetic-observed-format-repair",
        domain="libreoffice_impress",
        instruction="Make the title on slide 3 bold.",
        completion_rejections=1,
        events=[
            _event(1, "presentation.inspect", {"slides": [2]}, _inspection(100.0)),
            _event(2, "shape.format_text", arguments, {"properties": {"CharWeight": "150.0"}}),
            _event(3, "presentation.save", {}, {"status": "ok"}),
            _event(4, "presentation.inspect", {"slides": [2]}, _inspection(100.0)),
        ],
    )
    executor = RecordingExecutor()
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
        executor,
        model_client=SimpleNamespace(client=object()),
    )
    gate = agent._generic_completion_gate(state)
    assert not gate["passed"]
    assert any("does not show" in item for item in gate["missing"])

    tools = agent.tools(state)
    names = {tool["function"]["name"] for tool in tools}
    assert "adapter__shape_format_text" in names
    assert "tools_search" in names
    event = agent.execute_proposal(state, {
        "tool": "adapter__shape_format_text",
        "arguments_raw": json.dumps(arguments),
        "_model_visible_tools": tools,
    })
    assert event.executed, event.error
    assert executor.calls == [(state.domain, "shape.format_text", arguments)]
    assert event.proposed["arguments"] == arguments

    state.events.extend([
        _event(6, "presentation.save", {}, {"status": "ok"}),
        _event(7, "presentation.inspect", {"slides": [2]}, _inspection(150.0)),
    ])
    assert agent._generic_completion_gate(state) == {"passed": True, "missing": []}
