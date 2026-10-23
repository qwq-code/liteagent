from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from vscode_adapter import accessibility_state
from vscode_adapter.accessibility_state import (
    expand_accessible_section,
    inspect_section_state,
    inspect_view_state,
)
from vscode_adapter.errors import AdapterError
from vscode_adapter.worker import _default_specs


class FakeState:
    def __init__(self, states: set[str]) -> None:
        self.states = states

    def contains(self, state: str) -> bool:
        return state in self.states


class FakeAction:
    def __init__(
        self,
        names: list[str],
        callback: Callable[[str], bool] | None = None,
    ) -> None:
        self.names = names
        self.callback = callback

    @property
    def nActions(self) -> int:
        return len(self.names)

    def getName(self, index: int) -> str:
        return self.names[index]

    def doAction(self, index: int) -> bool:
        name = self.names[index]
        return self.callback(name) if self.callback else True


class FakeNode:
    def __init__(
        self,
        name: str,
        role: str,
        *,
        states: set[str] | None = None,
        children: list[FakeNode] | None = None,
        actions: FakeAction | None = None,
    ) -> None:
        self.name = name
        self.role = role
        self.states = states or set()
        self.children = children or []
        self.actions = actions

    @property
    def childCount(self) -> int:
        return len(self.children)

    def getChildAtIndex(self, index: int) -> FakeNode:
        return self.children[index]

    def getRoleName(self) -> str:
        return self.role

    def getState(self) -> FakeState:
        return FakeState(self.states)

    def queryAction(self) -> FakeAction:
        if self.actions is None:
            raise NotImplementedError
        return self.actions


class FakeRegistry:
    def __init__(self, desktop: FakeNode) -> None:
        self.desktop = desktop

    def getDesktop(self, _index: int) -> FakeNode:
        return self.desktop


class FakeAtspi:
    STATE_ACTIVE = "active"
    STATE_CHECKED = "checked"
    STATE_EXPANDED = "expanded"
    STATE_EXPANDABLE = "expandable"
    STATE_FOCUSED = "focused"
    STATE_SELECTED = "selected"
    STATE_SHOWING = "showing"
    STATE_VISIBLE = "visible"

    def __init__(self, desktop: FakeNode) -> None:
        self.Registry = FakeRegistry(desktop)


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, argv: list[str], **_kwargs: Any) -> dict[str, Any]:
        self.calls.append(argv)
        if argv == ["wmctrl", "-lx"]:
            return {
                "returncode": 0,
                "stdout": (
                    "0x01a00001  0 code.Code host Alpha - Visual Studio Code\n"
                    "0x01a00002  0 code.Code host Beta - Visual Studio Code\n"
                ),
                "stderr": "",
                "argv": argv,
            }
        return {"returncode": 0, "stdout": "", "stderr": "", "argv": argv}


def node_tree(
    first_children: list[FakeNode],
    second_children: list[FakeNode],
    *,
    second_active: bool = True,
) -> FakeAtspi:
    showing = {"showing", "visible"}
    first = FakeNode(
        "Alpha - Visual Studio Code",
        "frame",
        states=set() if second_active else {"active"},
        children=first_children,
    )
    second = FakeNode(
        "Beta - Visual Studio Code",
        "frame",
        states={"active"} if second_active else set(),
        children=second_children,
    )
    app = FakeNode("Visual Studio Code", "application", children=[first, second])
    desktop = FakeNode("Desktop", "desktop", states=showing, children=[app])
    return FakeAtspi(desktop)


def install_atspi(monkeypatch: pytest.MonkeyPatch, atspi: FakeAtspi) -> None:
    monkeypatch.setattr(accessibility_state, "_load_atspi", lambda: atspi)


def test_view_state_is_scoped_to_the_unique_requested_active_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    showing = {"showing", "visible"}
    first_explorer = FakeNode(
        "Explorer (Ctrl+Shift+E)",
        "page tab",
        states=showing | {"selected"},
    )
    second_explorer = FakeNode("Explorer (Ctrl+Shift+E)", "page tab", states=showing)
    second_search = FakeNode(
        "Search (Ctrl+Shift+F)",
        "page tab",
        states=showing | {"checked"},
    )
    install_atspi(
        monkeypatch,
        node_tree([first_explorer], [second_explorer, second_search]),
    )
    runner = FakeRunner()

    selected = inspect_view_state(runner, "0x01a00002", "search")
    wrong_view = inspect_view_state(runner, "0x01a00002", "explorer")

    assert selected["active"] is True
    assert selected["window_title"] == "Beta - Visual Studio Code"
    assert selected["selected_match_count"] == 1
    assert wrong_view["active"] is False
    assert wrong_view["visible_match_count"] == 1


def test_view_state_accepts_visible_panel_heading_without_selected_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    showing = {"showing", "visible"}
    heading = FakeNode("Run and Debug: Run", "panel", states=showing)
    install_atspi(monkeypatch, node_tree([], [heading]))

    state = inspect_view_state(FakeRunner(), "0x01a00002", "run_and_debug")

    assert state["active"] is True
    assert state["label_match_count"] == 1
    assert state["heading_match_count"] == 1
    assert state["selected_match_count"] == 0


