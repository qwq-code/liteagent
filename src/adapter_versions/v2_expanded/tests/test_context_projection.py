from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.agent import LiteAgentConfig
from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_context_hint_for_model,
    compact_presentation_hint_for_model,
    compact_execution_summary_for_model,
    execution_context_summary,
    text_batch_context_for_model,
)
from integrations.lite_agent.context_projection import (
    compact_hint,
    durable_observations,
    failure_summary,
)
from integrations.lite_agent.episode_control import mark_tool_result_for_audit
from integrations.lite_agent.safety import (
    assert_agent_surface_safe,
    sanitize_agent_visible_result,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from os_adapter.actions import _text_window
from os_adapter.errors import AdapterError as OSAdapterError
from os_adapter.schema import validate_action_params as validate_os_action
from os_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS as OS_SCHEMAS


def _protocol() -> AgentProtocolMixin:
    protocol = AgentProtocolMixin()
    protocol.config = LiteAgentConfig(base_url="http://unused/v1")
    return protocol


def event(
    step: int,
    *,
    action: str,
    executed: bool = True,
    result: object = None,
    error: object = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        step=step,
        proposed={
            "kind": "adapter",
            "tool": f"adapter__{action.replace('.', '_')}",
            "action": action,
            "arguments": {"path": f"/tmp/input-{step}.txt"},
        },
        executed=executed,
        result=result,
        error=error,
    )


def test_large_context_hint_is_valid_structured_json_within_budget() -> None:
    value = {
        "path": "/tmp/counterfactual-output.txt",
        "title": "Counterfactual output",
        "matches": ["/tmp/first.txt", "/tmp/last.txt"],
        "guidance": "Inspect the returned state before choosing the next action. " * 80,
        "rows": [
            {"index": index, "name": f"row-{index}", "value": "x" * 180}
            for index in range(80)
        ],
        "expected": "must never reach the model",
        "nested": {"task_id": "internal-id", "kind": "table"},
    }

    projected = compact_context_hint_for_model(value, remaining_chars=5_000)
    encoded = json.dumps(projected, ensure_ascii=False)

    assert len(encoded) <= 5_000
    assert json.loads(encoded) == projected
    assert projected["path"] == "/tmp/counterfactual-output.txt"
    assert projected["matches"] == ["/tmp/first.txt", "/tmp/last.txt"]
    assert projected["guidance"]
    assert len(projected["guidance"]) <= 1_200
    assert "preview" not in encoded
    assert "internal-id" not in encoded
    assert "must never reach the model" not in encoded


def test_projection_preserves_sensitive_words_in_observed_document_text() -> None:
    value = {
        "task_name": "Quarterly review",
        "task_description": "Please answer the question from the reference dataset.",
        "text": (
            "The answer column is on the right. Expected annual return is 5%. "
            "Reference document title: Dataset overview."
        ),
        "path": "/tmp/observed.txt",
    }

    projected = compact_context_hint_for_model(value, remaining_chars=2_000)

    assert projected["task_name"] == value["task_name"]
    assert projected["task_description"] == value["task_description"]
    assert projected["text"] == value["text"]
    assert projected["path"] == value["path"]


def test_fitted_dictionary_keeps_observed_null_distinct_from_an_omitted_key() -> None:
    value = {"index": 4, "value": None, "details": "x" * 2000}

    projected = compact_context_hint_for_model(value, remaining_chars=250)

    assert projected["index"] == 4
    assert "value" in projected
    assert projected["value"] is None
    assert len(json.dumps(projected)) <= 250


@pytest.mark.parametrize("forwarded", [False, True])
def test_writer_tab_effect_summary_survives_large_format_readback(forwarded) -> None:
    observation = {
        "selected_paragraph_count": 12,
        "paragraphs_with_tabs_count": 4,
        "paragraphs_without_tabs_count": 8,
        "guidance": (
            "Tab stops were configured, but paragraphs without Tab characters have "
            "no Tab-separated text for those stops to align. Text was not changed."
        ),
    }
    result = {
        "tab_stop_observation": observation,
        "formats": {"tab_stops": [{"position": {"value": 82, "unit": "mm"}, "alignment": "right"}]},
        "paragraph_details": [
            {
                "index": index,
                "nonempty_ordinal": index + 1,
                "text": f"Paragraph {index} " * 100,
                "has_tab_character": index < 4,
                "tab_stops": [{"position": {"value": 82, "unit": "mm"}, "alignment": "right"}],
            }
            for index in range(12)
        ],
    }
    original = copy.deepcopy(result)
    hint = adapter_context_hint(
        "libreoffice_writer", "paragraph.set_format",
        {"status": "ok", "verification": {"passed": True}, "result": result},
    )
    if forwarded:
        hint = {"downstream_action": "paragraph.set_format", "downstream_context": hint}
    projected = compact_context_hint_for_model(hint, remaining_chars=1500)
    observed = projected["downstream_context"] if forwarded else projected

    assert {key: observed[key] for key in observation} == observation
    assert observed["verification_passed"] is True
    assert len(json.dumps(projected)) <= 1500
    assert result == original


@pytest.mark.parametrize("action", ["document.inspect", "paragraph.set_format"])
def test_writer_tab_positions_remain_distinct_from_literal_escapes(action) -> None:
    text = "Map\\tTitle\t"
    body = {
        "status": "ok",
        "result": {
            "paragraphs": [text],
            "paragraph_start": 0,
            "paragraph_limit": 1,
            "paragraph_details": [{
                "index": 0, "nonempty_ordinal": 1, "text": text,
                "text_length": len(text), "has_tab_character": True,
                "tab_character_offsets": [10], "literal_tab_escape_count": 1,
            }],
        },
    }
    original = copy.deepcopy(body)
    context = adapter_context_hint("libreoffice_writer", action, body)
    observed = compact_context_hint_for_model(context, remaining_chars=2500)
    row = observed.get("paragraph_details", observed.get("formatted_paragraphs"))[0]

    assert row["tab_character_offsets"] == [len(text) - 1]
    assert row["literal_tab_escape_count"] == 1
    assert row["text"] == text
    assert body == original


@pytest.mark.parametrize("forwarded", [False, True])
def test_writer_clear_receipt_keeps_explicit_targets_and_native_readback(forwarded) -> None:
    result = {
        "indices": [8, 2, 5],
        "paragraph_count_before": 12,
        "paragraph_count_after": 12,
        "paragraph_details": [
            {"index": index, "text_length": 0} for index in [8, 2, 5]
        ],
        "saved": {"path": "/tmp/Observed.odt", "size_bytes": 2100},
    }
    original = copy.deepcopy(result)
    context = adapter_context_hint(
        "libreoffice_writer", "paragraph.clear_text",
        {"status": "ok", "result": result, "verification": {"passed": True}},
    )
    if forwarded:
        context = {"downstream_action": "paragraph.clear_text", "downstream_context": context}
    projected = compact_context_hint_for_model(context, remaining_chars=2500)
    observed = projected["downstream_context"] if forwarded else projected

    assert observed == result | {"verification_passed": True}
    assert result == original


@pytest.mark.parametrize("forwarded", [False, True])
def test_writer_paragraph_projection_retains_text_and_blank_identity(forwarded) -> None:
    details = []
    ordinal = 0
    for index in range(60):
        text = "" if index % 3 == 1 else f"Observed paragraph {index}. " * 7
        ordinal += bool(text)
        details.append(
            {
                "index": index,
                "nonempty_ordinal": ordinal if text else None,
                "text": text,
                "line_spacing": 1.5,
                "alignment": "left",
                "font_size": 12,
                "has_tab_character": False,
                "tab_stops": [],
                "numbering": {
                    "is_numbered": False,
                    "level": 0,
                    "list_label": "",
                    "restart": False,
                    "start_value": -1,
                    "style_name": "",
                },
            }
        )
    result = {
        "identity": {"title": "Notes.odt", "url": "file:///tmp/Notes.odt"},
        "highlighting": {
            "highlighted_run_count": 0,
            "highlighted_paragraph_count": 0,
            "colors": {},
        },
        "graphic_object_count": 0,
        "embedded_images": 0,
        "paragraph_count": len(details),
        "nonempty_paragraph_count": ordinal,
        "paragraphs": [item["text"] for item in details],
        "paragraph_details": details,
        "tables": [],
    }
    hint = adapter_context_hint(
        "libreoffice_writer", "document.inspect", {"status": "ok", "result": result}
    )
    if forwarded:
        hint = {"downstream_context": hint, "downstream_action": "document.inspect"}
    original = copy.deepcopy(hint)
    projected = compact_context_hint_for_model(hint, remaining_chars=5000)
    paragraphs = (projected["downstream_context"] if forwarded else projected)[
        "paragraph_details"
    ]

    assert len(json.dumps(projected)) <= 5000
    assert hint == original
    assert {0, 1, 2}.issubset({item["index"] for item in paragraphs})
    for paragraph in paragraphs:
        observed = details[paragraph["index"]]
        assert paragraph["text"] == observed["text"]
        assert paragraph["nonempty_ordinal"] == observed["nonempty_ordinal"]
        assert paragraph["line_spacing"] == observed["line_spacing"]


@pytest.mark.parametrize("forwarded", [False, True])
@pytest.mark.parametrize("recovery", [None, "protocol", "execution"])
def test_writer_coordinates_and_color_reach_model_request(
    forwarded: bool, recovery: str | None
) -> None:
    cells = [
        {
            "name": f"{column}{row}",
            "text": f"Record {row}-{column}",
            "font_color": "#146C94",
            "row_index": row,
            "column_index": index,
        }
        for row in range(1, 13)
        for index, column in enumerate("ABCDE", 1)
    ]
    cells[0]["font_color"] = "mixed"
    cells[1]["font_color"] = None
    cells[2]["text"] = 'Quoted "label" | next\nline\tend'
    cells[3] = {"name": "D1.1.1", "text": "Nested cell", "font_color": "automatic"}
    cell_fields = ["name", "text", "font_color", "row_index", "column_index"]
    normalized_cells = [{field: cell.get(field) for field in cell_fields} for cell in cells]
    domain, action = "libreoffice_writer", "table.read"
    body = {
        "status": "ok",
        "result": {"name": "Labels", "rows": 12, "columns": 5, "cells": cells},
    }
    if forwarded:
        body = {
            "status": "ok",
            "result": {"adapter": domain, "action": action, "response": body},
        }
        domain, action = "multi_apps", "adapter.call"
    original = copy.deepcopy(body)
    hint = adapter_context_hint(domain, action, body)
    previous_hint = copy.deepcopy(hint)
    previous_table = previous_hint["downstream_context"] if forwarded else previous_hint
    previous_table["name"] = "EarlierTable"
    for cell in previous_table["cells"]:
        cell[1] = f"Earlier value {cell[0]}"
    previous = ExecutionEvent(
        step=1,
        timestamp_utc="2026-09-06T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": {}},
        executed=True,
        result={"context_hint": previous_hint},
    )
    observation = ExecutionEvent(
        step=2,
        timestamp_utc="2026-09-06T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": {}},
        executed=True,
        result={"context_hint": hint},
    )
    state = RuntimeState(
        task_id="synthetic-table-budget",
        domain=domain,
        instruction="Inspect the observed table.",
        events=[previous, observation],
    )
    mark_tool_result_for_audit(state, observation)
    original_events = copy.deepcopy(state.events)
    messages = _protocol()._messages(
        state,
        b"png",
        protocol_recovery=recovery == "protocol",
        execution_recovery=recovery == "execution",
    )
    state_text = messages[2]["content"][0]["text"]
    summary = json.loads(state_text.split("\n")[1])
    projected = next(item for item in summary if item.get("step") == 2)["result"][
        "context_hint"
    ]
    assert len(json.dumps(projected, ensure_ascii=False)) <= 9_000
    if forwarded:
        projected = projected["downstream_context"]

    assert projected["cell_fields"] == cell_fields
    assert [dict(zip(cell_fields, cell, strict=True)) for cell in projected["cells"]] == (
        normalized_cells
    )
    assert projected["context_char_budget"] == 8_000
    assert state.task_id not in state_text
    assert body == original
    assert state.events == original_events
    assert [item["step"] for item in summary if "step" in item] == [1, 2]
    assert summary[0]["model_audit_required"]["event_step"] == 2
    if recovery:
        assert len(json.dumps(summary, ensure_ascii=False)) <= 9_000


