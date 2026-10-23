from copy import deepcopy
import json

from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_adapter_body,
)
from integrations.lite_agent.context_projection import sanitize


def _body(pivots, **sheet_fields):
    return {
        "status": "ok",
        "result": {
            "title": "Inventory.xlsx",
            "url": "file:///tmp/Inventory.xlsx",
            "active_sheet": "Summary",
            "modified": False,
            "sheets": [{
                "name": "Summary",
                "used_range": {
                    "start_column": 2, "start_row": 2,
                    "end_column": 4, "end_row": 12,
                },
                "charts": [],
                "pivot_tables": pivots,
                **sheet_fields,
            }],
        },
    }


def test_native_pivot_ranges_and_read_failure_survive_model_context():
    pivots = [
        {"name": "ByRegion", "output_range": "C3:E13"},
        {"name": "ByQuarter", "output_range": "C3:D7"},
        {"name": "Unavailable", "inspect_error": "native output unavailable"},
    ]
    body = _body(pivots)
    original = deepcopy(body)
    hint = adapter_context_hint("libreoffice_calc", "workbook.inspect", body)
    rendered = json.loads(json.dumps(sanitize({
        "context_hint": hint,
        "adapter_response": compact_adapter_body(body),
    })))
    sheet = rendered["context_hint"]["sheets"][0]
    assert sheet["pivot_tables"] == pivots
    assert sheet["pivot_table_count"] == 3
    assert sheet["pivot_tables_omitted_from_context"] == 0
    assert "overlapping rectangles" in rendered["context_hint"]["guidance"]
    assert body == original


def test_pivot_enumeration_failure_is_not_reported_as_zero_tables():
    body = _body([], pivot_tables_inspect_error="native inventory unavailable")
    hint = adapter_context_hint("libreoffice_calc", "workbook.inspect", body)
    sheet = sanitize(hint)["sheets"][0]
    assert sheet["pivot_table_count"] is None
    assert sheet["pivot_tables_inspect_error"] == "native inventory unavailable"


def test_large_pivot_inventory_reports_omitted_records():
    pivots = [{"name": f"Group{i}", "output_range": f"C{i + 1}:D{i + 1}"}
              for i in range(30)]
    hint = adapter_context_hint("libreoffice_calc", "workbook.inspect", _body(pivots))
    sheet = hint["sheets"][0]
    assert sheet["pivot_table_count"] == len(pivots)
    assert sheet["pivot_tables"] == pivots[:len(sheet["pivot_tables"])]
    assert 0 < sheet["pivot_tables_omitted_from_context"] < len(pivots)
    assert len(sheet["pivot_tables"]) + sheet["pivot_tables_omitted_from_context"] == len(pivots)
    assert len(json.dumps(hint)) <= 4200
