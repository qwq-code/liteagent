from __future__ import annotations

import copy
import hashlib
import io
import json
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from integrations.holo_agent.gateway import HoloGuiGateway, HoloGuiGatewayError
from integrations.holo_agent.grounding import (
    HoloGroundingAgent,
    HoloGroundingConfig,
    HoloGroundingError,
)
from integrations.holo_agent.tools import HOLO_GROUNDING_TOOLS
from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.context_projection import summarize_events
from integrations.lite_agent.state_model import RuntimeState
from integrations.lite_agent.tool_catalog import build_tools


def _png(width: int = 200, height: int = 100) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return output.getvalue()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class _NoAdapter:
    def execute(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("Adapter execution is not expected")


class _FakeHoloClient:
    def __init__(self, *, actual_model: str = "holo3.1-4b") -> None:
        call = SimpleNamespace(
            id="holo-call",
            function=SimpleNamespace(
                name="click",
                arguments=json.dumps({"element": "Save button", "x": 500, "y": 250}),
            ),
        )
        message = SimpleNamespace(
            content=None,
            reasoning_content="visual grounding trace",
            tool_calls=[call],
            model_dump=lambda **_kwargs: {
                "content": None,
                "reasoning_content": "visual grounding trace",
                "tool_calls": [
                    {
                        "id": "holo-call",
                        "type": "function",
                        "function": {
                            "name": "click",
                            "arguments": json.dumps(
                                {
                                    "element": "Save button",
                                    "x": 500,
                                    "y": 250,
                                }
                            ),
                        },
                    }
                ],
            },
        )
        self.response = SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
            model=actual_model,
            model_dump=lambda **_kwargs: {
                "id": "response-1",
                "model": actual_model,
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": message.model_dump(),
                    }
                ],
            },
        )
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **request: Any) -> Any:
        self.requests.append(request)
        return self.response


class _FailingHoloClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    @staticmethod
    def _create(**_request: Any) -> Any:
        raise TimeoutError("synthetic endpoint timeout")


def test_holo_grounding_is_one_shot_and_has_no_terminal_tools() -> None:
    client = _FakeHoloClient()
    observed: list[dict[str, Any]] = []
    agent = HoloGroundingAgent(
        HoloGroundingConfig(base_url="http://holo.invalid/v1"),
        client=client,
        request_observer=observed.append,
    )

    result = agent.ground(
        _png(),
        {"intent": "Click the visible Save button"},
    )

    assert result["tool"] == "gui_action"
    assert result["name"] == "click"
    assert result["arguments"]["x"] == 500
    assert observed[0]["parallel_tool_calls"] is False
    assert observed[0]["extra_body"]["reasoning_effort"] == "medium"
    names = {item["function"]["name"] for item in observed[0]["tools"]}
    assert names == {item["function"]["name"] for item in HOLO_GROUNDING_TOOLS}
    assert {"answer", "fail"}.isdisjoint(names)


def test_holo_grounding_rejects_non_object_request() -> None:
    agent = HoloGroundingAgent(
        HoloGroundingConfig(base_url="http://holo.invalid/v1"),
        client=_FakeHoloClient(),
    )

    with pytest.raises(HoloGroundingError, match="gui_request must be an object"):
        agent.ground(_png(), None)  # type: ignore[arg-type]


def test_holo_grounding_persists_linked_binary_mode_evidence() -> None:
    screenshot = _png()
    evidence: list[dict[str, Any]] = []
    agent = HoloGroundingAgent(
        HoloGroundingConfig(
            base_url="http://holo.invalid/v1",
            model="holo3.1-4b",
            reasoning_effort=None,
            reasoning_mode="thinking",
            reasoning_profile="binary_thinking_switch",
            expected_model_root="Hcompany/Holo-3.1-4B",
            accepted_actual_models=("holo3.1-4b",),
        ),
        client=_FakeHoloClient(),
        evidence_observer=evidence.append,
    )

    result = agent.ground(
        screenshot,
        {"intent": "Click the visible Save button"},
    )

    assert [item["record_type"] for item in evidence] == [
        "request_attempt",
        "response_received",
        "grounding_selected",
    ]
    assert len({item["request_id"] for item in evidence}) == 1
    attempt, response, selected = evidence
    image_artifact = attempt["request"]["messages"][1]["content"][1]["image_url"]
    assert image_artifact == {
        "artifact_type": "inline_image_digest",
        "media_type": "image/png",
        "sha256": hashlib.sha256(screenshot).hexdigest(),
        "bytes": len(screenshot),
    }
    assert "base64" not in json.dumps(attempt["request"])
    assert attempt["request_sha256"] == _canonical_sha256(attempt["request"])
    assert response["response_sha256"] == _canonical_sha256(response["response"])
    assert response["response"]["choices"][0]["message"]["tool_calls"]
    assert response["model_requested"] == "holo3.1-4b"
    assert response["model_actual"] == "holo3.1-4b"
    assert response["actual_model_accepted"] is True
    assert response["reasoning_mode_requested"] == "thinking"
    assert response["reasoning_mode_effective"] == "thinking"
    assert response["enable_thinking_requested"] is True
    assert response["reasoning_profile"] == "binary_thinking_switch"
    assert response["expected_model_root"] == "Hcompany/Holo-3.1-4B"
    assert response["accepted_actual_models"] == ["holo3.1-4b"]
    assert selected["selected_tool_call"] == {
        "tool": "gui_action",
        "name": "click",
        "arguments_raw": json.dumps({"element": "Save button", "x": 500, "y": 250}),
        "arguments": {"element": "Save button", "x": 500, "y": 250},
        "call_id": "holo-call",
    }
    assert result["request_id"] == attempt["request_id"]
    assert result["request_sha256"] == attempt["request_sha256"]
    assert result["response_sha256"] == response["response_sha256"]
    assert result["reasoning_mode_effective"] == "thinking"