@pytest.mark.parametrize("forwarded", [False, True])
@pytest.mark.parametrize("budget", [3000, 1500])
def test_compact_writer_cells_keep_field_legend_and_complete_record_prefix(
    forwarded, budget,
):
    fields = ["name", "text", "font_color", "row_index", "column_index"]
    cells = [
        {
            "name": f"{letter}{row}", "text": "Label", "font_color": "#146C94",
            "row_index": row, "column_index": column,
        }
        for row in range(1, 13)
        for column, letter in enumerate("ABCDE", 1)
    ]
    body = {"result": {"name": "Labels", "rows": 12, "columns": 5, "cells": cells}}
    original_body = copy.deepcopy(body)
    hint = adapter_context_hint("libreoffice_writer", "table.read", body)
    if forwarded:
        hint = {"downstream_action": "table.read", "downstream_context": hint}
    original_hint = copy.deepcopy(hint)

    projected = compact_context_hint_for_model(hint, remaining_chars=budget)

    assert len(json.dumps(projected)) <= budget
    observed = projected["downstream_context"] if forwarded else projected
    assert observed["cell_fields"] == fields
    records = observed["cells"]
    assert records
    assert all(len(record) == len(fields) for record in records)
    assert [dict(zip(fields, record, strict=True)) for record in records] == (
        cells[:len(records)]
    )
    if budget == 3000:
        assert len(records) == len(cells)
    else:
        assert len(records) < len(cells)
        assert observed["context_truncated"] is True
    assert hint == original_hint
    assert body == original_body


def test_projection_still_removes_explicit_internal_metadata_fields() -> None:
    projected = compact_context_hint_for_model(
        {
            "text": "The answer column is visible in the observed document.",
            "answer_value": "private-answer",
            "expected_state": {"sha256": "private-hash"},
            "reference_profile": "private-profile",
            "path": "/tmp/observed.txt",
        },
        remaining_chars=2_000,
    )

    encoded = json.dumps(projected, ensure_ascii=False).casefold()
    assert projected["text"].startswith("The answer column")
    assert "answer_value" not in encoded
    assert "private-answer" not in encoded
    assert "expected_state" not in encoded
    assert "private-hash" not in encoded
    assert "reference_profile" not in encoded


@pytest.mark.parametrize("saved", [False, True])
def test_command_result_keeps_observed_streams_in_forwarded_model_context(
    saved,
) -> None:
    raw = {
        "argv": ["diagnostic-tool"],
        "returncode": 0,
        "stdout": "Observed result: 27\n",
        "stderr": "Optional component was skipped\n",
    }
    if saved:
        raw.update(stdout_path="/tmp/diagnostic-output.txt", stdout_bytes=20)
    body = {
        "status": "ok",
        "result": {
            "adapter": "os",
            "action": "command.run",
            "response": {"status": "ok", "result": raw},
        },
    }
    original = copy.deepcopy(body)
    hint = adapter_context_hint("multi_apps", "adapter.call", body)
    summary = execution_context_summary(
        [event(1, action="adapter.call", result={"context_hint": hint})],
        "multi_apps",
        strict_generic=True,
    )
    projected = compact_execution_summary_for_model(summary)
    result = projected[0]["result"]["context_hint"]["downstream_context"]

    assert result["stdout"] == raw["stdout"]
    assert result["stderr"] == raw["stderr"]
    assert result["stdout_context_truncated"] is False
    assert result["output_saved"] is saved
    assert body == original


@pytest.mark.parametrize("forwarded", [False, True])
def test_captured_command_feedback_distinguishes_existing_terminal_output(
    forwarded: bool,
) -> None:
    body = {
        "status": "ok",
        "result": {
            "argv": ["uname", "-a"],
            "returncode": 0,
            "stdout": "Synthetic system details\n",
            "stderr": "",
        },
    }
    domain, action = "os", "command.run"
    if forwarded:
        body = {
            "status": "ok",
            "result": {"adapter": domain, "action": action, "response": body},
        }
        domain, action = "multi_apps", "adapter.call"
    original = copy.deepcopy(body)
    hint = adapter_context_hint(domain, action, body)
    summary = execution_context_summary(
        [event(1, action=action, result={"context_hint": hint})],
        domain,
        strict_generic=True,
    )
    result = compact_execution_summary_for_model(summary)[0]["result"]["context_hint"]
    if forwarded:
        result = result["downstream_context"]

    assert result["terminal_launch"] is False
    assert "not displayed in a desktop terminal" in result["guidance"]
    assert "terminal.show_output" in result["guidance"]
    assert result["stdout"] == "Synthetic system details\n"
    assert body == original


def test_terminal_launch_feedback_does_not_claim_background_capture() -> None:
    hint = adapter_context_hint(
        "os",
        "command.run",
        {
            "status": "ok",
            "result": {
                "argv": ["bash"],
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "terminal": {"launched": True, "child_status": "not_waited"},
            },
        },
    )
    assert hint["terminal_launch"] is True
    assert "Visible terminal launch was verified" in hint["guidance"]
    assert "not displayed in a desktop terminal" not in hint["guidance"]


def test_command_stream_projection_is_bounded_and_marks_truncation() -> None:
    hint = adapter_context_hint(
        "os",
        "command.run",
        {
            "status": "ok",
            "result": {
                "argv": ["diagnostic-tool"],
                "stdout": "x" * 10_000,
                "stderr": "",
            },
        },
    )

    assert len(hint["stdout"]) == 1_200
    assert hint["stdout_chars"] == 10_000
    assert hint["stdout_context_truncated"] is True
    assert hint["stderr"] == ""
    assert hint["stderr_context_truncated"] is False
    assert len(json.dumps(hint)) < 5_000


def test_projection_preserves_hex_observation_values_but_hides_error_prefixes() -> None:
    projected = compact_context_hint_for_model(
        {
            "text": "Observed color/hash token deadbeef in the document.",
            "error": {"detail": "session deadbeef"},
            "path": "/tmp/observed.txt",
        },
        remaining_chars=2_000,
    )

    assert "deadbeef" in projected["text"]
    assert projected["error"]["detail"] == "<internal-benchmark-metadata>"


def test_small_budget_keeps_selectors_before_verbose_guidance() -> None:
    value = {
        "path": "/tmp/important-output.txt",
        "matches": ["/tmp/a.txt", "/tmp/b.txt"],
        "guidance": "long guidance " * 500,
    }

    projected = compact_context_hint_for_model(value, remaining_chars=1_000)

    assert projected["path"] == "/tmp/important-output.txt"
    assert projected["matches"] == ["/tmp/a.txt", "/tmp/b.txt"]
    assert len(projected.get("guidance", "")) <= 1_200


@pytest.mark.parametrize("forwarded", [False, True])
def test_file_content_survives_before_usage_guidance(forwarded: bool) -> None:
    content = (
        "# source line\n" * 18
        + "def convert(value):\n    return value / 4\n"
        + "# source line\n" * 18
    )
    body = {
        "status": "ok",
        "result": {
            "path": "/tmp/measurements.py",
            "content": content,
            "total_chars": len(content),
            "total_lines": len(content.splitlines()),
            "truncated": False,
            "sibling_file_paths": ["/tmp/formatting.py", "/tmp/constants.py"],
            "sibling_file_count": 2,
        },
    }
    domain, action = "vs_code", "file.read_text"
    if forwarded:
        body = {
            "status": "ok",
            "result": {"adapter": domain, "action": action, "response": body},
        }
        domain, action = "multi_apps", "adapter.call"
    original = copy.deepcopy(body)
    hint = adapter_context_hint(domain, action, body)

    file_hint = hint["downstream_context"] if forwarded else hint
    assert "file.replace_literal replaces only old" in file_hint["guidance"]
    assert "complete current block in old" in file_hint["guidance"]
    assert "file.write_text" not in file_hint["guidance"]

    projected = compact_context_hint_for_model(hint, remaining_chars=3000)
    assert len(json.dumps(projected, ensure_ascii=False)) <= 3000
    if forwarded:
        projected = projected["downstream_context"]

    assert projected["files"][0]["handle"]["path"] == "/tmp/measurements.py"
    assert "".join(chunk["text"] for chunk in projected["files"][0]["chunks"]) == content
    assert body == original

    observation = ExecutionEvent(
        step=1,
        timestamp_utc="2026-09-06T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": {}},
        executed=True,
        result={"adapter_response": body, "context_hint": hint},
    )
    state = RuntimeState(
        task_id="synthetic-source-usage",
        domain=domain,
        instruction="Inspect the observed source file.",
        events=[observation],
    )
    mark_tool_result_for_audit(state, observation)
    messages = _protocol()._messages(state, b"png")
    encoded = json.dumps(messages)
    assert "file.replace_literal replaces only old" in encoded
    assert "complete current block in old" in encoded
    assert "file.write_text" not in encoded
    assert state.task_id not in encoded
    assert body == original


