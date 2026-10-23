from __future__ import annotations

import json
from types import SimpleNamespace

import jsonschema
import pytest

from vscode_adapter.actions import VscodeActions
from vscode_adapter.errors import AdapterError
from vscode_adapter.schema import validate_action_params
from vscode_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from integrations.lite_agent.vscode_workspace_context import (
    constrain_workspace_add_tools,
    has_successful_workspace_inspect,
    has_verified_workspace_addition,
    observed_workspace_file,
    requests_workspace_folder_addition,
)


def _schema(action: str) -> dict:
    return STRICT_ACTION_PARAM_SCHEMAS[action]


def test_order183_workspace_add_preserves_existing_state(tmp_path) -> None:
    path = tmp_path / "project.code-workspace"
    path.write_text(
        json.dumps(
            {
                "folders": [{"path": "project"}],
                "settings": {"editor.wordWrap": "on"},
            }
        ),
        encoding="utf-8",
    )
    params = {
        "path": str(path),
        "folders": [
            {"path": str(tmp_path / "data1")},
            {"path": str(tmp_path / "data2")},
        ],
    }
    jsonschema.Draft202012Validator(_schema("workspace.add_folders")).validate(
        params
    )
    validate_action_params("workspace.add_folders", params)

    result = VscodeActions().workspace_add_folders(params, 45.0)

    assert result["added_folders"] == [{"path": "data1"}, {"path": "data2"}]
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["folders"] == [
        {"path": "project"},
        {"path": "data1"},
        {"path": "data2"},
    ]
    assert saved["settings"] == {"editor.wordWrap": "on"}


def test_order183_workspace_add_rejects_missing_folders() -> None:
    params = {"path": "/home/user/project.code-workspace"}
    assert not jsonschema.Draft202012Validator(
        _schema("workspace.add_folders")
    ).is_valid(params)
    with pytest.raises(AdapterError, match="params.folders"):
        validate_action_params("workspace.add_folders", params)


