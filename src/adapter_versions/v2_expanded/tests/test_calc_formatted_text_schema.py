from __future__ import annotations

from copy import deepcopy
import json

import jsonschema
import pytest

from calc_adapter.errors import AdapterError
from calc_adapter.schema import (
    orient_typed_values,
    parse_action_request,
    validate_typed_matrix,
)
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools


def _schema(wrapped: bool) -> dict:
    if not wrapped:
        return build_tools(
            "libreoffice_calc",
            ["range.write"],
            include_gui=False,
            include_control_tools=False,
            strict_generic=True,
        )[0]["function"]["parameters"]
    tools = constrain_adapter_call_routes(
        build_tools(
            "multi_apps", ["adapter.call"], include_gui=False, strict_generic=True
        ),
        [("libreoffice_calc", "range.write")],
    )
    function = next(
        tool["function"]
        for tool in tools
        if tool["function"]["name"] == "adapter__adapter_call"
    )
    return function["parameters"]["oneOf"][0]["properties"]["payload"]["properties"][
        "params"
    ]


@pytest.mark.parametrize("wrapped", [False, True])
def test_formatted_text_array_shape_is_rejected_consistently(wrapped: bool):
    params = {
        "sheet": "Measurements",
        "range": "F4",
        "values": [
            {
                "kind": "formatted_text",
                "value": [
                    {"text": "Reading: "},
                    {"cell": "C4", "decimal_places": 3},
                ],
            }
        ],
    }
    with pytest.raises(AdapterError, match="value must be an object"):
        validate_typed_matrix(params["values"])
    assert not jsonschema.Draft202012Validator(_schema(wrapped)).is_valid(params)


@pytest.mark.parametrize("wrapped", [False, True])
def test_formatted_text_preserves_explicit_reference_parts(wrapped: bool):
    params = {
        "sheet": "Measurements",
        "range": "F4",
        "values": [
            {
                "kind": "formatted_text",
                "value": {
                    "parts": [
                        {"cell": "$C$1"},
                        {"text": ": "},
                        {"cell": "C4", "decimal_places": 3},
                        {"text": " units"},
                    ]
                },
            }
        ],
    }
    before = deepcopy(params)
    schema = _schema(wrapped)
    assert "Omit for text references" in json.dumps(schema)
    jsonschema.validate(params, schema)
    assert validate_typed_matrix(params["values"]) == [params["values"]]
    assert params == before


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize(
    "part",
    [{"text": "Reading", "cell": "C4"}, {"text": "Reading", "decimal_places": 3}],
)
def test_formatted_text_parts_have_distinct_literal_and_reference_shapes(
    wrapped: bool, part: dict
):
    params = {
        "sheet": "Measurements",
        "range": "F4",
        "values": [{"kind": "formatted_text", "value": {"parts": [part]}}],
    }
    with pytest.raises(AdapterError):
        validate_typed_matrix(params["values"])
    assert not jsonschema.Draft202012Validator(_schema(wrapped)).is_valid(params)


@pytest.mark.parametrize("wrapped", [False, True])
def test_other_cell_kinds_keep_their_existing_contract(wrapped: bool):
    params = {
        "sheet": "Measurements",
        "range": "A1:F1",
        "values": [
            {"kind": "blank"},
            {"kind": "string", "value": "Series"},
            {"kind": "number", "value": 7.125},
            {"kind": "boolean", "value": True},
            {"kind": "date", "value": "2032-04-09"},
            {"kind": "formula", "value": "=3*7"},
        ],
    }
    before = deepcopy(params)
    jsonschema.validate(params, _schema(wrapped))
    assert validate_typed_matrix(params["values"]) == [params["values"]]
    assert params == before


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("vertical", [False, True])
def test_literal_flat_cells_preserve_values_and_follow_target_geometry(
    wrapped: bool, vertical: bool
):
    values = ["=2+3", "  雪\t\n", "2032-04-09", "0007", 2**60 + 1, 7.125, True, False, None]
    expected = [
        {"kind": "string", "value": "=2+3"},
        {"kind": "string", "value": "  雪\t\n"},
        {"kind": "string", "value": "2032-04-09"},
        {"kind": "string", "value": "0007"},
        {"kind": "number", "value": 2**60 + 1},
        {"kind": "number", "value": 7.125},
        {"kind": "boolean", "value": True},
        {"kind": "boolean", "value": False},
        {"kind": "blank"},
    ]
    params = {
        "sheet": "Measurements",
        "range": "B2:B10" if vertical else "B2:J2",
        "values": values,
    }
    before = deepcopy(params)
    jsonschema.validate(params, _schema(wrapped))
    parsed = parse_action_request({"action": "range.write", "params": params})
    assert parsed.params == parsed.to_worker_payload()["params"] == before
    oriented = orient_typed_values(
        values, target_rows=9 if vertical else 1, target_columns=1 if vertical else 9
    )
    assert oriented == ([[cell] for cell in expected] if vertical else [expected])
    assert params == before