def test_presentation_projection_hard_bound_never_uses_prefix_preview() -> None:
    value = {
        "identity": {"url": "file:///tmp/deck.pptx", "title": "deck.pptx"},
        "slide_count": 80,
        "slides": [
            {
                "slide": index,
                "width": 50_800,
                "height": 28_575,
                "background": {"color": index},
                "graphic_shapes": [],
                "picture_containers": [],
                "text_shapes": [],
                "table_shapes": [],
            }
            for index in range(80)
        ],
    }

    # The existing Impress semantic projection remains application-owned; the
    # generic model boundary applies the hard budget after that projection.
    projected = compact_context_hint_for_model(
        compact_presentation_hint_for_model(value), remaining_chars=6_000
    )
    encoded = json.dumps(projected, ensure_ascii=False)

    assert len(encoded) <= 6_000
    assert isinstance(projected["slides"], list)
    assert "preview" not in encoded
    assert projected.get("context_truncated") is True or len(projected["slides"]) < 80


def test_presentation_projection_preserves_early_text_selectors() -> None:
    """A bounded deck view must not force text actions to guess selectors."""
    value = {
        "identity": {"url": "file:///tmp/deck.pptx", "title": "deck.pptx"},
        "slide_count": 22,
        "slides": [
            {
                "slide": index,
                "width": 50_800,
                "height": 28_575,
                "background": {"color": index},
                "graphic_shapes": [
                    {"path": [shape], "kind": "GraphicObjectShape"}
                    for shape in range(6)
                ],
                "picture_containers": [
                    {"path": [shape], "kind": "GraphicObjectShape"}
                    for shape in range(6)
                ],
                "text_shapes": [
                    {
                        "path": [shape],
                        "name": f"Textbox {shape}",
                        "kind": "CustomShape",
                        "lines": [f"Text {shape}"],
                        "text_style": {"color": 0},
                    }
                    for shape in range(3 if index == 0 else 5)
                ],
                "table_shapes": [],
            }
            for index in range(22)
        ],
    }

    projected = compact_context_hint_for_model(
        compact_presentation_hint_for_model(value), remaining_chars=6_000
    )
    first_slide = projected["slides"][0]
    assert first_slide["slide_index"] == 0
    assert first_slide["display_slide_number"] == 1
    assert "slide" not in first_slide
    assert first_slide["text_shapes"]
    assert first_slide["text_shapes_omitted"] == 0
    assert first_slide["text_shapes"][0]["path"] == [0]
    assert first_slide["text_shapes"][0]["tool_target"] == {
        "slide": 0, "selector": {"path": [0]}
    }


@pytest.mark.parametrize("wrapped", [False, True])
def test_large_presentation_keeps_early_graphics_and_text(wrapped) -> None:
    value = {
        "slide_count": 18,
        "slides": [
            {
                "slide": slide,
                "width": 32_000,
                "height": 18_000,
                "graphic_shapes": [
                    {
                        "path": [index],
                        "name": f"Diagram {index}",
                        "width": 5_000,
                        "height": 3_000,
                    }
                    for index in (6, 8, 11)
                ],
                "text_shapes": [
                    {"path": [index], "lines": ["Observed slide text. " * 16]}
                    for index in (2, 4)
                ],
            }
            for slide in range(18)
        ],
    }
    original = copy.deepcopy(value)
    if wrapped:
        hint = {
            "downstream_adapter": "libreoffice_impress",
            "downstream_action": "presentation.inspect",
            "downstream_context": value,
        }
        summary = execution_context_summary(
            [event(1, action="adapter.call", result={"context_hint": hint})],
            "multi_apps",
            strict_generic=True,
        )
        projected = summary[0]["result"]["context_hint"]["downstream_context"]
        budget = 12_000
    else:
        budget = 6_000
        projected = compact_context_hint_for_model(
            compact_presentation_hint_for_model(value), remaining_chars=budget
        )
    assert len(json.dumps(projected, ensure_ascii=False)) <= budget
    assert value == original
    for index, slide in enumerate(projected["slides"][:2]):
        assert slide["slide_index"] == index
        assert slide["display_slide_number"] == index + 1
        assert "slide" not in slide
        assert [shape["path"] for shape in slide["graphic_shapes"]] == [[6], [8], [11]]
        assert all(shape["tool_target"]["slide"] == index for shape in slide["graphic_shapes"])
        assert slide["text_shapes"]
        assert slide["graphic_shapes_omitted"] == 0
    assert len(projected["slides"]) >= 2


@pytest.mark.parametrize("wrapped", [False, True])
def test_presentation_notes_do_not_displace_all_observed_text(wrapped) -> None:
    value = {
        "slide_count": 24,
        "slides": [
            {
                "slide": index,
                "width": 32_000,
                "height": 18_000,
                "notes": "Speaker detail. " * 55,
                "graphic_shapes": [],
                "picture_containers": [],
                "text_shapes": [
                    {
                        "path": [shape],
                        "name": f"Box {shape}",
                        "lines": [f"Observed page {index}, line {shape}."],
                    }
                    for shape in (0, 1)
                ],
            }
            for index in range(24)
        ],
    }
    original = copy.deepcopy(value)
    owning = compact_presentation_hint_for_model(value)
    assert len(json.dumps(owning, ensure_ascii=False)) <= 12_000

    domain, action = "libreoffice_impress", "presentation.inspect"
    hint = value
    if wrapped:
        hint = {
            "downstream_adapter": domain,
            "downstream_action": action,
            "downstream_context": value,
        }
        domain, action = "multi_apps", "adapter.call"
    summary = execution_context_summary(
        [event(1, action=action, result={"context_hint": hint})],
        domain,
        strict_generic=True,
    )
    projected = summary[0]["result"]["context_hint"]
    if wrapped:
        projected = projected["downstream_context"]
    assert len(json.dumps(projected, ensure_ascii=False)) <= 12_000
    assert projected["slides"][0]["text_shapes"]
    assert projected["slides_omitted_from_context"] == 24 - len(projected["slides"])
    assert projected["guidance"] == owning["guidance"]
    assert "Speaker notes are metadata, not visible slide text" in projected["guidance"]
    assert "with explicit slides reads only those zero-based pages" in projected["guidance"]
    for slide in projected["slides"]:
        index = slide["slide_index"]
        assert slide["display_slide_number"] == index + 1
        assert slide["notes"] == value["slides"][index]["notes"]
        for shape in slide["text_shapes"]:
            path = shape["path"]
            assert shape["lines"] == value["slides"][index]["text_shapes"][path[0]]["lines"]
            assert shape["tool_target"] == {"slide": index, "selector": {"path": path}}
    assert value == original


def test_summary_keeps_durable_observation_and_coarse_older_failure() -> None:
    events = [
        event(
            1,
            action="filesystem.find",
            result={
                "context_hint": {
                    "path": "/tmp/important-report.txt",
                    "match_count": 1,
                    "guidance": "Use the exact returned path.",
                }
            },
        ),
        event(
            2,
            action="filesystem.copy",
            executed=False,
            result=None,
            error={"type": "PATH_NOT_FOUND", "detail": "/tmp/private.txt"},
        ),
    ]
    events.extend(
        event(step, action="filesystem.inspect", result={"status": "ok"})
        for step in range(3, 16)
    )

    summary = execution_context_summary(
        events,
        "os",
        limit=3,
        strict_generic=True,
    )
    history = summary[0]

    assert history["history_summary"] is True
    observations = history["durable_observations"]
    assert any(item["step"] == 1 for item in observations)
    failures = history["failed_actions"]
    assert failures[0]["error_type"] == "PATH_NOT_FOUND"
    encoded = json.dumps(history, ensure_ascii=False)
    assert "/tmp/private.txt" not in encoded
    assert "preview" not in encoded


def test_durable_history_reuses_unused_shares_without_losing_format_counts() -> None:
    matches = [
        {
            "paragraph_index": index,
            "start_offset": 0,
            "end_offset": len(f"entry-{index}"),
            "matched_text": f"entry-{index}",
            "format": {
                "font_size": 18.0,
                "bold": False,
                "italic": True,
                "script": "normal",
            },
        }
        for index in range(23)
    ]
    large = {
        "matches": matches,
        "returned_count": len(matches),
        "has_more": False,
        "format_counts": [
            {"format": matches[0]["format"], "match_count": len(matches)}
        ],
        "format_counts_scope": "returned_matches",
    }
    assert 4000 < len(json.dumps(large)) < 5000
    small = {
        "paragraph_index": 0,
        "start_offset": 0,
        "end_offset": 7,
        "text": "entry-0",
        "format": {"font_size": 23.5},
    }
    events = [
        event(1, action="text.find", result={"context_hint": large}),
        event(2, action="text.set_format", result={"context_hint": small}),
        *[
            event(step, action="document.inspect", result={"status": "ok"})
            for step in range(3, 7)
        ],
    ]
    original = copy.deepcopy(large)

    summary = execution_context_summary(
        events, "libreoffice_writer", limit=4, strict_generic=True
    )
    recovery = compact_execution_summary_for_model(summary, max_chars=9000)
    history = next(item for item in recovery if item.get("history_summary"))
    observations = {
        item["action"]: item["observation"] for item in history["durable_observations"]
    }

    assert observations["text.find"] == large
    assert observations["text.set_format"] == small
    assert len(json.dumps(recovery)) <= 9000
    assert large == original


