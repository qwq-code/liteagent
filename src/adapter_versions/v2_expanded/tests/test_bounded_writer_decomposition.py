from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace

import jsonschema
import pytest

from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_context_hint_for_model,
)
from integrations.lite_agent.agent import LiteAgent
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import (
    DIRECT_ACTION_SCHEMAS,
    build_tools,
    public_actions,
    search_actions,
    select_actions,
)
from writer_adapter.schema import ACTIONS as WRITER_ACTIONS
from writer_adapter.errors import AdapterError
from writer_adapter.schema import validate_action_params
from writer_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from writer_adapter.uno_worker import GENERIC_ACTIONS
import writer_adapter.uno_worker as writer_worker


RETIRED_MACROS = {
    "paragraph.format_groups",
    "table.color_words_by_initial",
    "paragraph.separate_sentences",
    "document.add_numbered_reference",
}
REPLACEMENTS = {
    "paragraph.set_format",
    "paragraph.replace_text",
    "text.find_replace",
    "document.append_paragraphs",
    "table.read",
    "table.set_cell_text_color",
}


def test_writer_macros_are_absent_and_replacements_are_public() -> None:
    surfaces = (
        set(WRITER_ACTIONS),
        set(GENERIC_ACTIONS),
        set(STRICT_ACTION_PARAM_SCHEMAS),
        set(DIRECT_ACTION_SCHEMAS["libreoffice_writer"]),
        set(public_actions("libreoffice_writer")),
    )

    assert all(RETIRED_MACROS.isdisjoint(surface) for surface in surfaces)
    assert all(REPLACEMENTS.issubset(surface) for surface in surfaces)


def test_distinct_paragraph_formats_are_independent_model_calls() -> None:
    first = {"nonempty_ordinals": [1, 3], "font_size": 13, "alignment": "center"}
    second = {"nonempty_ordinals": [2, 4], "line_spacing": 1.5}

    validate_action_params("paragraph.set_format", first)
    validate_action_params("paragraph.set_format", second)

    assert first != second


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        ({"indices": [1, 3]}, [1, 3]),
        ({"nonempty_ordinals": [2, 3]}, [2, 4]),
        ({}, [0, 1, 2, 3, 4]),
    ],
)
def test_paragraph_selection_keeps_raw_blanks_distinct_from_text_positions(
    selector, expected
) -> None:
    paragraphs = [
        SimpleNamespace(String=text)
        for text in ["Heading", "", "North", " \t", "South"]
    ]
    params = selector | {"font_size": 14}
    validate_action_params("paragraph.set_format", params)

    assert writer_worker._paragraph_target_indices(paragraphs, params) == expected
    assert params == selector | {"font_size": 14}


def test_table_policy_is_replaced_by_explicit_observation_and_cell_batches() -> None:
    validate_action_params("table.read", {"name": "Inventory 2036"})
    vowel_cells = {
        "name": "Inventory 2036",
        "cells": ["A2", "C4", "D7"],
        "color": "#146C94",
    }
    other_cells = {
        "name": "Inventory 2036",
        "cells": ["A3", "B2", "B4"],
        "color": "#A61B1B",
    }

    validate_action_params("table.set_cell_text_color", vowel_cells)
    validate_action_params("table.set_cell_text_color", other_cells)

    assert set(vowel_cells["cells"]).isdisjoint(other_cells["cells"])


