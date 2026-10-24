import jsonschema

from integrations.lite_agent.model_client import _provider_tools
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools
from integrations.lite_agent.tool_surface import ToolSurfaceMixin


def test_provider_adapter_call_requires_route_outside_payload() -> None:
    tool = {
        "type": "function",
        "function": {
            "name": "adapter__adapter_call",
            "parameters": {
                "type": "object",
                "properties": {
                    "adapter": {"type": "string"},
                    "action": {"type": "string"},
                    "payload": {
                        "type": "object",
                        "properties": {"params": {"type": "object"}},
                    },
                },
                "required": ["adapter", "action", "payload"],
            },
        },
    }

    schema = _provider_tools([tool])[0]["function"]["parameters"]
    validator = jsonschema.Draft202012Validator(schema)
    assert schema["required"] == ["adapter", "action", "payload"]
    assert validator.is_valid(
        {"adapter": "os", "action": "filesystem.find", "payload": {"params": {}}}
    )
    assert not validator.is_valid({"payload": {"params": {}}})
    assert not validator.is_valid(
        {"payload": {"params": {"adapter": "os", "action": "filesystem.find"}}}
    )


def test_successful_discovered_atom_can_repeat_but_other_routes_require_search() -> None:
    catalog = ExecutionEvent(
        step=1,
        timestamp_utc="",
        proposed={"kind": "catalog", "tool": "tools_search", "arguments": {"query": "documents"}},
        executed=True,
        result={
            "status": "ok",
            "matches": [
                {"action": "adapter.call", "adapter": "os", "downstream_action": "filesystem.find"},
                {"action": "adapter.call", "adapter": "os", "downstream_action": "archive.create_zip"},
            ],
        },
    )
    found = ExecutionEvent(
        step=2,
        timestamp_utc="",
        proposed={
            "kind": "adapter",
            "action": "adapter.call",
            "arguments": {"adapter": "os", "action": "filesystem.find", "payload": {"params": {}}},
        },
        executed=True,
        result={"status": "ok"},
    )
    tools = build_tools(
        "multi_apps", ["adapter.call"], include_gui=False,
        include_control_tools=True, strict_generic=True,
    )
    state = RuntimeState(task_id="synthetic", domain="multi_apps", instruction="organize documents")

    state.events = [catalog]
    before = ToolSurfaceMixin._apply_common_tool_constraints(tools, state)
    assert "tools_search" not in {tool["function"]["name"] for tool in before}

    state.events = [catalog, found]
    after = ToolSurfaceMixin._apply_common_tool_constraints(tools, state)
    names = {tool["function"]["name"] for tool in after}
    assert "tools_search" in names
    assert "adapter__adapter_call" in names
    schema = next(t['function']['parameters'] for t in after if t['function']['name'] == 'adapter__adapter_call')
    assert schema['x-route'] == {'adapter': 'os', 'action': 'filesystem.find'}
    assert schema['properties']['action'] == {'const': 'filesystem.find'}
