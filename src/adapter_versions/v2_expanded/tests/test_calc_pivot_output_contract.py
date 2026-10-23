from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from calc_adapter import uno_worker
from calc_adapter.errors import AdapterError
from calc_adapter.schema import PIVOT_DESTINATION_SCHEMA, validate_action_params
from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_adapter_body,
)
from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.instruction_semantics import (
    strict_instruction_required_actions,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools, select_actions, tool_name


class NoExecutor:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("Tool selection must not execute application actions")


def _event(step: int, action: str, arguments: dict, result: dict) -> ExecutionEvent:
    return ExecutionEvent(
        step=step,
        timestamp_utc="2032-06-07T00:00:00Z",
        proposed={
            "kind": "adapter",
            "tool": tool_name(action),
            "action": action,
            "arguments": arguments,
        },
        parsed=True,
        validated=True,
        executed=True,
        result=result,
    )


def test_filtered_source_read_slot_is_refilled_without_raising_top_k() -> None:
    state = RuntimeState(
        task_id="synthetic-pivot-layout",
        domain="libreoffice_calc",
        instruction=(
            "Create a new sheet. Merge B2:D2 and write a bold title there. "
            "Create three pivot tables showing percentages, separated by blank rows."
        ),
        events=[
            _event(1, "workbook.inspect", {}, {"status": "ok"}),
            _event(2, "sheet.create", {"name": "Overview"}, {"status": "ok"}),
            _event(
                3, "range.read", {"sheet": "Input", "range": "A1:D9"}, {"status": "ok"}
            ),
        ],
    )
    required = strict_instruction_required_actions(state.domain, state.instruction)
    assert {"range.merge", "pivot.create"}.issubset(required)
    assert state.stage_read_satisfied("range.read")
    before = deepcopy(state.events)
    agent = LiteAgent(
        LiteAgentConfig(
            base_url="http://unused/v1", top_k_actions=7, include_gui=False
        ),
        NoExecutor(),
    )
    selected = agent.selected_actions(state)
    assert len(selected) <= 7
    assert {"range.merge", "pivot.create", "workbook.save"}.issubset(selected)
    assert "range.read" not in selected
    tools = {tool["function"]["name"] for tool in agent.tools(state)}
    assert {"adapter__range_merge", "adapter__pivot_create"}.issubset(tools)
    assert state.events == before


def test_unbounded_ranking_preserves_existing_bounded_order() -> None:
    instruction = "Format the selected cells."
    ranked = select_actions("libreoffice_calc", instruction, limit=None)
    assert len(ranked) > 7
    assert select_actions("libreoffice_calc", instruction, limit=7) == ranked[:7]


def _pivot_inventory_session(monkeypatch, tables):
    sheet = SimpleNamespace(
        getName=lambda: "Overview",
        getCharts=lambda: SimpleNamespace(getElementNames=lambda: ()),
        getDataPilotTables=lambda: tables,
    )
    doc = SimpleNamespace(
        getCurrentController=lambda: SimpleNamespace(getActiveSheet=lambda: sheet),
        isModified=lambda: False,
    )
    monkeypatch.setattr(uno_worker, "_sheet_names", lambda doc: ["Overview"])
    monkeypatch.setattr(uno_worker, "_used_range", lambda sheet: {})
    monkeypatch.setattr(uno_worker, "_hidden_rows_in_used_range", lambda *args: [])
    return SimpleNamespace(
        doc=doc,
        sheet=lambda name: sheet,
        _identity=lambda doc: {"title": "Quarterly.xlsx"},
    )


def test_workbook_inspection_lists_native_pivot_names_and_output_ranges(monkeypatch):
    outputs = {
        "UnitsByRegion_7": SimpleNamespace(
            StartColumn=7, StartRow=4, EndColumn=9, EndRow=17,
        ),
        "ReturnsByPeriod_2": SimpleNamespace(
            StartColumn=13, StartRow=2, EndColumn=15, EndRow=8,
        ),
    }
    tables = SimpleNamespace(
        getElementNames=lambda: tuple(outputs),
        getByName=lambda name: SimpleNamespace(getOutputRange=lambda: outputs[name]),
    )

    result = uno_worker._inspect(_pivot_inventory_session(monkeypatch, tables), {})

    sheet = result["sheets"][0]
    assert sheet["pivot_tables"] == [
        {"name": "UnitsByRegion_7", "output_range": "H5:J18"},
        {"name": "ReturnsByPeriod_2", "output_range": "N3:P9"},
    ]
    assert "pivot_tables_inspect_error" not in sheet
    assert result["modified"] is False


@pytest.mark.parametrize("failure", ["enumeration", "output_range"])
def test_workbook_pivot_inspection_reports_failed_reads_explicitly(monkeypatch, failure):
    def unavailable():
        raise RuntimeError("Native pivot metadata unavailable")

    good_output = SimpleNamespace(StartColumn=3, StartRow=6, EndColumn=5, EndRow=11)
    tables = SimpleNamespace(
        getElementNames=(
            unavailable if failure == "enumeration" else lambda: ("Readable", "Unknown")
        ),
        getByName=lambda name: SimpleNamespace(
            getOutputRange=(lambda: good_output) if name == "Readable" else unavailable,
        ),
    )

    sheet = uno_worker._inspect(_pivot_inventory_session(monkeypatch, tables), {})[
        "sheets"
    ][0]

    if failure == "enumeration":
        assert sheet["pivot_tables"] == []
        assert sheet["pivot_tables_inspect_error"] == "Native pivot metadata unavailable"
    else:
        assert sheet["pivot_tables"] == [
            {"name": "Readable", "output_range": "D7:F12"},
            {"name": "Unknown", "inspect_error": "Native pivot metadata unavailable"},
        ]
        assert "pivot_tables_inspect_error" not in sheet


def _native_pivot_fixture(
    monkeypatch, output, *, anchor="H5", display_text=None, readback_error=None
):
    fields = {name: SimpleNamespace() for name in ("Area", "Units")}
    descriptor = SimpleNamespace(
        getDataPilotFields=lambda: SimpleNamespace(
            hasByName=lambda name: name in fields,
            getByName=fields.__getitem__,
        )
    )
    destination = SimpleNamespace(Column=7, Row=output.StartRow)
    source = SimpleNamespace(StartColumn=0, StartRow=0, EndColumn=3, EndRow=8)
    inserted = []
    preview_reads = []
    if display_text is None:
        display_text = [
            [
                f"Native {row}:{column}"
                for column in range(output.EndColumn - output.StartColumn + 1)
            ]
            for row in range(output.EndRow - output.StartRow + 1)
        ]

    def get_pivot(name):
        assert inserted == [(name, destination, descriptor)]
        return SimpleNamespace(getOutputRange=lambda: output)

    def get_preview(start_column, start_row, end_column, end_row):
        assert len(inserted) == 1
        preview_reads.append((start_column, start_row, end_column, end_row))
        if readback_error is not None:
            raise RuntimeError(readback_error)
        address = SimpleNamespace(
            StartColumn=start_column, StartRow=start_row,
            EndColumn=end_column, EndRow=end_row,
        )
        return SimpleNamespace(
            getRangeAddress=lambda: address,
            getCellByPosition=lambda column, row: SimpleNamespace(
                getString=lambda: display_text[
                    start_row - output.StartRow + row
                ][start_column - output.StartColumn + column],
            ),
        )

    tables = SimpleNamespace(
        hasByName=lambda name: False,
        createDataPilotDescriptor=lambda: descriptor,
        insertNewByName=lambda *args: inserted.append(args),
        getByName=get_pivot,
    )
    sheets = {
        "Input": SimpleNamespace(
            getCellRangeByName=lambda value: {
                "A1:D9": SimpleNamespace(getRangeAddress=lambda: source),
            }[value]
        ),
        "Overview": SimpleNamespace(
            getDataPilotTables=lambda: tables,
            getCellRangeByPosition=get_preview,
            getCellRangeByName=lambda value: {
                anchor: SimpleNamespace(getCellAddress=lambda: destination),
                "H2:J3": SimpleNamespace(getRangeAddress=lambda: SimpleNamespace(
                    StartColumn=7, EndRow=2,
                )),
            }[value],
        ),
    }
    monkeypatch.setattr(
        uno_worker,
        "_uno_modules",
        lambda: (SimpleNamespace(Enum=lambda type_name, value: value), None),
    )
    return SimpleNamespace(
        session=SimpleNamespace(sheet=sheets.__getitem__),
        descriptor=descriptor, fields=fields, source=source,
        inserted=inserted, preview_reads=preview_reads, display_text=display_text,
    )


def _pivot_params(destination="H5"):
    return {
        "source_sheet": "Input",
        "source_range": "A1:D9",
        "destination_sheet": "Overview",
        "destination": destination,
        "name": "ByArea",
        "row_fields": ["Area"],
        "data_fields": [{"field": "Units", "aggregation": "sum"}],
    }


@pytest.mark.parametrize(
    ("end_column", "end_row", "expected"),
    [(9, 17, "J18"), (27, 6, "AB7")],
)
@pytest.mark.parametrize(
    "relative_gap,anchor,start_row", [(None, "H5", 4), (0, "H4", 3), (3, "H7", 6)],
)
def test_pivot_returns_actual_native_output_not_an_inferred_size(
    monkeypatch,
    end_column: int,
    end_row: int,
    expected: str,
    relative_gap: int | None,
    anchor: str,
    start_row: int,
) -> None:
    params = _pivot_params(
        "H5" if relative_gap is None
        else {"below_range": "H2:J3", "blank_rows": relative_gap}
    )
    before = deepcopy(params)
    output = SimpleNamespace(
        StartColumn=7, StartRow=start_row, EndColumn=end_column, EndRow=end_row
    )
    fixture = _native_pivot_fixture(monkeypatch, output, anchor=anchor)
    result = uno_worker._pivot_create(fixture.session, params)
    assert result == {
        "name": "ByArea",
        "source_range": "A1:D9",
        "destination": anchor,
        **({"requested_destination": before["destination"]} if relative_gap is not None else {}),
        "destination_sheet": "Overview",
        "output_range": f"{anchor}:{expected}",
        "output_last_row": end_row + 1,
        "output_row_count": end_row - output.StartRow + 1,
        "readback": {
            "sheet": "Overview",
            "range": f"{anchor}:{expected if end_column == 9 else 'W7'}",
            "display_text": [row[:16] for row in fixture.display_text],
            "truncated": end_column == 27,
        },
    }
    assert fixture.preview_reads == [(7, start_row, min(end_column, 22), end_row)]
    assert fixture.descriptor.SourceRange is fixture.source
    assert fixture.fields["Area"].Orientation == "ROW"
    assert fixture.fields["Units"].Function == "SUM"
    assert params == before


def test_pivot_readback_preserves_native_percentage_text_without_interpreting_it(
    monkeypatch,
):
    output = SimpleNamespace(StartColumn=7, StartRow=4, EndColumn=9, EndRow=7)
    displayed = [
        ["Area", "Row share", "Overall share"],
        ["North", "100.00%", "25.00%"],
        ["South", "100.00%", "75.00%"],
        ["Grand Total", "100.00%", "100.00%"],
    ]
    fixture = _native_pivot_fixture(monkeypatch, output, display_text=displayed)
    params = _pivot_params()
    before = deepcopy(params)

    result = uno_worker._pivot_create(fixture.session, params)

    assert result["readback"] == {
        "sheet": "Overview", "range": "H5:J8",
        "display_text": displayed, "truncated": False,
    }
    assert result["output_range"] == "H5:J8"
    assert len(fixture.inserted) == 1
    assert fixture.preview_reads == [(7, 4, 9, 7)]
    assert params == before


@pytest.mark.parametrize(
    "end_column,end_row,preview_end,preview_range,truncated",
    [
        (22, 35, (22, 35), "H5:W36", False),
        (23, 35, (22, 35), "H5:W36", True),
        (9, 36, (9, 35), "H5:J36", True),
        (28, 50, (22, 35), "H5:W36", True),
    ],
)
def test_pivot_readback_bounds_do_not_shrink_actual_output(
    monkeypatch, end_column, end_row, preview_end, preview_range, truncated,
):
    output = SimpleNamespace(
        StartColumn=7, StartRow=4, EndColumn=end_column, EndRow=end_row,
    )
    fixture = _native_pivot_fixture(monkeypatch, output)

    result = uno_worker._pivot_create(fixture.session, _pivot_params())

    assert fixture.preview_reads == [(7, 4, *preview_end)]
    assert result["readback"] == {
        "sheet": "Overview", "range": preview_range,
        "display_text": [row[:16] for row in fixture.display_text[:32]],
        "truncated": truncated,
    }
    assert result["output_range"] == uno_worker._range_a1(output)
    assert result["output_last_row"] == end_row + 1
    assert result["output_row_count"] == end_row - 3
    assert len(fixture.inserted) == 1


def test_pivot_preview_read_failure_preserves_created_table_without_retry(monkeypatch):
    output = SimpleNamespace(StartColumn=7, StartRow=4, EndColumn=9, EndRow=7)
    fixture = _native_pivot_fixture(
        monkeypatch, output, readback_error="Native display temporarily unavailable",
    )
    params = _pivot_params()
    before = deepcopy(params)

    result = uno_worker._pivot_create(fixture.session, params)

    assert result == {
        "name": "ByArea", "source_range": "A1:D9", "destination": "H5",
        "destination_sheet": "Overview", "output_range": "H5:J8",
        "output_last_row": 8, "output_row_count": 4,
        "readback_error": "Native display temporarily unavailable",
    }
    assert len(fixture.inserted) == 1
    assert fixture.preview_reads == [(7, 4, 9, 7)]
    assert params == before


@pytest.mark.parametrize("forwarded", [False, True])
@pytest.mark.parametrize("recovery", [None, "protocol", "execution"])
@pytest.mark.parametrize("readback_kind", [None, "values", "error"])
def test_pivot_output_and_optional_readback_reach_actual_model_messages(
    forwarded, recovery, readback_kind
):
    native = {
        "name": "ByArea",
        "source_range": "A1:D9",
        "destination": "H5",
        "requested_destination": {"below_range": "H2:J3", "blank_rows": 1},
        "destination_sheet": "Overview",
        "output_range": "H5:J18",
        "output_last_row": 18,
        "output_row_count": 14,
    }
    if readback_kind == "values":
        native["readback"] = {
            "sheet": "Overview",
            "range": "H5:J18",
            "display_text": [
                ["Area", "Row share", "Overall share"],
                ["North", "100.00%", "25.00%"],
                ["South", "100.00%", "75.00%"],
                *[["", "", ""] for _ in range(10)],
                ["Grand Total", "100.00%", "100.00%"],
            ],
            "truncated": False,
        }
    elif readback_kind == "error":
        native["readback_error"] = "Native display temporarily unavailable"
    body = {"status": "ok", "result": native}
    domain, action = "libreoffice_calc", "pivot.create"
    if forwarded:
        body = {
            "status": "ok",
            "result": {"adapter": domain, "action": action, "response": body},
        }
        domain, action = "multi_apps", "adapter.call"
    hint = adapter_context_hint(domain, action, body)
    result = compact_adapter_body(body)
    if hint is not None:
        result = {"context_hint": hint, "adapter_response": result}
    if not forwarded and readback_kind is None:
        assert hint is None
    state = RuntimeState(
        task_id="synthetic-output-projection",
        domain=domain,
        instruction="Create pivot tables with a blank row between them.",
        events=[_event(1, action, {}, result)],
    )
    before = deepcopy(state.events)
    messages = AgentProtocolMixin()._messages(
        state,
        b"png",
        protocol_recovery=recovery == "protocol",
        execution_recovery=recovery == "execution",
    )
    summary = json.loads(messages[2]["content"][0]["text"].split("\n")[1])
    projected = next(item for item in summary if item.get("step") == 1)["result"]
    if forwarded:
        observed = projected["context_hint"]["downstream_context"]
    elif readback_kind is not None:
        observed = projected["context_hint"]
    else:
        observed = projected["result"]
    if readback_kind is None:
        assert observed == native
    else:
        assert set(observed) == set(native) | {"context_char_budget", "guidance"}
        assert {key: observed[key] for key in native} == native
        assert observed["context_char_budget"] == 16000
        assert isinstance(observed["guidance"], str) and observed["guidance"]
    assert state.events == before


def test_pivot_usage_distinguishes_anchor_from_occupied_range() -> None:
    tool = build_tools("libreoffice_calc", ["pivot.create"], include_gui=False)[0][
        "function"
    ]
    assert "output_range" in tool["description"]
    assert "occupied" in tool["description"]
    assert "destination_sheet" in tool["description"]
    assert "output_last_row + n + 1" in tool["description"]
    assert "output_row_count" in tool["description"]
    destination = tool["parameters"]["properties"]["destination"]
    assert "below_range" in destination["description"]
    assert "between the title and the first table" in destination["description"]


@pytest.mark.parametrize("gap", [0, 3])
@pytest.mark.parametrize("forwarded", [False, True])
def test_relative_pivot_destination_contract_preserves_model_arguments(gap, forwarded):
    params = {
        "source_sheet": "Stock", "source_range": "B3:F18",
        "destination_sheet": "Summary", "name": "ByZone",
        "destination": {"below_range": "J8:L14", "blank_rows": gap},
        "row_fields": ["Zone"], "data_fields": [{"field": "Revenue", "aggregation": "sum"}],
    }
    before = deepcopy(params)
    tool = build_tools("libreoffice_calc", ["pivot.create"], include_gui=False)[0]
    schema = tool["function"]["parameters"]
    if forwarded:
        tools = constrain_adapter_call_routes(
            build_tools("multi_apps", ["adapter.call"], include_gui=False, strict_generic=True),
            [("libreoffice_calc", "pivot.create")],
        )
        schema = tools[0]["function"]["parameters"]["oneOf"][0]["properties"]["payload"][
            "properties"
        ]["params"]
    assert schema["properties"]["destination"] == PIVOT_DESTINATION_SCHEMA
    Draft202012Validator(schema).validate(params)
    validate_action_params("pivot.create", params)
    assert params == before


def test_relative_pivot_destination_rejects_negative_gap_without_rewriting():
    params = {
        "source_sheet": "Stock", "source_range": "B3:F18",
        "destination_sheet": "Summary", "name": "ByZone",
        "destination": {"below_range": "J8:L14", "blank_rows": -1},
        "row_fields": ["Zone"], "data_fields": [{"field": "Revenue", "aggregation": "sum"}],
    }
    before = deepcopy(params)
    with pytest.raises(AdapterError, match="blank_rows must be a non-negative integer"):
        validate_action_params("pivot.create", params)
    assert params == before
