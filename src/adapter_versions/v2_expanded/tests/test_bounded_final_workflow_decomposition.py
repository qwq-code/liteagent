from __future__ import annotations

import pytest

import vscode_adapter.actions as vscode_actions
import vscode_adapter.worker as vscode_worker
from integrations.lite_agent.action_selection import ActionSelectionMixin
from integrations.lite_agent.adapter_results import adapter_context_hint
from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.git_semantics import required_actions as git_actions
from integrations.lite_agent.terminal_capture_semantics import (
    required_actions as terminal_capture_actions,
)
from integrations.lite_agent.tool_catalog import (
    DIRECT_ACTION_SCHEMAS,
    public_actions,
    search_actions,
    select_actions,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from multi_apps_adapter.schema import ACTIONS as MULTI_APPS_ACTIONS
from multi_apps_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as MULTI_APPS_SCHEMAS,
)
from os_adapter.errors import AdapterError as OSAdapterError
from os_adapter.schema import ACTIONS as OS_ACTIONS
from os_adapter.schema import validate_action_params as validate_os
from os_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS as OS_SCHEMAS
from vscode_adapter.errors import AdapterError as VscodeAdapterError
from vscode_adapter.actions import VscodeActions
from vscode_adapter.schema import ACTIONS as VSCODE_ACTIONS
from vscode_adapter.schema import parse_action_request as parse_vscode_request
from vscode_adapter.schema import validate_action_params as validate_vscode
from vscode_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS as VSCODE_SCHEMAS


RETIRED_MULTI_APPS_WORKFLOWS = {
    "git.commit_and_push",
    "terminal.capture_command_screenshot",
}
RETIRED_VSCODE_WORKFLOWS = {
    "ui.show_array_variables",
    "workspace.add_folders_to_active",
    "workspace.save_current_project",
}
MULTI_APPS_PRIMITIVES = {"adapter.call"}
VSCODE_PRIMITIVES = {
    "file.read_text",
    "editor.open_file",
    "ui.open_view",
    "ui.expand_section",
    "workspace.inspect",
    "workspace.add_folders",
    "workspace.write",
}


def test_retired_workflows_are_absent_and_primitives_are_public() -> None:
    multi_apps_surfaces = (
        set(MULTI_APPS_ACTIONS),
        set(MULTI_APPS_SCHEMAS),
        set(DIRECT_ACTION_SCHEMAS["multi_apps"]),
        set(public_actions("multi_apps")),
    )
    os_surfaces = (
        set(OS_ACTIONS),
        set(OS_SCHEMAS),
        set(DIRECT_ACTION_SCHEMAS["os"]),
        set(public_actions("os")),
    )
    vscode_surfaces = (
        set(VSCODE_ACTIONS),
        set(VSCODE_SCHEMAS),
        set(DIRECT_ACTION_SCHEMAS["vs_code"]),
        set(public_actions("vs_code")),
    )

    assert all(
        RETIRED_MULTI_APPS_WORKFLOWS.isdisjoint(surface)
        for surface in multi_apps_surfaces
    )
    assert set(MULTI_APPS_ACTIONS) == MULTI_APPS_PRIMITIVES
    assert set(MULTI_APPS_SCHEMAS) == MULTI_APPS_PRIMITIVES
    assert set(DIRECT_ACTION_SCHEMAS["multi_apps"]) == MULTI_APPS_PRIMITIVES
    assert DIRECT_ACTION_SCHEMAS["multi_apps"] == MULTI_APPS_SCHEMAS
    assert set(public_actions("multi_apps")) == MULTI_APPS_PRIMITIVES
    assert all(
        "terminal.capture_command_screenshot" not in surface for surface in os_surfaces
    )
    assert all(
        {"terminal.show_output", "window.capture"}.issubset(surface)
        for surface in os_surfaces
    )
    assert all(
        RETIRED_VSCODE_WORKFLOWS.isdisjoint(surface) for surface in vscode_surfaces
    )
    assert all(VSCODE_PRIMITIVES.issubset(surface) for surface in vscode_surfaces)


