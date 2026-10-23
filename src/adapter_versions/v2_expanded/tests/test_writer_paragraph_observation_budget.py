from copy import deepcopy
import json

import pytest

from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_context_hint_for_model,
)
from integrations.lite_agent.agent import LiteAgent
from integrations.lite_agent.episode_control import mark_tool_result_for_audit
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


def rich_inspection(texts):
    details = []
    ordinal = 20
    for index, text in enumerate(texts, 30):
        ordinal += bool(text)
        details.append({
            "index": index,
            "nonempty_ordinal": ordinal if text else None,
            "text": text,
            "text_length": len(text),
            "line_spacing": 1.15,
            "alignment": "left",
            "font_size": 11.0,
            "strikethrough": False,
            "numbering": {
                "is_numbered": False, "level": 0, "list_label": "",
                "restart": False, "start_value": -1, "style_name": "",
            },
            "tab_stops": [{
                "position": {"value": 70, "unit": "mm"},
                "alignment": "left", "fill_character": " ",
            }],
            "has_tab_character": "\t" in text,
            "tab_character_offsets": [i for i, char in enumerate(text) if char == "\t"],
            "literal_tab_escape_count": text.count("\\t"),
        })
    return {
        "status": "ok",
        "result": {
            "identity": {"title": "Working notes.odt", "url": "file:///tmp/Working%20notes.odt"},
            "page_layouts": [{
                "name": "Default Page Style", "width_mm": 210, "height_mm": 297,
                "left_margin_mm": 20, "right_margin_mm": 20,
                "top_margin_mm": 20, "bottom_margin_mm": 20, "body_width_mm": 170,
            }],
            "footers": [{"page_style": "Default Page Style", "enabled": False, "text": ""}],
            "fonts": {"document_fonts": ["Liberation Serif", "Liberation Sans"], "mixed": True},
            "highlighting": {
                "highlighted_run_count": 0, "highlighted_paragraph_count": 0, "colors": {},
            },
            "graphic_object_count": 0,
            "embedded_images": 0,
            "tables": [{"name": "Existing table", "rows": 2, "columns": 3}],
            "paragraph_count": 60,
            "nonempty_paragraph_count": 50,
            "paragraph_start": 30,
            "paragraph_limit": len(texts),
            "next_paragraph_start": 30 + len(texts),
            "has_more": True,
            "paragraphs": texts,
            "paragraph_details": details,
        },
    }


def observed_messages(body, *, forwarded, recovery):
    domain, action = "libreoffice_writer", "document.inspect"
    if forwarded:
        body = {
            "status": "ok",
            "result": {"adapter": domain, "action": action, "response": body},
        }
        domain, action = "multi_apps", "adapter.call"
    hint = adapter_context_hint(domain, action, body)
    observation = ExecutionEvent(
        step=1, timestamp_utc="2026-09-13T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": {}},
        executed=True, result={"context_hint": hint},
    )
    state = RuntimeState(
        task_id="synthetic-paragraph-budget",
        domain=domain,
        instruction="Inspect the existing paragraphs.",
        events=[observation],
    )
    mark_tool_result_for_audit(state, observation)
    original_events = deepcopy(state.events)
    # Build the real Agent request without constructing a network client.
    messages = LiteAgent.__new__(LiteAgent)._messages(
        state, b"synthetic-screenshot",
        protocol_recovery=recovery == "protocol",
        execution_recovery=recovery == "execution",
    )
    state_text = messages[2]["content"][0]["text"]
    summary = json.loads(state_text.split("\n")[1])
    projected = next(item for item in summary if item.get("step") == 1)["result"]["context_hint"]
    assert state.task_id not in state_text
    assert state.events == original_events
    assert len(json.dumps(projected, ensure_ascii=False)) <= 5000
    if recovery:
        assert len(json.dumps(summary, ensure_ascii=False)) <= 9000
    return projected["downstream_context"] if forwarded else projected


@pytest.mark.parametrize("forwarded", [False, True])
@pytest.mark.parametrize("recovery", [None, "protocol", "execution"])
def test_rich_writer_inspection_keeps_paragraph_text_in_actual_request(forwarded, recovery):
    texts = [
        f'Item {index}\u00a0\u00a0|  雪🙂 | "Keep case" |\tLiteral\\t and repeated  spaces'
        for index in range(10)
    ]
    texts[3] = ""
    body = rich_inspection(texts)
    original = deepcopy(body)

    projected = observed_messages(body, forwarded=forwarded, recovery=recovery)

    rows = projected["paragraph_details"]
    assert [row["index"] for row in rows] == list(range(30, 40))
    assert [row["text"] for row in rows] == texts
    assert [row["text_length"] for row in rows] == list(map(len, texts))
    assert rows[3]["nonempty_ordinal"] is None
    assert projected["paragraph_start"] == 30
    assert projected["next_paragraph_start"] == 40
    assert projected["has_more"] is True
    assert body == original


@pytest.mark.parametrize("forwarded", [False, True])
def test_long_writer_paragraph_keeps_length_and_truthful_truncation(forwarded):
    text = "Beginning with\u00a0spacing. " + "Observed body text. " * 600 + " Exact ending."
    body = rich_inspection([text])
    original = deepcopy(body)

    projected = observed_messages(body, forwarded=forwarded, recovery="protocol")
    row = projected["paragraph_details"][0]

    assert row["index"] == 30
    assert row["text_length"] == len(text)
    assert "...<truncated>..." in row["text"]
    assert len(row["text"]) <= 1200
    assert row["text"] != text
    assert row["context_truncated"] is True
    assert body == original


def test_paragraph_observation_that_fits_keeps_native_formatting_nulls():
    body = rich_inspection([""])
    body["result"]["paragraph_details"][0]["line_spacing"] = None
    hint = adapter_context_hint("libreoffice_writer", "document.inspect", body)
    original = deepcopy(hint)

    projected = compact_context_hint_for_model(hint, remaining_chars=5000)

    row = projected["paragraph_details"][0]
    assert row["text"] == ""
    assert row["text_length"] == 0
    assert row["nonempty_ordinal"] is None
    assert row["line_spacing"] is None
    assert projected == original
