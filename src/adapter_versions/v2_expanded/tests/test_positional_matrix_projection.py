from __future__ import annotations

from copy import deepcopy
import json

import pytest

from integrations.lite_agent.adapter_results import adapter_context_hint, compact_adapter_body
from integrations.lite_agent.context_projection import (
    compact_execution_summary_for_model,
)


def _hint() -> dict:
    return adapter_context_hint(
        "libreoffice_calc",
        "range.read",
        {
            "result": {
                "sheet": "Measurements",
                "range": "C3:F26",
                "display_text": [
                    [f"row{row}_column{column}" for column in range(3, 7)]
                    for row in range(3, 27)
                ],
            }
        },
    )


@pytest.mark.parametrize("max_chars", [900, 1600])
def test_recovery_matrix_keeps_whole_leading_rows_and_columns(max_chars: int):
    hint = _hint()
    original = deepcopy(hint)
    projected = compact_execution_summary_for_model(
        [
            {
                "step": 1,
                "action": "range.read",
                "executed": True,
                "result": {"context_hint": hint},
            }
        ],
        max_chars=max_chars,
    )
    observed = projected[0]["result"]["context_hint"]
    rows = observed["display_text"]
    assert 0 < len(rows) < len(hint["display_text"])
    assert rows == hint["display_text"][: len(rows)]
    assert observed["context_truncated"] is True
    assert len(json.dumps(projected, ensure_ascii=False)) <= max_chars
    assert hint == original


def test_fitting_matrix_is_returned_without_sampling():
    hint = _hint()
    source = [{"step": 1, "result": {"context_hint": hint}}]
    assert compact_execution_summary_for_model(source, max_chars=9000) == source


def test_calc_guidance_explains_partial_prefix_projection():
    guidance = _hint()["guidance"]
    assert "context_truncated" in guidance
    assert "leading rows" in guidance


def test_calc_single_column_read_suggests_adjacent_observed_columns() -> None:
    hint = adapter_context_hint(
        "libreoffice_calc",
        "range.read",
        {
            "result": {
                "sheet": "Measurements",
                "range": "F6:F20",
                "display_text": [["value"], [""]],
            }
        },
    )
    assert "one column only" in hint["guidance"]
    assert "adjacent observed columns" in hint["guidance"]


def test_calc_range_read_marks_observed_summary_row_blank_cells() -> None:
    hint = adapter_context_hint(
        "libreoffice_calc",
        "range.read",
        {
            "result": {
                "sheet": "Measurements",
                "range": "A1:C3",
                "display_text": [["Product", "Q1", "Total"], ["Total", "", ""] , ["", "", ""]],
                "kinds": [["string", "string", "string"], ["string", "blank", "blank"], ["blank", "blank", "blank"]],
            }
        },
    )
    assert hint["summary_rows"] == [
        {
            "label": "Total",
            "label_cell": "A2",
            "blank_cells": ["B2", "C2"],
        }
    ]
    assert "summary_rows lists" in hint["guidance"]
    assert "vertical column formula" in hint["guidance"]
    assert "horizontal" in hint["guidance"]


def test_calc_summary_row_context_reports_contiguous_detail_span() -> None:
    hint = adapter_context_hint(
        "libreoffice_calc",
        "range.read",
        {
            "result": {
                "sheet": "Measurements",
                "range": "A1:C5",
                "display_text": [
                    ["Product", "Q1", "Total"],
                    ["A", 1, ""],
                    ["B", 2, ""],
                    ["C", 3, ""],
                    ["Total", "", ""],
                ],
                "kinds": [
                    ["string", "string", "string"],
                    ["string", "number", "blank"],
                    ["string", "number", "blank"],
                    ["string", "number", "blank"],
                    ["string", "blank", "blank"],
                ],
            }
        },
    )
    assert hint["summary_rows"][0]["detail_row_range"] == "2:4"
    assert "detail_row_range" in hint["guidance"]
    assert hint["summary_rows"][0]["detail_total_cells"] == ["C2", "C3", "C4"]
    assert "detail_total_cells" in hint["guidance"]
    assert hint["detail_total_cells"] == ["C2", "C3", "C4"]
    assert "union of both target sets" in hint["guidance"]
    assert hint["summary_rows"][0]["period_cells"] == ["B5"]
    assert hint["summary_rows"][0]["final_total_cell"] == "C5"
    assert "formula_roles" in hint["summary_rows"][0]


def test_calc_range_read_exposes_a1_address_matrix_aligned_with_values() -> None:
    hint = _hint()
    addresses = hint["cell_addresses"]
    assert addresses[0] == ["C3", "D3", "E3", "F3"]
    assert addresses[1] == ["C4", "D4", "E4", "F4"]
    assert len(addresses) == len(hint["display_text"])
    assert all(
        len(address_row) == len(value_row)
        for address_row, value_row in zip(
            addresses, hint["display_text"], strict=True
        )
    )
    assert "cell_addresses[i][j]" in hint["guidance"]


def test_calc_range_read_address_matrix_truncates_with_the_same_leading_rows() -> None:
    hint = _hint()
    projected = compact_execution_summary_for_model(
        [{"step": 1, "result": {"context_hint": hint}}],
        max_chars=1600,
    )
    observed = projected[0]["result"]["context_hint"]
    assert observed["cell_addresses"] == hint["cell_addresses"][: len(observed["display_text"])]


@pytest.mark.parametrize("filled_cells", [None, 0, 11])
def test_large_fill_readback_keeps_reported_count_in_model_context(filled_cells):
    display = _hint()["display_text"]
    body = {
        "status": "ok",
        "verification": {"passed": True},
        "result": {
            "sheet": "Measurements",
            "range": "C3:F26",
            "readback": {
                "display_text": display,
                "styles": [
                    [
                        {"background_color": "#ffffff", "font_color": "#374151", "bold": False}
                        for _ in row
                    ]
                    for row in display
                ],
            },
        },
    }
    if filled_cells is not None:
        body["result"]["filled_cells"] = filled_cells
    original = deepcopy(body)
    compacted = compact_adapter_body(body)
    assert compacted["truncated"] is True
    projected = compact_execution_summary_for_model(
        [{"step": 1, "action": "range.fill_down", "executed": True, "result": compacted}],
        max_chars=3200,
    )
    observed = projected[0]["result"]["result"]
    if filled_cells is None:
        assert "filled_cells" not in compacted["result"]
        assert "filled_cells" not in observed
    else:
        assert compacted["result"]["filled_cells"] == filled_cells
        assert observed["filled_cells"] == filled_cells
    rows = observed["display_text"]
    assert rows == display[:len(rows)]
    assert len(json.dumps(projected, ensure_ascii=False)) <= 3200
    assert body == original