@pytest.mark.parametrize(
    ("color", "property_state", "observed"),
    [
        (0x146C94, "DIRECT_VALUE", "#146C94"),
        (0, "DEFAULT_VALUE", "#000000"),
        (-1, "DEFAULT_VALUE", "automatic"),
        (0, "AMBIGUOUS_VALUE", "mixed"),
        (None, "DIRECT_VALUE", None),
        (0x146C94, None, None),
    ],
)
def test_table_read_observes_whole_cell_font_color(
    monkeypatch, color, property_state, observed
) -> None:
    selections = []
    cursor = SimpleNamespace(
        CharColor=color,
        gotoRange=lambda end, expand: selections.append((end, expand)),
    )
    if property_state is not None:
        cursor.getPropertyState = lambda name: SimpleNamespace(value=property_state)
    cell = SimpleNamespace(
        String="Observed text",
        Text=SimpleNamespace(
            getStart=lambda: "start",
            getEnd=lambda: "end",
            createTextCursorByRange=lambda start: cursor,
        ),
    )
    table = SimpleNamespace(
        Name="Inventory 2036",
        Rows=SimpleNamespace(Count=1),
        Columns=SimpleNamespace(Count=1),
        getCellNames=lambda: ("A1",),
        getCellByName=lambda name: cell,
    )
    monkeypatch.setattr(writer_worker, "_named_table", lambda doc, name: table)

    result = GENERIC_ACTIONS["table.read"](
        SimpleNamespace(doc=object()), {"name": table.Name}
    )

    assert selections == [("end", True)]
    assert result["cells"] == [
        {
            "name": "A1",
            "text": "Observed text",
            "font_color": observed,
            "row_index": 1,
            "column_index": 1,
        }
    ]
    hint = adapter_context_hint(
        "libreoffice_writer", "table.read", {"status": "ok", "result": result}
    )
    assert hint["cell_fields"] == [
        "name", "text", "font_color", "row_index", "column_index",
    ]
    assert [dict(zip(hint["cell_fields"], cell, strict=True)) for cell in hint["cells"]] == (
        result["cells"]
    )
    assert "font_color" in hint["guidance"]
    assert "row_index" in hint["guidance"]
    assert "first character" in hint["guidance"]


def test_table_cell_snapshot_exposes_unambiguous_row_and_column_indices(
    monkeypatch,
) -> None:
    cells = {
        "A1": SimpleNamespace(String="top-left"),
        "B2": SimpleNamespace(String="second-row-second-column"),
    }
    table = SimpleNamespace(
        Name="Inventory 2036",
        Rows=SimpleNamespace(Count=2),
        Columns=SimpleNamespace(Count=2),
        getCellNames=lambda: ("A1", "B2"),
        getCellByName=lambda name: cells[name],
    )
    monkeypatch.setattr(writer_worker, "_named_table", lambda doc, name: table)

    result = GENERIC_ACTIONS["table.read"](
        SimpleNamespace(doc=object()), {"name": table.Name}
    )

    assert result["cells"] == [
        {
            "name": "A1",
            "text": "top-left",
            "font_color": None,
            "row_index": 1,
            "column_index": 1,
        },
        {
            "name": "B2",
            "text": "second-row-second-column",
            "font_color": None,
            "row_index": 2,
            "column_index": 2,
        },
    ]


def test_paragraph_replacement_requires_every_output_string() -> None:
    arguments = {
        "index": 8,
        "paragraphs": [
            "A model-authored first block.",
            "A structurally different second block!",
            "A final block without hidden segmentation",
        ],
        "blank_paragraphs_between": 2,
    }

    validate_action_params("paragraph.replace_text", arguments)


def test_reference_workflow_uses_literal_replace_then_explicit_append() -> None:
    replacement = {
        "find": "<source pending>",
        "replacement": "[7]",
        "replace_all": False,
        "case_sensitive": True,
    }
    append = {
        "paragraphs": ["[7] Example Author. A Different Work. 2036."],
        "blank_paragraphs_before": 0,
        "blank_paragraphs_between": 0,
    }

    validate_action_params("text.find_replace", replacement)
    validate_action_params("document.append_paragraphs", append)


@pytest.mark.parametrize("replace_all", [False, True])
def test_literal_paragraph_breaks_use_native_range_assignment(replace_all):
    matches = [SimpleNamespace(String="anchor"), SimpleNamespace(String="anchor")]
    visited = []
    descriptor = SimpleNamespace()

    def match_at(index):
        visited.append(index)
        return matches[index]

    document = SimpleNamespace(
        createReplaceDescriptor=lambda: descriptor,
        findFirst=lambda _: matches[0],
        findAll=lambda _: SimpleNamespace(
            getCount=lambda: len(matches), getByIndex=match_at
        ),
        replaceAll=lambda _: pytest.fail("replacement descriptor embeds CR literally"),
    )
    arguments = {
        "find": "anchor",
        "replacement": "North\u2019s notes. \r\rNext section",
        "replace_all": replace_all,
        "case_sensitive": True,
    }
    original = deepcopy(arguments)
    validate_action_params("text.find_replace", arguments)

    result = GENERIC_ACTIONS["text.find_replace"](
        SimpleNamespace(doc=document), arguments
    )

    assert arguments == original
    assert descriptor.SearchRegularExpression is False
    assert descriptor.ReplaceString == arguments["replacement"]
    assert matches[0].String == arguments["replacement"]
    assert matches[1].String == (arguments["replacement"] if replace_all else "anchor")
    assert visited == ([1, 0] if replace_all else [])
    assert result["replacement_count"] == (2 if replace_all else 1)


