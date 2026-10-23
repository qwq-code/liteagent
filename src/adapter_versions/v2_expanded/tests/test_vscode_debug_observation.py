from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from vscode_adapter import accessibility_state, actions, debug_control, verifier
from vscode_adapter.accessibility_state import (
    WindowRecord,
    inspect_debug_session_state,
    inspect_debug_variables,
    wait_for_debug_state,
)
from vscode_adapter.actions import VscodeActions
from vscode_adapter.errors import AdapterError
from vscode_adapter.schema import validate_action_params
from vscode_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
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
        self.performed: list[str] = []

    @property
    def nActions(self) -> int:
        return len(self.names)

    def getName(self, index: int) -> str:
        return self.names[index]

    def doAction(self, index: int) -> bool:
        name = self.names[index]
        self.performed.append(name)
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


class FakeAtspi:
    STATE_ACTIVE = "active"
    STATE_CHECKED = "checked"
    STATE_EXPANDED = "expanded"
    STATE_EXPANDABLE = "expandable"
    STATE_FOCUSED = "focused"
    STATE_SELECTED = "selected"
    STATE_SHOWING = "showing"
    STATE_VISIBLE = "visible"


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, argv: list[str], **_kwargs: Any) -> dict[str, Any]:
        self.calls.append(argv)
        return {"returncode": 0, "stdout": "", "stderr": "", "argv": argv}


def visible_node(
    name: str,
    role: str,
    children: list[FakeNode] | None = None,
    *,
    actions: FakeAction | None = None,
) -> FakeNode:
    return FakeNode(
        name,
        role,
        states={"showing", "visible"},
        children=children,
        actions=actions,
    )


def debug_frame(
    variable_names: list[str],
    *,
    active: bool = True,
    progress_control: str = "Continue (F5)",
) -> FakeNode:
    controls = []
    if active:
        controls = [
            visible_node(progress_control, "push button"),
            visible_node("Stop (Shift+F5)", "push button"),
        ]
    variables = visible_node(
        "VARIABLES",
        "tree",
        [visible_node(name, "tree item") for name in variable_names],
    )
    return visible_node(
        "Counterfactual - Visual Studio Code", "frame", controls + [variables]
    )


def install_frame(monkeypatch: pytest.MonkeyPatch, frame: FakeNode) -> None:
    atspi = FakeAtspi()
    window = WindowRecord(
        "0x2a00002", "code.Code", "Counterfactual - Visual Studio Code"
    )
    monkeypatch.setattr(accessibility_state, "_load_atspi", lambda: atspi)
    monkeypatch.setattr(
        accessibility_state,
        "requested_code_window",
        lambda _runner, _window_id: window,
    )
    monkeypatch.setattr(
        accessibility_state,
        "active_window_node",
        lambda _window, _atspi=None: frame,
    )


def test_variables_tree_without_debug_controls_is_not_an_active_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_frame(monkeypatch, debug_frame(["sample matrix"], active=False))

    state = inspect_debug_session_state(FakeRunner(), "0x2a00002")

    assert state["active"] is False
    assert state["variables_tree_count"] == 1
    with pytest.raises(AdapterError, match="no observable paused debug session"):
        inspect_debug_variables(FakeRunner(), "0x2a00002")


def test_running_session_is_not_paused_and_cannot_read_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_frame(
        monkeypatch,
        debug_frame(["sample matrix"], progress_control="Pause (F6)"),
    )

    state = inspect_debug_session_state(FakeRunner(), "0x2a00002")

    assert state["active"] is True
    assert state["running"] is True
    assert state["paused"] is False
    assert state["phase"] == "running"
    with pytest.raises(AdapterError, match="no observable paused debug session"):
        inspect_debug_variables(FakeRunner(), "0x2a00002")


def test_conflicting_debug_controls_fail_closed_as_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = debug_frame([])
    frame.children.insert(1, visible_node("Pause (F6)", "push button"))
    install_frame(monkeypatch, frame)

    state = inspect_debug_session_state(FakeRunner(), "0x2a00002")

    assert state["phase"] == "ambiguous"
    assert state["active"] is False
    assert state["paused"] is False
    assert state["running"] is False


def test_wait_for_debug_state_requires_the_exact_observed_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_frame(monkeypatch, debug_frame([], progress_control="Pause (F6)"))

    state = wait_for_debug_state(FakeRunner(), "0x2a00002", "running", 0.1)

    assert state["phase"] == "running"