def test_multi_apps_exposes_adapter_call_only_after_catalog_search() -> None:
    selector = ActionSelectionMixin()
    selector.config = type("Config", (), {"top_k_actions": 7})()
    state = RuntimeState(
        task_id="synthetic-multi-app-search",
        domain="multi_apps",
        instruction="Crop the image on the Desktop.",
    )

    assert selector.selected_actions(state) == []
    matches = search_actions(
        "multi_apps",
        "crop image",
        instruction=state.instruction,
        strict_generic=True,
    )
    assert matches
    assert {item["action"] for item in matches} == {"adapter.call"}
    state.expanded_actions = [item["action"] for item in matches]
    assert selector.selected_actions(state) == ["adapter.call"]


def test_failed_debug_start_exposes_public_extension_install_recovery() -> None:
    selector = ActionSelectionMixin()
    selector.config = type("Config", (), {"top_k_actions": 7})()
    state = RuntimeState(
        task_id="synthetic-debug-dependency-recovery",
        domain="vs_code",
        instruction="Visualize the runtime arrays in the open Python file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-09-08T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__debug_start",
                    "action": "debug.start",
                    "arguments": {"window_id": "0x2a00002"},
                },
                executed=False,
                error={
                    "code": "VSCODE_NOT_READY",
                    "message": "VS Code did not expose an active debug session",
                },
            )
        ],
    )

    selected = selector.selected_actions(state)

    assert "extension.install" in selected
    assert len(selected) <= 7


def test_multi_apps_completion_recovery_keeps_only_discovered_persist_readback_routes() -> None:
    state = RuntimeState(
        task_id="synthetic-route-recovery",
        domain="multi_apps",
        instruction="Update the current workbook and save it.",
        completion_rejections=1,
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-09-03T00:00:00Z",
                proposed={
                    "kind": "catalog",
                    "tool": "tools_search",
                    "action": "tools_search",
                    "arguments": {"query": "workbook range save inspect"},
                },
                executed=True,
                result={
                    "matches": [
                        {
                            "action": "adapter.call",
                            "adapter": "libreoffice_calc",
                            "downstream_action": route,
                        }
                        for route in (
                            "range.write",
                            "workbook.save",
                            "workbook.inspect",
                        )
                    ]
                },
            ),
            ExecutionEvent(
                step=2,
                timestamp_utc="2026-09-03T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__adapter_call",
                    "action": "adapter.call",
                    "arguments": {
                        "adapter": "libreoffice_calc",
                        "action": "range.write",
                        "payload": {
                            "params": {
                                "sheet": "Sheet1",
                                "range": "A1",
                                "values": [["updated"]],
                            }
                        },
                    },
                },
                executed=True,
                result={"status": "ok"},
            ),
            ExecutionEvent(
                step=3,
                timestamp_utc="2026-09-03T00:00:00Z",
                proposed={"kind": "completion", "tool": "propose_done"},
                executed=False,
                error={"status": "rejected"},
            ),
        ],
    )

    gate = CompletionMixin._generic_completion_gate(state)
    assert "save" in " ".join(gate["missing"])
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        type("Executor", (), {"execute": lambda *_args, **_kwargs: {}})(),
    )
    tools = agent.tools(state)
    names = {tool["function"]["name"] for tool in tools}
    assert "adapter__adapter_call" in names
    assert "adapter__spreadsheet_save" not in names
    route_tool = next(
        tool for tool in tools if tool["function"]["name"] == "adapter__adapter_call"
    )
    routes = {
        branch["properties"]["action"]["enum"][0]
        for branch in route_tool["function"]["parameters"]["oneOf"]
    }
    assert routes == {"workbook.save", "workbook.inspect"}


def test_git_transaction_recall_exposes_only_the_command_primitive() -> None:
    instruction = (
        "Commit the observed repository changes and push them to the named branch."
    )

    assert git_actions("multi_apps", instruction) == []
    assert git_actions("os", instruction) == ["command.run"]