def test_order183_workspace_add_resolves_observed_active_root(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    workspace_file = tmp_path / "project.code-workspace"
    workspace_file.write_text(
        json.dumps({"folders": [{"path": "project"}], "settings": {}}),
        encoding="utf-8",
    )
    active = {
        "window_id": "0x01",
        "workspace_name": "project",
        "workspace_file": str(workspace_file),
        "workspace_roots": [str(root)],
        "resolution_source": "workspace_storage",
    }
    monkeypatch.setattr(
        "vscode_adapter.actions.resolve_active_workspace_file",
        lambda _runner: active,
    )

    result = VscodeActions(object()).workspace_add_folders(
        {
            "path": str(root),
            "folders": [{"path": str(tmp_path / "data1")}],
        },
        45.0,
    )

    assert result["path"] == str(workspace_file)
    assert result["resolution_source"] == "active_workspace_root"
    assert json.loads(workspace_file.read_text(encoding="utf-8"))["folders"] == [
        {"path": "project"},
        {"path": "data1"},
    ]


def test_workspace_add_omits_redundant_display_name_but_keeps_custom_name(
    tmp_path,
) -> None:
    path = tmp_path / "project.code-workspace"
    path.write_text(json.dumps({"folders": [{"path": "project"}]}), encoding="utf-8")

    result = VscodeActions().workspace_add_folders(
        {
            "path": str(path),
            "folders": [
                {"path": str(tmp_path / "data1"), "name": "data1"},
                {"path": str(tmp_path / "data2"), "name": "Research"},
            ],
        },
        45.0,
    )

    assert result["workspace"]["folders"] == [
        {"path": "project"},
        {"path": "data1"},
        {"path": "data2", "name": "Research"},
    ]


def test_order183_workspace_add_rejects_unobserved_directory(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    workspace_file = tmp_path / "project.code-workspace"
    workspace_file.write_text(json.dumps({"folders": [{"path": "project"}]}), encoding="utf-8")
    monkeypatch.setattr(
        "vscode_adapter.actions.resolve_active_workspace_file",
        lambda _runner: {
            "workspace_file": str(workspace_file),
            "workspace_roots": [str(root)],
        },
    )

    with pytest.raises(AdapterError, match="not an observed root"):
        VscodeActions(object()).workspace_add_folders(
            {"path": str(other), "folders": [{"path": str(tmp_path / "data1")}]},
            45.0,
        )


def test_order183_instruction_stage_recognizes_addition_after_inspect() -> None:
    instruction = (
        'Please help me add folder "/home/user/data1" and folder '
        '"/home/user/data2" to the current workspace.'
    )
    event = SimpleNamespace(
        executed=True,
        error=None,
        proposed={"action": "workspace.inspect"},
    )

    assert requests_workspace_folder_addition(instruction)
    assert has_successful_workspace_inspect(SimpleNamespace(events=[event]))


def test_order183_model_surface_binds_observed_workspace_file_and_drops_search() -> None:
    workspace_file = "/home/user/project.code-workspace"
    event = SimpleNamespace(
        executed=True,
        error=None,
        proposed={"action": "workspace.inspect"},
        result={"context_hint": {"workspace_file": workspace_file}},
    )
    state = SimpleNamespace(
        domain="vs_code",
        instruction=(
            'Please help me add folder "/home/user/data1" and folder '
            '"/home/user/data2" to the current workspace.'
        ),
        events=[event],
        latest_context_hint=lambda _action: {"workspace_file": workspace_file},
    )
    tools = [
        {"function": {"name": "adapter__workspace_add_folders", "parameters": {
            "type": "object", "properties": {"path": {"type": "string"}},
        }}},
        {"function": {"name": "adapter__workspace_find_files", "parameters": {}}},
        {"function": {"name": "tools_search", "parameters": {}}},
        {"function": {"name": "propose_done", "parameters": {}}},
    ]
    constrained = constrain_workspace_add_tools(tools, state)
    assert [tool["function"]["name"] for tool in constrained] == [
        "adapter__workspace_add_folders",
        "propose_done",
    ]
    assert constrained[0]["function"]["parameters"]["properties"]["path"]["const"] == workspace_file
    assert observed_workspace_file(state) == workspace_file


def test_order183_model_surface_omits_unrequested_folder_names() -> None:
    workspace_file = "/home/user/project.code-workspace"
    event = SimpleNamespace(
        executed=True,
        error=None,
        proposed={"action": "workspace.inspect"},
    )
    state = SimpleNamespace(
        domain="vs_code",
        instruction=(
            'Please help me add folder "/home/user/data1" and folder '
            '"/home/user/data2" to the current workspace.'
        ),
        events=[event],
        latest_context_hint=lambda _action: {"workspace_file": workspace_file},
    )
    tool = {"function": {"name": "adapter__workspace_add_folders", "parameters": {
        "type": "object", "properties": {
            "path": {"type": "string"},
            "folders": {"type": "array", "items": {"type": "object", "properties": {
                "path": {"type": "string"}, "name": {"type": "string"}
            }, "required": ["path", "name"]}}
        }
    }}}
    constrained = constrain_workspace_add_tools([tool], state)
    item = constrained[0]["function"]["parameters"]["properties"]["folders"]["items"]
    assert "name" not in item["properties"]
    assert item["required"] == ["path"]


def test_order183_verified_addition_closes_mutation_surface() -> None:
    from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
    from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState

    state = RuntimeState(
        task_id="synthetic-workspace-addition",
        domain="vs_code",
        instruction=(
            'Please help me add folder "/home/user/data1" and folder '
            '"/home/user/data2" to the current workspace.'
        ),
        events=[ExecutionEvent(
            step=1,
            timestamp_utc="2026-10-09T00:00:00Z",
            proposed={"kind": "adapter", "action": "workspace.add_folders", "arguments": {
                "path": "/home/user/project.code-workspace",
                "folders": [{"path": "/home/user/data1"}, {"path": "/home/user/data2"}],
            }},
            executed=True,
            result={"adapter_response": {"verification": {"passed": True}}},
        )],
    )
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        type("Executor", (), {"execute": lambda *_args, **_kwargs: {}})(),
    )
    assert has_verified_workspace_addition(state)
    assert {tool["function"]["name"] for tool in agent.tools(state)} == {
        "propose_done", "fail_task",
    }


def test_workspace_add_verified_result_exposes_completion_only() -> None:
    inspect = SimpleNamespace(
        executed=True, error=None, proposed={"action": "workspace.inspect"}
    )
    addition = SimpleNamespace(
        executed=True,
        error=None,
        proposed={"action": "workspace.add_folders"},
        result={"adapter_response": {"verification": {"passed": True}}},
    )
    state = SimpleNamespace(
        domain="vs_code",
        instruction="Add the selected folders to the current workspace.",
        events=[inspect, addition],
    )
    tools = [
        {"function": {"name": "adapter__workspace_add_folders"}},
        {"function": {"name": "tools_search"}},
        {"function": {"name": "propose_done"}},
        {"function": {"name": "fail_task"}},
    ]

    assert [
        tool["function"]["name"] for tool in constrain_workspace_add_tools(tools, state)
    ] == ["propose_done", "fail_task"]


def test_order185_files_configure_accepts_coupled_autosave_settings(tmp_path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"editor.wordWrap": "on"}), encoding="utf-8"
    )
    params = {
        "path": str(settings_path),
        "auto_save": "after_delay",
        "auto_save_delay_ms": 500,
    }
    jsonschema.Draft202012Validator(_schema("files.configure")).validate(params)
    validate_action_params("files.configure", params)
    result = VscodeActions().files_configure(params, 45.0)

    assert result["configured"] == {
        "auto_save": "after_delay",
        "auto_save_delay_ms": 500,
    }
    assert json.loads(settings_path.read_text(encoding="utf-8")) == {
        "editor.wordWrap": "on",
        "files.autoSave": "afterDelay",
        "files.autoSaveDelay": 500,
    }


def test_order185_files_configure_rejects_independent_settings_together() -> None:
    params = {"auto_save": "after_delay", "auto_save_delay_ms": 500, "hot_exit": "off"}
    assert not jsonschema.Draft202012Validator(_schema("files.configure")).is_valid(params)
    with pytest.raises(AdapterError, match="exactly one semantic setting"):
        validate_action_params("files.configure", params)
