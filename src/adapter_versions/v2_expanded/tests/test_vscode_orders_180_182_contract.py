import jsonschema
import pytest

from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS
from vscode_adapter.errors import AdapterError
from vscode_adapter.schema import validate_action_params
from vscode_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


def _schemas(action: str):
    return (
        STRICT_ACTION_PARAM_SCHEMAS[action],
        DIRECT_ACTION_SCHEMAS["vs_code"][action],
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("word_wrap_column", 50),
        ("wrap_tabs", True),
    ],
)
def test_orders_180_181_accept_one_editor_setting(field: str, value: object) -> None:
    params = {field: value}
    for schema in _schemas("editor.configure"):
        jsonschema.Draft202012Validator(schema).validate(params)
    validate_action_params("editor.configure", params)


def test_editor_configure_rejects_multiple_independent_settings() -> None:
    params = {"word_wrap_column": 50, "wrap_tabs": True}
    for schema in _schemas("editor.configure"):
        assert not jsonschema.Draft202012Validator(schema).is_valid(params)
    with pytest.raises(AdapterError, match="editor.configure accepts"):
        validate_action_params("editor.configure", params)


def test_editor_configure_rejects_empty_setting_request() -> None:
    with pytest.raises(AdapterError, match="exactly one documented editor setting"):
        validate_action_params("editor.configure", {})


@pytest.mark.parametrize("action", ["workspace.write", "workspace.set_folders"])
def test_order182_workspace_write_requires_structured_destination_and_folders(
    action: str,
) -> None:
    params = {
        "path": "/home/user/project/project.code-workspace",
        "folders": [{"path": "/home/user/project"}],
    }
    for schema in _schemas(action):
        jsonschema.Draft202012Validator(schema).validate(params)
    validate_action_params(action, params)


@pytest.mark.parametrize("action", ["workspace.write", "workspace.set_folders"])
@pytest.mark.parametrize(
    "path",
    [
        ".code-workspace",
        "project.code-workspace",
        "relative/project.code-workspace",
        "~/project.code-workspace",
    ],
)
def test_workspace_write_rejects_relative_destination(action: str, path: str) -> None:
    params = {"path": path, "folders": [{"path": "/home/user/project"}]}
    for schema in _schemas(action):
        assert not jsonschema.Draft202012Validator(schema).is_valid(params)
    with pytest.raises(AdapterError, match="absolute .code-workspace filename"):
        validate_action_params(action, params)


def test_order182_workspace_write_rejects_missing_folders() -> None:
    params = {"path": "/home/user/project/project.code-workspace"}
    for schema in _schemas("workspace.write"):
        assert not jsonschema.Draft202012Validator(schema).is_valid(params)
    with pytest.raises(AdapterError, match="params.folders"):
        validate_action_params("workspace.write", params)


def test_order182_workspace_write_rejects_directory_destination() -> None:
    params = {
        "path": "/home/user/project/",
        "folders": [{"path": "/home/user/project"}],
    }
    for schema in _schemas("workspace.write"):
        assert not jsonschema.Draft202012Validator(schema).is_valid(params)
    with pytest.raises(AdapterError, match="complete .code-workspace filename"):
        validate_action_params("workspace.write", params)