def test_terminal_capture_requires_two_independent_model_calls() -> None:
    instruction = (
        "Run uname -a in a terminal and save a screenshot of that window to "
        "/tmp/audit-2039.png."
    )

    assert terminal_capture_actions("multi_apps", instruction) == []
    assert terminal_capture_actions("os", instruction) == [
        "terminal.show_output",
        "window.capture",
    ]
    validate_os(
        "terminal.show_output",
        {
            "argv": ["uname", "-a"],
            "cwd_source": "home",
            "provenance": "shell_history",
        },
    )
    validate_os(
        "window.capture",
        {
            "title_contains": "Terminal - audit-2039",
            "output_path": "/tmp/audit-2039.png",
            "overwrite": False,
        },
    )


def test_window_capture_rejects_command_execution_arguments() -> None:
    with pytest.raises(OSAdapterError):
        validate_os(
            "window.capture",
            {
                "title_contains": "Terminal - counterfactual",
                "output_path": "/tmp/counterfactual.png",
                "argv": ["uname", "-a"],
            },
        )


def test_vscode_ui_primitives_require_explicit_observed_handles() -> None:
    validate_vscode(
        "editor.open_file",
        {"path": "/tmp/project-2040/arrays.py", "reuse_window": True},
    )
    validate_vscode(
        "ui.open_view",
        {"window_id": "0x04A00007", "view": "run_and_debug"},
    )
    validate_vscode(
        "ui.expand_section",
        {"window_id": "0x04A00007", "name": "Variables"},
    )

    with pytest.raises(VscodeAdapterError):
        validate_vscode(
            "ui.expand_section",
            {
                "window_id": "0x04A00007",
                "name": "Variables",
                "names": ["arr", "matrix"],
            },
        )


def test_vscode_workspace_inspect_is_read_only_and_returns_exact_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = {
        "window_id": "0x04A00007",
        "window_title": "project - Visual Studio Code",
        "window_classes": ["code.Code"],
        "workspace_name": "project",
        "workspace_roots": ["/home/user/project"],
        "resolution_source": "workspace_storage",
    }
    saved = {**observed, "workspace_file": "/home/user/project.code-workspace"}
    runner = object()
    writes: list[tuple[object, ...]] = []

    def resolve(actual_runner: object) -> dict[str, object]:
        assert actual_runner is runner
        return observed

    monkeypatch.setattr(vscode_actions, "resolve_active_workspace", resolve)
    monkeypatch.setattr(
        vscode_actions,
        "resolve_active_workspace_file",
        lambda actual_runner: saved if actual_runner is runner else {},
    )
    monkeypatch.setattr(
        vscode_actions,
        "atomic_write_json",
        lambda *args: writes.append(args),
    )

    result = VscodeActions(runner).workspace_inspect({}, 10)

    assert result == saved
    assert writes == []
    validate_vscode("workspace.inspect", {})
    parsed = parse_vscode_request({"action": "workspace.inspect", "params": {}})
    assert parsed.params == {}
    with pytest.raises(VscodeAdapterError, match="does not accept parameters"):
        validate_vscode("workspace.inspect", {"path": "/tmp/project.code-workspace"})

    manifest = VSCODE_SCHEMAS["workspace.inspect"]
    assert manifest["properties"] == {}
    assert manifest["required"] == []
    assert DIRECT_ACTION_SCHEMAS["vs_code"]["workspace.inspect"] == manifest

    projected = adapter_context_hint(
        "vs_code",
        "workspace.inspect",
        {"result": result, "verification": {"passed": True}},
    )
    assert projected is not None
    assert {key: projected[key] for key in saved} == saved
    assert "workspace.write" in projected["guidance"]