def test_view_state_falls_back_to_controller_when_atspi_has_no_view_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_atspi(monkeypatch, node_tree([], []))
    monkeypatch.setattr(
        accessibility_state,
        "inspect_controller_view",
        lambda window_id, window_title, expected_label: {
            "window_id": window_id,
            "window_title": window_title,
            "expected_label": expected_label,
            "active": True,
            "label_match_count": 1,
            "visible_match_count": 1,
            "selected_match_count": 0,
            "heading_match_count": 1,
            "selected_matches": [],
            "source": "osworld_accessibility_control",
        },
    )

    state = inspect_view_state(FakeRunner(), "0x01a00002", "run_and_debug")

    assert state["active"] is True
    assert state["source"] == "osworld_accessibility_control"
    assert state["view"] == "run_and_debug"


def test_view_state_fails_closed_when_two_code_frames_are_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    showing = {"showing", "visible", "selected"}
    atspi = node_tree([], [FakeNode("Extensions", "page tab", states=showing)])
    application = atspi.Registry.desktop.children[0]
    application.children[0].states.add("active")
    install_atspi(monkeypatch, atspi)

    with pytest.raises(AdapterError, match="unique active accessible frame"):
        inspect_view_state(FakeRunner(), "0x01a00002", "extensions")


@pytest.mark.parametrize("label", ["Outline", "Breakpoints"])
def test_expand_section_presses_only_the_exact_match_in_requested_window(
    monkeypatch: pytest.MonkeyPatch,
    label: str,
) -> None:
    showing = {"showing", "visible", "expandable"}
    presses = {"first": 0, "second": 0}

    def press_first(_name: str) -> bool:
        presses["first"] += 1
        return True

    def press_second(_name: str) -> bool:
        presses["second"] += 1
        second_section.states.add("expanded")
        return True

    first_section = FakeNode(
        label,
        "toggle button",
        states=showing | {"expanded"},
        actions=FakeAction(["press"], press_first),
    )
    second_section = FakeNode(
        label,
        "toggle button",
        states=set(showing),
        actions=FakeAction(["press"], press_second),
    )
    install_atspi(
        monkeypatch,
        node_tree([first_section], [second_section]),
    )
    runner = FakeRunner()

    result = expand_accessible_section(runner, "0x01a00002", label, 0.2)
    observed = inspect_section_state(runner, "0x01a00002", label)

    assert result["already_expanded"] is False
    assert result["action"] == "press"
    assert presses == {"first": 0, "second": 1}
    assert observed["match_count"] == 1
    assert observed["expanded"] is True


def test_expand_section_fails_closed_on_ambiguous_exact_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    showing = {"showing", "visible", "expandable"}
    sections = [
        FakeNode(
            "Watch",
            "toggle button",
            states=set(showing),
            actions=FakeAction(["press"]),
        )
        for _index in range(2)
    ]
    install_atspi(monkeypatch, node_tree([], sections))

    with pytest.raises(AdapterError) as caught:
        expand_accessible_section(FakeRunner(), "0x01a00002", "Watch", 0.1)

    assert caught.value.code == "AMBIGUOUS_SECTION"
    assert caught.value.details["match_count"] == 2


def test_missing_section_is_not_reported_as_a_missing_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_atspi(monkeypatch, node_tree([], []))

    with pytest.raises(AdapterError) as caught:
        expand_accessible_section(FakeRunner(), "0x01a00002", "Locals", 0.1)

    assert caught.value.code == "SECTION_NOT_FOUND"
    assert caught.value.details["window_id"] == "0x1a00002"
    assert caught.value.details["match_count"] == 0
    assert "Keep the observed window_id" in caught.value.details["guidance"]


def test_expand_section_matches_case_and_whitespace_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    section = FakeNode(
        "VARIABLES",
        "toggle button",
        states={"showing", "visible", "expandable"},
    )
    section.actions = FakeAction(
        ["press"], lambda _name: section.states.add("expanded") or True
    )
    install_atspi(monkeypatch, node_tree([], [section]))

    result = expand_accessible_section(
        FakeRunner(), "0x01a00002", "  Variables  ", 0.1
    )

    assert result["already_expanded"] is False
    assert result["after"]["name"] == "VARIABLES"


def test_expand_section_fails_when_press_does_not_change_expanded_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    section = FakeNode(
        "Timeline",
        "toggle button",
        states={"showing", "visible", "expandable"},
        actions=FakeAction(["press"], lambda _name: True),
    )
    install_atspi(monkeypatch, node_tree([], [section]))

    with pytest.raises(AdapterError, match="did not become expanded") as caught:
        expand_accessible_section(FakeRunner(), "0x01a00002", "Timeline", 0.1)

    assert caught.value.code == "VERIFICATION_FAILED"
    assert caught.value.details["after"]["expanded"] is False


def test_worker_supplies_nonempty_semantic_verifiers_for_both_ui_actions() -> None:
    view_specs = _default_specs(
        "ui.open_view",
        {"window_id": "0x01a00002", "view": "source_control"},
        {
            "window_id": "0x1a00002",
            "window_title": "Beta - Visual Studio Code",
            "view": "source_control",
        },
    )
    section_specs = _default_specs(
        "ui.expand_section",
        {"window_id": "0x01a00002", "name": "Repositories"},
        {
            "window_id": "0x1a00002",
            "window_title": "Beta - Visual Studio Code",
            "section": {"name": "Repositories"},
        },
    )

    assert view_specs == [
        {
            "type": "vscode_view_active",
            "window_id": "0x1a00002",
            "view": "source_control",
        }
    ]
    assert section_specs == [
        {
            "type": "vscode_section_expanded",
            "window_id": "0x1a00002",
            "name": "Repositories",
        }
    ]