def test_holo_wrong_actual_model_is_rejected_before_gateway_dispatch() -> None:
    evidence: list[dict[str, Any]] = []
    executions: list[dict[str, Any]] = []
    agent = HoloGroundingAgent(
        HoloGroundingConfig(
            base_url="http://holo.invalid/v1",
            reasoning_effort=None,
            reasoning_mode="thinking",
            accepted_actual_models=("holo3.1-4b",),
        ),
        client=_FakeHoloClient(actual_model="unexpected-model"),
        evidence_observer=evidence.append,
    )
    gateway = HoloGuiGateway(
        agent,
        lambda payload: executions.append(payload) or {"executed": True},
    )

    with pytest.raises(HoloGuiGatewayError, match="HoloGroundingError"):
        gateway.execute({"intent": "Click Save"}, _png())

    assert executions == []
    assert [item["record_type"] for item in evidence] == [
        "request_attempt",
        "response_received",
        "grounding_failure",
    ]
    assert evidence[1]["model_actual"] == "unexpected-model"
    assert evidence[1]["actual_model_accepted"] is False
    assert "outside the frozen accepted set" in evidence[2]["error"]["detail"]


def test_holo_wrong_effective_mode_is_rejected_before_selection() -> None:
    evidence: list[dict[str, Any]] = []
    agent = HoloGroundingAgent(
        HoloGroundingConfig(
            base_url="http://holo.invalid/v1",
            reasoning_effort=None,
            reasoning_mode="non_thinking",
            accepted_actual_models=("holo3.1-4b",),
        ),
        client=_FakeHoloClient(),
        evidence_observer=evidence.append,
    )

    with pytest.raises(HoloGroundingError, match="effective thinking mode"):
        agent.ground(_png(), {"intent": "Click Save"})

    assert [item["record_type"] for item in evidence] == [
        "request_attempt",
        "response_received",
        "grounding_failure",
    ]
    assert evidence[1]["reasoning_mode_requested"] == "non_thinking"
    assert evidence[1]["reasoning_mode_effective"] == "thinking"


def test_holo_grounding_records_attempt_when_endpoint_fails() -> None:
    evidence: list[dict[str, Any]] = []
    agent = HoloGroundingAgent(
        HoloGroundingConfig(base_url="http://holo.invalid/v1"),
        client=_FailingHoloClient(),
        evidence_observer=evidence.append,
    )

    with pytest.raises(HoloGroundingError, match="request failed: TimeoutError"):
        agent.ground(_png(), {"intent": "Click Save"})

    assert [item["record_type"] for item in evidence] == [
        "request_attempt",
        "request_failure",
    ]
    assert evidence[0]["request_id"] == evidence[1]["request_id"]
    assert evidence[0]["request_sha256"] == evidence[1]["request_sha256"]
    assert evidence[1]["error"]["type"] == "TimeoutError"
    assert "data:image" not in json.dumps(evidence)