def test_small_batch_keeps_successful_receipts_when_they_enter_history() -> None:
    source_path = "/tmp/source.py"
    hints = [
        {
            "downstream_adapter": "vs_code",
            "downstream_action": "file.read_text",
            "downstream_status": "ok",
            "verification_passed": True,
            "downstream_context": {
                "observation_type": "text_batch",
                "reader_action": "file.read_text",
                "matched_count": 1,
                "files": [{"path": source_path, "text": "pending operation\n"}],
            },
        },
        {
            "downstream_adapter": "vs_code",
            "downstream_action": "file.replace_literal",
            "downstream_status": "ok",
            "verification_passed": True,
            "downstream_context": {
                "path": source_path,
                "content": "print('ready')\n",
                "replacement_count": 1,
            },
        },
        {
            "downstream_adapter": "os",
            "downstream_action": "command.run",
            "downstream_status": "ok",
            "verification_passed": True,
            "downstream_context": {
                "argv": ["python3", source_path],
                "returncode": 0,
                "stdout": "ready\n",
                "stdout_path": None,
                "output_saved": False,
                "guidance": "Stdout was returned but not saved to a file.",
            },
        },
    ]
    events = [
        event(step, action="adapter.call", result={"context_hint": hint})
        for step, hint in enumerate(hints, 1)
    ]
    recent = execution_context_summary(
        events, "multi_apps", limit=4, strict_generic=True
    )
    events.extend(
        event(
            step,
            action="adapter.call",
            executed=False,
            error={"type": "ValueError", "detail": "The command already ran."},
        )
        for step in range(4, 8)
    )
    original = copy.deepcopy(events)
    history = execution_context_summary(
        events, "multi_apps", limit=4, strict_generic=True
    )
    recovered = compact_execution_summary_for_model(history, max_chars=16_000)
    observations = [
        {item["step"]: item["result"]["context_hint"] for item in recent},
        *[
            {
                item["step"]: item["observation"]
                for item in summary[0]["durable_observations"]
            }
            for summary in (history, recovered)
        ],
    ]

    for observed in observations:
        assert observed[2] == hints[1]
        assert observed[3] == hints[2]
        assert "pending operation" in json.dumps(observed[1])
    assert len(json.dumps(recovered, ensure_ascii=False)) <= 16_000
    assert events == original


def test_durable_history_keeps_the_existing_total_observation_budget() -> None:
    events = [
        event(
            index,
            action=action,
            result={
                "context_hint": {
                    "name": f"observed-{index}",
                    "rows": [
                        {"index": row, "text": "value " * 40} for row in range(30)
                    ],
                }
            },
        )
        for index, action in enumerate(
            ("range.read", "document.inspect", "table.read"), 1
        )
    ]
    observations = durable_observations(
        events,
        "synthetic",
        strict_generic=True,
        budget=8000,
        context_hint_for_model=lambda domain, action, hint, **kwargs: hint,
    )

    assert len(observations) == 3
    assert sum(len(json.dumps(item["observation"])) for item in observations) <= 8000
    assert all(item["observation"].get("context_truncated") for item in observations)


@pytest.mark.parametrize("forwarded", [False, True])
@pytest.mark.parametrize("resource_kind", ["path", "identity", "text_batch"])
def test_durable_history_distinguishes_routes_and_observed_files(
    forwarded: bool, resource_kind: str
) -> None:
    events = []
    for step, path, content in (
        (1, "/tmp/brief.txt", "superseded source text"),
        (2, "/tmp/notes.txt", "independent source text"),
        (3, "/tmp/brief.txt", "updated source text"),
    ):
        if resource_kind == "text_batch":
            hint = {
                "observation_type": "text_batch",
                "files": [{"path": path, "text": content}],
            }
        elif resource_kind == "identity":
            hint = {"identity": {"url": f"file://{path}"}, "content": content}
        else:
            hint = {"path": path, "content": content}
        if forwarded:
            hint = {
                "downstream_adapter": "libreoffice_writer",
                "downstream_action": "document.read_file",
                "downstream_context": hint,
            }
        events.append(
            event(
                step,
                action="adapter.call" if forwarded else "document.read_file",
                result={"context_hint": hint},
            )
        )
    for step in (4, 5):
        hint = {"match_count": step, "matches": []}
        if forwarded:
            hint = {
                "downstream_adapter": "os",
                "downstream_action": "filesystem.find",
                "downstream_context": hint,
            }
        events.append(
            event(
                step,
                action="adapter.call" if forwarded else "filesystem.find",
                result={"context_hint": hint},
            )
        )
    events.extend(event(step, action="window.inspect") for step in range(6, 10))
    original = copy.deepcopy(events)

    summary = execution_context_summary(
        events, "multi_apps" if forwarded else "os", limit=4, strict_generic=True
    )
    recovery = compact_execution_summary_for_model(summary, max_chars=16_000)
    for projected in (summary, recovery):
        history = next(item for item in projected if item.get("history_summary"))
        observations = history["durable_observations"]
        assert [item["step"] for item in observations] == [2, 3, 5]
        encoded = json.dumps(observations)
        assert "independent source text" in encoded
        assert "updated source text" in encoded
        assert "superseded source text" not in encoded
    assert len(json.dumps(recovery)) <= 16_000
    assert events == original


def test_durable_forwarded_identity_includes_owning_adapter() -> None:
    events = [
        event(
            step,
            action="adapter.call",
            result={
                "context_hint": {
                    "downstream_adapter": adapter,
                    "downstream_action": "document.inspect",
                    "downstream_context": {"title": "Shared title", "revision": step},
                }
            },
        )
        for step, adapter in enumerate(("libreoffice_writer", "vs_code"), 1)
    ]
    observations = durable_observations(
        events,
        "multi_apps",
        strict_generic=True,
        budget=8000,
        context_hint_for_model=lambda domain, action, hint, **kwargs: hint,
    )
    assert [item["step"] for item in observations] == [1, 2]