@pytest.mark.parametrize(
    "variable_names,max_items,expected",
    [
        (
            ["Locals", "temperature: ndarray", "epoch: int"],
            8,
            ["Locals", "temperature: ndarray", "epoch: int"],
        ),
        (
            ["Globals", "frame: DataFrame", "mask: ndarray"],
            2,
            ["Globals", "frame: DataFrame"],
        ),
    ],
)
def test_debug_variables_reads_only_visible_live_tree_items(
    monkeypatch: pytest.MonkeyPatch,
    variable_names: list[str],
    max_items: int,
    expected: list[str],
) -> None:
    install_frame(monkeypatch, debug_frame(variable_names))

    observed = inspect_debug_variables(FakeRunner(), "0x2a00002", max_items)

    assert observed["session"]["active"] is True
    assert observed["item_names"] == expected
    assert observed["item_count"] == len(variable_names)
    assert observed["truncated"] is (len(expected) < len(variable_names))


def test_debug_start_sends_only_f5_and_returns_observed_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = FakeRunner()
    window = WindowRecord(
        "0x2a00002", "code.Code", "Counterfactual - Visual Studio Code"
    )
    observed_session = {
        "window_id": window.window_id,
        "window_title": window.title,
        "active": True,
    }
    monkeypatch.setattr(actions, "wait_for_active_window", lambda *_args: window)
    monkeypatch.setattr(
        actions, "wait_for_debug_session", lambda *_args: observed_session
    )

    result = VscodeActions(runner).debug_start({"window_id": "0x02A00002"}, 30)

    assert result["session"] == observed_session
    assert runner.calls == [
        ["wmctrl", "-ia", "0x02A00002"],
        ["python3", "-c", "import pyautogui; pyautogui.press('f5')"],
    ]


def test_wait_for_debug_session_returns_actionable_dependency_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        accessibility_state,
        "inspect_debug_session_state",
        lambda *_args: {"active": False, "phase": "inactive"},
    )

    with pytest.raises(AdapterError) as caught:
        accessibility_state.wait_for_debug_session(FakeRunner(), "0x2a00002", 0.1)

    assert caught.value.code == "VSCODE_NOT_READY"
    assert caught.value.details["last_observation"]["phase"] == "inactive"
    guidance = caught.value.details["guidance"]
    assert "extension.install" in guidance
    assert "source_type" in guidance
    assert "Do not retry F5 unchanged" in guidance


def test_debug_picker_returns_promptly_and_reaches_model_feedback(monkeypatch) -> None:
    import json

    from integrations.lite_agent.agent_protocol import AgentProtocolMixin
    from integrations.lite_agent.episode_control import mark_tool_result_for_audit
    from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState

    state = {
        "active": False,
        "phase": "inactive",
        "quick_inputs": [{
            "prompts": ["Select launch configuration"],
            "options": ["Node.js", "Attach to process"],
        }],
    }
    monkeypatch.setattr(accessibility_state, "inspect_debug_session_state", lambda *_: state)
    monkeypatch.setattr(accessibility_state.time, "monotonic", lambda: 1.0)
    monkeypatch.setattr(
        accessibility_state.time, "sleep",
        lambda *_: pytest.fail("a pending picker must not wait for debug controls"),
    )
    with pytest.raises(AdapterError) as caught:
        accessibility_state.wait_for_debug_session(FakeRunner(), "0x2a00002", 30)
    error = caught.value
    assert error.code == "VSCODE_NOT_READY"
    assert error.details["last_observation"] == state
    assert "gui_request" in error.details["guidance"]
    event = ExecutionEvent(
        step=1, timestamp_utc="2026-09-11T00:00:00Z",
        proposed={"kind": "adapter", "action": "debug.start", "arguments": {}},
        executed=False,
        error={"code": error.code, "message": error.message, "details": error.details},
    )
    runtime = RuntimeState(
        task_id="synthetic-picker-feedback", domain="vs_code",
        instruction="Inspect the current program in its debugger.", events=[event],
    )
    mark_tool_result_for_audit(runtime, event)
    messages = AgentProtocolMixin()._messages(runtime, b"png")
    projected = json.dumps(messages, ensure_ascii=True)
    assert "Select launch configuration" in projected
    assert "Attach to process" in projected
    assert "gui_request" in projected


