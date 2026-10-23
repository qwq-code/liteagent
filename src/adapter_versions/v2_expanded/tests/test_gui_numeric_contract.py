from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import jsonschema
import pytest

from integrations.lite_agent.gui_actions import (
    GUI_ACTION_SCHEMA,
    build_gui_command,
    normalize_gui_arguments,
)
from integrations.lite_agent.gui_policy import repeated_gui_action_error
from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.state_model import RuntimeState


def _click(**overrides: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "action": "click",
        "fallback_reason": "the visible control is not exposed by an Adapter",
        "x": "470",
        "y": "283",
    }
    arguments.update(overrides)
    return arguments


def test_public_schema_accepts_qwen_numeric_string_representation() -> None:
    arguments = _click(seconds="0.5")

    jsonschema.validate(arguments, GUI_ACTION_SCHEMA)
    assert normalize_gui_arguments(arguments) == {
        **arguments,
        "x": 470,
        "y": 283,
        "seconds": 0.5,
    }


def test_command_conversion_keeps_model_arguments_and_uses_canonical_numbers() -> None:
    arguments = _click(seconds="1")
    original = copy.deepcopy(arguments)

    command = build_gui_command(arguments)

    assert command == "pyautogui.click(470, 283)"
    assert arguments == original
    assert arguments["x"] == "470"
    assert arguments["y"] == "283"
    assert arguments["seconds"] == "1"


def test_execution_event_keeps_raw_model_args_while_gateway_gets_command() -> None:
    arguments = _click(seconds="1")
    raw_arguments = json.dumps(arguments, separators=(",", ":"))
    gateway_calls: list[dict[str, object]] = []

    def gui_executor(payload: dict[str, object]) -> dict[str, object]:
        gateway_calls.append(payload)
        return {"executed": True, "result": {"environment_acknowledged": True}}

    agent = LiteAgent(
        LiteAgentConfig(base_url="http://qwen.invalid/v1"),
        SimpleNamespace(),  # type: ignore[arg-type]
        gui_executor=gui_executor,
        model_client=SimpleNamespace(client=None),  # type: ignore[arg-type]
    )
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Use the visible GUI to click the control.",
    )

    event = agent.execute_proposal(
        state,
        {"tool": "gui_action", "arguments_raw": raw_arguments},
    )

    assert event.executed is True
    assert event.proposed["arguments_raw"] == raw_arguments
    assert event.proposed["arguments"] == arguments
    assert event.proposed["gui_arguments"] == arguments
    assert event.proposed["command"] == "pyautogui.click(470, 283)"
    assert gateway_calls == [{**arguments, "command": "pyautogui.click(470, 283)"}]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("x", "470.0"),
        ("x", " 470"),
        ("x", "1e2"),
        ("y", "-1"),
        ("seconds", "1e1"),
        ("seconds", "-0.5"),
        ("seconds", "11"),
        ("seconds", "nan"),
        ("seconds", "inf"),
    ],
)
def test_numeric_string_boundary_rejects_non_decimal_or_out_of_range_values(
    field: str, value: str
) -> None:
    with pytest.raises((ValueError, jsonschema.ValidationError)):
        build_gui_command(_click(**{field: value}))


def test_scroll_accepts_signed_integer_string_but_rejects_fraction() -> None:
    arguments = {
        "action": "scroll",
        "fallback_reason": "the visible pane needs scrolling",
        "amount": "-3",
        "seconds": "2",
    }

    assert build_gui_command(arguments) == "pyautogui.scroll(-3)"
    with pytest.raises((ValueError, jsonschema.ValidationError)):
        build_gui_command({**arguments, "amount": "-3.5"})


def test_boolean_numeric_fields_remain_invalid() -> None:
    with pytest.raises(jsonschema.ValidationError):
        build_gui_command(_click(x=True))


def test_duplicate_policy_matches_numeric_string_and_number_representations() -> None:
    prior = SimpleNamespace(
        proposed={
            "kind": "gui",
            "gui_arguments": _click(x="470", y="283"),
        },
        executed=True,
        step=1,
    )
    second = SimpleNamespace(
        proposed={
            "kind": "gui",
            "gui_arguments": {**_click(x=470, y=283)},
        },
        executed=True,
        step=2,
    )

    blocked = repeated_gui_action_error(
        [prior, second],
        command="pyautogui.click(470, 283)",
        arguments=_click(x="470", y="283"),
        step=3,
        block_window_steps=3,
    )

    assert blocked is not None
    assert blocked["type"] == "RepeatedActionBlocked"


def test_duplicate_policy_keeps_delegated_request_arguments_coordinate_free() -> None:
    prior = SimpleNamespace(
        proposed={
            "kind": "gui",
            "gui_request_arguments": {
                "action": "gui_request",
                "intent": "Click Save",
            },
        },
        executed=True,
        step=1,
    )
    second = SimpleNamespace(
        proposed={
            "kind": "gui",
            "gui_request_arguments": {
                "action": "gui_request",
                "intent": "Click Save",
            },
        },
        executed=True,
        step=2,
    )

    blocked = repeated_gui_action_error(
        [prior, second],
        command="holo.gui_request",
        arguments={"action": "gui_request", "intent": "Click Save"},
        step=3,
        block_window_steps=3,
        blocked_action="gui_request",
    )

    assert blocked is not None
    assert blocked["blocked_action"] == "gui_request"


def test_non_finite_numeric_seconds_are_invalid() -> None:
    with pytest.raises(ValueError, match="must be finite"):
        build_gui_command(_click(seconds=float("nan")))


def test_holo_request_schema_remains_coordinate_free() -> None:
    # Importing the separate schema here guards the direct-GUI compatibility
    # change against accidentally widening the Qwen-to-Holo request surface.
    from integrations.lite_agent.gui_actions import GUI_REQUEST_SCHEMA

    request = {"intent": "Click the visible Save button"}
    jsonschema.validate(request, GUI_REQUEST_SCHEMA)
    assert "x" not in GUI_REQUEST_SCHEMA["properties"]