def test_summary_projects_nested_results_without_opaque_prefixes() -> None:
    huge_hint = {
        "downstream_adapter": "libreoffice_impress",
        "downstream_action": "presentation.inspect",
        "downstream_context": {
            "identity": {"url": "file:///tmp/deck.pptx", "title": "deck.pptx"},
            "slide_count": 80,
            "slides": [
                {
                    "slide": index,
                    "width": 50_800,
                    "height": 28_575,
                    "graphic_shapes": [],
                    "picture_containers": [],
                    "text_shapes": [],
                    "table_shapes": [],
                }
                for index in range(80)
            ],
        },
    }
    summary = execution_context_summary(
        [event(1, action="adapter.call", result={"context_hint": huge_hint})],
        "multi_apps",
        strict_generic=True,
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert "preview" not in encoded
    projected = summary[0]["result"]["context_hint"]["downstream_context"]
    # The declared presentation window is 12k, plus the existing 1k envelope.
    assert len(json.dumps(projected, ensure_ascii=False)) <= 12_000
    assert len(encoded) < 13_000
    assert projected["slides"]


def test_summary_projects_nested_impress_graphic_selectors() -> None:
    """A wrapped Impress inspection keeps observed picture targets visible."""
    wrapped = {
        "downstream_adapter": "libreoffice_impress",
        "downstream_action": "presentation.inspect",
        "downstream_context": {
            "identity": {"url": "file:///tmp/deck.pptx", "title": "deck.pptx"},
            "slide_count": 2,
            "slides": [
                {
                    "slide": 1,
                    "width": 33867,
                    "height": 19050,
                    "graphic_shapes": [
                        {
                            "index": 0,
                            "path": [0],
                            "name": "Photo",
                            "kind": "com.sun.star.drawing.GraphicObjectShape",
                            "x": 0,
                            "y": 0,
                            "width": 30000,
                            "height": 18000,
                        }
                    ],
                    "picture_containers": [],
                    "text_shapes": [],
                    "table_shapes": [],
                }
            ],
        },
    }

    summary = execution_context_summary(
        [event(1, action="adapter.call", result={"context_hint": wrapped})],
        "multi_apps",
        strict_generic=True,
    )

    nested = summary[0]["result"]["context_hint"]["downstream_context"]
    assert nested["slides"][0]["graphic_shapes"][0]["tool_target"] == {
        "slide": 1,
        "selector": {"path": [0]},
    }
    from impress_adapter.schema import validate_action_params

    validate_action_params(
        "shape.export_image",
        {
            **nested["slides"][0]["graphic_shapes"][0]["tool_target"],
            "output_path": "/tmp/selected-image.png",
        },
    )


def test_protocol_recovery_preserves_batch_continuation_ranges() -> None:
    batch = _text_batch_hint(count=9, text_chars=4_000)
    wrapped = {
        "downstream_adapter": "os",
        "downstream_action": "pdf.extract_text_batch",
        "downstream_status": "ok",
        "verification_passed": True,
        "downstream_context": batch,
    }
    events = [
        event(
            1,
            action="adapter.call",
            result={"context_hint": wrapped},
        ),
        event(2, action="spreadsheet.inspect_current", result={"status": "ok"}),
        event(3, action="spreadsheet.read_file", result={"status": "ok"}),
        event(
            4,
            action="spreadsheet.write_range",
            executed=False,
            error={"type": "INVALID_ARGUMENT", "detail": "values required"},
        ),
        event(5, action="spreadsheet.inspect_current", result={"status": "ok"}),
    ]

    normal = execution_context_summary(
        events,
        "multi_apps",
        limit=4,
        strict_generic=True,
    )
    recovered = compact_execution_summary_for_model(normal, max_chars=9_000)
    encoded = json.dumps(recovered, ensure_ascii=False)

    assert len(encoded) <= 9_000
    observations = [
        item
        for entry in recovered
        if isinstance(entry, dict)
        for item in entry.get("durable_observations", [])
        if isinstance(item, dict)
    ]
    assert observations
    observation = observations[0]["observation"]["downstream_context"]
    assert observation["guidance"]
    assert observation["has_more"] is True
    assert observation["input_directory"] == "/home/user/Documents/sources"
    assert observation["input_pattern"] == "*.pdf"
    assert len(observation["files"]) == 9
    assert observation["source_has_more"] is True
    assert observation["context_has_more"] is True
    assert observation["context_files_omitted"] == 0
    first_file = observation["files"][0]
    assert first_file["handle"]["path"].endswith("source-0.pdf")
    assert first_file["chunks"]
    assert all(
        sum(
            len(chunk.get("text", ""))
            for chunk in file.get("chunks", [])
            if isinstance(chunk, dict)
        )
        >= 40
        for file in observation["files"]
    )
    chunk = first_file["chunks"][0]
    assert {"start_char", "end_char"}.issubset(chunk)
    assert (
        chunk.get("offset_basis", first_file["offset_basis"]) == "adapter_returned_text"
    )
    assert chunk["source_has_more"] is True
    assert chunk["context_has_more"] is True
    assert "preview" not in encoded


def test_batch_recovery_compaction_is_bounded_non_mutating_and_redacted() -> None:
    value = _text_batch_hint(count=20, text_chars=2_000)
    value["answer_value"] = "private-answer"
    value["files"][0]["private_preview"] = "private-preview"
    original = copy.deepcopy(value)

    projected = compact_context_hint_for_model(value, remaining_chars=2_000)
    encoded = json.dumps(projected, ensure_ascii=False)

    assert len(encoded) <= 2_000
    assert value == original
    assert projected["context_truncated"] is True
    assert projected["files_omitted"] > 0
    assert projected["files"]
    assert "private-answer" not in encoded
    assert "private-preview" not in encoded
    assert "answer_value" not in encoded
    assert "private_preview" not in encoded

    tiny = compact_context_hint_for_model(value, remaining_chars=63)
    assert len(json.dumps(tiny, ensure_ascii=False)) <= 63


def test_batch_recovery_keeps_all_observed_handles_before_optional_detail() -> None:
    value = _text_batch_hint(count=20, text_chars=2_000)
    value["context_char_budget"] = 8_000

    projected = compact_context_hint_for_model(value, remaining_chars=9_000)

    assert len(json.dumps(projected, ensure_ascii=False)) <= 9_000
    assert len(projected["files"]) == 20
    assert projected["files_omitted"] == 0
    assert all("handle" in item for item in projected["files"])


def test_batch_recovery_marks_chunks_omitted_by_the_source_projection() -> None:
    value = _text_batch_hint(count=1, text_chars=200)
    value["files"][0]["chunks"] = [
        {
            "type": "text",
            "offset_basis": "adapter_returned_text",
            "index": index,
            "start_char": index * 50,
            "end_char": (index + 1) * 50,
            "total_chars": 200,
            "text": f"chunk-{index}",
            "has_more": False,
        }
        for index in range(3)
    ]
    value["files"][0].pop("text")

    projected = compact_context_hint_for_model(value, remaining_chars=5_000)

    assert len(projected["files"][0]["chunks"]) == 2
    assert projected["files"][0]["has_more"] is True
    assert projected["has_more"] is True


def test_recovery_keeps_latest_batch_and_recent_failure_with_two_batches() -> None:
    older = _text_batch_hint(count=9, text_chars=4_000)
    latest = _text_batch_hint(count=1, text_chars=1_000)
    latest["input_pattern"] = "source-0.pdf"
    summary = [
        {"step": 1, "result": {"context_hint": older}},
        {"step": 2, "result": {"context_hint": latest}},
        {
            "step": 3,
            "action": "spreadsheet.write_range",
            "executed": False,
            "error": {"type": "INVALID_ARGUMENT"},
        },
        {
            "step": 4,
            "action": "spreadsheet.inspect_current",
            "executed": True,
            "result": {"status": "ok"},
        },
    ]

    recovered = compact_execution_summary_for_model(summary, max_chars=9_000)
    encoded = json.dumps(recovered, ensure_ascii=False)

    assert len(encoded) <= 9_000
    assert encoded.count('"observation_type": "text_batch"') == 1
    assert "source-0.pdf" in encoded
    assert "INVALID_ARGUMENT" in encoded
    assert "spreadsheet.write_range" in encoded


@pytest.mark.parametrize("max_chars", [9_000, 16_000])
def test_small_batch_releases_unused_recovery_budget_to_catalog_and_error(
    max_chars: int,
) -> None:
    batch = {
        "step": 1,
        "action": "adapter.call",
        "result": {
            "context_hint": {
                "downstream_adapter": "os",
                "downstream_action": "pdf.extract_text_batch",
                "downstream_context": _text_batch_hint(count=1, text_chars=195),
            }
        },
    }
    matches = [
        {
            "adapter": "os",
            "action": action,
            "tool_name": f"adapter__{action.replace('.', '_')}",
            "description": "Read the model-selected local resource without editing it.",
            "match_reason": "Matched the requested read-only file operation.",
        }
        for action in (
            "filesystem.find",
            "filesystem.inspect",
            "file.read_text",
            "pdf.extract_text",
            "pdf.outline.inspect",
        )
    ]
    summary = [
        batch,
        *[
            {
                "step": step,
                "action": "tools.search",
                "executed": True,
                "result": {"status": "ok", "matches": copy.deepcopy(matches)},
            }
            for step in range(2, 5)
        ],
        {
            "step": 5,
            "action": "file.read_text",
            "executed": False,
            "error": {
                "type": "AdapterError",
                "details": {
                    "code": "FILE_NOT_FOUND",
                    "message": "The selected local path does not exist.",
                    "path": "/tmp/missing-notes.txt",
                },
            },
        },
    ]
    original = copy.deepcopy(summary)

    recovered = compact_execution_summary_for_model(summary, max_chars=max_chars)
    batch_only = compact_execution_summary_for_model([batch], max_chars=max_chars)

    assert len(json.dumps(recovered, ensure_ascii=False)) <= max_chars
    assert summary == original
    assert recovered[0] == batch_only[0]
    assert [entry["step"] for entry in recovered] == [1, 2, 3, 4, 5]
    for entry in recovered[1:4]:
        assert entry["result"]["matches"] == matches
    assert recovered[-1] == original[-1]


def test_projection_drops_legacy_opaque_preview_and_internal_signatures() -> None:
    summary = execution_context_summary(
        [
            event(
                2,
                action="filesystem.find",
                result={
                    "truncated": True,
                    "chars": 10_000,
                    "preview": '{"private":"should not be shown"',
                    "path": "/tmp/observed.txt",
                    "argument_signature": "another-internal-hash",
                },
            )
        ],
        "os",
        strict_generic=True,
    )

    encoded = json.dumps(summary, ensure_ascii=False)
    assert "preview" not in encoded
    assert "should not be shown" not in encoded
    assert "argument_signature" not in encoded
    assert "another-internal-hash" not in encoded
    assert summary[0]["result"]["path"] == "/tmp/observed.txt"


def test_summary_redacts_forbidden_action_names_and_keeps_nested_error_code() -> None:
    forbidden = event(
        1,
        action="task.execute",
        executed=False,
        error={
            "type": "AdapterError",
            "details": {"code": "PATH_NOT_FOUND", "detail": "golden"},
        },
    )

    summary = execution_context_summary([forbidden], "os", strict_generic=True)
    encoded = json.dumps(summary, ensure_ascii=False).casefold()

    assert "task.execute" not in encoded
    assert "task_execute" not in encoded
    assert "golden" not in encoded
    assert summary[0]["error"]["details"]["code"] == "PATH_NOT_FOUND"


@pytest.mark.parametrize(
    "route",
    [
        "task%2Eexecute",
        r"task\u002Eexecute",
        "ｔａｓｋ．ｅｘｅｃｕｔｅ",
        "assessment/grade/multiple_choice_documents",
    ],
)
def test_summary_redacts_encoded_forbidden_routes(route: str) -> None:
    forbidden = event(step=1, action="generic.observe", error={"message": route})
    summary = execution_context_summary([forbidden], "os", strict_generic=True)
    encoded = json.dumps(summary, ensure_ascii=False)

    assert route not in encoded
    assert "internal-benchmark-metadata" in encoded


@pytest.mark.parametrize(
    "text",
    [
        "The agent can select actions, execute subtasks, and evaluate results.",
        "Read the article; execute the selected application step after inspection.",
    ],
)
def test_document_prose_does_not_match_punctuation_joined_forbidden_route(
    text: str,
) -> None:
    projected = compact_context_hint_for_model(
        {"text": text, "path": "/tmp/observed.pdf"}, remaining_chars=2_000
    )
    assert projected["text"] == text


def test_failure_summary_prefers_error_inside_repeated_action_wrapper() -> None:
    failed = event(
        2,
        action="filesystem.find",
        executed=False,
        error={
            "type": "RepeatedActionBlocked",
            "previous_error": {
                "type": "INVALID_ARGUMENT",
                "detail": "path is not absolute",
            },
        },
    )

    summary = failure_summary(failed)

    assert summary is not None
    assert summary["error_type"] == "INVALID_ARGUMENT"


def _observed_filename_messages(
    filename: str, task_id: str, forwarded: bool
) -> tuple[dict, list[dict], dict]:
    body = {
        "status": "ok",
        "result": {
            "match_count": 1,
            "returned_count": 1,
            "truncated": False,
            "matches": [
                {"path": f"/tmp/{filename}", "name": filename, "kind": "file"}
            ],
        },
    }
    domain, action = "os", "filesystem.find"
    if forwarded:
        body = {
            "status": "ok",
            "result": {"adapter": domain, "action": action, "response": body},
        }
        domain, action = "multi_apps", "adapter.call"
    original = copy.deepcopy(body)
    hint = adapter_context_hint(domain, action, body)
    assert isinstance(hint, dict)
    observation = ExecutionEvent(
        step=1,
        timestamp_utc="2026-09-12T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": {}},
        executed=True,
        result=sanitize_agent_visible_result({"context_hint": hint}, task_id),
    )
    state = RuntimeState(
        task_id=task_id,
        domain=domain,
        instruction="Locate the spreadsheet and use its exact observed path.",
        events=[observation],
    )
    mark_tool_result_for_audit(state, observation)
    messages = _protocol()._messages(state, b"synthetic-screenshot")
    summary = json.loads(messages[2]["content"][0]["text"].split("\n")[1])
    entry = next(item for item in summary if item.get("step") == 1)
    projected = entry["result"]["context_hint"]
    if forwarded:
        projected = projected["downstream_context"]
    assert body == original
    return body, messages, projected["matches"][0]


