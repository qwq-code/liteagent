from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from impress_adapter import uno_worker
from impress_adapter.errors import AdapterError
from impress_adapter.schema import parse_action_request
from impress_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from impress_adapter.uno_worker import _path_from_input
from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_context_hint_for_model,
    compact_execution_summary_for_model,
    context_hint_for_model,
    execution_context_summary,
)
from integrations.lite_agent.agent_protocol import (
    AgentProtocolMixin,
    MODEL_PROTOCOL_RECOVERY_MAX_CHARS,
)
from integrations.lite_agent.context_projection import (
    MODEL_CONTEXT_HINT_TOTAL_MAX_CHARS,
    MODEL_CONTEXT_MAX_STRING_CHARS,
)
from integrations.lite_agent.episode_control import mark_tool_result_for_audit
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS, build_tools


DOMAIN = "libreoffice_impress"
ACTION = "presentation.inspect"


def inspection(indices=range(12)):
    return {
        "result": {
            "identity": {"url": "file:///tmp/example.odp", "title": "Example"},
            "slide_count": 12,
            "inspected_slides": list(indices),
            "slides": [
                {
                    "index": index,
                    "width": 25000,
                    "height": 18000,
                    "orientation": "landscape",
                    "notes": "",
                    "shapes": [
                        {
                            "index": shape,
                            "path": [shape],
                            "name": f"Text {shape}",
                            "kind": "com.sun.star.drawing.CustomShape",
                            "is_text": True,
                            "text": "\n".join(
                                "" if p == 1 else f"Page {index} text {shape} item {p}"
                                for p in range(6)
                            ),
                            "paragraphs": [
                                {
                                    "index": p,
                                    "text": ""
                                    if p == 1
                                    else f"Page {index} text {shape} item {p}",
                                    "level": p % 3,
                                    "bullet": p != 4,
                                    "left_margin": p * 120,
                                    "first_line_indent": -80,
                                }
                                for p in range(6)
                            ],
                        }
                        for shape in range(3)
                    ],
                }
                for index in indices
            ],
        }
    }


def tool_schema():
    return build_tools(
        DOMAIN,
        [ACTION],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )[0]["function"]["parameters"]


@pytest.mark.parametrize(
    "params,indices", [({}, list(range(12))), ({"slides": [6, 2]}, [6, 2])]
)
def test_inspection_reads_only_explicit_pages_without_reindexing(
    monkeypatch, params, indices
):
    data = inspection()["result"]
    native = SimpleNamespace(
        pages=SimpleNamespace(getCount=lambda: 12), identity=lambda: data["identity"]
    )
    visited = []

    def summary(session, index):
        assert session is native
        visited.append(index)
        return deepcopy(data["slides"][index])

    original = deepcopy(params)
    jsonschema.validate(params, tool_schema())
    request = parse_action_request({"action": ACTION, "params": params})
    monkeypatch.setattr(uno_worker, "ImpressSession", lambda _: native)
    monkeypatch.setattr(uno_worker, "_page_summary", summary)

    result = uno_worker.execute(request.to_worker_payload())["result"]

    assert visited == indices
    assert result["slide_count"] == 12
    assert result["inspected_slides"] == indices
    assert [page["index"] for page in result["slides"]] == indices
    assert params == original
    assert DIRECT_ACTION_SCHEMAS[DOMAIN][ACTION] == STRICT_ACTION_PARAM_SCHEMAS[ACTION]


@pytest.mark.parametrize(
    "params",
    [
        {"slides": []},
        {"slides": [True]},
        {"slides": [-1]},
        {"slides": [2, 2]},
        {"slides": "2"},
        {"page": 2},
    ],
)
def test_inspection_schema_and_runtime_agree_on_invalid_selectors(params):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(params, tool_schema())
    with pytest.raises(AdapterError):
        parse_action_request({"action": ACTION, "params": params})


def test_focused_inspection_preserves_paragraph_state_and_blank_indices():
    raw = inspection([6])
    original = deepcopy(raw)
    hint = adapter_context_hint(DOMAIN, ACTION, raw)
    normal = context_hint_for_model(DOMAIN, ACTION, hint, strict_generic=True)
    compact = compact_context_hint_for_model(normal, remaining_chars=7000)

    assert hint["slides"][0]["slide"] == 6
    assert "slide_index" not in hint["slides"][0]
    for projected in (normal, compact):
        assert projected["slides"][0]["slide_index"] == 6
        assert projected["slides"][0]["display_slide_number"] == 7
        assert "slide" not in projected["slides"][0]
    for value in (hint, normal, compact):
        assert value["slide_count"] == 12
        assert value["inspected_slides"] == [6]
        for shape in value["slides"][0]["text_shapes"]:
            expected = raw["result"]["slides"][0]["shapes"][shape["index"]]
            assert shape["paragraphs"] == expected["paragraphs"]
            assert shape["paragraphs"][1]["text"] == ""
    assert raw == original


