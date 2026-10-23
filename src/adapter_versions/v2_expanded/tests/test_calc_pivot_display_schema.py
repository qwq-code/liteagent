from copy import deepcopy

from jsonschema import Draft202012Validator
import pytest

from calc_adapter.errors import AdapterError
from calc_adapter.schema import validate_action_params
from calc_adapter.tool_manifest import PIVOT_DATA_FIELD
from integrations.lite_agent.model_client import _schema_validation_hints
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools


def _schema(wrapped: bool) -> dict:
    if not wrapped:
        return build_tools(
            "libreoffice_calc", ["pivot.create"], include_gui=False,
            include_control_tools=False, strict_generic=True,
        )[0]["function"]["parameters"]
    tools = constrain_adapter_call_routes(
        build_tools("multi_apps", ["adapter.call"], include_gui=False, strict_generic=True),
        [("libreoffice_calc", "pivot.create")],
    )
    return tools[0]["function"]["parameters"]["oneOf"][0]["properties"]["payload"]["properties"]["params"]


def _params(mode: str) -> dict:
    return {
        "source_sheet": "Stock", "source_range": "B3:F18",
        "destination_sheet": "Summary", "destination": "H5", "name": "RegionShare",
        "row_fields": ["Region"],
        "data_fields": [{"field": "Units", "aggregation": "sum", "show_data_as": mode}],
    }


@pytest.mark.parametrize("wrapped", [False, True])
def test_model_pivot_display_modes_reuse_the_adapter_contract(wrapped: bool) -> None:
    schema = _schema(wrapped)
    field = schema["properties"]["data_fields"]["items"]
    assert field == PIVOT_DATA_FIELD
    assert "total_percentage" in field["properties"]["show_data_as"]["description"]
    for mode in PIVOT_DATA_FIELD["properties"]["show_data_as"]["enum"]:
        params = _params(mode)
        original = deepcopy(params)
        Draft202012Validator(schema).validate(params)
        validate_action_params("pivot.create", params)
        assert params == original


@pytest.mark.parametrize("wrapped", [False, True])
def test_unknown_pivot_display_value_returns_usable_schema_feedback(wrapped: bool) -> None:
    params = _params("percentage")
    errors = list(Draft202012Validator(_schema(wrapped)).iter_errors(params))
    assert len(errors) == 1
    hints = " ".join(_schema_validation_hints(errors))
    assert "data_fields.0.show_data_as" in hints
    for mode in ("row_percentage", "column_percentage", "total_percentage"):
        assert mode in hints


def test_native_pivot_display_error_names_the_invalid_value_and_choices() -> None:
    params = _params("percentage")
    original = deepcopy(params)
    with pytest.raises(AdapterError) as failure:
        validate_action_params("pivot.create", params)
    assert failure.value.code == "INVALID_REQUEST"
    message = str(failure.value)
    assert "show_data_as value is unsupported" in message
    for mode in PIVOT_DATA_FIELD["properties"]["show_data_as"]["enum"]:
        assert mode in message
    assert params == original


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize(
    ("group", "measure", "aggregation", "mode"),
    [
        ("Zone", "Zone", "count", "total_percentage"),
        ("Zone", "Record", "count", "total_percentage"),
        ("Quarter", "Revenue", "sum", "none"),
    ],
)
def test_pivot_grouping_and_measure_usage_reaches_both_routes(
    wrapped: bool, group: str, measure: str, aggregation: str, mode: str,
) -> None:
    schema = _schema(wrapped)
    properties = schema["properties"]
    assert "distinct values" in properties["row_fields"]["description"]
    assert "one group per record" in properties["row_fields"]["description"]
    fields = properties["data_fields"]["items"]["properties"]
    assert "within each group" in fields["aggregation"]["description"]
    assert "same field can serve both roles" in fields["field"]["description"]
    assert "output heading" in fields["field"]["description"]
    params = _params(mode)
    params["row_fields"] = [group]
    params["data_fields"] = [
        {"field": measure, "aggregation": aggregation, "show_data_as": mode}
    ]
    before = deepcopy(params)
    Draft202012Validator(schema).validate(params)
    validate_action_params("pivot.create", params)
    assert params == before