@pytest.mark.parametrize(
    "started_active,current_phase,passed,ended",
    [(True, "inactive", False, True), (False, "inactive", False, False),
     (True, "paused", True, False)],
)
def test_debug_start_verification_reports_transition_without_changing_verdict(
    monkeypatch, started_active, current_phase, passed, ended,
) -> None:
    import json

    from integrations.lite_agent.agent_protocol import AgentProtocolMixin
    from integrations.lite_agent.episode_control import mark_tool_result_for_audit
    from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState

    observed = {"active": current_phase == "paused", "phase": current_phase}
    monkeypatch.setattr(verifier, "inspect_debug_session_state", lambda *_: observed)
    verification = verifier.verify_specs(
        [{"type": "vscode_debug_session", "window_id": "0x2a00002"}],
        {"session": {"active": started_active}}, FakeRunner(),
    )
    assert verification["passed"] is passed
    check = verification["checks"][0]["observed"]
    assert (check.get("transition") == "started_then_ended") is ended
    assert "guidance" not in observed
    if not ended:
        assert "guidance" not in check
        return
    event = ExecutionEvent(
        step=1, timestamp_utc="2026-09-11T00:00:00Z",
        proposed={"kind": "adapter", "action": "debug.start", "arguments": {}},
        executed=False,
        error={"status": "error", "error": {
            "code": "VERIFICATION_FAILED", "message": "operation verification failed",
            "details": verification,
        }},
    )
    state = RuntimeState(
        task_id="synthetic-debug-transition", domain="vs_code",
        instruction="Inspect the running program.", events=[event],
    )
    mark_tool_result_for_audit(state, event)
    projected = json.dumps(AgentProtocolMixin()._messages(state, b"png"))
    assert "started_then_ended" in projected
    assert "debug.breakpoint.set" in projected
    assert "before its line executes" in projected


def test_debug_variables_action_only_reads_the_selected_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = FakeRunner()
    window = WindowRecord(
        "0x2a00002", "code.Code", "Counterfactual - Visual Studio Code"
    )
    calls: list[tuple[str, int]] = []
    observed = {
        "window_id": window.window_id,
        "item_names": ["batch: ndarray"],
        "session": {"active": True},
    }
    monkeypatch.setattr(actions, "wait_for_active_window", lambda *_args: window)

    def read_variables(
        _runner: FakeRunner, window_id: str, max_items: int
    ) -> dict[str, Any]:
        calls.append((window_id, max_items))
        return observed

    monkeypatch.setattr(actions, "inspect_debug_variables", read_variables)

    result = VscodeActions(runner).debug_variables_read(
        {"window_id": "0x02A00002", "max_items": 19}, 30
    )

    assert result["variables"] is observed
    assert calls == [("0x2a00002", 19)]
    assert runner.calls == [["wmctrl", "-ia", "0x02A00002"]]


def test_continue_presses_unique_accessible_control_and_observes_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    continue_action: FakeAction
    continue_node = visible_node("Continue (F5)", "push button")

    def continue_session(_name: str) -> bool:
        continue_node.name = "Pause (F6)"
        return True

    continue_action = FakeAction(["click"], continue_session)
    continue_node.actions = continue_action
    frame = visible_node(
        "Counterfactual - Visual Studio Code",
        "frame",
        [
            continue_node,
            visible_node("Stop (Shift+F5)", "push button"),
            visible_node("VARIABLES", "tree"),
        ],
    )
    install_frame(monkeypatch, frame)

    result = debug_control.continue_debug_session(FakeRunner(), "0x2a00002", 0.1)

    assert continue_action.performed == ["click"]
    assert result["before"]["phase"] == "paused"
    assert result["after"]["phase"] == "running"


