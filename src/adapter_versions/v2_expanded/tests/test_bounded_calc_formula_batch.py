from __future__ import annotations

import json

import pytest

from calc_adapter.errors import AdapterError
from calc_adapter.schema import ACTIONS as CALC_ACTIONS
from calc_adapter.schema import validate_action_params
from calc_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from calc_adapter.uno_worker import ACTIONS as CALC_WORKER_ACTIONS
from integrations.lite_agent.adapter_results import adapter_context_hint
from integrations.lite_agent.agent import LiteAgent
from integrations.lite_agent.calc_semantics import operation_required_actions
from integrations.lite_agent.state_model import RuntimeState
from integrations.lite_agent.tool_catalog import (
    DIRECT_ACTION_SCHEMAS,
    build_tools,
    public_actions,
    search_actions,
    select_actions,
)


RETIRED_SOLVERS = {
    "table.fill_missing_totals",
    "chart.create_from_table_blocks",
    "table.add_date_offset_column",
}
ATOMIC_BATCH = "cells.set_formulas"


def test_task_shaped_calc_solvers_are_not_public_and_formula_batch_is_public() -> None:
    surfaces = (
        set(CALC_ACTIONS),
        set(CALC_WORKER_ACTIONS),
        set(STRICT_ACTION_PARAM_SCHEMAS),
        set(DIRECT_ACTION_SCHEMAS["libreoffice_calc"]),
        set(public_actions("libreoffice_calc")),
    )

    assert all(RETIRED_SOLVERS.isdisjoint(surface) for surface in surfaces)
    assert all(ATOMIC_BATCH in surface for surface in surfaces)


def test_explicit_formula_batch_accepts_counterfactual_cells_and_values() -> None:
    params = {
        "sheet": "Forecast 2031",
        "writes": [
            {"cell": "H12", "formula": "=SUM(C12:G12)"},
            {"cell": "$D$27", "formula": "=AVERAGE(D19:D26)"},
        ],
    }

    validate_action_params(ATOMIC_BATCH, params)


def test_formula_batch_description_covers_complete_summary_rows() -> None:
    description = STRICT_ACTION_PARAM_SCHEMAS[ATOMIC_BATCH]["description"]

    assert "every blank numeric cell" in description
    assert "Total or Subtotal" in description
    assert "do not truncate the SUM" in description
    assert "Do not repeat or overwrite" in description
    assert "every observed numeric column before it" in description
    assert "Successful formulas persist" in description
    assert "Err:<code> is a failed formula" in description
    assert "one cell for each numeric period" in description
    assert "inside the observed used range" in description
    assert "vertical column sum" in description
    assert "across that same summary row" in description
    assert "do not use a detail-row horizontal formula" in description
    assert "detail_total_cells" in description
    assert "union of both target sets" in description
    assert "do not write formulas into header, category, or separator rows" in description
    assert "model still selects each cell" in description


def test_text_transform_destination_description_preserves_headers() -> None:
    contract = STRICT_ACTION_PARAM_SCHEMAS["range.text_transform"]
    tool = build_tools(
        "libreoffice_calc",
        ["range.text_transform"],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )[0]["function"]
    assert contract["description"] in tool["description"]
    assert tool["parameters"]["properties"] == contract["properties"]
    source_description = tool["parameters"]["properties"]["source_range"]["description"]
    description = tool["parameters"]["properties"]["destination"]["description"]

    assert "start at the first data row" in source_description
    assert "observed header" in source_description
    assert "transforms every cell" in source_description
    assert "Top-left destination cell only" in description
    assert "Do not pass a destination range" in description
    assert "exclude headers from source_range" in description


def test_range_read_description_requires_one_contiguous_range() -> None:
    description = DIRECT_ACTION_SCHEMAS["libreoffice_calc"]["range.read"][
        "description"
    ]

    assert "one contiguous A1 range" in description
    assert "do not join non-contiguous ranges with commas" in description
    assert "separate range.read calls" in description
    assert "cell_addresses[i][j]" in description


@pytest.mark.parametrize("strict_generic", [False, True])
def test_calc_inspection_descriptions_distinguish_cells_from_charts(
    strict_generic: bool,
) -> None:
    tools = build_tools(
        "libreoffice_calc",
        ["workbook.inspect", "range.read"],
        include_gui=False,
        include_control_tools=False,
        strict_generic=strict_generic,
    )
    descriptions = {
        tool["function"]["name"]: tool["function"]["description"] for tool in tools
    }
    workbook = descriptions["adapter__workbook_inspect"]
    cells = descriptions["adapter__range_read"]

    assert "settings in sheets[].charts" in workbook
    assert "data_series_count and data_series" in workbook
    assert "category_axes reports category labels separately" in workbook
    assert "chart read-back" in workbook
    assert "equivalent rectangle" in workbook
    assert "compare covered cells and header flags" in workbook
    assert "not chart objects" in cells
    assert "use workbook.inspect for charts" in cells


