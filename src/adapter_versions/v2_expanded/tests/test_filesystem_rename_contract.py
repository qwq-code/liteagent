from pathlib import Path

import jsonschema
import pytest
from types import SimpleNamespace

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.execution_engine import ExecutionEngineMixin
from integrations.lite_agent.state_model import RuntimeState

from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS
from os_adapter.actions import OSActions
from os_adapter.errors import AdapterError
from os_adapter.schema import validate_action_params
from os_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


def test_rename_rejects_same_absolute_path(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")

    arguments = {"source": str(source), "destination": str(source)}
    validate_action_params("filesystem.rename", arguments)

    with pytest.raises(AdapterError, match="destination must differ from source"):
        OSActions().rename(arguments, 1)
    assert source.read_text(encoding="utf-8") == "payload"


def test_rename_rejects_path_alias_of_source(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")

    arguments = {
        "source": str(source),
        "destination": str(tmp_path / "nested" / ".." / "source.txt"),
    }
    validate_action_params("filesystem.rename", arguments)

    with pytest.raises(AdapterError, match="destination must differ from source"):
        OSActions().rename(arguments, 1)


def test_rename_rejects_same_inode_even_when_replace_requested(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    alias = tmp_path / "alias.txt"
    source.write_text("payload", encoding="utf-8")
    alias.hardlink_to(source)

    arguments = {
        "source": str(source),
        "destination": str(alias),
        "replace": True,
    }
    validate_action_params("filesystem.rename", arguments)

    with pytest.raises(AdapterError, match="same inode"):
        OSActions().rename(arguments, 1)
    assert source.exists()
    assert alias.exists()


def test_rename_keeps_new_destination_semantics(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "renamed.txt"
    source.write_text("payload", encoding="utf-8")

    result = OSActions().rename(
        {"source": str(source), "destination": str(destination)}, 1
    )

    assert result == {
        "source": str(source),
        "destination": str(destination),
    }
    assert not source.exists()
    assert destination.read_text(encoding="utf-8") == "payload"


def test_rename_accepts_basename_pair_with_explicit_search_root(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")
    arguments = {
        "source_query": source.name,
        "new_name": "renamed.txt",
        "search_roots": [str(tmp_path)],
    }

    validate_action_params("filesystem.rename", arguments)
    result = OSActions().rename(arguments, 1)
    assert result["source"] == str(source)
    assert result["destination"] == str(tmp_path / "renamed.txt")
    assert (tmp_path / "renamed.txt").read_text(encoding="utf-8") == "payload"

def _object_schema(properties: dict) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": ["source", "destination"],
        "additionalProperties": False,
    }


def test_public_rename_schemas_share_non_root_path_contract() -> None:
    os_properties = STRICT_ACTION_PARAM_SCHEMAS["filesystem.rename"]["properties"]
    rename_properties = DIRECT_ACTION_SCHEMAS["os"]["filesystem.rename"]["properties"]

    assert DIRECT_ACTION_SCHEMAS["os"]["filesystem.rename"] == (
        STRICT_ACTION_PARAM_SCHEMAS["filesystem.rename"]
    )
    assert set(os_properties) == {"source", "destination", "source_query", "new_name", "search_roots", "replace"}
    assert rename_properties["source"]["pattern"] == os_properties["source"]["pattern"]
    assert (
        rename_properties["destination"]["pattern"]
        == os_properties["destination"]["pattern"]
    )

    invalid = {"source": "~/", "destination": "/tmp/renamed.txt"}
    for properties in (os_properties, rename_properties):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, _object_schema(properties))


def test_rename_compatibility_schema_without_top_level_required_is_validated() -> None:
    ExecutionEngineMixin._validate_adapter_arguments(
        "os",
        "filesystem.rename",
        {"source": "todo_list_Jan_1", "destination": "todo_list_Jan_2"},
    )


def test_initial_rename_surface_exposes_only_the_mutation() -> None:
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
        SimpleNamespace(execute=lambda *_args, **_kwargs: None),
    )
    state = RuntimeState(
        task_id="synthetic-rename-surface",
        domain="os",
        instruction='Rename the directory "todo_list_Jan_1" to "todo_list_Jan_2".',
        events=[],
    )
    try:
        names = [tool["function"]["name"] for tool in agent.tools(state)]
        assert names == ["adapter__filesystem_rename"]
    finally:
        agent.client.close()


def test_successful_rename_surface_requires_structural_readback() -> None:
    from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
    from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState

    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
        SimpleNamespace(execute=lambda *_args, **_kwargs: None),
    )
    state = RuntimeState(
        task_id="synthetic-rename-readback",
        domain="os",
        instruction='Rename the directory "todo_list_Jan_1" to "todo_list_Jan_2".',
        events=[
            ExecutionEvent(
                step=1, timestamp_utc="x",
                proposed={"kind": "adapter", "action": "filesystem.rename", "arguments": {}},
                validated=True, executed=True,
                result={"source": "/home/u/Desktop/todo_list_Jan_1", "destination": "/home/u/Desktop/todo_list_Jan_2"},
            )
        ],
    )
    try:
        assert [tool["function"]["name"] for tool in agent.tools(state)] == [
            "adapter__filesystem_find"
        ]
        state.events.append(
            ExecutionEvent(
                step=2, timestamp_utc="x",
                proposed={"kind": "adapter", "action": "filesystem.find", "arguments": {}},
                validated=True, executed=True,
                result={"matches": [{"path": "/home/u/Desktop/todo_list_Jan_2"}]},
            )
        )
        assert [tool["function"]["name"] for tool in agent.tools(state)] == [
            "propose_done", "fail_task"
        ]
    finally:
        agent.client.close()


def test_strict_model_rename_surface_is_compact() -> None:
    from integrations.lite_agent.tool_catalog import build_tools

    tools = build_tools(
        "os", ["filesystem.rename"], include_gui=False,
        include_control_tools=False, strict_generic=True,
    )
    parameters = tools[0]["function"]["parameters"]
    assert set(parameters["properties"]) == {"source", "destination", "replace"}
    assert parameters["required"] == ["source", "destination"]
    assert "oneOf" not in parameters


@pytest.mark.parametrize(
    "source, destination",
    [
        ("/", "/tmp/renamed.txt"),
        ("~/", "/tmp/renamed.txt"),
        ("~", "/tmp/renamed.txt"),
        ("/.", "/tmp/renamed.txt"),
        ("/..", "/tmp/renamed.txt"),
        ("~/.", "/tmp/renamed.txt"),
        ("~/..", "/tmp/renamed.txt"),
        ("/tmp/source.txt", "/"),
        ("/tmp/source.txt", "~/"),
        ("/tmp/source.txt", "~"),
        ("/tmp/source.txt", "/."),
        ("/tmp/source.txt", "/.."),
        ("/tmp/source.txt", "~/./"),
        ("/tmp/source.txt", "~/../"),
    ],
)
def test_os_schema_rejects_root_aliases(source: str, destination: str) -> None:
    with pytest.raises(AdapterError):
        validate_action_params(
            "filesystem.rename", {"source": source, "destination": destination}
        )


def test_rename_schema_rejects_nested_relative_targeting() -> None:
    for params in (
        {"source": "source/name", "destination": "renamed.txt"},
        {"source_query": "source/name", "new_name": "renamed-file"},
        {"source": "/tmp/source.txt", "destination": "renamed.txt", "source_query": "old", "new_name": "new"},
        {"source": "source.txt", "destination": "renamed.txt", "search_roots": ["relative"]},
    ):
        with pytest.raises(AdapterError):
            validate_action_params("filesystem.rename", params)


def test_rename_accepts_source_basename_and_exact_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "nested" / "renamed.txt"
    source.write_text("payload", encoding="utf-8")
    arguments = {
        "source": source.name,
        "destination": str(destination),
        "search_roots": [str(tmp_path)],
    }

    validate_action_params("filesystem.rename", arguments)
    result = OSActions().rename(arguments, 1)
    assert result["destination"] == str(destination)
    assert destination.read_text(encoding="utf-8") == "payload"


def test_rename_rejects_ambiguous_basename(tmp_path: Path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    (first / "same-name").mkdir()
    (second / "same-name").mkdir()

    arguments = {
        "source": "same-name",
        "destination": "renamed-name",
        "search_roots": [str(tmp_path)],
    }
    validate_action_params("filesystem.rename", arguments)
    with pytest.raises(AdapterError, match="multiple filesystem objects"):
        OSActions().rename(arguments, 1)

def test_runtime_rejects_root_and_home_without_mutating(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")
    home = str(Path.home())

    for source_value, destination_value in (
        ("/", str(tmp_path / "renamed.txt")),
        ("~/", str(tmp_path / "renamed.txt")),
        (home, str(tmp_path / "renamed.txt")),
        (str(source), "/"),
        (str(source), "~/"),
        (str(source), home),
    ):
        with pytest.raises(AdapterError):
            OSActions().rename(
                {
                    "source": source_value,
                    "destination": destination_value,
                    "replace": True,
                },
                1,
            )
    assert source.read_text(encoding="utf-8") == "payload"


def test_rename_replaces_a_distinct_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "renamed.txt"
    source.write_text("new payload", encoding="utf-8")
    destination.write_text("old payload", encoding="utf-8")

    result = OSActions().rename(
        {"source": str(source), "destination": str(destination), "replace": True},
        1,
    )

    assert result["destination"] == str(destination)
    assert not source.exists()
    assert destination.read_text(encoding="utf-8") == "new payload"
