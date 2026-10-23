from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from vscode_adapter import controller_accessibility
from vscode_adapter.controller_accessibility import (
    inspect_debug_session,
    inspect_debug_variables,
    inspect_source_breakpoint,
    inspect_view,
)


STATE_NS = "https://accessibility.ubuntu.example.org/ns/state"
WINDOW_TITLE = "counterfactual.py - workspace - Visual Studio Code"


def controller_tree() -> ET.Element:
    return ET.fromstring(
        f"""
        <desktop-frame xmlns:st="{STATE_NS}">
          <application name="code">
            <frame name="{WINDOW_TITLE}" st:active="true" st:showing="true" st:visible="true">
              <push-button name="Continue (F5)" st:showing="true" st:visible="true" />
              <push-button name="Stop (Shift+F5)" st:showing="true" st:visible="true" />
              <heading name="Run and Debug: Run" st:showing="true" st:visible="true" />
              <heading name="VARIABLES" st:showing="true" st:visible="true" />
              <tree name="Debug Variables" st:showing="true" st:visible="true">
                <tree-item name="Scope Locals" st:showing="true" st:visible="true" />
                <tree-item name="matrix, value array([1, 2])" st:showing="true" st:visible="true" />
              </tree>
              <heading name="BREAKPOINTS" st:showing="true" st:visible="true" />
              <check-box name="counterfactual.py 12, ~/work/counterfactual.py"
                         st:checked="true" st:showing="true" st:visible="true" />
            </frame>
          </application>
        </desktop-frame>
        """
    )


def install_tree(monkeypatch) -> None:
    monkeypatch.setattr(
        controller_accessibility, "fetch_accessibility_root", controller_tree
    )


def test_controller_session_observes_real_paused_toolbar(monkeypatch) -> None:
    install_tree(monkeypatch)

    state = inspect_debug_session("0x2a00002", WINDOW_TITLE)

    assert state["phase"] == "paused"
    assert state["active"] is True
    assert state["continue_control_count"] == 1
    assert state["stop_control_count"] == 1
    assert state["variables_tree_count"] == 1


def test_controller_variables_return_only_visible_debug_tree_items(monkeypatch) -> None:
    install_tree(monkeypatch)

    result = inspect_debug_variables("0x2a00002", WINDOW_TITLE, 8)

    assert result["item_names"] == [
        "Scope Locals",
        "matrix, value array([1, 2])",
    ]
    assert result["source"] == "osworld_accessibility_control"


def test_controller_breakpoint_requires_exact_path_line_and_checked_state(
    monkeypatch,
) -> None:
    install_tree(monkeypatch)

    exact = inspect_source_breakpoint(
        "0x2a00002", WINDOW_TITLE, Path("/home/user/work/counterfactual.py"), 12
    )
    wrong_path = inspect_source_breakpoint(
        "0x2a00002", WINDOW_TITLE, Path("/home/user/other/counterfactual.py"), 12
    )
    wrong_line = inspect_source_breakpoint(
        "0x2a00002", WINDOW_TITLE, Path("/home/user/work/counterfactual.py"), 13
    )

    assert exact["breakpoints_heading_count"] == 1
    assert exact["match_count"] == 1
    assert exact["checked_count"] == 1
    assert wrong_path["match_count"] == 0
    assert wrong_line["match_count"] == 0


def test_controller_view_accepts_visible_panel_heading(monkeypatch) -> None:
    install_tree(monkeypatch)
    result = inspect_view("0x2a00002", WINDOW_TITLE, "Run and Debug")

    assert result["active"] is True
    assert result["heading_match_count"] == 1
    assert result["label_match_count"] == 1


def test_debug_observation_preserves_native_picker_prompt_and_visible_choices(
    monkeypatch,
) -> None:
    root = controller_tree()
    frame = root.find("application/frame")
    for button in frame.findall("push-button"):
        frame.remove(button)
    frame.append(ET.fromstring(f"""
        <section xmlns:st="{STATE_NS}"
                 xmlns:attr="{controller_accessibility.ATTR_NS}"
                 attr:class="quick-input-widget show-file-icons"
                 st:showing="true" st:visible="true">
          <combo-box name="input" attr:placeholder="Select launch configuration"
                     st:focused="true" st:showing="true" st:visible="true" />
          <list-box name="Select launch configuration" st:showing="true" st:visible="true">
            <list-item name="Node.js" st:showing="true" st:visible="true" />
            <list-item name="Attach to process" st:showing="true" st:visible="true" />
            <list-item name="Hidden choice" st:visible="true" />
          </list-box>
        </section>
    """))
    monkeypatch.setattr(controller_accessibility, "fetch_accessibility_root", lambda: root)

    state = inspect_debug_session("0x2a00002", WINDOW_TITLE)

    assert state["active"] is False
    assert state["quick_inputs"] == [{
        "prompts": ["Select launch configuration"],
        "list_names": ["Select launch configuration"],
        "options": ["Node.js", "Attach to process"],
        "option_count": 2,
        "truncated": False,
    }]
    frame[-1].set(f"{{{STATE_NS}}}showing", "false")
    assert inspect_debug_session("0x2a00002", WINDOW_TITLE)["quick_inputs"] == []