def test_vscode_workspace_inspect_worker_evidence_and_retired_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = {
        "window_id": "0x04A00007",
        "window_title": "project - Visual Studio Code",
        "window_classes": ["code.Code"],
        "workspace_name": "project",
        "workspace_roots": ["/home/user/project"],
        "resolution_source": "workspace_storage",
    }
    monkeypatch.setattr(
        vscode_actions,
        "resolve_active_workspace",
        lambda _runner: observed,
    )
    monkeypatch.setattr(
        vscode_actions,
        "resolve_active_workspace_file",
        lambda _runner: {
            **observed,
            "workspace_file": "/home/user/project.code-workspace",
        },
    )
    execution = vscode_worker.execute(
        {"action": "workspace.inspect", "params": {}, "timeout_ms": 45_000}
    )

    assert execution["result"]["workspace_file"] == "/home/user/project.code-workspace"
    assert execution["verification"]["passed"] is True
    assert execution["verification"]["observed_state"] == execution["result"]

    for action, method in (
        ("workspace.save_current_project", "workspace_save_current_project"),
        ("workspace.add_folders_to_active", "workspace_add_folders_to_active"),
    ):
        with pytest.raises(VscodeAdapterError) as parsed_error:
            parse_vscode_request({"action": action, "params": {}})
        assert parsed_error.value.code == "UNSUPPORTED_ACTION"
        assert not hasattr(VscodeActions, method)
        with pytest.raises(VscodeAdapterError, match="unsupported VS Code action"):
            VscodeActions(object()).dispatch(action, {}, 10)


def test_search_recalls_atomic_replacements_without_retired_workflows() -> None:
    git_matches = {
        item["action"]
        for item in search_actions(
            "os",
            "commit and push repository changes with git commands",
            instruction="Commit and push repository changes with git commands.",
            limit=10,
            strict_generic=True,
        )
    }
    terminal_matches = {
        item["action"]
        for item in search_actions(
            "os",
            "run command in terminal and save the window screenshot as PNG",
            instruction=(
                "Run a command in a terminal and save its window screenshot to "
                "/tmp/counterfactual.png."
            ),
            limit=10,
            strict_generic=True,
        )
    }
    vscode_matches = {
        item["action"]
        for item in search_actions(
            "vs_code",
            "open a source file then open debug view and expand variables section",
            instruction="Open a source file, open the debug view, and expand Variables.",
            limit=10,
            strict_generic=True,
        )
    }

    assert "command.run" in git_matches
    assert {"terminal.show_output", "window.capture"}.issubset(terminal_matches)
    assert {"editor.open_file", "ui.open_view", "ui.expand_section"}.issubset(
        vscode_matches
    )
    assert RETIRED_MULTI_APPS_WORKFLOWS.isdisjoint(git_matches | terminal_matches)
    assert RETIRED_VSCODE_WORKFLOWS.isdisjoint(vscode_matches)


@pytest.mark.parametrize(
    "query",
    [
        "inspect the values of the array in the debugger",
        "read numpy array variables while paused",
        "visualize variables in debug session",
    ],
)
def test_search_recalls_existing_debug_variables_read_for_array_observation(query) -> None:
    matches = search_actions(
        "vs_code",
        query,
        limit=6,
        strict_generic=True,
    )

    assert matches
    assert matches[0]["action"] == "debug.variables.read"


@pytest.mark.parametrize(
    "instruction",
    [
        "Show the arrays from the currently open source file in the debugger.",
        "Inspect runtime variables from this Python program in VS Code.",
        "Visualize runtime arrays in the active script.",
    ],
)
def test_initial_debug_surface_includes_session_start(instruction: str) -> None:
    selected = select_actions("vs_code", instruction, limit=7)

    assert "debug.start" in selected
    assert "debug.variables.read" in selected
    assert "ui.show_array_variables" not in selected


def test_debug_ui_descriptions_explain_session_prerequisites() -> None:
    assert "use debug.start" in VSCODE_SCHEMAS["ui.open_view"]["description"]
    assert "SECTION_NOT_FOUND" in VSCODE_SCHEMAS["ui.expand_section"]["description"]
    assert "extension.install" in VSCODE_SCHEMAS["debug.start"]["description"]