@pytest.mark.parametrize("forwarded", [False, True])
def test_ordinary_uuid_filename_reaches_model_unchanged(forwarded: bool) -> None:
    task_id = "123e4567-e89b-12d3-a456-426614174000"
    filename = "report_51b36b92-99f9-4c60-8a73-28d4581d59ca.xlsx"
    _, messages, observed = _observed_filename_messages(filename, task_id, forwarded)

    assert observed["name"] == filename
    assert observed["path"] == f"/tmp/{filename}"
    assert_agent_surface_safe(task_id=task_id, messages=messages, tools=[])


@pytest.mark.parametrize("forwarded", [False, True])
@pytest.mark.parametrize("identity_part", ["uuid", "prefix"])
def test_observed_filename_still_protects_actual_task_identity(
    forwarded: bool, identity_part: str
) -> None:
    task_id = "123e4567-e89b-12d3-a456-426614174000"
    token = task_id if identity_part == "uuid" else task_id[:8]
    filename = f"report_{token}.xlsx"
    body, messages, observed = _observed_filename_messages(filename, task_id, forwarded)

    assert token not in json.dumps(messages, ensure_ascii=False)
    assert observed["name"] != filename
    assert observed["path"] != f"/tmp/{filename}"
    assert_agent_surface_safe(task_id=task_id, messages=messages, tools=[])
    with pytest.raises(RuntimeError, match="task identity"):
        assert_agent_surface_safe(
            task_id=task_id,
            messages=[{"role": "user", "content": json.dumps(body)}],
            tools=[],
        )


def test_context_projection_redacts_identity_keys_and_sensitive_uuid_values() -> None:
    value = {
        "TASKID": "task-id-sentinel",
        "Task-UUID": "123e4567-e89b-12d3-a456-426614174000",
        "task-prefix": "deadbeef",
        "error": {"runtime-note": "session 123e4567-e89b-72d3-a456-426614174000"},
        "EvaluatorURL": "https://example.invalid/evaluator",
        "ExpectedState": {"answer": "secret"},
        "answer_value": "SECRET_ANSWER_VALUE",
        "task-inspect": "task-inspect",
        "nested": {
            "tool": "task_execute",
            "action": "artifact.materialize",
            "path": "/tmp/visible.txt",
        },
    }

    projected = compact_context_hint_for_model(value, remaining_chars=2_000)
    encoded = json.dumps(projected, ensure_ascii=False).casefold()

    assert "task-id-sentinel" not in encoded
    assert "123e4567-e89b-12d3-a456-426614174000" not in encoded
    assert "deadbeef" not in encoded
    assert "123e4567-e89b-72d3-a456-426614174000" not in encoded
    assert "evaluatorurl" not in encoded
    assert "answer_value" not in encoded
    assert "secret_answer_value" not in encoded
    assert "task-inspect" not in encoded
    assert "task_execute" not in encoded
    assert "artifact.materialize" not in encoded
    assert projected["nested"]["path"] == "/tmp/visible.txt"


def test_context_projection_redacts_encoded_uuid_values_in_error_context() -> None:
    task_id = "123e4567-e89b-12d3-a456-426614174000"
    encoded = "".join(f"%{ord(character):02X}" for character in task_id)

    projected = compact_context_hint_for_model(
        {"error": {"message": encoded}, "path": "/tmp/visible.txt"},
        remaining_chars=2_000,
    )

    assert projected["error"]["message"] == "<internal-benchmark-metadata>"
    assert projected["path"] == "/tmp/visible.txt"


def test_context_projection_redacts_unicode_escaped_uuid_values_in_error_context() -> None:
    task_id = "123e4567-e89b-12d3-a456-426614174000"
    encoded = "".join(f"\\u{ord(character):04x}" for character in task_id)
    doubly_escaped = encoded.replace("\\", "\\\\")

    for value in (encoded, doubly_escaped):
        projected = compact_context_hint_for_model(
            {"error": {"message": value}, "path": "/tmp/visible.txt"},
            remaining_chars=2_000,
        )
        assert projected["error"]["message"] == "<internal-benchmark-metadata>"
        assert projected["path"] == "/tmp/visible.txt"


def test_context_projection_redacts_sensitive_error_token_variants() -> None:
    projected = compact_context_hint_for_model(
        {
            "error_code": "ANSWER_SECRET",
            "error": {"type": "EXPECTED_SECRET"},
            "value": "EXPECTED_SECRET",
            "path": "/tmp/visible.txt",
        },
        remaining_chars=2_000,
    )

    encoded = json.dumps(projected, ensure_ascii=False).casefold()

    assert "answer_secret" not in encoded
    assert "expected_secret" not in encoded
    assert projected["path"] == "/tmp/visible.txt"


def test_failure_summary_filters_sensitive_key_family_variants() -> None:
    failed = event(
        1,
        action="filesystem.find",
        executed=False,
        error={"type": "INVALID_ARGUMENT"},
    )
    failed.proposed["arguments"].update(
        {
            "answer_value": "SECRET_ARG",
            "Task-UUID": "123e4567-e89b-12d3-a456-426614174000",
            "task-inspect": "task-inspect",
            "roots": ["~/"],
        }
    )

    summary = failure_summary(failed)

    assert summary is not None
    assert summary["argument_fields"] == ["path", "roots"]
    encoded = json.dumps(summary, ensure_ascii=False).casefold()
    assert "secret_arg" not in encoded
    assert "answer_value" not in encoded
    assert "task-inspect" not in encoded


def test_projection_hard_bounds_long_lists_and_nested_records() -> None:
    value = {
        "path": "/tmp/result.txt",
        "rows": [{"index": index, "text": "value" * 500} for index in range(200)],
    }

    projected = compact_context_hint_for_model(value, remaining_chars=200)
    encoded = json.dumps(projected, ensure_ascii=False)

    assert len(encoded) <= 200
    assert json.loads(encoded) == projected


