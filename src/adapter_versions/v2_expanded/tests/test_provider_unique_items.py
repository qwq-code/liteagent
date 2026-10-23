"""Local NPU grammar compatibility must not bypass executable validation."""
import copy
import json

import pytest
from jsonschema import Draft202012Validator

from integrations.lite_agent.model_client import (
    _provider_array_uniqueness, _provider_tools,
    StructuredToolModelClient, StructuredToolProtocolError,
)
from test_protocol_recovery import _FakeCompletionClient, _tool_call


def tools():
    return [{"type": "function", "function": {
        "name": "record_values", "parameters": {
            "type": "object", "properties": {
                "values": {"type": "array", "items": {"type": "integer"},
                           "uniqueItems": True, "minItems": 2, "maxItems": 3},
                "uniqueItems": {"type": "boolean"},
            }, "required": ["values"], "additionalProperties": False,
        },
    }}]


def test_wire_schema_preserves_types_bounds_property_names_and_original():
    original = tools()
    before = copy.deepcopy(original)
    wire = _provider_tools(original)[0]["function"]["parameters"]
    assert original == before
    assert wire["properties"]["uniqueItems"] == {"type": "boolean"}
    array = wire["properties"]["values"]
    assert "uniqueItems" not in array
    assert "must be unique" in array["description"]
    validator = Draft202012Validator(wire)
    assert validator.is_valid({"values": [1, 2]})
    for values in [[1], [1, 2, 3, 4], [1, "2"]]:
        assert not validator.is_valid({"values": values})


@pytest.mark.parametrize("values,valid", [([1, 2], True), ([1, 1], False)])
def test_real_client_rejects_duplicates_after_provider_conversion(values, valid):
    fake = _FakeCompletionClient(
        tool_calls=[_tool_call(json.dumps({"values": values}), "record_values")],
        finish_reason="tool_calls",
    )
    client = StructuredToolModelClient(base_url="http://synthetic", api_key="unused",
                                      request_timeout_seconds=1, client=fake)
    kwargs = dict(model="synthetic", messages=[{"role": "user", "content": "Record values"}],
                  tools=tools(), temperature=0, output_token_budget=64, enable_thinking=False)
    if valid:
        client.propose(**kwargs)
    else:
        with pytest.raises(StructuredToolProtocolError, match="do not satisfy"):
            client.propose(**kwargs)


def test_nested_schema_conversion_preserves_literals_and_false_semantics():
    literal = {"uniqueItems": True}
    original = {"$defs": {"list": {"type": "array", "uniqueItems": True}},
                "anyOf": [{"type": "array", "uniqueItems": False}],
                "default": literal, "enum": [literal], "examples": [literal]}
    wire = _provider_array_uniqueness(original)
    assert "uniqueItems" not in wire["$defs"]["list"]
    assert wire["anyOf"] == [{"type": "array"}]
    for key in ("default", "enum", "examples"):
        assert wire[key] == original[key]
    assert original["$defs"]["list"]["uniqueItems"] is True