def test_range_read_rejects_multi_area_with_actionable_error() -> None:
    with pytest.raises(AdapterError) as caught:
        validate_action_params(
            "range.read",
            {"sheet": "工作表1", "range": "F3:F5,F10:F12,F17:F19"},
        )

    error = caught.value
    assert error.code == "INVALID_REQUEST"
    assert "one contiguous A1 range" in error.message
    assert "separate calls" in error.message
    assert error.details == {"range": "F3:F5,F10:F12,F17:F19"}


@pytest.mark.parametrize("range_value", ["A1", "A1:B2", "$F$3:$F$20"])
def test_range_read_accepts_contiguous_a1_ranges(range_value: str) -> None:
    validate_action_params(
        "range.read", {"sheet": "Synthetic", "range": range_value}
    )


def test_chart_create_rejects_multi_area_source_range_with_actionable_error() -> None:
    with pytest.raises(AdapterError) as caught:
        validate_action_params(
            "chart.create",
            {
                "sheet": "Sheet1",
                "source_sheet": "Sheet1",
                "name": "Chart 1",
                "source_ranges": ["A1:A12,B1:B12"],
                "type": "column",
            },
        )

    error = caught.value
    assert error.code == "INVALID_REQUEST"
    assert "source_ranges[0]" in error.message
    assert "do not join areas with commas" in error.message


@pytest.mark.parametrize(
    "writes",
    [
        [
            {"cell": "C9", "formula": "=SUM(C2:C8)"},
            {"cell": "$C$9", "formula": "=AVERAGE(C2:C8)"},
        ],
        [{"cell": "C9:D9", "formula": "=SUM(C2:C8)"}],
        [{"cell": "C9", "formula": "42"}],
    ],
)
def test_formula_batch_rejects_implicit_or_ambiguous_targets(
    writes: list[dict],
) -> None:
    with pytest.raises(AdapterError):
        validate_action_params(
            ATOMIC_BATCH,
            {"sheet": "Synthetic", "writes": writes},
        )


def test_complete_range_read_context_preserves_the_last_rows_and_formulas() -> None:
    display_text = [[f"Item {row}", str(row), ""] for row in range(1, 121)]
    formulas = [["", "", f"=B{row}*2"] for row in range(1, 121)]
    kinds = [["string", "number", "formula"] for _ in range(120)]

    context = adapter_context_hint(
        "libreoffice_calc",
        "range.read",
        {
            "result": {
                "sheet": "Synthetic",
                "range": "A1:C120",
                "display_text": display_text,
                "formulas": formulas,
                "kinds": kinds,
                "styles": [[{"large": "irrelevant" * 100}] for _ in range(120)],
            }
        },
    )

    assert context is not None
    assert context["display_text"][-1] == ["Item 120", "120", ""]
    assert context["formulas"][-1][-1] == "=B120*2"
    assert context["kinds"][-1][-1] == "formula"
    assert "styles" not in context
    assert len(json.dumps(context, ensure_ascii=False)) < 64_000


def test_total_like_paraphrase_recalls_observation_and_explicit_formula_batch() -> None:
    instruction = (
        "Complete every blank subtotal cell in the repeated quarterly tables by "
        "entering spreadsheet formulas for the row and column sums."
    )
    selected = set(select_actions("libreoffice_calc", instruction, limit=7))
    searched = {
        item["action"]
        for item in search_actions(
            "libreoffice_calc",
            "batch cells formulas totals",
            instruction=instruction,
            limit=8,
            strict_generic=True,
        )
    }

    assert {"workbook.inspect", "range.read", ATOMIC_BATCH}.issubset(selected)
    assert ATOMIC_BATCH in searched
    assert RETIRED_SOLVERS.isdisjoint(selected | searched)


def test_repeated_table_charts_recall_observation_and_one_explicit_chart() -> None:
    instruction = (
        "Create a separate column chart for each of the three observed tables, using "
        "the first column as categories and the final numeric column as values."
    )

    required = operation_required_actions(instruction, strict_generic=True)
    selected = set(
        select_actions("libreoffice_calc", instruction, recommended=required, limit=8)
    )

    assert {"range.read", "chart.create"}.issubset(required)
    assert {"range.read", "chart.create"}.issubset(selected)
    assert "chart.create_from_table_blocks" not in selected
    validate_action_params(
        "chart.create",
        {
            "sheet": "Dashboard",
            "source_sheet": "Observed Data",
            "name": "North 2034",
            "source_ranges": ["B7:B18", "F7:F18"],
            "type": "column",
            "data_row_source": "columns",
            "column_headers": False,
            "row_headers": True,
            "title": "North 2034",
            "position": {"x": 9000, "y": 1500, "width": 14000, "height": 8000},
        },
    )