@pytest.mark.parametrize("wrapped", [False, True])
def test_literal_and_typed_cells_mix_in_a_rectangular_matrix(wrapped: bool):
    formula = {"kind": "formula", "value": "=2*3"}
    number = {"kind": "number", "value": 7.125, "number_format": "0.000"}
    params = {
        "sheet": "Measurements",
        "range": "B2:C3",
        "values": [["Header", formula], [None, number]],
    }
    before = deepcopy(params)
    jsonschema.validate(params, _schema(wrapped))
    assert orient_typed_values(params["values"], target_rows=2, target_columns=2) == [
        [{"kind": "string", "value": "Header"}, formula],
        [{"kind": "blank"}, number],
    ]
    assert params == before


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_literal_numbers_are_rejected(value: float):
    with pytest.raises(AdapterError, match="finite JSON scalar"):
        validate_typed_matrix([value])


@pytest.mark.parametrize(
    "values",
    ["bare scalar", [], [["first"], "second"], [[1], [2, 3]], [[]], [[["nested"]]]],
)
def test_literal_support_retains_container_shape_errors(values):
    before = deepcopy(values)
    with pytest.raises(AdapterError) as failure:
        validate_typed_matrix(values)
    assert failure.value.code == "INVALID_REQUEST"
    assert values == before


@pytest.mark.parametrize("values", [["only"], [["only"]]])
def test_literal_support_retains_destination_dimension_errors(values):
    before = deepcopy(values)
    with pytest.raises(AdapterError) as failure:
        orient_typed_values(values, target_rows=1, target_columns=2)
    assert failure.value.code == "RANGE_INVALID"
    assert values == before


def test_literal_formatted_text_error_explains_the_supported_alternative():
    values = [{"kind": "formatted_text", "value": {"parts": [{"text": "Overview"}]}}]
    before = deepcopy(values)
    with pytest.raises(AdapterError) as failure:
        validate_typed_matrix(values)
    assert failure.value.code == "INVALID_REQUEST"
    message = str(failure.value)
    assert "kind=string" in message
    assert "text directly in value" in message
    assert "range.format" in message
    assert values == before


@pytest.mark.parametrize("matrix", [False, True])
def test_single_value_shape_error_explains_merged_cell_targeting(matrix: bool):
    row = [{"kind": "string", "value": "Overview"}]
    values = [row] if matrix else row
    before = deepcopy(values)
    with pytest.raises(AdapterError) as failure:
        orient_typed_values(values, target_rows=1, target_columns=4)
    assert failure.value.code == "RANGE_INVALID"
    assert "top-left cell" in str(failure.value)
    assert values == before
    assert orient_typed_values(values, target_rows=1, target_columns=1) == [row]


@pytest.mark.parametrize("wrapped", [False, True])
def test_literal_and_merged_range_usage_reaches_both_routes(wrapped: bool):
    properties = _schema(wrapped)["properties"]
    assert "kind=string for literal text" in properties["values"]["description"]
    assert "top-left cell" in properties["range"]["description"]
