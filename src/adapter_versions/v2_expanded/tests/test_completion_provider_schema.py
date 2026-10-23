import jsonschema
from types import SimpleNamespace

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.model_client import _provider_tools
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools


def test_provider_completion_evidence_has_supported_string_schema() -> None:
    tool = next(
        tool for tool in build_tools(
            "os", [], include_gui=False, include_control_tools=True,
            strict_generic=True,
        )
        if tool["function"]["name"] == "propose_done"
    )
    original = tool["function"]["parameters"]["properties"]["evidence"]
    provider = _provider_tools([tool])[0]["function"]["parameters"]["properties"]["evidence"]

    assert provider["type"] == "string"
    assert provider["minLength"] == 1
    assert jsonschema.Draft202012Validator(provider).is_valid("Verified destination exists")
    assert not jsonschema.Draft202012Validator(provider).is_valid([])
    assert original != provider


def test_directory_rename_readback_requires_directory_kind() -> None:
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
        SimpleNamespace(execute=lambda *_args, **_kwargs: None),
    )
    state = RuntimeState(
        task_id="synthetic-rename-readback",
        domain="os",
        instruction="Rename a directory.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="x",
                proposed={"kind": "adapter", "action": "filesystem.rename", "arguments": {}},
                validated=True,
                executed=True,
                result={
                    "destination": "/home/u/Desktop/renamed_dir",
                    "verification": {"checks": [{"observed": {"is_directory": True}}]},
                },
            )
        ],
    )
    try:
        tools = agent.tools(state)
        assert [tool["function"]["name"] for tool in tools] == ["adapter__filesystem_find"]
        kind = tools[0]["function"]["parameters"]["properties"]["kind"]
        assert kind["enum"] == ["directory"]
    finally:
        agent.client.close()
