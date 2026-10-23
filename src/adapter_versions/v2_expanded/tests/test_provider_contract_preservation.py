"""Provider adaptation must preserve meaningful value and route constraints."""
import copy

import pytest
from jsonschema import Draft202012Validator

from integrations.lite_agent.model_client import _provider_tools
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools


def schemas(domain, action):
    tools = build_tools(domain, [action], include_gui=False, include_control_tools=False, strict_generic=True)
    original = copy.deepcopy(tools)
    adapted = _provider_tools(tools)
    assert tools == original
    return tools[0]["function"]["parameters"], adapted[0]["function"]["parameters"]


@pytest.mark.parametrize("values", [
    [1, "sample", True, None], [[1, "sample"], [False, None]],
    [{"kind": "formula", "value": "=SUM(A1:A2)"}],
])
def test_cell_types_and_matrix_shape_survive_provider_conversion(values):
    original, provider = schemas("libreoffice_calc", "range.write")
    params = {"sheet": "Data", "range": "A1:D1", "values": values}
    assert Draft202012Validator(original).is_valid(params)
    assert Draft202012Validator(provider).is_valid(params)
    for bad in [{"kind": "unknown"}, {"arbitrary": 4}]:
        invalid = {**params, "values": [bad]}
        assert not Draft202012Validator(provider).is_valid(invalid)


def test_type_array_is_inclusive_union_and_retains_existing_constraints():
    schema = {"type": ["integer", "number"], "minimum": 0, "anyOf": [{"maximum": 3}, {"minimum": 9}]}
    tool = {"type": "function", "function": {"name": "numeric", "parameters": schema}}
    output = _provider_tools([tool])[0]["function"]["parameters"]
    for value in [-1, 1, 1.5, 5, 9, "one", True]:
        assert Draft202012Validator(output).is_valid(value) == Draft202012Validator(schema).is_valid(value)


def test_route_union_keeps_each_actions_required_arguments():
    tools = build_tools("multi_apps", ["adapter.call"], include_gui=False, include_control_tools=False, strict_generic=True)
    tools = constrain_adapter_call_routes(tools, [("os", "command.run"), ("os", "filesystem.find")])
    original = tools[0]["function"]["parameters"]
    provider = _provider_tools(tools)[0]["function"]["parameters"]
    for params in [
        {"adapter": "os", "action": "command.run", "payload": {"params": {"argv": ["pwd"], "cwd_source": "home"}}},
        {"adapter": "os", "action": "command.run", "payload": {"params": {"command": "pwd"}}},
        {"adapter": "os", "action": "filesystem.find", "payload": {"params": {"roots": ["/tmp"], "name_patterns": ["*.txt"]}}},
        {"adapter": "os", "action": "invented", "payload": {"params": {}}},
    ]:
        assert Draft202012Validator(provider).is_valid(params) == Draft202012Validator(original).is_valid(params)
    assert not Draft202012Validator(provider).is_valid({"adapter": "os", "action": "command.run", "payload": {"params": {}}})


def test_write_route_keeps_required_values_with_sheet_aliases():
    tools = build_tools("multi_apps", ["adapter.call"], include_gui=False, include_control_tools=False, strict_generic=True)
    tools = constrain_adapter_call_routes(tools, [("libreoffice_calc", "range.write")])
    provider = _provider_tools(tools)[0]["function"]["parameters"]
    route = {"adapter": "libreoffice_calc", "action": "range.write"}
    for params in [{"sheet": "S", "range": "A1", "values": [1]}, {"sheet_name": "S", "used_range_a1": "A1", "values": [1]}]:
        assert Draft202012Validator(provider).is_valid({**route, "payload": {"params": params}})
    for params in [{"sheet": "S", "range": "A1"}, {"values": [1]}, {}]:
        assert not Draft202012Validator(provider).is_valid({**route, "payload": {"params": params}})


@pytest.mark.parametrize('action,params', [
    ('workbook.read_file', {'path': '/tmp/source.ods'}),
    ('workbook.inspect', {'path': '/tmp/source.ods'}),
    ('workbook.save', {'path': '/tmp/output.ods'}),
])
def test_client_does_not_invent_inspection_or_erase_file_arguments(action, params):
    import json
    from integrations.lite_agent.model_client import StructuredToolModelClient, StructuredToolProtocolError
    from test_protocol_recovery import _FakeCompletionClient, _tool_call

    tools = build_tools('multi_apps', ['adapter.call'], include_gui=False,
                        include_control_tools=False, strict_generic=True)
    tools = constrain_adapter_call_routes(tools, [('libreoffice_calc', 'workbook.inspect')])
    arguments = {'adapter': 'libreoffice_calc', 'action': action, 'payload': {'params': params}}
    fake = _FakeCompletionClient(tool_calls=[_tool_call(json.dumps(arguments), 'adapter_call')], finish_reason='tool_calls')
    client = StructuredToolModelClient(base_url='http://synthetic', api_key='unused',
                                      request_timeout_seconds=1, client=fake)
    with pytest.raises(StructuredToolProtocolError) as error:
        client.propose(messages=[{'role': 'user', 'content': 'Inspect the opened workbook'}],
                       model='synthetic', tools=tools, temperature=0,
                       output_token_budget=512, enable_thinking=False)
    raw = error.value.response_snapshot['message']['tool_calls'][0]['function']['arguments']
    assert json.loads(raw) == arguments
