from types import SimpleNamespace

import pytest

from integrations.lite_agent.agent import LiteAgent
from integrations.lite_agent.state_model import RuntimeState
from integrations.lite_agent.tool_catalog import build_tools, select_actions


@pytest.mark.parametrize("instruction", [
    'Create a new Python file named "example.py" in the selected directory.',
    'Help me create a text file in VS Code and save it on the Desktop.',
    'Create a shell script for the new project.',
])
def test_new_file_creation_reaches_model_without_existing_workspace(instruction):
    agent = object.__new__(LiteAgent)
    agent.config = SimpleNamespace(top_k_actions=7)
    state = RuntimeState(task_id="synthetic-create", domain="vs_code", instruction=instruction)
    tools = build_tools("vs_code", agent.selected_actions(state), include_gui=True)
    creation = next(t["function"] for t in tools if t["function"]["name"] == "adapter__file_create")
    # Discovery must leave selection and values to the model, without inventing
    # a workspace, output path, contents, or overwrite permission.
    assert "const" not in creation["parameters"]["properties"]["path"]
    assert state.events == []


@pytest.mark.parametrize("instruction", [
    "Fix the existing Python file without creating another file.",
    "Create a folder for the new project.",
])
def test_unrelated_requests_do_not_promote_file_creation_above_inspection(instruction):
    actions = select_actions("vs_code", instruction)
    assert actions[0] != "file.create"
