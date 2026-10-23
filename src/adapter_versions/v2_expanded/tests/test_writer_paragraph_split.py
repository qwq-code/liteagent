from copy import deepcopy
from types import SimpleNamespace

import jsonschema
import pytest

from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_context_hint_for_model,
)
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import (
    build_tools,
    public_actions,
    search_actions,
)
from writer_adapter import uno_worker
from writer_adapter.errors import AdapterError
from writer_adapter.schema import ACTIONS, validate_action_params
from writer_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


class Cursor:
    def __init__(self, paragraph):
        self.paragraph = paragraph
        self.start = self.end = 0

    @property
    def String(self):
        return self.paragraph.String[self.start : self.end]

    def goRight(self, count, expand):
        self.end += count
        if not expand:
            self.start = self.end
        return self.end <= len(self.paragraph.String)

    def collapseToEnd(self):
        self.start = self.end


class Paragraph:
    def __init__(self, text, body):
        self.String = text
        self.body = body

    def getText(self):
        return self.body

    def getStart(self):
        return self


class Body:
    def __init__(self, strings):
        self.paragraphs = [Paragraph(text, self) for text in strings]
        self.insertions = 0

    def createTextCursorByRange(self, paragraph):
        return Cursor(paragraph)

    def insertControlCharacter(self, cursor, control, absorb):
        assert control == 0
        assert absorb is False
        assert cursor.start == cursor.end
        paragraph = cursor.paragraph
        index = self.paragraphs.index(paragraph)
        right = Paragraph(paragraph.String[cursor.end :], self)
        paragraph.String = paragraph.String[: cursor.end]
        self.paragraphs.insert(index + 1, right)
        cursor.paragraph = right
        cursor.start = cursor.end = 0
        self.insertions += 1


@pytest.fixture
def session(monkeypatch):
    body = Body(
        [
            "Unchanged heading",
            "North\u2019s notes.  Middle?  Tail \u201cZ\u201d.",
            "Unchanged tail",
        ]
    )
    monkeypatch.setattr(uno_worker, "_paragraphs", lambda text: list(text.paragraphs))
    return SimpleNamespace(doc=SimpleNamespace(Text=body))


@pytest.mark.parametrize("forwarded", [False, True])
@pytest.mark.parametrize("after_text", ["section;  ", [";", ";", "end"]])
def test_split_uses_one_public_schema_and_preserves_arguments(forwarded, after_text):
    params = {"index": 2, "after_text": after_text, "blank_paragraphs_between": 1}
    original = deepcopy(params)
    if forwarded:
        tool = constrain_adapter_call_routes(
            build_tools("multi_apps", ["adapter.call"], include_gui=False),
            [("libreoffice_writer", "paragraph.split")],
        )[0]
        schema = tool["function"]["parameters"]["oneOf"][0]["properties"]["payload"][
            "properties"
        ]["params"]
    else:
        schema = build_tools(
            "libreoffice_writer",
            ["paragraph.split"],
            include_control_tools=False,
            include_gui=False,
        )[0]["function"]["parameters"]
    assert (
        schema["properties"]
        == STRICT_ACTION_PARAM_SCHEMAS["paragraph.split"]["properties"]
    )
    jsonschema.validate(params, schema)
    validate_action_params("paragraph.split", params)
    assert params == original
    assert "paragraph.split" in ACTIONS & uno_worker.GENERIC_ACTIONS.keys()
    assert "paragraph.split" in public_actions("libreoffice_writer")


@pytest.mark.parametrize(
    "anchor,blank_between",
    [("notes.  ", 0), ("Middle?  ", 1), ("North\u2019s", 2), (".", 1)],
)
def test_split_changes_only_the_selected_boundary(session, anchor, blank_between):
    body = session.doc.Text
    original = [paragraph.String for paragraph in body.paragraphs]
    params = {
        "index": 1,
        "after_text": anchor,
        "blank_paragraphs_between": blank_between,
    }
    unchanged_params = deepcopy(params)
    offset = original[1].index(anchor) + len(anchor)

    result = uno_worker.GENERIC_ACTIONS["paragraph.split"](session, params)

    expected = [original[1][:offset], *([""] * blank_between), original[1][offset:]]
    assert [paragraph.String for paragraph in body.paragraphs] == [
        original[0],
        *expected,
        original[2],
    ]
    assert result["paragraphs"] == expected
    assert result["right_paragraph_index"] == blank_between + 2
    assert result["text_unchanged"] is True
    assert result["split_offset"] == offset
    assert params == unchanged_params
    context = adapter_context_hint(
        "libreoffice_writer", "paragraph.split", {"result": result}
    )
    compact = compact_context_hint_for_model(context, remaining_chars=2000)
    assert compact["right_paragraph_index"] == result["right_paragraph_index"]
    assert compact["paragraphs"] == expected