def test_plain_literal_replace_all_keeps_native_bulk_path():
    descriptor = SimpleNamespace()
    document = SimpleNamespace(
        createReplaceDescriptor=lambda: descriptor, replaceAll=lambda _: 3
    )
    arguments = {
        "find": "anchor", "replacement": "replacement",
        "replace_all": True, "case_sensitive": False,
    }

    result = GENERIC_ACTIONS["text.find_replace"](
        SimpleNamespace(doc=document), arguments
    )

    assert result["replacement_count"] == 3
    assert descriptor.SearchCaseSensitive is False


def test_empty_literal_replacement_deletes_only_the_model_selected_match():
    descriptor = SimpleNamespace()
    first = SimpleNamespace(String="Draft note")
    later = SimpleNamespace(String="Draft note")
    document = SimpleNamespace(
        createReplaceDescriptor=lambda: descriptor,
        findFirst=lambda _: first,
    )
    arguments = {
        "find": "Draft note", "replacement": "",
        "replace_all": False, "case_sensitive": True,
    }
    original = deepcopy(arguments)
    schema = build_tools(
        "libreoffice_writer", ["text.find_replace"], include_control_tools=False,
        include_gui=False,
    )[0]["function"]["parameters"]
    jsonschema.validate(arguments, schema)
    validate_action_params("text.find_replace", arguments)
    state = RuntimeState(
        task_id="synthetic-deletion", domain="libreoffice_writer",
        instruction="Delete the first exact observed literal.",
    )
    LiteAgent._validate_stateful_arguments(state, "text.find_replace", arguments)

    result = GENERIC_ACTIONS["text.find_replace"](
        SimpleNamespace(doc=document), arguments
    )

    assert arguments == original
    assert descriptor.SearchString == original["find"]
    assert descriptor.ReplaceString == ""
    assert descriptor.SearchRegularExpression is False
    assert first.String == ""
    assert later.String == "Draft note"
    assert result["replacement"] == ""
    assert result["replacement_count"] == 1


def test_empty_paragraph_replacement_clears_text_and_keeps_existing_boundary(monkeypatch):
    selected = SimpleNamespace(String="Draft paragraph")
    other = SimpleNamespace(String="Keep this paragraph")
    paragraphs = [selected, other]
    ranges = []
    selected.getStart = lambda: "start"
    selected.getEnd = lambda: "end"
    selected.gotoRange = lambda end, expand: ranges.append((end, expand))
    text = SimpleNamespace(
        createTextCursorByRange=lambda _: selected,
        insertString=lambda cursor, value, _: setattr(cursor, "String", value),
        insertControlCharacter=lambda *args: pytest.fail("must keep paragraph boundaries"),
    )
    selected.getText = lambda: text
    monkeypatch.setattr(writer_worker, "_paragraphs", lambda _: paragraphs)
    arguments = {"index": 0, "paragraphs": [""]}
    original = deepcopy(arguments)
    jsonschema.validate(arguments, STRICT_ACTION_PARAM_SCHEMAS["paragraph.replace_text"])
    validate_action_params("paragraph.replace_text", arguments)

    GENERIC_ACTIONS["paragraph.replace_text"](
        SimpleNamespace(doc=SimpleNamespace(Text=text)), arguments
    )

    assert arguments == original
    assert ranges == [("end", True)]
    assert [paragraph.String for paragraph in paragraphs] == ["", "Keep this paragraph"]