@pytest.mark.parametrize("modifiers", [None, [], ["ctrl", "shift"]])
def test_holo_gateway_passes_exact_grounded_payload_and_audit_result(modifiers) -> None:
    calls: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    arguments = {"element": "Save button", "x": 500, "y": 250}
    modifier_fields = {} if modifiers is None else {"modifiers": modifiers}
    arguments.update(modifier_fields)
    raw_arguments = json.dumps(arguments)
    command = "pyautogui.click(100, 25)"
    if modifiers:
        command = f"\nwith pyautogui.hold({modifiers!r}):\n    {command}"

    def grounder(_screenshot: bytes, _request: dict[str, Any]) -> dict[str, Any]:
        return {
            "tool": "gui_action",
            "name": "click",
            "arguments_raw": raw_arguments,
            "arguments": arguments,
            "call_id": "holo-call",
            "request_id": "grounding-request",
            "request_sha256": "a" * 64,
            "response_sha256": "b" * 64,
            "model_requested": "holo3.1-4b",
            "model_actual": "holo3.1-4b",
            "reasoning_mode_requested": "thinking",
            "reasoning_mode_effective": "thinking",
            "enable_thinking_requested": True,
        }

    def executor(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return {"status": "ok", "executed": True}

    result = HoloGuiGateway(
        grounder,
        executor,
        execution_observer=evidence.append,
    ).execute(
        {"intent": "Click Save"},
        _png(),
    )

    assert calls == [{**arguments, "command": command}]
    assert result["executed"] is True
    assert result["result"]["grounded_action"] == {
        "action": "click",
        "x": 500,
        "y": 250,
        **modifier_fields,
    }
    assert result["prepared_action"]["pixel_arguments"] == {
        "x": 100, "y": 25, **modifier_fields,
    }
    assert result["grounding"]["request_id"] == "grounding-request"
    assert result["grounding"]["response_sha256"] == "b" * 64
    assert result["grounding"]["reasoning_mode_effective"] == "thinking"
    assert [item["record_type"] for item in evidence] == [
        "gateway_dispatch",
        "gateway_result",
    ]
    dispatch, gateway_result = evidence
    assert dispatch["request_id"] == "grounding-request"
    assert dispatch["selected_tool_call"] == {
        "tool": "gui_action",
        "name": "click",
        "arguments_raw": raw_arguments,
        "arguments": arguments,
        "call_id": "holo-call",
    }
    assert (
        dispatch["prepared_action"]["model_arguments"]
        == dispatch["selected_tool_call"]["arguments"]
    )
    assert dispatch["executor_payload"] == calls[0]
    assert gateway_result["request_id"] == dispatch["request_id"]
    assert gateway_result["execution_result"] == {
        "status": "ok",
        "executed": True,
    }


def test_holo_gateway_accepts_read_only_grounding_arguments() -> None:
    from types import MappingProxyType

    def grounder(_screenshot: bytes, _request: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": "click",
            "arguments": MappingProxyType({"element": "button", "x": 500, "y": 250}),
        }

    result = HoloGuiGateway(
        grounder,
        lambda _payload: {"executed": True},
    ).execute({"intent": "Click button"}, _png())

    assert result["executed"] is True


def test_hybrid_surface_exposes_gui_request_instead_of_coordinates() -> None:
    tools = build_tools(
        "os",
        ["filesystem.inspect"],
        include_gui=True,
        include_control_tools=True,
        strict_generic=True,
        gui_request=True,
    )
    names = {item["function"]["name"] for item in tools}
    assert "gui_request" in names
    assert "gui_action" not in names
    request_tool = next(
        item for item in tools if item["function"]["name"] == "gui_request"
    )
    assert "x" not in request_tool["function"]["parameters"]["properties"]


@pytest.mark.parametrize(
    ("name", "arguments", "expected", "intent"),
    [
        (
            "hotkey",
            {"keys": ["ctrl", "c"]},
            {"action": "hotkey", "keys": ["ctrl", "c"]},
            "Copy the selected text",
        ),
        (
            "write",
            {"content": "sample value", "press_enter": True},
            {"action": "type", "text": "sample value", "press_enter": True},
            "Type sample value and press Enter",
        ),
        (
            "write",
            {"content": "sample value", "press_enter": False},
            {"action": "type", "text": "sample value", "press_enter": False},
            "Type sample value without pressing Enter",
        ),
        (
            "click",
            {"element": "item", "x": 500, "y": 250, "modifiers": ["ctrl", "shift"]},
            {"action": "click", "x": 500, "y": 250, "modifiers": ["ctrl", "shift"]},
            "Ctrl+Shift-click the visible item",
        ),
    ],
    ids=["hotkey", "write-with-enter", "write-without-enter", "modified-click"],
)
def test_grounded_action_details_reach_next_parent_request(
    name,
    arguments,
    expected,
    intent,
) -> None:
    grounded = {
        "name": name,
        "arguments": arguments,
        "arguments_raw": json.dumps(arguments),
        "request_id": "host-only-gui-request",
        "response": {"reasoning_content": "host-only-gui-reasoning"},
    }
    original_grounded = copy.deepcopy(grounded)
    executed_payloads = []

    def executor(payload):
        executed_payloads.append(copy.deepcopy(payload))
        return {
            "executed": True,
            "result": {"transport": {"detail": "host-only-gui-transport"}},
        }

    agent = LiteAgent(
        LiteAgentConfig(base_url="http://planner.invalid/v1"),
        _NoAdapter(),
        gui_executor=executor,
        holo_grounder=lambda _screenshot, _request: grounded,
    )
    screenshot = _png()
    state = RuntimeState(
        task_id="synthetic-gui-feedback",
        domain="os",
        instruction=intent,
    )
    event = agent.execute_proposal(
        state,
        {
            "tool": "gui_request",
            "arguments_raw": json.dumps({"intent": intent}),
        },
        screenshot=screenshot,
    )
    original_event = copy.deepcopy(event)
    messages = agent._messages(state, screenshot)
    summary = json.loads(messages[2]["content"][0]["text"].split("\n")[1])
    feedback = next(item for item in summary if item.get("step") == event.step)
    assert event.executed is True
    assert {key: executed_payloads[0][key] for key in arguments} == arguments
    if name == "write":
        assert (
            "pyautogui.press('enter')" in executed_payloads[0]["command"]
        ) is arguments["press_enter"]
    assert event.proposed["gui_arguments"] == expected
    assert event.result["grounded_action"] == expected
    assert feedback["result"]["grounded_action"] == expected
    if name == "hotkey":
        assert (
            event.result["grounded_action"]["keys"]
            is not event.proposed["gui_arguments"]["keys"]
        )
    if name == "click":
        assert (
            event.result["grounded_action"]["modifiers"]
            is not event.proposed["gui_arguments"]["modifiers"]
        )
    serialized = json.dumps(messages)
    assert "host-only-gui" not in serialized
    assert "pyautogui." not in serialized
    assert grounded == original_grounded
    assert event == original_event


@pytest.mark.parametrize("planner_model", ["qwen3.5-4b", "holo3.1-4b"])
def test_lite_agent_routes_gui_request_through_holo_and_gateway(planner_model) -> None:
    grounded_calls: list[tuple[bytes, dict[str, Any]]] = []
    executed_payloads: list[dict[str, Any]] = []

    def grounder(screenshot: bytes, request: dict[str, Any]) -> dict[str, Any]:
        grounded_calls.append((screenshot, request))
        return {
            "name": "click",
            "arguments": {"element": "button", "x": 500, "y": 250},
            "request_id": "host-only-grounding-request",
            "request_sha256": "a" * 64,
            "response_sha256": "b" * 64,
            "reasoning_mode_requested": "thinking",
            "reasoning_mode_effective": "thinking",
            "response": {"reasoning_content": "host-only-response"},
        }

    def executor(payload: dict[str, Any]) -> dict[str, Any]:
        executed_payloads.append(payload)
        return {"executed": True, "result": {"environment_acknowledged": True}}

    agent = LiteAgent(
        LiteAgentConfig(base_url="http://planner.invalid/v1", model=planner_model),
        _NoAdapter(),  # type: ignore[arg-type]
        gui_executor=executor,
        holo_grounder=grounder,
    )
    screenshot = _png()
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Use the visible GUI to click Save.",
    )
    event = agent.execute_proposal(
        state,
        {
            "tool": "gui_request",
            "model_actual": planner_model,
            "arguments_raw": json.dumps(
                {
                    "intent": "Click the visible Save button",
                    "fallback_reason": "No deterministic action is available",
                }
            ),
        },
        screenshot=screenshot,
    )

    assert event.executed is True
    assert event.proposed["delegation"] == "planner_to_holo"
    assert event.proposed["planner_model_requested"] == planner_model
    assert event.proposed["model_actual"] == planner_model
    assert event.proposed["arguments"]["intent"].startswith("Click")
    assert event.proposed["gui_arguments"] == {
        "action": "click",
        "x": 500,
        "y": 250,
    }
    assert grounded_calls == [(screenshot, event.proposed["arguments"])]
    assert executed_payloads[0]["x"] == 500
    assert event.result["grounded_action"]["action"] == "click"
    assert event.proposed["holo_grounding"]["request_id"] == (
        "host-only-grounding-request"
    )
    assert "response" not in event.proposed["holo_grounding"]
    model_summary = summarize_events(
        [event],
        "os",
        strict_generic=True,
        context_hint_for_model=lambda *_args, **_kwargs: {},
    )
    serialized_summary = json.dumps(model_summary)
    assert "host-only-grounding-request" not in serialized_summary
    assert "reasoning_mode" not in serialized_summary
    assert "host-only-response" not in serialized_summary

    second = agent.execute_proposal(
        state,
        {
            "tool": "gui_request",
            "arguments_raw": json.dumps({"intent": "Click the visible Save button"}),
        },
        screenshot=screenshot,
    )
    assert second.executed is True

    blocked = agent.execute_proposal(
        state,
        {
            "tool": "gui_request",
            "arguments_raw": json.dumps({"intent": "Click the visible Save button"}),
        },
        screenshot=screenshot,
    )
    assert blocked.executed is False
    assert blocked.error["type"] == "RepeatedActionBlocked"
    assert len(executed_payloads) == 2
