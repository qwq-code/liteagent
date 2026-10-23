"""A single discovered operation keeps its contract across the provider boundary."""
import copy
import json

import pytest
from jsonschema import Draft202012Validator

from integrations.lite_agent.atomic_tool_surface import (
    atomic_provider_surface, restore_adapter_arguments,
)
from integrations.lite_agent.model_client import (
    StructuredToolModelClient, StructuredToolProtocolError, _provider_tools,
)
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools
from test_protocol_recovery import _FakeCompletionClient, _tool_call


def wrapper(adapter="os", action="filesystem.find"):
    tools = build_tools("multi_apps", ["adapter.call"], include_gui=False,
                        include_control_tools=False, strict_generic=True)
    return constrain_adapter_call_routes(tools, [(adapter, action)])


def client_call(tools, name, arguments, messages=None):
    fake = _FakeCompletionClient(tool_calls=[_tool_call(json.dumps(arguments), name)],
                                 finish_reason="tool_calls")
    client = StructuredToolModelClient(base_url="http://unused", api_key="unused",
                                      request_timeout_seconds=1, client=fake)
    result = client.propose(model="synthetic", messages=messages or [], tools=tools,
                            temperature=0, output_token_budget=512, enable_thinking=False)
    return result, fake.requests[0]


@pytest.mark.parametrize("system_content", [None, "Existing safety rules.",
    [{"type": "text", "text": "Existing safety rules."}]])
def test_provider_guidance_keeps_system_first_and_original_messages(system_content):
    messages = [{"role": "user", "content": "Find the PDFs."}]
    if system_content is not None:
        messages.insert(0, {"role": "system", "content": system_content})
    before = copy.deepcopy(messages)
    tools = wrapper()
    surface, _ = atomic_provider_surface(tools)
    _, request = client_call(tools, surface[0]["function"]["name"],
        {"roots": ["/tmp"], "name_patterns": ["*.pdf"]}, messages)
    assert messages == before
    assert request["messages"][0]["role"] == "system"
    assert all(m["role"] != "system" for m in request["messages"][1:])
    assert request["messages"][-1] == before[-1]
    if system_content is not None:
        assert "Existing safety rules." in json.dumps(request["messages"][0])


def test_single_action_has_flat_parameters_and_lossless_request_metadata():
    tools = wrapper()
    before = copy.deepcopy(tools)
    surface, bindings = atomic_provider_surface(tools)
    function = surface[0]["function"]
    name = function["name"]
    arguments = {
        "roots": ["/home/user/Downloads"], "name_patterns": ["*.pdf"],
        "request_options": {
            "document": {"url": "file:///tmp/sample.odt"},
            "target": {"window": "chosen-by-model"},
            "verify": [{"type": "synthetic"}], "timeout_ms": 300000,
        },
    }
    assert name.startswith("atomic__os_filesystem_find_")
    assert len(name) <= 64
    assert "payload" not in function["parameters"]["properties"]
    assert Draft202012Validator(function["parameters"]).is_valid(arguments)
    result, request = client_call(tools, name, arguments)
    restored = json.loads(result["arguments_raw"])
    assert restored == restore_adapter_arguments(arguments, bindings[name])
    assert restored["payload"]["verify"] == arguments["request_options"]["verify"]
    assert restored["payload"]["params"] == {key: value for key, value in arguments.items() if key != "request_options"}
    assert result["tool"] == "adapter__adapter_call"
    assert result["provider_tool"] == name
    assert json.loads(result["provider_arguments_raw"]) == arguments
    assert request["tool_choice"]["function"]["name"] == name
    assert tools == before


@pytest.mark.parametrize("arguments", [
    {"roots": ["/tmp"]},
    {"roots": ["/tmp"], "name_patterns": ["*.pdf"], "payload": {}},
    {"roots": ["/tmp"], "name_patterns": ["*.pdf"], "request_options": {"timeout_ms": 1}},
    {"roots": ["/tmp"], "name_patterns": ["*.pdf"], "request_options": {"params": {}}},
])
def test_invalid_atomic_arguments_never_reach_execution(arguments):
    tools = wrapper()
    surface, _ = atomic_provider_surface(tools)
    with pytest.raises(StructuredToolProtocolError, match="do not satisfy"):
        client_call(tools, surface[0]["function"]["name"], arguments)


