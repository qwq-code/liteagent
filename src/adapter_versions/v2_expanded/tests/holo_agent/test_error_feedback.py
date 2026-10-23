from __future__ import annotations

import io
import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from integrations.holo_agent.grounding import (
    HoloGroundingAgent,
    HoloGroundingConfig,
    HoloGroundingError,
)
from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.state_model import RuntimeState


def test_holo_field_error_reaches_parent_without_invalid_value() -> None:
    sensitive_value = "synthetic-private-input"
    message = SimpleNamespace(
        tool_calls=[
            SimpleNamespace(
                id="synthetic-call",
                function=SimpleNamespace(
                    name="click",
                    arguments=json.dumps(
                        {"element": "Apply button", "x": [sensitive_value], "y": 430}
                    ),
                ),
            )
        ]
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
        model="holo3.1-4b",
    )
    requests: list[dict[str, Any]] = []

    def create(**request: Any) -> Any:
        requests.append(request)
        return response

    grounder = HoloGroundingAgent(
        HoloGroundingConfig(base_url="http://holo.invalid/v1"),
        client=SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    executions: list[dict[str, Any]] = []
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://qwen.invalid/v1"),
        SimpleNamespace(
            execute=lambda *_args, **_kwargs: pytest.fail("no Adapter expected")
        ),
        holo_grounder=grounder,
        gui_executor=lambda payload: executions.append(payload) or {"executed": True},
    )
    output = io.BytesIO()
    Image.new("RGB", (240, 180), "white").save(output, format="PNG")
    state = RuntimeState(
        task_id="host-only-synthetic-task",
        domain="os",
        instruction="Click the visible Apply button.",
    )
    event = agent.execute_proposal(
        state,
        {
            "tool": "gui_request",
            "arguments_raw": json.dumps({"intent": "Click the Apply button"}),
        },
        screenshot=output.getvalue(),
    )

    assert not event.executed
    assert len(requests) == 1
    assert executions == []
    detail = event.error["detail"]
    assert "x" in detail
    assert "integer" in detail
    assert sensitive_value not in detail
    next_messages = json.dumps(agent._messages(state, output.getvalue()))
    assert "type must be" in next_messages
    assert "integer" in next_messages
    assert sensitive_value not in next_messages

    message.tool_calls[0].function.arguments = json.dumps(
        {"element": "Apply button", "x": 516, "y": 430}
    )
    corrected = agent.execute_proposal(
        state,
        {
            "tool": "gui_request",
            "arguments_raw": json.dumps({"intent": "Click the Apply button"}),
        },
        screenshot=output.getvalue(),
    )
    assert corrected.executed
    assert len(requests) == 2
    assert len(executions) == 1
    feedback_request = json.dumps(requests[1])
    assert "x: type must be 'integer'" in feedback_request
    assert sensitive_value not in feedback_request
    assert requests[1]["tools"] == requests[0]["tools"]
    assert requests[1]["messages"][1] == requests[0]["messages"][1]


@pytest.mark.parametrize("change", ["none", "intent", "screenshot", "fallback", "contract"])
def test_holo_schema_feedback_follows_contract_for_one_request(change, monkeypatch) -> None:
    requests = []

    def create(**request):
        requests.append(request)
        call = SimpleNamespace(
            id="synthetic-call",
            function=SimpleNamespace(
                name="click",
                arguments=json.dumps(
                    {
                        "element": "Apply button",
                        "x": [516] if len(requests) == 1 else 516,
                        "y": 430,
                    }
                ),
            ),
        )
        return SimpleNamespace(
            model="holo3.1-4b",
            choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call]))],
        )

    grounder = HoloGroundingAgent(
        HoloGroundingConfig(base_url="http://holo.invalid/v1"),
        client=SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    output = io.BytesIO()
    Image.new("RGB", (240, 180), "white").save(output, format="PNG")
    screenshot = output.getvalue()
    intent = {"intent": "Click the Apply button"}
    with pytest.raises(HoloGroundingError, match="integer"):
        grounder.ground(screenshot, intent)
    assert len(requests) == 1
    if change == "intent":
        intent = {"intent": "Click the Cancel button"}
    elif change == "fallback":
        intent = {"intent": "Click the Apply button", "fallback_reason": "The visible dialog needs a click"}
    elif change == "screenshot":
        output = io.BytesIO()
        Image.new("RGB", (240, 180), "black").save(output, format="PNG")
        screenshot = output.getvalue()
    elif change == "contract":
        from integrations.holo_agent import grounding

        tools = deepcopy(grounding.HOLO_GROUNDING_TOOLS)
        tools[0]["function"]["description"] += " Synthetic updated contract."
        monkeypatch.setattr(grounding, "HOLO_GROUNDING_TOOLS", tools)
    result = grounder.ground(screenshot, intent)
    assert result["arguments"] == {"element": "Apply button", "x": 516, "y": 430}
    has_feedback = "x: type must be 'integer'" in json.dumps(requests[1])
    assert has_feedback is (change != "contract")
    assert (requests[1]["tools"] == requests[0]["tools"]) is (change != "contract")
    assert "Apply button" not in requests[1]["messages"][0]["content"]
    if change == "intent":
        assert "Cancel button" in json.dumps(requests[1]["messages"][1])
    if change == "fallback":
        assert intent["fallback_reason"] in json.dumps(requests[1]["messages"][1])
    if change == "screenshot":
        assert requests[1]["messages"][1]["content"][1] != requests[0]["messages"][1]["content"][1]
    grounder.ground(screenshot, intent)
    assert len(requests) == 3
    assert "type must be" not in json.dumps(requests[2])