@pytest.mark.parametrize("forwarded", [False, True])
def test_local_literal_insertion_contract_preserves_cr_and_scope(forwarded):
    if forwarded:
        tool = constrain_adapter_call_routes(
            build_tools("multi_apps", ["adapter.call"], include_gui=False),
            [("libreoffice_writer", "text.find_replace")],
        )[0]
        schema = tool["function"]["parameters"]["properties"]["payload"][
            "properties"
        ]["params"]
    else:
        schema = build_tools(
            "libreoffice_writer", ["text.find_replace"], include_control_tools=False,
            include_gui=False,
        )[0]["function"]["parameters"]
    params = {
        "find": "end. Start", "replacement": "end. \r\rStart",
        "replace_all": False, "case_sensitive": True,
    }
    jsonschema.validate(params, schema)
    validate_action_params("text.find_replace", params)
    assert json.loads(json.dumps(params)) == params
    assert "\\r\\r" in schema["properties"]["replacement"]["description"]
    assert "whole document" in schema["properties"]["replace_all"]["description"]


def test_writer_paraphrases_recall_atomic_replacements_only() -> None:
    queries = {
        "split this paragraph into explicit text blocks": "paragraph.replace_text",
        "replace an exact placeholder literal": "text.find_replace",
        "insert a paragraph boundary inside a literal anchor": "text.find_replace",
        "append citation paragraphs at the end": "document.append_paragraphs",
        "read table cell values": "table.read",
        "set font color on selected table cells": "table.set_cell_text_color",
    }
    for query, expected in queries.items():
        matches = {
            item["action"]
            for item in search_actions(
                "libreoffice_writer",
                query,
                instruction=query,
                limit=8,
                strict_generic=True,
            )
        }
        assert expected in matches
        assert RETIRED_MACROS.isdisjoint(matches)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("delete exact text", "text.find_replace"),
        ("remove a literal", "text.find_replace"),
        ("clear paragraph text", "paragraph.replace_text"),
        ("remove document highlighting", "document.remove_highlighting"),
    ],
)
def test_writer_deletion_language_discovers_existing_public_edit(query, expected):
    assert expected in select_actions("libreoffice_writer", query, limit=7)
    matches = search_actions(
        "libreoffice_writer", query, instruction=query, limit=3, strict_generic=True,
    )
    assert expected in {item["action"] for item in matches}


def test_runner_preserves_writer_replacement_arguments() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="libreoffice_writer",
        instruction="Replace the observed literal and append the supplied paragraph.",
    )
    arguments = {
        "find": "{citation}",
        "replacement": "[3]",
        "replace_all": True,
        "case_sensitive": False,
    }

    LiteAgent._validate_stateful_arguments(state, "text.find_replace", arguments)
    assert arguments == {
        "find": "{citation}",
        "replacement": "[3]",
        "replace_all": True,
        "case_sensitive": False,
    }


@pytest.fixture
def paged_writer_session(monkeypatch):
    paragraphs = [
        SimpleNamespace(
            String="" if index in (0, 5, 14) else f"Observed section {index}.",
            ParaTabStops=(
                SimpleNamespace(
                    Position=1270,
                    Alignment=SimpleNamespace(value="DEFAULT"),
                    DecimalChar=SimpleNamespace(value="."),
                    FillChar=SimpleNamespace(value=" "),
                ),
            ),
            ParaAdjust=0,
            ParaLineSpacing=SimpleNamespace(Mode=0, Height=100),
            CharHeight=12,
        )
        for index in range(37)
    ]
    monkeypatch.setattr(writer_worker, "_paragraphs", lambda _: paragraphs)
    monkeypatch.setattr(writer_worker, "_tables", lambda _: [])
    monkeypatch.setattr(
        writer_worker,
        "_highlight_summary",
        lambda _: {
            "highlighted_run_count": 0,
            "highlighted_paragraph_count": 0,
            "colors": {},
        },
    )
    monkeypatch.setattr(writer_worker, "_graphic_object_count", lambda _: 0)
    monkeypatch.setattr(writer_worker, "_footer_summary", lambda _: [])
    page_style = SimpleNamespace(
        Width=21000, Height=29700, LeftMargin=1800, RightMargin=2200,
        isInUse=lambda: True,
    )
    page_styles = SimpleNamespace(
        getElementNames=lambda: ["Body"], getByName=lambda _: page_style,
    )
    return SimpleNamespace(
        doc=SimpleNamespace(
            Text=object(), isModified=lambda: False,
            StyleFamilies=SimpleNamespace(getByName=lambda _: page_styles),
        ),
        path=None,
        identity=lambda: {"title": "Notes.odt", "url": "file:///tmp/Notes.odt"},
    ), paragraphs


