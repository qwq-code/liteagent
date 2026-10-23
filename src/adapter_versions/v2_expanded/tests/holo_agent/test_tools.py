from __future__ import annotations

from contextlib import contextmanager

import pytest

from integrations.holo_agent.tools import (
    HOLO_GROUNDING_TOOLS,
    HOLO_GUI_TOOLS,
    prepare_action,
    validate_grounding_action,
)
from integrations.lite_agent.gui_actions import build_gui_command


def test_click_scales_normalized_coordinates_against_exact_screenshot() -> None:
    action = prepare_action(
        "click",
        {"element": "button", "x": 500, "y": 250},
        screenshot_width=1920,
        screenshot_height=1080,
        default_settle_seconds=2.0,
    )

    assert action.model_arguments == {"element": "button", "x": 500, "y": 250}
    assert action.pixel_arguments == {"x": 960, "y": 270}
    assert action.command == "pyautogui.click(960, 270)"


@pytest.mark.parametrize("click_raises", [False, True])
def test_modifier_click_keeps_keys_held_only_during_the_selected_click(
    click_raises: bool,
) -> None:
    arguments = {
        "element": "selected item", "x": 500, "y": 250,
        "modifiers": ["ctrl", "shift"],
    }
    validate_grounding_action("click", arguments)
    action = prepare_action(
        "click", arguments, screenshot_width=1920, screenshot_height=1080,
        default_settle_seconds=2.0,
    )
    assert action.model_arguments == arguments
    assert action.pixel_arguments == {
        "x": 960, "y": 270, "modifiers": ["ctrl", "shift"],
    }
    assert action.command is not None
    # The pinned controller appends commands after a semicolon. A compound
    # with statement must start a new line to be valid in that context.
    compile("import pyautogui; pyautogui.FAILSAFE = False; " + action.command,
            "<controller-command>", "exec")
    calls = []

    class FakeDesktop:
        @contextmanager
        def hold(self, keys):
            calls.append(("hold", list(keys)))
            try:
                yield
            finally:
                calls.append(("release", list(keys)))

        def click(self, x, y):
            calls.append(("click", x, y))
            if click_raises:
                raise RuntimeError("synthetic click failure")

    if click_raises:
        with pytest.raises(RuntimeError, match="synthetic click failure"):
            exec(action.command, {"pyautogui": FakeDesktop()})
    else:
        exec(action.command, {"pyautogui": FakeDesktop()})
    assert calls == [
        ("hold", ["ctrl", "shift"]),
        ("click", 960, 270),
        ("release", ["ctrl", "shift"]),
    ]
    assert arguments["modifiers"] == ["ctrl", "shift"]


def test_write_preserves_model_text_and_uses_direct_desktop_typing() -> None:
    action = prepare_action(
        "write",
        {"content": "alpha beta", "press_enter": True},
        screenshot_width=100,
        screenshot_height=100,
        default_settle_seconds=1.0,
    )

    assert action.model_arguments["content"] == "alpha beta"
    assert str(action.command).startswith(
        "pyautogui.write('alpha beta', interval=0.03)"
    )
    assert "pyperclip" not in str(action.command)
    assert str(action.command).endswith("pyautogui.press('enter')")


def test_write_rejects_non_ascii_without_substituting_model_text() -> None:
    with pytest.raises(ValueError, match="ASCII"):
        prepare_action(
            "write",
            {"content": "café", "press_enter": False},
            screenshot_width=100,
            screenshot_height=100,
            default_settle_seconds=1.0,
        )


def test_terminal_action_has_no_implicit_gui_command() -> None:
    action = prepare_action(
        "answer",
        {"content": "The requested state is visible."},
        screenshot_width=1920,
        screenshot_height=1080,
        default_settle_seconds=2.0,
    )

    assert action.command is None
    assert action.terminal == "DONE"


def test_invalid_coordinate_is_rejected_without_clamping_model_argument() -> None:
    with pytest.raises(Exception):
        prepare_action(
            "click",
            {"element": "outside", "x": 1001, "y": 500},
            screenshot_width=1920,
            screenshot_height=1080,
            default_settle_seconds=2.0,
        )


@pytest.mark.parametrize("amount", [-30, 30])
def test_scroll_preserves_existing_signed_wheel_contract(amount: int) -> None:
    for tools in (HOLO_GUI_TOOLS, HOLO_GROUNDING_TOOLS):
        scroll = next(tool["function"] for tool in tools
                      if tool["function"]["name"] == "scroll")
        amount_schema = scroll["parameters"]["properties"]["amount"]
        assert {key: value for key, value in amount_schema.items()
                if key != "description"} == {"type": "integer"}

    arguments = {"element": "document", "x": 500, "y": 250, "amount": amount}
    validate_grounding_action("scroll", arguments)
    action = prepare_action(
        "scroll", arguments, screenshot_width=1920, screenshot_height=1080,
        default_settle_seconds=2.0,
    )
    command = build_gui_command({
        "action": "scroll", "amount": amount, "fallback_reason": "scroll the document",
    })

    assert arguments == {"element": "document", "x": 500, "y": 250, "amount": amount}
    assert action.model_arguments == arguments
    assert action.pixel_arguments == {"x": 960, "y": 270}
    assert command == f"pyautogui.scroll({amount})"
    assert action.command == f"pyautogui.moveTo(960, 270); {command}"