def test_execution_summary_has_one_total_budget_for_many_large_hints() -> None:
    events = [
        event(
            step=index,
            action=f"observe_{index}",
            result={
                "context_hint": {
                    "path": f"/tmp/observed-{index}.txt",
                    "selector": {"index": index, "name": f"item-{index}"},
                    "rows": [{"index": row, "text": "x" * 900} for row in range(80)],
                }
            },
        )
        for index in range(16)
    ]

    summary = execution_context_summary(
        events,
        "os",
        limit=16,
        strict_generic=True,
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert len(encoded) <= 65_000
    assert summary
    # The most recent observation remains available after structural fitting.
    assert any(item.get("step") == 15 for item in summary if isinstance(item, dict))
    assert "preview" not in encoded


def _text_batch_hint(*, count: int = 4, text_chars: int = 8_000) -> dict:
    return {
        "input_directory": "/home/user/Documents/sources",
        "input_pattern": "*.pdf",
        "start_page": 1,
        "matched_count": count,
        "total_returned_chars": count * text_chars,
        "files": [
            {
                "path": f"/home/user/Documents/sources/source-{index}.pdf",
                "status": "ok",
                "source_kind": "pdf",
                "pages_processed": 3,
                "returned_chars": text_chars,
                "extracted_chars": text_chars + 1_000,
                "raw_extracted_chars": text_chars + 1_500,
                "truncated": True,
                "text": (f"record-{index} " * (text_chars // 10))[:text_chars],
                # This legacy field must never be copied as an opaque prefix.
                "preview": '{"private":"not model content"}',
            }
            for index in range(count)
        ],
    }


def test_text_batch_projection_is_typed_bounded_and_keeps_handles() -> None:
    value = _text_batch_hint(count=8, text_chars=12_000)

    projected = text_batch_context_for_model(value)
    encoded = json.dumps(projected, ensure_ascii=False)

    assert len(encoded) <= 18_000
    assert projected["observation_type"] == "text_batch"
    assert projected["context_truncated"] is True
    assert projected["has_more"] is True
    assert len(projected["files"]) == 8
    first = projected["files"][0]
    assert first["handle"] == {
        "kind": "file",
        "path": "/home/user/Documents/sources/source-0.pdf",
    }
    assert first.get("path", first["handle"]["path"]) == first["handle"]["path"]
    assert first["metadata"]["source_kind"] == "pdf"
    assert first["metadata"]["pages_processed"] == 3
    assert first["metadata"]["source_truncated"] is True
    assert first["chunks"][0]["type"] == "text"
    assert first["chunks"][0]["start_char"] == 0
    assert first["chunks"][0]["end_char"] <= 2_400
    assert first["chunks"][0]["source_has_more"] is True
    assert len(first["chunks"]) == 2
    head, tail = first["chunks"]
    source_text = value["files"][0]["text"]
    assert head.get("offset_basis", first["offset_basis"]) == "adapter_returned_text"
    assert tail.get("offset_basis", first["offset_basis"]) == "adapter_returned_text"
    assert head["text"] == source_text[head["start_char"] : head["end_char"]]
    assert tail["text"] == source_text[tail["start_char"] : tail["end_char"]]
    assert head["end_char"] <= tail["start_char"]
    assert tail["end_char"] == len(source_text)
    assert head.get("total_chars", first["source_total_chars"]) == 13_000
    assert tail.get("total_chars", first["source_total_chars"]) == 13_000
    assert head["source_has_more"] is True
    assert tail["source_has_more"] is True
    assert head.get("has_more", head["source_has_more"]) is True
    assert tail.get("has_more", tail["source_has_more"]) is True
    assert head["context_has_more"] is True
    assert tail["context_has_more"] is True
    assert "preview" not in encoded
    assert "private" not in encoded


def test_text_batch_projection_keeps_long_text_tail_with_truthful_offsets() -> None:
    text = "HEADER\n" + ("middle\n" * 700) + "TAIL-SENTINEL\n"
    value = {
        "input_directory": "/tmp/sources",
        "input_pattern": "*.txt",
        "matched_count": 1,
        "files": [
            {
                "path": "/tmp/sources/long.txt",
                "status": "ok",
                "extracted_chars": len(text),
                "returned_chars": len(text),
                "truncated": False,
                "text": text,
                "private_preview": "must remain outside the projection",
            }
        ],
    }

    projected = text_batch_context_for_model(value, max_chars=3_000)
    encoded = json.dumps(projected, ensure_ascii=False)
    file = projected["files"][0]
    chunks = file["chunks"]

    assert len(encoded) <= 3_000
    assert len(chunks) == 2
    head, tail = chunks
    assert (
        head.get("offset_basis", file["offset_basis"])
        == tail.get("offset_basis", file["offset_basis"])
        == "adapter_returned_text"
    )
    assert head["text"] == text[head["start_char"] : head["end_char"]]
    assert tail["text"] == text[tail["start_char"] : tail["end_char"]]
    assert head["start_char"] == 0
    assert head["end_char"] <= tail["start_char"]
    assert tail["end_char"] == len(text)
    assert (
        head.get("total_chars", file["source_total_chars"])
        == tail.get("total_chars", file["source_total_chars"])
        == len(text)
    )
    assert "TAIL-SENTINEL" in tail["text"]
    assert "private_preview" not in encoded
    assert "must remain outside the projection" not in encoded


@pytest.mark.parametrize("through_messages", [False, True])
def test_text_batch_table_metadata_does_not_starve_every_file_header(
    through_messages: bool,
) -> None:
    header = (
        "Category\tRequested units\tApproved units\tRequested funds\tApproved funds\n"
    )
    totals = "\t".join(str(index * 17) for index in range(1, 29))
    text = (
        "Annual resource allocation report\n"
        + header
        + "detail\t17\t9\t200\t100\n" * 100
        + "Subtotal\t"
        + totals
        + "\n"
        + "additional detail\t21\t12\t400\t150\n" * 40
        + "Total\t"
        + totals
        + "\nEnd of report\n"
    )
    files = [
        {
            "path": f"/home/user/Documents/department-reports/annual/period-{index}.pdf",
            "status": "ok",
            "text": text,
            "source_kind": None,
            "pages_processed": None,
            "returned_chars": len(text),
            "extracted_chars": len(text),
            "raw_extracted_chars": len(text) + 500,
            "source_start_char": 0,
            "source_end_char": len(text),
            "source_total_chars": len(text),
            "next_start_char": None,
            "offset_basis": "layout_compacted_text",
            "source_truncated": False,
        }
        for index in range(10)
    ]
    value = {"input_pattern": "*.pdf", "matched_count": len(files), "files": files}
    original = json.dumps(value, ensure_ascii=False)

    if through_messages:
        state = RuntimeState(
            task_id="synthetic-batch-context",
            domain="multi_apps",
            instruction="Read the reports.",
            events=[
                event(
                    1,
                    action="adapter.call",
                    result={
                        "context_hint": {
                            "downstream_adapter": "os",
                            "downstream_action": "pdf.extract_text_batch",
                            "downstream_context": value,
                        }
                    },
                )
            ],
        )
        messages = _protocol()._messages(state, b"synthetic-screenshot")
        summary = json.loads(messages[2]["content"][0]["text"].split("\n")[1])
        projected = summary[0]["result"]["context_hint"]["downstream_context"]
    else:
        projected = text_batch_context_for_model(value)

    assert len(json.dumps(projected, ensure_ascii=False)) <= 18_000
    assert len(projected["files"]) == len(files)
    assert projected["files_omitted"] == 0
    assert projected["source_has_more"] is False
    assert projected["context_char_budget"] == 18_000
    assert "narrow input_pattern to one observed basename" in projected["guidance"]
    assert len(projected["guidance"]) <= 320
    for source, observed in zip(files, projected["files"], strict=True):
        assert observed["handle"]["path"] == source["path"]
        assert observed["source_total_chars"] == len(text)
        assert header in observed["chunks"][0]["text"]
        assert any(row["text"].startswith("Total\t") for row in observed["table_rows"])
        for part in [*observed["chunks"], *observed["table_rows"]]:
            assert part["text"] == text[part["start_char"] : part["end_char"]]
    assert json.dumps(value, ensure_ascii=False) == original


@pytest.mark.parametrize("projection", ["direct", "normal", "recovery"])
def test_text_batch_keeps_multilevel_headers_with_numeric_summary(projection) -> None:
    header = (
        "Area\tNorth\tSouth\tEast\tWest\tCentral\tCoast\tRural\tUrban\tTotal\n"
        + "\tOrdered\tShipped" * 9
        + "\n"
        + "\tUnits\tValue" * 18
        + "\n"
    )
    numbers = "\t".join(str(index * 31) for index in range(1, 37))
    text = (
        "\t2034 / 2035 Regional inventory statement\tSection D\n"
        + "Statement information\n" * 8
        + header
        + "Supplies\t"
        + numbers
        + "\n"
        + ("detail\t9\t27\t8\t24\n" * 90)
        + "Subtotal\t"
        + numbers
        + "\n"
        + ("detail\t7\t21\t6\t18\n" * 60)
        + "Total\t"
        + numbers
        + "\nEnd of statement\n"
    )
    files = [
        {
            "path": f"/home/user/Documents/regional-inventory/statements/report-{index}.pdf",
            "status": "ok",
            "text": text,
            "source_start_char": index * 1000,
            "source_end_char": index * 1000 + len(text),
            "source_total_chars": index * 1000 + len(text),
            "source_truncated": False,
            "offset_basis": "layout_compacted_text",
        }
        for index in range(9)
    ]
    value = {"input_pattern": "*.pdf", "matched_count": len(files), "files": files}
    original = copy.deepcopy(value)
    if projection == "direct":
        observed = text_batch_context_for_model(value)
    else:
        state = RuntimeState(
            task_id="synthetic-header-context",
            domain="multi_apps",
            instruction="Read the inventory reports.",
            events=[
                event(
                    1,
                    action="adapter.call",
                    result={
                        "context_hint": {
                            "downstream_adapter": "os",
                            "downstream_action": "pdf.extract_text_batch",
                            "downstream_context": value,
                        }
                    },
                )
            ],
        )
        messages = _protocol()._messages(
            state,
            b"synthetic-screenshot",
            protocol_recovery=projection == "recovery",
        )
        summary = json.loads(messages[2]["content"][0]["text"].split("\n")[1])
        if projection == "recovery":
            assert len(json.dumps(summary, ensure_ascii=False)) <= 16_000
        observed = summary[0]["result"]["context_hint"]["downstream_context"]

    assert len(json.dumps(observed, ensure_ascii=False)) <= 18_000
    assert len(observed["files"]) == len(files)
    for source, file in zip(files, observed["files"], strict=True):
        assert file["handle"]["path"] == source["path"]
        assert len(file["table_rows"]) == 2
        assert file["table_rows"][0]["type"] == "table_header"
        assert file["table_rows"][0]["text"] == header.rstrip("\n")
        assert file["table_rows"][1]["type"] == "table_row"
        assert file["table_rows"][1]["text"] == "Total\t" + numbers
        assert file["table_rows"][0]["context_has_more"] is False
        for part in file["table_rows"]:
            assert (
                part.get("offset_basis", file["offset_basis"]) == source["offset_basis"]
            )
            base = source["source_start_char"]
            assert (
                part["text"]
                == text[part["start_char"] - base : part["end_char"] - base]
            )
    assert value == original


def test_text_batch_projection_keeps_one_chunk_for_short_complete_text() -> None:
    text = "first row\nsecond row\n"
    value = {
        "input_directory": "/tmp/sources",
        "input_pattern": "*.txt",
        "matched_count": 1,
        "files": [
            {
                "path": "/tmp/sources/short.txt",
                "status": "ok",
                "extracted_chars": len(text),
                "returned_chars": len(text),
                "truncated": False,
                "text": text,
            }
        ],
    }

    projected = text_batch_context_for_model(value)
    file = projected["files"][0]

    assert len(file["chunks"]) == 1
    chunk = file["chunks"][0]
    assert chunk["start_char"] == 0
    assert chunk["end_char"] == len(text)
    assert chunk["total_chars"] == len(text)
    assert chunk["text"] == text
    assert chunk["source_has_more"] is False
    assert chunk["context_has_more"] is False
    assert chunk.get("has_more", chunk["source_has_more"]) is False
    assert file["has_more"] is False
    assert file["context_truncated"] is False


def test_compact_hint_preserves_complete_text_batch_when_budget_fits() -> None:
    text = "Question one\nQuestion two\n" * 80
    value = {
        "observation_type": "text_batch",
        "matched_count": 1,
        "context_char_budget": 8_000,
        "files": [
            {
                "path": "/tmp/sources/test.docx",
                "source_start_char": 0,
                "source_end_char": len(text),
                "source_total_chars": len(text),
                "source_has_more": False,
                "text": text,
            }
        ],
    }

    projected = compact_hint(value, remaining_chars=8_000)
    forwarded = compact_context_hint_for_model(
        {
            "downstream_adapter": "libreoffice_writer",
            "downstream_action": "document.read_file",
            "downstream_context": value,
        },
        remaining_chars=8_000,
    )

    assert projected == value
    assert projected["files"][0]["text"] == text
    assert forwarded["downstream_context"] == value


def test_compact_hint_preserves_complete_typed_chunk_through_recovery() -> None:
    text = "Question one\nQuestion two\n" * 60
    value = {
        "observation_type": "text_batch",
        "matched_count": 1,
        "context_char_budget": 8_000,
        "guidance": "read the complete returned source before repeating extraction "
        * 80,
        "files": [
            {
                "path": "/tmp/sources/test.docx",
                "source_start_char": 0,
                "source_end_char": len(text),
                "source_total_chars": len(text),
                "source_has_more": False,
                "context_has_more": False,
                "chunks": [
                    {
                        "type": "text",
                        "index": 0,
                        "start_char": 0,
                        "end_char": len(text),
                        "total_chars": len(text),
                        "text": text,
                        "source_has_more": False,
                        "context_has_more": False,
                    }
                ],
            }
        ],
    }

    projected = compact_hint(value, remaining_chars=4_000)

    chunk = projected["files"][0]["chunks"][0]
    assert chunk["text"] == text
    assert chunk["start_char"] == 0
    assert chunk["end_char"] == len(text)
    assert chunk["context_has_more"] is False


@pytest.mark.parametrize("source_has_more", [False, True])
def test_final_batch_fit_propagates_context_loss_without_changing_source_window(
    source_has_more,
):
    text = "Observed source text. " * 300
    start = 24_000
    end = start + len(text)
    source_total = end + 5_000 if source_has_more else end
    raw = {
        "matched_count": 1,
        "files": [
            {
                "path": "/tmp/sources/window.txt",
                "text": text,
                "source_start_char": start,
                "source_end_char": end,
                "source_total_chars": source_total,
                "next_start_char": end if source_has_more else None,
                "source_truncated": source_has_more,
                "offset_basis": "extracted_text",
            }
        ],
    }
    original = copy.deepcopy(raw)
    observed = text_batch_context_for_model(raw)
    assert observed["context_truncated"] is False
    assert observed["files"][0]["context_has_more"] is False
    assert observed["files"][0]["chunks"][0]["text"] == text
    original_observed = copy.deepcopy(observed)

    forwarded = compact_context_hint_for_model(
        {
            "downstream_adapter": "os",
            "downstream_action": "pdf.extract_text_batch",
            "downstream_context": observed,
        },
        remaining_chars=5_000,
    )

    batch = forwarded["downstream_context"]
    file = batch["files"][0]
    chunk = file["chunks"][0]
    assert chunk["context_has_more"] is True
    assert file["context_has_more"] is True
    assert batch["context_has_more"] is True
    assert batch["context_truncated"] is True
    assert file["has_more"] is batch["has_more"] is True
    assert chunk["source_has_more"] is source_has_more
    assert file["source_has_more"] is batch["source_has_more"] is source_has_more
    assert file["source_start_char"] == start
    assert file["source_end_char"] == end
    assert file["source_total_chars"] == source_total
    assert file.get("next_start_char") == (end if source_has_more else None)
    assert file["offset_basis"] == "extracted_text"
    assert chunk["start_char"] == start
    assert start < chunk["end_char"] < end
    assert chunk["end_char"] == start + len(chunk["text"])
    assert chunk["text"] == text[: len(chunk["text"])]
    assert len(json.dumps(forwarded, ensure_ascii=False)) <= 5_000
    assert raw == original
    assert observed == original_observed


def test_text_batch_projection_preserves_absolute_source_window_offsets() -> None:
    full_text = "".join(str(index % 10) for index in range(8_000))
    window_start = 2_400
    window_end = 6_400
    window = full_text[window_start:window_end]
    value = {
        "input_directory": "/tmp/sources",
        "input_pattern": "source-0.pdf",
        "matched_count": 1,
        "files": [
            {
                "path": "/tmp/sources/source-0.pdf",
                "text": window,
                "extracted_chars": len(full_text),
                "source_start_char": window_start,
                "source_end_char": window_end,
                "source_total_chars": len(full_text),
                "next_start_char": window_end,
                "offset_basis": "layout_compacted_text",
                "source_truncated": True,
            }
        ],
    }

    projected = text_batch_context_for_model(value, max_chars=3_000)
    file = projected["files"][0]

    assert projected["source_has_more"] is True
    assert file["source_start_char"] == window_start
    assert file["source_end_char"] == window_end
    assert file["source_total_chars"] == len(full_text)
    assert file["next_start_char"] == window_end
    assert file["offset_basis"] == "layout_compacted_text"
    assert len(file["chunks"]) == 2
    head, tail = file["chunks"]
    assert (
        head.get("offset_basis", file["offset_basis"])
        == tail.get("offset_basis", file["offset_basis"])
        == "layout_compacted_text"
    )
    assert head["text"] == window[0 : head["end_char"] - window_start]
    assert tail["text"] == window[tail["start_char"] - window_start :]
    assert head["start_char"] == window_start
    assert tail["end_char"] == window_end
    assert (
        head.get("total_chars", file["source_total_chars"])
        == tail.get("total_chars", file["source_total_chars"])
        == len(full_text)
    )


@pytest.mark.parametrize("start", [0, 5_000])
@pytest.mark.parametrize("inherited_metadata", [False, True])
def test_requested_pdf_window_preserves_middle_text_through_recovery_and_messages(
    start, inherited_metadata,
):
    text = "Opening text. " * 240 + "MIDDLE-WINDOW-CONTENT" + " Closing text." * 300
    end = start + len(text)
    raw = {
        "input_directory": "/tmp/sources",
        "input_pattern": "article.pdf",
        "matched_count": 1,
        "files": [
            {
                "path": "/tmp/sources/article.pdf",
                "text": text,
                "source_start_char": start,
                "source_end_char": end,
                "source_total_chars": end + 20_000,
                "next_start_char": end,
                "source_truncated": True,
                "offset_basis": "extracted_text",
            }
        ],
    }
    original = copy.deepcopy(raw)
    observed = text_batch_context_for_model(raw)
    assert observed["context_truncated"] is False
    assert observed["source_has_more"] is True
    assert observed["files"][0]["chunks"][0]["text"] == text

    if inherited_metadata:
        for chunk in observed["files"][0]["chunks"]:
            chunk.pop("total_chars", None)
            chunk.pop("offset_basis", None)
    observed["guidance"] = "Optional verbose reader guidance. " * 600
    recovered = compact_hint(observed, remaining_chars=12_000)
    recovered = compact_hint(recovered, remaining_chars=12_000)
    chunk = recovered["files"][0]["chunks"][0]
    assert chunk["text"] == text
    assert (chunk["start_char"], chunk["end_char"]) == (start, end)
    assert chunk["source_has_more"] is True
    assert chunk["context_has_more"] is False
    assert len(json.dumps(recovered, ensure_ascii=False)) <= 12_000

    state = RuntimeState(
        task_id="synthetic-window",
        domain="multi_apps",
        instruction="Read this document.",
    )
    state.events.append(
        event(
            1,
            action="adapter.call",
            result={
                "context_hint": {
                    "downstream_adapter": "os",
                    "downstream_action": "pdf.extract_text_batch",
                    "downstream_context": raw,
                }
            },
        )
    )
    messages = _protocol()._messages(state, b"synthetic-screenshot")
    assert "MIDDLE-WINDOW-CONTENT" in json.dumps(messages, ensure_ascii=False)
    assert raw == original


def test_batch_window_cursor_is_validated_and_published_by_the_owning_adapter() -> None:
    arguments = {
        "input_pattern": "source-0.pdf",
        "cwd_source": "explicit",
        "cwd_path": "/tmp/sources",
        "start_char": 2_400,
    }

    validate_os_action("pdf.extract_text_batch", arguments)
    schema = OS_SCHEMAS["pdf.extract_text_batch"]
    assert schema["properties"]["start_char"]["minimum"] == 0
    assert schema["properties"]["start_char"]["maximum"] == 100_000_000

    with pytest.raises(OSAdapterError):
        validate_os_action(
            "pdf.extract_text_batch",
            {**arguments, "start_char": -1},
        )


def test_text_window_reports_truthful_next_cursor_without_injecting_content() -> None:
    text = "header\nbody\ntrailer"

    window, start, end, has_more = _text_window(text, start_char=7, max_chars=4)

    assert window == text[7:11]
    assert (start, end, has_more) == (7, 11, True)
    assert _text_window(text, start_char=99, max_chars=4) == (
        "",
        len(text),
        len(text),
        False,
    )


def test_text_batch_projection_separates_source_and_context_truncation() -> None:
    text = "complete-source " * 2_000
    value = {
        "input_directory": "/tmp/sources",
        "input_pattern": "*.pdf",
        "matched_count": 1,
        "files": [
            {
                "path": "/tmp/sources/complete.pdf",
                "source_truncated": False,
                "extracted_chars": len(text),
                "returned_chars": len(text),
                "text": text,
            }
        ],
    }

    projected = text_batch_context_for_model(value, max_chars=2_000)

    assert projected["source_has_more"] is False
    assert projected["context_truncated"] is True
    assert projected["has_more"] is True
    assert projected["files"][0]["source_has_more"] is False
    assert projected["files"][0]["context_truncated"] is True
    assert projected["files"][0]["context_has_more"] is True
    assert projected["files"][0]["has_more"] is True
    chunk = projected["files"][0]["chunks"][0]
    assert chunk["source_has_more"] is False
    assert chunk["context_has_more"] is True
    assert chunk.get("has_more", chunk["source_has_more"]) is False


def test_layout_compaction_does_not_claim_source_pagination() -> None:
    """Representation compaction is not an unread source window."""
    text = "institution\tapplications\tsupported\nPolyU\t59\t27\n"
    value = {
        "input_directory": "/tmp/sources",
        "input_pattern": "*.pdf",
        "matched_count": 1,
        "files": [
            {
                "path": "/tmp/sources/compact.pdf",
                "text": text,
                "extracted_chars": len(text) + 320,
                "raw_extracted_chars": len(text) + 1_100,
                "layout_compacted": True,
                "source_truncated": False,
                "truncated": False,
            }
        ],
    }

    projected = text_batch_context_for_model(value, max_chars=2_000)

    assert projected["source_has_more"] is False
    assert projected["files"][0]["source_has_more"] is False
    assert projected["files"][0]["has_more"] is False


def test_text_batch_projection_preserves_nested_wrapper_and_multiple_events() -> None:
    first = _text_batch_hint(count=2, text_chars=6_000)
    second = _text_batch_hint(count=2, text_chars=7_000)
    second["files"][0]["path"] = "/home/user/Documents/sources/second.pdf"
    events = [
        event(1, action="pdf.extract_text_batch", result={"context_hint": first}),
        event(2, action="spreadsheet.inspect_current", result={"status": "ok"}),
        event(
            3,
            action="adapter.call",
            result={
                "context_hint": {
                    "downstream_adapter": "os",
                    "downstream_action": "pdf.extract_text_batch",
                    "downstream_context": second,
                }
            },
        ),
    ]

    summary = execution_context_summary(
        events,
        "multi_apps",
        limit=3,
        strict_generic=True,
    )
    encoded = json.dumps(summary, ensure_ascii=False)
    nested = summary[-1]["result"]["context_hint"]["downstream_context"]

    assert len(encoded) <= 65_000
    assert nested["observation_type"] == "text_batch"
    assert nested["files"][0]["handle"]["path"].endswith("second.pdf")
    assert nested["files"][0]["metadata"]["pages_processed"] == 3
    assert nested["has_more"] is True
    assert "preview" not in encoded