def test_continue_rejects_duplicate_controls_without_pressing_either(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = FakeAction(["click"])
    second = FakeAction(["click"])
    frame = visible_node(
        "Counterfactual - Visual Studio Code",
        "frame",
        [
            visible_node("Continue (F5)", "push button", actions=first),
            visible_node("Continue", "push button", actions=second),
            visible_node("Stop (Shift+F5)", "push button"),
        ],
    )
    install_frame(monkeypatch, frame)

    with pytest.raises(AdapterError, match="observable paused session"):
        debug_control.continue_debug_session(FakeRunner(), "0x2a00002", 0.1)

    assert first.performed == []
    assert second.performed == []


def test_stop_presses_unique_accessible_control_and_observes_inactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = visible_node("Counterfactual - Visual Studio Code", "frame")
    variables = visible_node("VARIABLES", "tree")
    continue_node = visible_node("Continue (F5)", "push button")

    def stop_session(_name: str) -> bool:
        frame.children = [variables]
        return True

    stop_action = FakeAction(["press"], stop_session)
    stop_node = visible_node("Stop (Shift+F5)", "push button", actions=stop_action)
    frame.children = [continue_node, stop_node, variables]
    install_frame(monkeypatch, frame)

    result = debug_control.stop_debug_session(FakeRunner(), "0x2a00002", 0.1)

    assert stop_action.performed == ["press"]
    assert result["before"]["phase"] == "paused"
    assert result["after"]["phase"] == "inactive"


def test_session_wait_action_uses_canonical_selected_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = FakeRunner()
    window = WindowRecord(
        "0x2a00002", "code.Code", "Counterfactual - Visual Studio Code"
    )
    calls: list[tuple[str, str]] = []
    observed = {"window_id": window.window_id, "phase": "paused"}
    monkeypatch.setattr(actions, "wait_for_active_window", lambda *_args: window)

    def wait_for_state(
        _runner: FakeRunner,
        window_id: str,
        expected_state: str,
        _timeout: float,
    ) -> dict[str, Any]:
        calls.append((window_id, expected_state))
        return observed

    monkeypatch.setattr(actions, "wait_for_debug_state", wait_for_state)

    result = VscodeActions(runner).debug_session_wait(
        {"window_id": "0x02A00002", "state": "paused"}, 30
    )

    assert result["session"] is observed
    assert calls == [("0x2a00002", "paused")]
    assert runner.calls == [["wmctrl", "-ia", "0x02A00002"]]


@pytest.mark.parametrize(
    "action,bad_field",
    [
        ("debug.start", "task_id"),
        ("debug.start", "path"),
        ("debug.breakpoint.set", "task_id"),
        ("debug.session.wait", "task_id"),
        ("debug.session.wait", "path"),
        ("debug.continue", "source"),
        ("debug.stop", "expected"),
        ("debug.variables.read", "names"),
        ("debug.variables.read", "source"),
        ("debug.variables.read", "expected"),
    ],
)
def test_debug_contracts_reject_task_or_source_derived_arguments(
    action: str,
    bad_field: str,
) -> None:
    params = {"window_id": "0x2a00002", bad_field: "x"}
    if action == "debug.breakpoint.set":
        params.update({"path": "/tmp/counterfactual.py", "line": 9})
    if action == "debug.session.wait":
        params["state"] = "paused"
    with pytest.raises(AdapterError, match="unsupported parameters"):
        validate_action_params(action, params)


def test_debug_contracts_and_default_verifiers_are_atomic() -> None:
    validate_action_params(
        "debug.breakpoint.set",
        {"window_id": "0x2a00002", "path": "/tmp/counterfactual.py", "line": 9},
    )
    validate_action_params("debug.start", {"window_id": "0x2a00002"})
    validate_action_params(
        "debug.session.wait", {"window_id": "0x2a00002", "state": "paused"}
    )
    validate_action_params("debug.continue", {"window_id": "0x2a00002"})
    validate_action_params("debug.stop", {"window_id": "0x2a00002"})
    validate_action_params(
        "debug.variables.read", {"window_id": "0x2a00002", "max_items": 37}
    )
    assert STRICT_ACTION_PARAM_SCHEMAS["debug.breakpoint.set"]["required"] == [
        "window_id",
        "path",
        "line",
    ]
    assert STRICT_ACTION_PARAM_SCHEMAS["debug.start"]["required"] == ["window_id"]
    assert STRICT_ACTION_PARAM_SCHEMAS["debug.session.wait"]["required"] == [
        "window_id",
        "state",
    ]
    assert STRICT_ACTION_PARAM_SCHEMAS["debug.continue"]["required"] == ["window_id"]
    assert STRICT_ACTION_PARAM_SCHEMAS["debug.stop"]["required"] == ["window_id"]
    assert STRICT_ACTION_PARAM_SCHEMAS["debug.variables.read"]["required"] == [
        "window_id"
    ]
    assert _default_specs(
        "debug.breakpoint.set",
        {"window_id": "0x2a00002", "path": "/tmp/counterfactual.py", "line": 9},
        {
            "window_id": "0x2a00002",
            "path": "/tmp/counterfactual.py",
            "line": 9,
        },
    ) == [
        {
            "type": "vscode_breakpoint_set",
            "window_id": "0x2a00002",
            "path": "/tmp/counterfactual.py",
            "line": 9,
        }
    ]
    assert _default_specs(
        "debug.start",
        {"window_id": "0x2a00002"},
        {"window_id": "0x2a00002", "session": {"active": True}},
    ) == [{"type": "vscode_debug_session", "window_id": "0x2a00002"}]
    assert _default_specs(
        "debug.session.wait",
        {"window_id": "0x2a00002", "state": "paused"},
        {"window_id": "0x2a00002", "session": {"phase": "paused"}},
    ) == [
        {
            "type": "vscode_debug_state",
            "window_id": "0x2a00002",
            "state": "paused",
        }
    ]
    assert _default_specs(
        "debug.continue",
        {"window_id": "0x2a00002"},
        {"window_id": "0x2a00002", "after": {"phase": "running"}},
    ) == [
        {
            "type": "vscode_debug_state",
            "window_id": "0x2a00002",
            "states": ["inactive", "running"],
        }
    ]
    assert _default_specs(
        "debug.stop",
        {"window_id": "0x2a00002"},
        {"window_id": "0x2a00002", "after": {"phase": "inactive"}},
    ) == [
        {
            "type": "vscode_debug_state",
            "window_id": "0x2a00002",
            "state": "inactive",
        }
    ]
    assert _default_specs(
        "debug.variables.read",
        {"window_id": "0x2a00002", "max_items": 37},
        {
            "window_id": "0x2a00002",
            "variables": {"item_names": ["tensor: ndarray"]},
        },
    ) == [
        {
            "type": "vscode_debug_variables",
            "window_id": "0x2a00002",
            "max_items": 37,
            "item_names": ["tensor: ndarray"],
        }
    ]


def test_session_wait_rejects_absence_of_controls_as_a_requested_state() -> None:
    with pytest.raises(AdapterError, match="must be paused or running"):
        validate_action_params(
            "debug.session.wait",
            {"window_id": "0x2a00002", "state": "inactive"},
        )


def test_breakpoint_toggle_targets_only_the_explicit_file_and_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    source = tmp_path / "counterfactual.py"
    source.write_text("alpha = 1\nbeta = 2\ngamma = 3\n", encoding="utf-8")
    runner = FakeRunner()
    window = WindowRecord(
        "0x2a00002", "code.Code", "counterfactual.py - Visual Studio Code"
    )
    monkeypatch.setattr(actions, "wait_for_active_window", lambda *_args: window)
    before = {
        "breakpoints_heading_count": 1,
        "match_count": 0,
        "checked_count": 0,
    }
    after = {
        "breakpoints_heading_count": 1,
        "match_count": 1,
        "checked_count": 1,
    }
    monkeypatch.setattr(actions, "wait_for_breakpoints_view", lambda *_args: before)
    monkeypatch.setattr(actions, "wait_for_source_breakpoint", lambda *_args: after)

    result = VscodeActions(runner).debug_breakpoint_set(
        {"window_id": "0x02A00002", "path": str(source), "line": 2}, 30
    )

    assert result["path"] == str(source.resolve())
    assert result["line"] == 2
    assert result["line_text"] == "beta = 2"
    assert result["already_set"] is False
    assert result["before"] is before
    assert result["after"] is after
    assert runner.calls == [
        ["wmctrl", "-ia", "0x02A00002"],
        [
            "python3",
            "-c",
            "import pyautogui,time; pyautogui.hotkey('ctrl','shift','d'); time.sleep(1)",
        ],
        ["code", "--reuse-window", "--goto", f"{source.resolve()}:2:1"],
        ["wmctrl", "-ia", "0x2a00002"],
        ["python3", "-c", "import pyautogui; pyautogui.press('f9')"],
    ]


def test_breakpoint_toggle_rejects_a_line_beyond_the_observed_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    source = tmp_path / "short.py"
    source.write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        actions,
        "wait_for_active_window",
        lambda *_args: WindowRecord(
            "0x2a00002", "code.Code", "short.py - Visual Studio Code"
        ),
    )

    with pytest.raises(AdapterError, match="beyond end of file"):
        VscodeActions(FakeRunner()).debug_breakpoint_set(
            {"window_id": "0x2a00002", "path": str(source), "line": 2}, 30
        )