def test_chart_contract_distinguishes_internal_name_from_display_title() -> None:
    schema = DIRECT_ACTION_SCHEMAS["libreoffice_calc"]["chart.create"]
    properties = schema["properties"]

    assert "do not pass a rectangle" in schema["description"]
    assert "internal" in properties["name"]["description"]
    assert "not the text" in properties["name"]["description"]
    assert "never include component columns" in properties["source_ranges"]["description"]
    assert "each array item is exactly one" in properties["source_ranges"]["description"]
    assert "never one comma-joined item" in properties["source_ranges"]["description"]
    assert "does not create a worksheet" in properties["sheet"]["description"]
    assert "displayed main chart title" in properties["title"]["description"]
    assert "exact text here" in properties["title"]["description"]
    assert "vertical columns" in properties["type"]["description"]


@pytest.mark.parametrize("strict_generic", [False, True])
def test_chart_public_contract_explains_headers_without_changing_arguments(
    strict_generic: bool,
) -> None:
    tool = build_tools(
        "libreoffice_calc",
        ["chart.create"],
        include_gui=False,
        include_control_tools=False,
        strict_generic=strict_generic,
    )[0]
    schema = tool["function"]["parameters"]
    properties = schema["properties"]
    original = DIRECT_ACTION_SCHEMAS["libreoffice_calc"]["chart.create"]["properties"]

    for field in ("sheet", "source_sheet", "source_ranges", "column_headers", "row_headers"):
        assert properties[field] == original[field]
    assert "does not create a worksheet" in properties["sheet"]["description"]
    assert "different existing sheet" in properties["source_sheet"]["description"]
    assert '["D8:D10", "G8:G10"]' in properties["source_ranges"]["description"]
    assert "column_headers=false" in tool["function"]["description"]
    assert "not summed" in properties["source_ranges"]["description"]
    assert "one value-column range" in properties["source_ranges"]["description"]
    assert "first data row is not omitted" in properties["column_headers"]["description"]
    assert "true consumes it as labels" in properties["column_headers"]["description"]
    assert "row outside source_ranges is not read" in properties["column_headers"]["description"]
    assert "independent of row_headers" in properties["column_headers"]["description"]
    assert "category labels" in properties["row_headers"]["description"]
    for field in ("column_headers", "row_headers"):
        assert "Defaults to true" in properties[field]["description"]
        assert properties[field]["type"] == "boolean"
        assert "default" not in properties[field]
        assert field not in schema["required"]


def test_date_calculation_does_not_require_a_redundant_fill_operation() -> None:
    instruction = (
        'Calculate each maturity date in a new column called "Maturity 2035" from '
        "the observed start-date and duration-in-months columns."
    )

    required = operation_required_actions(instruction, strict_generic=True)
    selected = set(
        select_actions("libreoffice_calc", instruction, recommended=required, limit=10)
    )

    assert {"range.read", "range.write", "range.format"}.issubset(required)
    assert "range.fill_down" not in required
    assert {"range.read", "range.write", "range.format"}.issubset(selected)
    assert "table.add_date_offset_column" not in selected
    validate_action_params(
        "range.write",
        {
            "sheet": "Schedule",
            "range": "G1:G2",
            "values": [
                [{"kind": "string", "value": "Maturity 2035"}],
                [{"kind": "formula", "value": "=EDATE(C2;F2)"}],
            ],
        },
    )
    validate_action_params(
        "range.fill_down",
        {
            "sheet": "Schedule",
            "range": "G2:G41",
            "mode": "formula_pattern",
            "source_rows": 1,
        },
    )
    validate_action_params(
        "range.format",
        {
            "sheet": "Schedule",
            "range": "G2:G41",
            "format": {"number_format": "YYYY-MM-DD"},
        },
    )


def test_hiding_missing_rows_recalls_the_public_row_visibility_mutation() -> None:
    instruction = (
        "Some data are filled by N/A temporarily. Hide those rows in the table; "
        "do not delete cells."
    )

    required = operation_required_actions(instruction, strict_generic=True)

    assert {"range.read", "rows.set_hidden"}.issubset(required)


def test_runner_accepts_model_selected_formula_batch_arguments_unchanged() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="libreoffice_calc",
        instruction="Add formulas to the explicitly observed blank totals.",
    )
    arguments = {
        "sheet": "Alternative Data",
        "writes": [
            {"cell": "J14", "formula": "=SUM(E14:I14)"},
            {"cell": "F31", "formula": "=SUM(F22:F30)"},
        ],
    }

    LiteAgent._validate_stateful_arguments(state, ATOMIC_BATCH, arguments)
    assert arguments == {
        "sheet": "Alternative Data",
        "writes": [
            {"cell": "J14", "formula": "=SUM(E14:I14)"},
            {"cell": "F31", "formula": "=SUM(F22:F30)"},
        ],
    }