@pytest.mark.parametrize("recovery", [False, True])
def test_forwarded_speaker_notes_reach_actual_model_messages(recovery):
    raw = inspection([6, 2])
    notes = [
        "Introduce the prototype.\n\nThen explain the measured trade-off.\n",
        " \n\t",
    ]
    for slide, text in zip(raw["result"]["slides"], notes):
        slide["notes"] = text
    original_raw = deepcopy(raw)
    forwarded = {
        "status": "ok",
        "result": {"adapter": DOMAIN, "action": ACTION, "response": raw},
    }
    event = ExecutionEvent(
        step=1,
        timestamp_utc="2026-09-13T00:00:00Z",
        proposed={
            "kind": "adapter",
            "tool": "adapter__adapter_call",
            "action": "adapter.call",
            "arguments": {
                "adapter": DOMAIN,
                "action": ACTION,
                "payload": {"params": {"slides": [6, 2]}},
            },
        },
        executed=True,
        result={
            "context_hint": adapter_context_hint(
                "multi_apps", "adapter.call", forwarded
            )
        },
    )
    state = RuntimeState(
        task_id="synthetic-notes-feedback",
        domain="multi_apps",
        instruction="Read the existing speaker notes on the requested slides.",
        events=[event],
    )
    mark_tool_result_for_audit(state, event)
    original_events = deepcopy(state.events)

    agent = AgentProtocolMixin()
    agent.config = SimpleNamespace(include_gui=True)
    messages = agent._messages(
        state,
        b"png",
        execution_recovery=recovery,
    )
    state_text = messages[2]["content"][0]["text"]
    summary = json.loads(state_text.split("\n")[1])
    observed = next(item for item in summary if item.get("step") == 1)["result"][
        "context_hint"
    ]["downstream_context"]

    assert [slide["slide_index"] for slide in observed["slides"]] == [6, 2]
    assert [slide["display_slide_number"] for slide in observed["slides"]] == [7, 3]
    assert [slide["notes"] for slide in observed["slides"]] == notes
    assert [slide["has_speaker_notes"] for slide in observed["slides"]] == [True, False]
    assert state.task_id not in state_text
    assert raw == original_raw
    assert state.events == original_events
    budget = (
        MODEL_PROTOCOL_RECOVERY_MAX_CHARS
        if recovery
        else MODEL_CONTEXT_HINT_TOTAL_MAX_CHARS
    )
    assert len(json.dumps(summary, ensure_ascii=False)) <= budget


def test_long_speaker_notes_use_existing_string_limit_and_truncation_marker():
    raw = inspection([6])
    raw["result"]["slides"][0]["notes"] = (
        "Opening\n" + "Explain the findings.\n" * 100 + "Closing"
    )
    original = deepcopy(raw)
    hint = adapter_context_hint(DOMAIN, ACTION, raw)

    observed = context_hint_for_model(DOMAIN, ACTION, hint, strict_generic=True)
    slide = observed["slides"][0]

    assert slide["has_speaker_notes"] is True
    assert slide["notes"].startswith("Opening\n")
    assert slide["notes"].endswith("Closing")
    assert "...<truncated>..." in slide["notes"]
    assert len(slide["notes"]) <= MODEL_CONTEXT_MAX_STRING_CHARS
    assert raw == original


def test_inspection_projection_preserves_existing_media_urls_and_selectors():
    body = inspection([0])
    body["result"]["slides"][0]["shapes"].append(
        {
            "index": 7,
            "path": [7],
            "name": "Media 1",
            "kind": "com.sun.star.presentation.MediaShape",
            "is_text": False,
            "media_url": "file:///home/user/Desktop/Quarterly%20Intro.mp3",
            "x": 0,
            "y": 0,
            "width": 4000,
            "height": 2000,
            "visible": True,
        }
    )
    original = deepcopy(body)
    hint = adapter_context_hint(DOMAIN, ACTION, body)
    normal = context_hint_for_model(DOMAIN, ACTION, hint, strict_generic=True)
    compact = compact_context_hint_for_model(normal, remaining_chars=2_000)

    for projected in (hint, normal, compact):
        media = projected["slides"][0]["media_shapes"]
        assert media[0]["path"] == [7]
        assert (
            media[0]["media_url"] == "file:///home/user/Desktop/Quarterly%20Intro.mp3"
        )
    assert body == original