def test_original_wrapper_constraints_are_checked_after_restoring():
    tools = wrapper()
    tools[0]["function"]["parameters"]["not"] = {
        "properties": {"payload": {"properties": {"params": {
            "properties": {"roots": {"const": ["/blocked"]}}, "required": ["roots"],
        }}, "required": ["params"]}}, "required": ["payload"],
    }
    surface, _ = atomic_provider_surface(tools)
    with pytest.raises(StructuredToolProtocolError, match="do not satisfy"):
        client_call(tools, surface[0]["function"]["name"],
                    {"roots": ["/blocked"], "name_patterns": ["*.pdf"]})


def test_schema_uniqueness_still_enforced_after_wire_conversion():
    tools = wrapper()
    schema = tools[0]["function"]["parameters"]["properties"]["payload"]["properties"]["params"]
    schema["properties"]["roots"]["uniqueItems"] = True
    surface, _ = atomic_provider_surface(tools)
    wire = _provider_tools(surface)[0]["function"]["parameters"]
    assert "uniqueItems" not in wire["properties"]["roots"]
    with pytest.raises(StructuredToolProtocolError, match="do not satisfy"):
        client_call(tools, surface[0]["function"]["name"],
                    {"roots": ["/tmp", "/tmp"], "name_patterns": ["*.pdf"]})


def test_old_route_alias_does_not_enable_a_different_operation():
    tools = wrapper()
    with pytest.raises(StructuredToolProtocolError):
        client_call(tools, "atomic__os_filesystem_remove_fake", {"path": "/tmp/a"})
    result, _ = client_call(tools, "adapter_call", {
        "adapter": "os", "action": "filesystem.find",
        "payload": {"params": {"roots": ["/tmp"], "name_patterns": ["*.pdf"]}},
    })
    assert result["tool"] == "adapter__adapter_call"


def test_ambiguous_untyped_and_reference_contracts_keep_wrapper():
    tools = build_tools("multi_apps", ["adapter.call"], include_gui=False,
                        include_control_tools=False, strict_generic=True)
    alternatives = constrain_adapter_call_routes(tools, [
        ("os", "filesystem.find"), ("os", "archive.create_zip"),
    ])
    for original in (tools, alternatives):
        surface, bindings = atomic_provider_surface(original)
        assert surface == original
        assert not bindings
    fixed = wrapper()
    fixed[0]["function"]["parameters"]["properties"]["payload"]["properties"]["params"]["$ref"] = "#/$defs/params"
    assert atomic_provider_surface(fixed) == (fixed, {})


@pytest.mark.parametrize("adapter,action,params", [
    ("os", "image.extract_text_batch", {"input_pattern": "*.pdf", "cwd_source": "explicit", "cwd_path": "/tmp"}),
    ("libreoffice_calc", "range.write", {"sheet": "Sheet1", "range": "A1", "values": [["text"]]}),
    ("libreoffice_writer", "document.save", {}),
])
def test_cross_application_routes_share_same_round_trip(adapter, action, params):
    tools = wrapper(adapter, action)
    surface, bindings = atomic_provider_surface(tools)
    name = surface[0]["function"]["name"]
    assert name in bindings
    result, _ = client_call(tools, name, params)
    restored = json.loads(result["arguments_raw"])
    assert restored["adapter"] == adapter
    assert restored["action"] == action
    assert restored["payload"]["params"] == params


def test_provider_schema_conversion_preserves_keyword_named_properties_and_literals():
    literal = {"const": "literal", "type": ["integer", "string"], "x-route": "literal"}
    schema = {"type": "object", "properties": {
        "const": {"const": literal}, "type": {"type": ["integer", "string"]},
        "x-route": {"type": "string"},
        "object": {"enum": [literal], "default": literal, "examples": [literal]},
    }, "required": ["const", "type", "x-route", "object"], "additionalProperties": False}
    original = copy.deepcopy(schema)
    tools = [{"type": "function", "function": {"name": "synthetic", "parameters": schema}}]
    converted = _provider_tools(tools)[0]["function"]["parameters"]
    assert schema == original
    assert set(converted["properties"]) == set(schema["properties"])
    assert converted["properties"]["const"]["enum"] == [literal]
    assert converted["properties"]["object"] == schema["properties"]["object"]
    valid = {"const": literal, "type": 2, "x-route": "value", "object": literal}
    assert Draft202012Validator(converted).is_valid(valid)
    assert Draft202012Validator(schema).is_valid(valid)