@pytest.mark.parametrize(
    ("params", "indices", "next_start"),
    [
        ({"paragraph_start": 13, "paragraph_limit": 4}, list(range(13, 17)), 17),
        ({"paragraph_start": 13}, list(range(13, 25)), 25),
        ({"paragraph_limit": 4}, list(range(4)), 4),
        ({"paragraph_start": 36, "paragraph_limit": 4}, [36], None),
        ({"paragraph_start": 80, "paragraph_limit": 2}, [], None),
    ],
)
def test_writer_inspection_pages_preserve_document_wide_identity(
    paged_writer_session, params, indices, next_start
):
    session, paragraphs = paged_writer_session
    original = deepcopy(params)
    text_before = [paragraph.String for paragraph in paragraphs]
    validate_action_params("document.inspect", params)
    state = RuntimeState(
        task_id="synthetic-page",
        domain="libreoffice_writer",
        instruction="Read the selected paragraph page.",
    )
    LiteAgent._validate_stateful_arguments(state, "document.inspect", params)

    result = GENERIC_ACTIONS["document.inspect"](session, params)

    assert params == original
    assert result["paragraph_count"] == 37
    assert result["nonempty_paragraph_count"] == 34
    assert result["paragraphs"] == [text_before[index] for index in indices]
    assert result["footers"] == []
    assert [row["index"] for row in result["paragraph_details"]] == indices
    for row in result["paragraph_details"]:
        index = row["index"]
        ordinal = sum(bool(text.strip()) for text in text_before[: index + 1])
        assert row["nonempty_ordinal"] == (ordinal if text_before[index] else None)
    assert result["next_paragraph_start"] == next_start
    assert result["has_more"] is (next_start is not None)
    assert [paragraph.String for paragraph in paragraphs] == text_before

    for forwarded in (False, True):
        hint = adapter_context_hint(
            "libreoffice_writer", "document.inspect", {"status": "ok", "result": result}
        )
        if forwarded:
            hint = {"downstream_action": "document.inspect", "downstream_context": hint}
        projected = compact_context_hint_for_model(hint, remaining_chars=5000)
        assert len(json.dumps(projected)) <= 5000
        page = projected["downstream_context"] if forwarded else projected
        assert page["next_paragraph_start"] == next_start
        assert page["has_more"] == result["has_more"]
        assert page["paragraph_start"] == params.get("paragraph_start", 0)
        assert [row["index"] for row in page["paragraph_details"]] == indices
        assert [row["text"] for row in page["paragraph_details"]] == result["paragraphs"]


def test_writer_inspection_without_paging_keeps_existing_overview(paged_writer_session):
    session, paragraphs = paged_writer_session

    result = GENERIC_ACTIONS["document.inspect"](session, {})

    assert result["paragraphs"] == [paragraph.String for paragraph in paragraphs]
    assert len(result["paragraph_details"]) == len(paragraphs)
    assert "paragraph_start" not in result
    assert "has_more" not in result
    hint = adapter_context_hint(
        "libreoffice_writer", "document.inspect", {"status": "ok", "result": result}
    )
    assert hint["paragraph_details_omitted"] == 13
    assert [row["index"] for row in hint["paragraph_details"]] == [
        *range(12), *range(25, 37)
    ]