def test_audio_insert_accepts_local_file_uri_and_rejects_remote_uri(
    monkeypatch, tmp_path
):
    audio = tmp_path / "Intro clip.mp3"
    audio.write_bytes(b"synthetic audio")

    class Page:
        def __init__(self):
            self.shapes = []

        def add(self, shape):
            self.shapes.append(shape)

        def getCount(self):
            return len(self.shapes)

    page = Page()
    media = SimpleNamespace(MediaURL="", Position=None, Size=None)
    session = SimpleNamespace(
        doc=SimpleNamespace(createInstance=lambda _: media),
        page=lambda _: page,
    )

    class FakeUno:
        @staticmethod
        def createUnoStruct(_, *values):
            return SimpleNamespace(
                X=values[0], Y=values[1], Width=values[0], Height=values[1]
            )

    monkeypatch.setattr(uno_worker, "_uno_modules", lambda: (FakeUno(), None))
    monkeypatch.setattr(uno_worker, "_file_url", lambda value: Path(value).as_uri())

    params = {"slide": 0, "path": audio.as_uri()}
    original = deepcopy(params)
    result = uno_worker._insert_audio(session, params)

    assert result["shape_index"] == 0
    assert result["media_url"] == audio.as_uri()
    assert result["source_path"] == str(audio)
    assert params == original
    assert media.MediaURL == audio.as_uri()
    with pytest.raises(AdapterError, match="local host"):
        _path_from_input("file://remote.invalid/tmp/Intro.mp3")


def test_focused_readback_survives_protocol_recovery_with_large_earlier_deck():
    full, focused = inspection(), inspection([6])
    paragraphs = focused["result"]["slides"][0]["shapes"][1]["paragraphs"]
    receipt = {
        "result": {
            "text": "Duplicate text",
            "properties": {},
            "paragraphs": paragraphs,
        },
        "verification": {"passed": True},
    }
    bodies = [full, receipt, focused, {"result": {"url": "file:///tmp/example.odp"}}]
    actions = [ACTION, "shape.format_text", ACTION, "presentation.save"]
    args = [
        {},
        {"slide": 6, "selector": {"path": [1]}, "lines": [4], "bullet": False},
        {"slides": [6]},
        {},
    ]
    events = []
    for index, (action, body, arguments) in enumerate(zip(actions, bodies, args), 1):
        hint = adapter_context_hint(DOMAIN, action, body)
        events.append(
            SimpleNamespace(
                step=index,
                executed=True,
                error=None,
                proposed={
                    "kind": "adapter",
                    "action": action,
                    "tool": f"adapter__{action.replace('.', '_')}",
                    "arguments": arguments,
                },
                result={"context_hint": hint, "adapter_response": body}
                if hint
                else body,
            )
        )
    original = deepcopy([event.proposed for event in events])
    summary = execution_context_summary(events, DOMAIN, limit=4, strict_generic=True)
    compact = compact_execution_summary_for_model(summary, max_chars=9000)
    readback = next(event for event in compact if event.get("step") == 3)
    value = readback["result"]["context_hint"]

    assert value["inspected_slides"] == [6]
    assert value["slides"][0]["text_shapes"][1]["paragraphs"] == paragraphs
    assert len(json.dumps(compact, ensure_ascii=False)) <= 9000
    assert [event.proposed for event in events] == original


def test_formatting_receipt_retains_observed_paragraphs_without_duplicate_text():
    paragraphs = inspection([4])["result"]["slides"][0]["shapes"][1]["paragraphs"]
    body = {
        "result": {
            "text": "Duplicate text",
            "properties": {},
            "paragraphs": paragraphs,
        },
        "verification": {"passed": True},
    }
    hint = adapter_context_hint(DOMAIN, "shape.format_text", body)
    assert hint["paragraphs"] == paragraphs
    assert hint["verification_passed"] is True
    assert "text" not in hint


def test_formatting_tool_explains_shape_scope_and_partial_selection():
    tool = build_tools(
        DOMAIN,
        ["shape.format_text"],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )[0]["function"]
    description = tool["description"]

    assert "whole text shape" in description
    assert "lines" in description
    assert "match_text" in description
    assert "Omitting both" in description


@pytest.mark.parametrize(
    "selection,expected",
    [
        ({}, [(0, 17)]),
        ({"lines": [0, 3]}, [(0, 4), (11, 5)]),
        ({"match_text": "note"}, [(0, 4), (6, 4)]),
    ],
)
def test_formatting_scope_keeps_existing_whole_line_and_literal_behavior(
    selection, expected
):
    params = {"slide": 4, "selector": {"index": 2}, "bullet": False, **selection}
    original = deepcopy(params)
    parse_action_request({"action": "shape.format_text", "params": params})

    assert uno_worker._text_spans("note\n\nnote\nother\n", params) == expected
    assert params == original
