from copy import deepcopy
from types import SimpleNamespace

import pytest

from calc_adapter.schema import explicit_format_ranges
from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_adapter_body,
    compact_context_hint_for_model,
    execution_context_summary,
)
from integrations.lite_agent.semantic_requirements import _has_region_format


def test_explicit_member_parsing_preserves_order_duplicates_and_cell_notation():
    assert explicit_format_ranges("D4, $D$9:$E$10, D4") == ("D4", "$D$9:$E$10", "D4")
    for raw in ("NamedBlock", "D4:E10", "D4,", "D4,NamedBlock", "D4;E10", None):
        assert explicit_format_ranges(raw) is None


def test_existing_format_completion_recognizes_only_explicit_complete_members():
    region = {"sheet": "Records", "range": "D9:E10", "format": {"bold": True}}
    arguments = {"sheet": "Records", "range": "D4, $D$9:$E$10", "format": {"bold": True}}
    original = deepcopy(arguments)
    assert _has_region_format([arguments], region)
    assert _has_region_format([{**arguments, "range": "D9:E10"}], region)
    assert not _has_region_format([{**arguments, "range": "D4,D9"}], region)
    assert not _has_region_format([{**arguments, "sheet": "Elsewhere"}], region)
    assert not _has_region_format([{**arguments, "format": {"bold": False}}], region)
    assert arguments == original


def test_area_format_readback_reaches_model_without_creating_a_false_rectangle():
    observed = {
        "sheet": "Records",
        "range": "D4,F9",
        "formatted_ranges": ["D4", "F9"],
        "date_cells": {"D4": {"date": "2032-04-10", "weekday": "Saturday"}},
        "background_cells": {"D4": "#335577", "F9": "#335577"},
        "range_results": [
            {"range": "D4", "display_text": [["10/04/2032"]], "styles": [[{"background_color": "#335577"}]]},
            {"range": "F9", "display_text": [["label"]], "styles": [[{"background_color": "#335577"}]]},
        ],
    }
    original = deepcopy(observed)
    hint = adapter_context_hint("libreoffice_calc", "range.format", {"result": observed})
    event = SimpleNamespace(
        step=1,
        proposed={"kind": "adapter", "action": "range.format", "tool": "adapter__range_format", "arguments": {"sheet": "Records", "range": "D4,F9", "format": {"background_color": "#335577"}}},
        executed=True,
        result={"context_hint": hint, "adapter_response": {"result": observed}},
        error=None,
    )
    visible = execution_context_summary([event], "libreoffice_calc", strict_generic=True)[0]["result"]["context_hint"]
    for key in ("range", "formatted_ranges", "date_cells", "background_cells", "range_results"):
        assert visible[key] == original[key]
    assert "styles" not in visible
    assert "display_text" not in visible
    assert observed == original


def test_large_format_response_keeps_explicit_execution_targets():
    body = {
        "status": "ok",
        "result": {
            "sheet": "Records",
            "range": "D4,F9",
            "formatted_ranges": ["D4", "F9"],
            "date_cells": {"D4": {"date": "2032-04-10", "weekday": "Saturday"}},
            "range_results": [{"range": "D4", "display_text": [["x" * 8000]]}],
        },
    }
    compacted = compact_adapter_body(body)
    assert compacted["truncated"] is True
    assert compacted["result"]["formatted_ranges"] == body["result"]["formatted_ranges"]
    assert compacted["result"]["date_cells"] == body["result"]["date_cells"]


def test_partial_format_error_remains_actionable_in_bounded_model_feedback():
    event = SimpleNamespace(
        step=1,
        proposed={"action": "range.format", "arguments": {"sheet": "Records", "range": "D4,F9,G12"}},
        executed=False,
        result=None,
        error={"error": {"code": "INVALID_REQUEST", "message": "unsupported native format", "details": {
            "sheet": "Records",
            "range": "D4,F9,G12",
            "stage": "apply",
            "applied_ranges": ["D4"],
            "failed_range": "F9",
            "failed_range_may_be_partially_formatted": True,
            "unattempted_ranges": ["G12"],
            "guidance": "Applied ranges remain changed; the failed range may be partly changed. Inspect the reported areas before retrying.",
            "native_error": "unsupported native format",
            "traceback": "synthetic stack line\n" * 1000,
        }}},
    )
    visible = execution_context_summary([event], "libreoffice_calc", strict_generic=True)[0]["error"]["error"]
    assert visible["code"] == "INVALID_REQUEST"
    details = visible["details"]
    assert details["applied_ranges"] == ["D4"]
    assert details["failed_range"] == "F9"
    assert details["failed_range_may_be_partially_formatted"] is True
    assert details["unattempted_ranges"] == ["G12"]
    assert "may be partly changed" in details["guidance"]


def _truncated_format_observation():
    return {
        "sheet": "Records", "range": "C:C", "formatted_ranges": ["C:C"],
        "range_results": [{
            "range": "C:C", "readback_range": "C1:C32", "truncated": True,
            "display_text": [["01/01/1900"], *[[""] for _ in range(31)]],
            "styles": [[{"background_color": "#ffffff"}] for _ in range(32)],
        }],
        "date_cells": {"C1": {"date": "1900-01-01", "weekday": "Monday"}},
        "background_cells": {}, "truncated": True,
        "date_cells_truncated": True, "background_cells_truncated": True,
    }


@pytest.mark.parametrize("forwarded", [False, True])
def test_format_preview_scope_reaches_model_for_direct_and_forwarded_calls(forwarded):
    observed = _truncated_format_observation()
    original = deepcopy(observed)
    domain, action = "libreoffice_calc", "range.format"
    body = {"status": "ok", "result": observed}
    if forwarded:
        body = {"status": "ok", "result": {
            "adapter": domain, "action": action, "response": body,
        }}
        domain, action = "multi_apps", "adapter.call"
    hint = adapter_context_hint(domain, action, body)
    event = SimpleNamespace(
        step=1, proposed={"kind": "adapter", "action": action, "arguments": {}},
        executed=True, result={"context_hint": hint}, error=None,
    )

    visible = execution_context_summary([event], domain, strict_generic=True)[0][
        "result"
    ]["context_hint"]
    if forwarded:
        visible = visible["downstream_context"]

    for key, value in observed.items():
        assert visible[key] == value
    assert "full range was formatted" in visible["guidance"]
    assert "is unobserved" in visible["guidance"]
    assert observed == original


def test_format_preview_coverage_survives_large_body_and_context_compaction():
    observed = _truncated_format_observation()
    observed["range_results"][0]["display_text"] = [["x" * 8000]]
    observed["background_cells"] = {
        f"C{row}": "#335577" for row in range(1, 33)
    }
    body = {"status": "ok", "result": observed}

    compacted = compact_adapter_body(body)
    hint = adapter_context_hint("libreoffice_calc", "range.format", body)
    visible = compact_context_hint_for_model(hint, remaining_chars=1400)

    assert compacted["truncated"] is True
    assert visible["context_truncated"] is True
    for result in (compacted["result"], visible):
        assert result["formatted_ranges"] == ["C:C"]
        assert result["truncated"] is True
        assert result["date_cells_truncated"] is True
        assert result["background_cells_truncated"] is True
    area = visible["range_results"][0]
    assert area["range"] == "C:C"
    assert area["readback_range"] == "C1:C32"
    assert area["truncated"] is True