@pytest.mark.parametrize(
    "anchors,gap,parts",
    [
        (
            ["  ", "  "],
            0,
            ["North\u2019s notes.  ", "Middle?  ", "Tail \u201cZ\u201d."],
        ),
        (
            ["notes.", "?"],
            1,
            ["North\u2019s notes.", "", "  Middle?", "", "  Tail \u201cZ\u201d."],
        ),
        (
            ["North\u2019s", "\u201d."],
            2,
            [
                "North\u2019s",
                "",
                "",
                " notes.  Middle?  Tail \u201cZ\u201d.",
                "",
                "",
                "",
            ],
        ),
    ],
)
def test_ordered_boundaries_preserve_source_and_report_final_indices(
    session, anchors, gap, parts
):
    body = session.doc.Text
    original = [paragraph.String for paragraph in body.paragraphs]
    params = {"index": 1, "after_text": anchors, "blank_paragraphs_between": gap}
    unchanged_params = deepcopy(params)

    result = uno_worker.GENERIC_ACTIONS["paragraph.split"](session, params)

    assert [paragraph.String for paragraph in body.paragraphs] == [
        original[0],
        *parts,
        original[2],
    ]
    assert "".join(parts) == original[1]
    assert result["paragraphs"] == parts
    assert result["after_text"] == anchors
    assert result["text_unchanged"] is True
    assert "split_offset" not in result
    offset = 0
    for position, boundary in enumerate(result["boundaries"]):
        offset = original[1].index(anchors[position], offset) + len(anchors[position])
        assert boundary == {
            "after_text": anchors[position],
            "split_offset": offset,
            "right_paragraph_index": 1 + (position + 1) * (gap + 1),
        }
    assert result["right_paragraph_index"] == 1 + len(anchors) * (gap + 1)
    assert body.insertions == len(anchors) * (gap + 1)
    assert params == unchanged_params
    compact = compact_context_hint_for_model(
        adapter_context_hint(
            "libreoffice_writer", "paragraph.split", {"result": result}
        ),
        remaining_chars=2000,
    )
    assert compact["boundaries"] == result["boundaries"]
    assert compact["paragraphs"] == parts


@pytest.mark.parametrize("anchor", ["absent", ["notes.", "absent"], ["?", "notes."]])
def test_unresolved_anchor_reports_an_error_without_inserting(session, anchor):
    body = session.doc.Text
    original = [paragraph.String for paragraph in body.paragraphs]
    with pytest.raises(AdapterError) as error:
        uno_worker.GENERIC_ACTIONS["paragraph.split"](
            session, {"index": 1, "after_text": anchor}
        )
    assert error.value.code == "TEXT_NOT_FOUND"
    assert error.value.details["after_text"] == anchor
    assert "No paragraph breaks were inserted" in error.value.message
    assert body.insertions == 0
    assert [paragraph.String for paragraph in body.paragraphs] == original


@pytest.mark.parametrize("anchor", [[], ["notes.", ""], ["."] * 33, [1]])
def test_anchor_list_validation_matches_public_schema(anchor):
    params = {"index": 1, "after_text": anchor}
    schema = build_tools(
        "libreoffice_writer",
        ["paragraph.split"],
        include_control_tools=False,
        include_gui=False,
    )[0]["function"]["parameters"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(params, schema)
    with pytest.raises(AdapterError, match="ordered list"):
        validate_action_params("paragraph.split", params)


def test_native_split_queries_recall_the_public_primitive():
    query = "split a paragraph at an observed text anchor with an empty line"
    hits = search_actions(
        "libreoffice_writer", query, instruction=query, limit=7, strict_generic=True
    )
    assert "paragraph.split" in {item["action"] for item in hits}
    assert "paragraph.separate_sentences" not in {item["action"] for item in hits}
