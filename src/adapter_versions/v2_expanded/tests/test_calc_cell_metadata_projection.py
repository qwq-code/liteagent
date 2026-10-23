from copy import deepcopy
from types import SimpleNamespace

import pytest

from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    execution_context_summary,
)
from integrations.lite_agent.context_projection import compact_execution_summary_for_model


def test_native_dates_and_backgrounds_reach_the_real_execution_context():
    observed = {
        "sheet": "Measurements",
        "range": "D8:E9",
        "display_text": [["10/04/2032", "label"], ["", "11/04/2032"]],
        "cell_addresses": [["D8", "E8"], ["D9", "E9"]],
        "date_cells": {
            "D8": {"date": "2032-04-10", "weekday": "Saturday"},
            "E9": {"date": "2032-04-11", "weekday": "Sunday"},
        },
        "background_cells": {"E8": "#335577", "D9": "#112233"},
    }
    original = deepcopy(observed)
    hint = adapter_context_hint("libreoffice_calc", "range.read", {"result": observed})
    event = SimpleNamespace(
        step=1,
        proposed={
            "kind": "adapter",
            "action": "range.read",
            "tool": "adapter__range_read",
            "arguments": {"sheet": "Measurements", "range": "D8:E9"},
        },
        result={"context_hint": hint, "adapter_response": {"result": observed}},
        executed=True,
        error=None,
    )
    visible = execution_context_summary([event], "libreoffice_calc", strict_generic=True)
    projected = visible[0]["result"]["context_hint"]
    assert projected["date_cells"] == original["date_cells"]
    assert projected["background_cells"] == original["background_cells"]
    assert projected["display_text"] == original["display_text"]
    assert observed == original


@pytest.mark.parametrize("max_chars", [1600, 2600])
def test_bounded_read_keeps_addressed_metadata_before_large_text(max_chars):
    hint = adapter_context_hint(
        "libreoffice_calc",
        "range.read",
        {
            "result": {
                "sheet": "Measurements",
                "range": "B3:C6",
                "display_text": [["x" * 500, "y" * 500] for _ in range(4)],
                "date_cells": {"B3": {"date": "2032-04-10", "weekday": "Saturday"}},
                "background_cells": {"C6": "#112233"},
            }
        },
    )
    visible = compact_execution_summary_for_model(
        [{"step": 1, "action": "range.read", "executed": True, "result": {"context_hint": hint}}],
        max_chars=max_chars,
    )[0]["result"]["context_hint"]
    assert visible["context_truncated"] is True
    assert visible["date_cells"] == hint["date_cells"]
    assert visible["background_cells"] == hint["background_cells"]


def test_complete_white_background_read_is_distinct_from_missing_metadata():
    body = {"result": {"sheet": "Measurements", "range": "D8", "display_text": [[""]]}}
    missing = adapter_context_hint("libreoffice_calc", "range.read", body)
    assert "background_cells" not in missing
    body["result"]["background_cells"] = {}
    complete = adapter_context_hint("libreoffice_calc", "range.read", body)
    assert complete["background_cells"] == {}
    assert "white only when that map is complete" in complete["guidance"]
