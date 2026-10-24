"""Keep atomic text-transform output actionable across the Agent handoff."""
from copy import deepcopy

from integrations.lite_agent.adapter_results import adapter_context_hint
from calc_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


def body(display):
    return {"result": {"source_sheet": "Data", "source_range": "D2:D3",
        "destination_sheet": "Data", "destination_range": "F2:F3",
        "operation": "title_case", "written_cells": 2,
        "readback": {"display_text": display}}, "verification": {"passed": True}}


def test_feedback_preserves_partial_effect_and_next_source_without_rewriting():
    result = body([["  First  Title"], ["Second Title"]])
    original = deepcopy(result)
    hint = adapter_context_hint("libreoffice_calc", "range.text_transform", result)
    assert hint["operation"] == "title_case"
    assert hint["destination_range"] == "F2:F3"
    assert hint["display_text"] == [["  First  Title"], ["Second Title"]]
    assert "did not apply any other" in hint["guidance"]
    assert "destination_range as source_range" in hint["guidance"]
    assert result == original


def test_large_readback_keeps_operation_and_summary_without_full_text():
    hint = adapter_context_hint("libreoffice_calc", "range.text_transform", body([["word " * 1000]]))
    assert "display_text" not in hint
    assert hint["display_summary"]
    assert hint["operation"] == "title_case"


def test_composition_guidance_keeps_existing_single_operation_contract():
    schema = STRICT_ACTION_PARAM_SCHEMAS["range.text_transform"]
    assert "operation" in schema["required"]
    assert "operations" not in schema["properties"]
    assert "transform" not in schema["properties"]
    assert "title_case changes letter case only" in schema["description"]