@pytest.mark.parametrize("forwarded", [False, True])
def test_writer_single_paragraph_read_keeps_exact_long_text(
    paged_writer_session, forwarded
):
    session, paragraphs = paged_writer_session
    text = (
        'The meeting notes say "keep our wording".\t'
        + "A longer section preserves punctuation and spacing. " * 15
        + "This final sentence must remain unchanged!"
    )
    assert 500 < len(text) < 1200
    paragraphs[13].String = text
    params = {"paragraph_start": 13, "paragraph_limit": 1}

    result = GENERIC_ACTIONS["document.inspect"](session, params)

    assert result["paragraphs"] == [text]
    assert result["paragraph_details"][0]["text"] == text
    assert result["paragraph_details"][0]["text_length"] == len(text)
    hint = adapter_context_hint(
        "libreoffice_writer", "document.inspect", {"status": "ok", "result": result}
    )
    if forwarded:
        hint = {"downstream_action": "document.inspect", "downstream_context": hint}
    projected = compact_context_hint_for_model(hint, remaining_chars=5000)
    assert len(json.dumps(projected)) <= 5000
    page = projected["downstream_context"] if forwarded else projected
    row = page["paragraph_details"][0]
    assert row["index"] == 13
    assert row["nonempty_ordinal"] == 12
    assert row["text"] == text
    assert row["text_length"] == len(text)
    assert page["next_paragraph_start"] == 14
    assert paragraphs[13].String == text


def test_writer_overview_marks_preview_with_native_length(paged_writer_session):
    session, paragraphs = paged_writer_session
    text = "Long source paragraph with exact wording. " * 20
    paragraphs[1].String = text

    result = GENERIC_ACTIONS["document.inspect"](session, {})

    assert result["paragraphs"][1] == text[:500]
    assert result["paragraph_details"][1]["text_length"] == len(text)
    hint = adapter_context_hint(
        "libreoffice_writer", "document.inspect", {"status": "ok", "result": result}
    )
    row = hint["paragraph_details"][1]
    assert row["text"] == text[:180]
    assert row["text_length"] == len(text)
    assert "paragraph_limit=1" in hint["guidance"]
    assert "context_truncated" in hint["guidance"]


def test_writer_oversized_paragraph_read_exposes_context_truncation(paged_writer_session):
    session, paragraphs = paged_writer_session
    text = "Long source paragraph with exact wording. " * 200
    paragraphs[13].String = text
    result = GENERIC_ACTIONS["document.inspect"](
        session, {"paragraph_start": 13, "paragraph_limit": 1}
    )
    assert result["paragraphs"] == [text]
    hint = adapter_context_hint(
        "libreoffice_writer", "document.inspect", {"status": "ok", "result": result}
    )

    projected = compact_context_hint_for_model(hint, remaining_chars=5000)

    assert len(json.dumps(projected)) <= 5000
    assert projected["context_truncated"] is True
    assert "...<truncated>..." in projected["paragraph_details"][0]["text"]
    assert projected["paragraph_details"][0]["text_length"] == len(text)


@pytest.mark.parametrize("forwarded", [False, True])
def test_writer_inspect_paging_schema_matches_owner(forwarded):
    if forwarded:
        tools = constrain_adapter_call_routes(
            build_tools("multi_apps", ["adapter.call"], include_gui=False),
            [("libreoffice_writer", "document.inspect")],
        )
        schema = tools[0]["function"]["parameters"]["properties"]["payload"][
            "properties"
        ]["params"]
    else:
        schema = build_tools(
            "libreoffice_writer", ["document.inspect"], include_control_tools=False,
            include_gui=False,
        )[0]["function"]["parameters"]
    assert schema["properties"] == STRICT_ACTION_PARAM_SCHEMAS["document.inspect"][
        "properties"
    ]
    for params in ({}, {"paragraph_start": 17, "paragraph_limit": 6}):
        jsonschema.validate(params, schema)
        validate_action_params("document.inspect", params)
    for params in ({"paragraph_start": -1}, {"paragraph_limit": 13}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(params, schema)
        with pytest.raises(AdapterError):
            validate_action_params("document.inspect", params)


def test_writer_paged_read_remains_available_after_successful_overview():
    state = RuntimeState(
        task_id="synthetic-page",
        domain="libreoffice_writer",
        instruction="Read the document paragraphs.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-09-07T00:00:00Z",
                proposed={"kind": "adapter", "action": "document.inspect", "arguments": {}},
                executed=True,
                result={"context_hint": {"paragraph_details_omitted": 13}},
            )
        ],
    )

    assert state.stage_read_satisfied("document.inspect") is False
