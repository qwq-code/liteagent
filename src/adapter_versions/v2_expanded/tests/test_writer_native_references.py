from __future__ import annotations

import copy
import sys
from types import SimpleNamespace
from typing import Any

import pytest
import jsonschema

from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_context_hint_for_model,
)
from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.state_model import RuntimeState
from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS, search_actions
from writer_adapter.errors import AdapterError
from writer_adapter.native_references import (
    apply_paragraph_numbering,
    create_bookmark,
    insert_cross_reference,
    paragraph_numbering_state,
)
from writer_adapter.schema import ACTIONS, validate_action_params
from writer_adapter.text_search import CONTEXT_RADIUS, find_text
from writer_adapter.text_format import set_text_format
from writer_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from writer_adapter.uno_worker import GENERIC_ACTIONS, NO_AUTO_SAVE_ACTIONS


NATIVE_REFERENCE_ACTIONS = {
    "paragraph.apply_numbering",
    "bookmark.create",
    "cross_reference.insert",
}


class FakeEnumeration:
    def __init__(self, values: list[Any]) -> None:
        self.values = iter(values)
        self.next_value: Any | None = None

    def hasMoreElements(self) -> bool:
        try:
            self.next_value = next(self.values)
        except StopIteration:
            return False
        return True

    def nextElement(self) -> Any:
        value = self.next_value
        self.next_value = None
        return value


class FakeNumberingRules:
    def __init__(self, numbering_type: int, next_label: str) -> None:
        self.numbering_type = numbering_type
        self.next_label = next_label

    def getByIndex(self, index: int) -> tuple[Any, ...]:
        if not 0 <= index <= 9:
            raise IndexError(index)
        return (SimpleNamespace(Name="NumberingType", Value=self.numbering_type),)


class FakeParagraph:
    def __init__(
        self,
        text: str,
        *,
        numbered: bool = False,
        label: str = "",
        rules: FakeNumberingRules | None = None,
        style_name: str = "",
    ) -> None:
        self.String = text
        self.NumberingIsNumber = numbered
        self.ListLabelString = label
        self._numbering_rules = rules
        self.NumberingStyleName = style_name
        self.NumberingLevel = 0
        self.ParaIsNumberingRestart = False
        self.NumberingStartValue = -1
        self.character_runs = [(text, "Original character style")]
        self.document: FakeDocument | None = None

    @property
    def NumberingRules(self) -> FakeNumberingRules | None:
        return self._numbering_rules

    @NumberingRules.setter
    def NumberingRules(self, value: FakeNumberingRules) -> None:
        self._numbering_rules = value
        self.NumberingIsNumber = True
        self.ListLabelString = value.next_label

    def supportsService(self, name: str) -> bool:
        return name == "com.sun.star.text.Paragraph"

    def getText(self) -> "FakeText":
        return FakeText(self)

    def getStart(self) -> object:
        return object()


class FakeCursor:
    def __init__(self, paragraph: FakeParagraph) -> None:
        self.paragraph = paragraph
        self.position = 0
        self.selection_start = 0
        self.selection_end = 0

    @property
    def String(self) -> str:
        return self.paragraph.String[self.selection_start : self.selection_end]

    def __getattr__(self, name: str) -> Any:
        return getattr(self.paragraph, name)

    def gotoStartOfParagraph(self, expand: bool) -> None:
        assert expand is False
        self.position = self.selection_start = self.selection_end = 0

    def gotoEndOfParagraph(self, expand: bool) -> None:
        assert expand is True
        self.selection_end = self.position = len(self.paragraph.String)

    def goRight(self, count: int, expand: bool) -> bool:
        destination = self.position + count
        if destination > len(self.paragraph.String):
            return False
        if expand:
            if self.selection_start == self.selection_end:
                self.selection_start = self.position
            self.selection_end = destination
        else:
            self.selection_start = destination
            self.selection_end = destination
        self.position = destination
        return True


class FakeAnchor:
    def __init__(self, cursor: FakeCursor) -> None:
        self.String = cursor.String
        self.paragraph = cursor.paragraph

    def getText(self) -> "FakeText":
        return self.paragraph.getText()

    def getStart(self) -> object:
        return self.paragraph.getStart()


class FakeBookmark:
    def __init__(self, document: "FakeDocument") -> None:
        self.document = document
        self.name = ""
        self.anchor: FakeAnchor | None = None

    def setName(self, name: str) -> None:
        self.name = name

    def getName(self) -> str:
        return self.name

    def attach(self, cursor: FakeCursor) -> None:
        self.anchor = FakeAnchor(cursor)
        self.document.bookmarks.values[self.name] = self

    def getAnchor(self) -> FakeAnchor:
        assert self.anchor is not None
        return self.anchor


class FakeReferenceField:
    def __init__(self, document: "FakeDocument") -> None:
        self.document = document
        self.SourceName = ""
        self.ReferenceFieldSource = -1
        self.ReferenceFieldPart = -1

    def getPresentation(self, show_command: bool) -> str:
        assert show_command is False
        if self.document.forced_presentation is not None:
            return self.document.forced_presentation
        bookmark = self.document.bookmarks.getByName(self.SourceName)
        anchor = bookmark.getAnchor()
        if self.ReferenceFieldPart in {8, 9, 10}:
            return anchor.paragraph.ListLabelString
        if self.ReferenceFieldPart == 2:
            return anchor.String
        return "3"


class FakeBookmarks:
    def __init__(self) -> None:
        self.values: dict[str, FakeBookmark] = {}

    def hasByName(self, name: str) -> bool:
        return name in self.values

    def getByName(self, name: str) -> FakeBookmark:
        return self.values[name]


class FakeTextFields:
    def __init__(self, document: "FakeDocument") -> None:
        self.document = document
        self.refresh_count = 0
        self.refresh_error: Exception | None = None

    def refresh(self) -> None:
        self.refresh_count += 1
        if self.refresh_error is not None:
            raise self.refresh_error

    def createEnumeration(self) -> FakeEnumeration:
        return FakeEnumeration(self.document.inserted_fields)


class FakeUndoManager:
    def __init__(self, document: "FakeDocument") -> None:
        self.document = document
        self.stack = []
        self.context = None
        self.undo_count = 0
        self.undo_error: Exception | None = None

    def snapshot(self):
        return (
            [(p.String, copy.deepcopy(p.character_runs)) for p in self.document.Text.paragraphs],
            list(self.document.inserted_fields),
        )

    def isLocked(self) -> bool:
        return False

    def enterUndoContext(self, title: str) -> None:
        assert self.context is None
        self.context = (title, self.snapshot())

    def leaveUndoContext(self) -> None:
        assert self.context is not None
        if self.context[1] != self.snapshot():
            self.stack.append(self.context)
        self.context = None

    def isUndoPossible(self) -> bool:
        return bool(self.stack)

    def getCurrentUndoActionTitle(self) -> str:
        return self.stack[-1][0]

    def undo(self) -> None:
        self.undo_count += 1
        if self.undo_error is not None:
            raise self.undo_error
        _, (paragraph_states, fields) = self.stack.pop()
        for paragraph, (text, runs) in zip(self.document.Text.paragraphs, paragraph_states, strict=True):
            paragraph.String = text
            paragraph.character_runs = runs
        self.document.inserted_fields[:] = fields


class FakeText:
    def __init__(self, paragraph: FakeParagraph) -> None:
        self.paragraph = paragraph

    def createTextCursorByRange(self, start: object) -> FakeCursor:
        return FakeCursor(self.paragraph)

    def insertTextContent(
        self, cursor: FakeCursor, field: FakeReferenceField, absorb: bool
    ) -> None:
        assert absorb is True
        assert self.paragraph.document is not None
        if self.paragraph.document.insert_error is not None:
            raise self.paragraph.document.insert_error
        presentation = field.getPresentation(False)
        before = self.paragraph.String[: cursor.selection_start]
        after = self.paragraph.String[cursor.selection_end :]
        self.paragraph.String = before + presentation + after
        self.paragraph.character_runs = [(self.paragraph.String, "Inserted field style")]
        self.paragraph.document.inserted_fields.append(field)


class MismatchedCursor(FakeCursor):
    @property
    def String(self) -> str:
        return "different UNO selection"


class MismatchedText(FakeText):
    def createTextCursorByRange(self, start: object) -> MismatchedCursor:
        return MismatchedCursor(self.paragraph)


class MismatchedParagraph(FakeParagraph):
    def getText(self) -> MismatchedText:
        return MismatchedText(self)


class FakeBodyText:
    def __init__(self, paragraphs: list[FakeParagraph]) -> None:
        self.paragraphs = paragraphs

    def createEnumeration(self) -> FakeEnumeration:
        return FakeEnumeration(self.paragraphs)


class FakeDocument:
    def __init__(self, paragraphs: list[FakeParagraph]) -> None:
        self.Text = FakeBodyText(paragraphs)
        self.bookmarks = FakeBookmarks()
        self.inserted_fields = []
        self.text_fields = FakeTextFields(self)
        self.undo_manager = FakeUndoManager(self)
        self.forced_presentation: str | None = None
        self.insert_error: Exception | None = None
        for paragraph in paragraphs:
            paragraph.document = self

    def createInstance(self, service: str) -> FakeBookmark | FakeReferenceField:
        if service == "com.sun.star.text.Bookmark":
            return FakeBookmark(self)
        if service == "com.sun.star.text.textfield.GetReference":
            return FakeReferenceField(self)
        raise AssertionError(service)

    def getBookmarks(self) -> FakeBookmarks:
        return self.bookmarks

    def getTextFields(self) -> FakeTextFields:
        return self.text_fields

    def getUndoManager(self) -> FakeUndoManager:
        return self.undo_manager


def fake_session(paragraphs: list[FakeParagraph]) -> Any:
    return SimpleNamespace(doc=FakeDocument(paragraphs))


def test_native_reference_actions_are_on_every_writer_surface() -> None:
    surfaces = (
        set(ACTIONS),
        set(GENERIC_ACTIONS),
        set(STRICT_ACTION_PARAM_SCHEMAS),
        set(DIRECT_ACTION_SCHEMAS["libreoffice_writer"]),
    )
    assert all(NATIVE_REFERENCE_ACTIONS.issubset(surface) for surface in surfaces)
    assert all("text.find" in surface for surface in surfaces)


def test_text_find_is_read_only_while_reference_mutations_auto_save() -> None:
    assert "text.find" in NO_AUTO_SAVE_ACTIONS
    assert "bookmark.create" not in NO_AUTO_SAVE_ACTIONS
    assert "cross_reference.insert" not in NO_AUTO_SAVE_ACTIONS


def test_reference_usage_exposes_existing_location_and_source_operations() -> None:
    schemas = DIRECT_ACTION_SCHEMAS["libreoffice_writer"]
    reference = schemas["cross_reference.insert"]
    assert "bookmark.create" in reference["description"]
    assert "text.find" in reference["description"]
    assert "matched_text as expected_text" in reference["description"]
    assert "surrounding text" in reference["description"]
    assert "insertion destination" in reference["properties"]["paragraph_index"]["description"]
    assert "paragraph.apply_numbering" in reference["properties"]["display"]["description"]
    assert "text.find" in schemas["bookmark.create"]["description"]
    assert reference == STRICT_ACTION_PARAM_SCHEMAS["cross_reference.insert"]
    for action in ("text.find", "bookmark.create", "paragraph.apply_numbering"):
        assert action in {
            match["action"]
            for match in search_actions("libreoffice_writer", action, strict_generic=True)
        }


@pytest.mark.parametrize(
    ("instruction", "expects_locator"),
    [
        ("Add a numbered reference to the bibliography and a cross reference at the marked position in a paragraph.", True),
        ("Insert a native reference field at the placeholder, keeping the surrounding words unchanged.", True),
        ("Create a bookmark around the source quotation and cite it at the marker.", True),
        ("Set all body paragraphs to double line spacing.", False),
        ("Set the document font family to Liberation Serif.", True),
    ],
)
def test_locator_recall_in_initial_writer_surface(instruction, expects_locator):
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        object(),
        model_client=SimpleNamespace(client=object()),
    )
    state = RuntimeState(
        task_id="synthetic-locator-recall",
        domain="libreoffice_writer",
        instruction=instruction,
    )
    assert ("text.find" in agent.selected_actions(state)) is expects_locator


@pytest.mark.parametrize("domain", ["libreoffice_writer", "multi_apps"])
@pytest.mark.parametrize("query", ["locate marker offsets", "placeholder location", "text.find"])
def test_locator_is_searchable_by_usage_and_exact_name(domain, query):
    matches = search_actions(domain, f"Writer {query}", strict_generic=True)
    actions = {item.get("downstream_action", item["action"]) for item in matches}
    assert "text.find" in actions


def test_text_find_returns_repeated_matches_across_body_paragraphs() -> None:
    prefix = "x" * (CONTEXT_RADIUS + 5)
    suffix = "y" * (CONTEXT_RADIUS + 7)
    paragraphs = [
        FakeParagraph("alpha token token omega"),
        FakeParagraph(f"{prefix}token{suffix}"),
        FakeParagraph("unrelated"),
    ]
    before = [paragraph.String for paragraph in paragraphs]

    result = find_text(
        fake_session(paragraphs),
        {"literal": "token", "case_sensitive": True, "max_results": 10},
    )

    assert result["returned_count"] == 3
    assert result["has_more"] is False
    assert [item["paragraph_index"] for item in result["matches"]] == [0, 0, 1]
    assert [
        (item["start_offset"], item["end_offset"]) for item in result["matches"][:2]
    ] == [
        (6, 11),
        (12, 17),
    ]
    long_match = result["matches"][2]
    assert long_match["context_truncated"] is True
    assert (
        long_match["context"]
        == paragraphs[1].String[
            long_match["context_start_offset"] : long_match["context_end_offset"]
        ]
    )
    assert [paragraph.String for paragraph in paragraphs] == before


def test_text_find_case_policy_and_result_limit_are_explicit() -> None:
    paragraphs = [
        FakeParagraph("Anchor anchor ANCHOR"),
        FakeParagraph("anchor"),
    ]

    sensitive = find_text(
        fake_session(paragraphs),
        {"literal": "anchor", "case_sensitive": True, "max_results": 8},
    )
    insensitive_limited = find_text(
        fake_session(paragraphs),
        {"literal": "anchor", "case_sensitive": False, "max_results": 2},
    )

    assert [item["matched_text"] for item in sensitive["matches"]] == [
        "anchor",
        "anchor",
    ]
    assert insensitive_limited["returned_count"] == 2
    assert insensitive_limited["has_more"] is True
    assert [item["matched_text"] for item in insensitive_limited["matches"]] == [
        "Anchor",
        "anchor",
    ]


def test_model_context_preserves_numbering_and_exact_search_locations() -> None:
    inspect_context = adapter_context_hint(
        "libreoffice_writer",
        "document.inspect",
        {
            "result": {
                "paragraphs": [],
                "paragraph_count": 1,
                "nonempty_paragraph_count": 1,
                "paragraph_details": [
                    {
                        "index": 0,
                        "nonempty_ordinal": 1,
                        "text": "Synthetic reference",
                        "numbering": {
                            "style_name": "References",
                            "level": 0,
                            "restart": False,
                            "start_value": -1,
                            "list_label": "[7]",
                            "is_numbered": True,
                        },
                    }
                ],
            }
        },
    )
    assert inspect_context is not None
    assert inspect_context["paragraph_details"][0]["numbering"]["list_label"] == "[7]"

    find_context = adapter_context_hint(
        "libreoffice_writer",
        "text.find",
        {
            "result": {
                "scope": "body_paragraphs",
                "literal": "<replace-me>",
                "case_sensitive": True,
                "max_results": 3,
                "returned_count": 1,
                "has_more": False,
                "matches": [
                    {
                        "paragraph_index": 4,
                        "start_offset": 23,
                        "end_offset": 35,
                        "matched_text": "<replace-me>",
                    }
                ],
            }
        },
    )
    assert find_context is not None
    assert find_context["matches"] == [
        {
            "paragraph_index": 4,
            "start_offset": 23,
            "end_offset": 35,
            "matched_text": "<replace-me>",
        }
    ]


def test_counterfactual_native_reference_contracts_validate() -> None:
    continuing = {
        "source_index": 12,
        "target_index": 19,
        "level": 0,
        "restart": False,
    }
    restarting = {
        "source_index": 3,
        "target_index": 8,
        "level": 2,
        "restart": True,
        "start_value": 42,
    }
    bookmark = {
        "name": "AppendixDelta2038",
        "paragraph_index": 19,
        "start_offset": 0,
        "end_offset": 18,
        "expected_text": "Calibration notes.",
    }
    reference = {
        "bookmark_name": "AppendixDelta2038",
        "paragraph_index": 4,
        "start_offset": 7,
        "end_offset": 20,
        "expected_text": "<policy-link>",
        "display": "number_no_context",
    }

    validate_action_params("paragraph.apply_numbering", continuing)
    validate_action_params("paragraph.apply_numbering", restarting)
    validate_action_params("bookmark.create", bookmark)
    validate_action_params("cross_reference.insert", reference)
    validate_action_params(
        "text.find",
        {"literal": "section marker", "case_sensitive": False, "max_results": 7},
    )
    validate_action_params(
        "text.find",
        {"literal": "SECTION MARKER", "case_sensitive": True, "max_results": 2},
    )

    assert continuing != restarting
    assert bookmark["paragraph_index"] != reference["paragraph_index"]


def test_numbering_copies_one_numeric_list_without_rewriting_text() -> None:
    rules = FakeNumberingRules(numbering_type=2, next_label="V")
    source = FakeParagraph(
        "Fourth principle", numbered=True, label="IV", rules=rules, style_name="Policy"
    )
    target = FakeParagraph("Fifth principle")
    session = fake_session([FakeParagraph("Heading"), source, target])

    result = apply_paragraph_numbering(
        session,
        {
            "source_index": 1,
            "target_index": 2,
            "level": 0,
            "restart": False,
        },
    )

    assert target.String == "Fifth principle"
    assert target.NumberingRules is rules
    assert result["source_list_label"] == "IV"
    assert result["list_label"] == "V"
    assert result["numbering_type"] == 2
    assert paragraph_numbering_state(target) == {
        "style_name": "Policy",
        "level": 0,
        "restart": False,
        "start_value": -1,
        "list_label": "V",
        "is_numbered": True,
    }


def test_numbering_rejects_a_bullet_source() -> None:
    bullet = FakeParagraph(
        "Supply list",
        numbered=True,
        label="•",
        rules=FakeNumberingRules(numbering_type=6, next_label="•"),
    )
    target = FakeParagraph("Safety glasses")
    session = fake_session([bullet, target])

    with pytest.raises(AdapterError, match="non-numeric list") as caught:
        apply_paragraph_numbering(
            session,
            {
                "source_index": 0,
                "target_index": 1,
                "level": 0,
                "restart": False,
            },
        )

    assert caught.value.code == "SOURCE_NOT_NUMBERED"
    assert target.String == "Safety glasses"


def test_bookmark_and_cross_reference_create_native_objects() -> None:
    rules = FakeNumberingRules(numbering_type=4, next_label="28")
    target = FakeParagraph(
        "Calibration protocol.", numbered=True, label="27", rules=rules
    )
    mention = FakeParagraph("See <policy-link> for constraints.")
    session = fake_session([FakeParagraph("Overview"), target, mention])
    source = find_text(
        session, {"literal": target.String, "case_sensitive": True, "max_results": 1}
    )["matches"][0]

    bookmark = create_bookmark(
        session,
        {
            "name": "CalibrationProtocol",
            "paragraph_index": source["paragraph_index"],
            "start_offset": source["start_offset"],
            "end_offset": source["end_offset"],
            "expected_text": source["matched_text"],
        },
    )
    marker = "<policy-link>"
    destination = find_text(
        session, {"literal": marker, "case_sensitive": True, "max_results": 1}
    )["matches"][0]
    reference = insert_cross_reference(
        session,
        {
            "bookmark_name": "CalibrationProtocol",
            "paragraph_index": destination["paragraph_index"],
            "start_offset": destination["start_offset"],
            "end_offset": destination["end_offset"],
            "expected_text": destination["matched_text"],
            "display": "number_no_context",
        },
    )

    assert bookmark["anchor_text"] == "Calibration protocol."
    assert reference["field_service"] == "com.sun.star.text.textfield.GetReference"
    assert reference["presentation"] == "27"
    assert mention.String == "See 27 for constraints."
    assert session.doc.text_fields.refresh_count == 1


def reference_session(source: FakeParagraph) -> tuple[Any, dict[str, Any]]:
    mention = FakeParagraph("See <policy-link> for constraints.")
    session = fake_session([source, mention, FakeParagraph("Earlier notes")])
    create_bookmark(session, {
        "name": "SelectedSource", "paragraph_index": 0,
        "start_offset": 0, "end_offset": len(source.String), "expected_text": source.String,
    })
    return session, {
        "bookmark_name": "SelectedSource", "paragraph_index": 1,
        "start_offset": 4, "end_offset": 17, "expected_text": "<policy-link>",
        "display": "number_no_context",
    }


@pytest.mark.parametrize("display", ["number", "number_no_context", "number_full_context"])
def test_numeric_reference_rejects_unnumbered_bookmark_before_consuming_marker(display) -> None:
    session, params = reference_session(FakeParagraph("Selected source text."))
    params["display"] = display
    original = copy.deepcopy(params)
    mention = session.doc.Text.paragraphs[1]
    original_runs = copy.deepcopy(mention.character_runs)

    with pytest.raises(AdapterError) as caught:
        insert_cross_reference(session, params)

    assert caught.value.code == "SOURCE_NOT_NUMBERED"
    assert caught.value.details["source_paragraph_text"] == "Selected source text."
    assert caught.value.details["anchor_text"] == "Selected source text."
    assert caught.value.details["numbering"]["is_numbered"] is False
    assert caught.value.details["destination_unchanged"] is True
    assert mention.String == "See <policy-link> for constraints."
    assert mention.character_runs == original_runs
    assert session.doc.inserted_fields == []
    assert session.doc.undo_manager.stack == []
    assert session.doc.text_fields.refresh_count == 0
    assert params == original


def test_numeric_reference_rejects_bullet_source_before_consuming_marker() -> None:
    session, params = reference_session(FakeParagraph(
        "Safety note.", numbered=True, label="•",
        rules=FakeNumberingRules(numbering_type=6, next_label="•"),
    ))

    with pytest.raises(AdapterError) as caught:
        insert_cross_reference(session, params)

    assert caught.value.code == "SOURCE_NOT_NUMBERED"
    assert caught.value.details["numbering_type"] == 6
    assert session.doc.Text.paragraphs[1].String == "See <policy-link> for constraints."
    assert session.doc.inserted_fields == []


def test_text_reference_to_unnumbered_source_remains_supported() -> None:
    session, params = reference_session(FakeParagraph("Selected source text."))
    params["display"] = "text"

    result = insert_cross_reference(session, params)

    assert result["presentation"] == "Selected source text."
    assert session.doc.Text.paragraphs[1].String == "See Selected source text. for constraints."
    assert len(session.doc.inserted_fields) == 1
    assert session.doc.undo_manager.undo_count == 0
    assert session.doc.undo_manager.context is None


def test_failed_native_reference_readback_restores_marker_and_character_formatting() -> None:
    session, params = reference_session(FakeParagraph(
        "Numbered source.", numbered=True, label="VII",
        rules=FakeNumberingRules(numbering_type=2, next_label="VIII"),
    ))
    mention = session.doc.Text.paragraphs[1]
    mention.character_runs = [("See ", "plain"), ("<policy-link>", "bold"), (" for constraints.", "italic")]
    original_runs = copy.deepcopy(mention.character_runs)
    session.doc.forced_presentation = ""

    with pytest.raises(AdapterError) as caught:
        insert_cross_reference(session, params)

    assert caught.value.code == "VERIFICATION_FAILED"
    assert caught.value.details["presentation"] == ""
    assert caught.value.details["restoration_attempted"] is True
    assert caught.value.details["destination_restored"] is True
    assert caught.value.details["destination_text"] == "See <policy-link> for constraints."
    assert caught.value.details["field_present"] is False
    assert mention.character_runs == original_runs
    assert session.doc.inserted_fields == []
    assert session.doc.undo_manager.undo_count == 1
    assert session.doc.undo_manager.context is None


@pytest.mark.parametrize("fail_before_insertion", [False, True])
def test_reference_failure_never_undoes_a_preceding_agent_action(fail_before_insertion) -> None:
    session, params = reference_session(FakeParagraph("Selected source text."))
    params["display"] = "text"
    undo = session.doc.undo_manager
    undo.enterUndoContext("Earlier Agent edit")
    session.doc.Text.paragraphs[2].String = "Keep the earlier Agent edit"
    undo.leaveUndoContext()
    if fail_before_insertion:
        session.doc.insert_error = RuntimeError("Native insertion failed before a change")
    else:
        session.doc.text_fields.refresh_error = RuntimeError("Native field refresh failed")

    with pytest.raises(AdapterError) as caught:
        insert_cross_reference(session, params)

    assert caught.value.code == "CROSS_REFERENCE_INSERT_FAILED"
    assert caught.value.details["restoration_attempted"] is not fail_before_insertion
    assert caught.value.details["destination_restored"] is not fail_before_insertion
    assert caught.value.details["field_present"] is False
    assert session.doc.Text.paragraphs[1].String == "See <policy-link> for constraints."
    assert session.doc.Text.paragraphs[2].String == "Keep the earlier Agent edit"
    assert undo.getCurrentUndoActionTitle() == "Earlier Agent edit"
    assert undo.undo_count == (0 if fail_before_insertion else 1)
    assert undo.context is None


def test_failed_reference_undo_reports_the_remaining_field_and_destination() -> None:
    session, params = reference_session(FakeParagraph(
        "Numbered source.", numbered=True, label="VII",
        rules=FakeNumberingRules(numbering_type=2, next_label="VIII"),
    ))
    session.doc.forced_presentation = ""
    session.doc.undo_manager.undo_error = RuntimeError("Native undo unavailable")

    with pytest.raises(AdapterError) as caught:
        insert_cross_reference(session, params)

    assert caught.value.details["restoration_attempted"] is True
    assert caught.value.details["destination_restored"] is False
    assert caught.value.details["destination_text"] == "See  for constraints."
    assert caught.value.details["field_present"] is True
    assert caught.value.details["remaining_field_presentation"] == ""
    assert caught.value.details["restoration_error"] == "Native undo unavailable"
    assert len(session.doc.inserted_fields) == 1


def test_range_precondition_fails_before_creating_a_bookmark() -> None:
    paragraph = FakeParagraph("A structurally unrelated paragraph.")
    session = fake_session([paragraph])

    with pytest.raises(AdapterError, match="does not match") as caught:
        create_bookmark(
            session,
            {
                "name": "UnrelatedAnchor",
                "paragraph_index": 0,
                "start_offset": 2,
                "end_offset": 14,
                "expected_text": "wrong value!",
            },
        )

    assert caught.value.code == "TEXT_MISMATCH"
    assert not session.doc.bookmarks.values


def test_uno_cursor_mismatch_fails_before_creating_a_bookmark() -> None:
    paragraph = MismatchedParagraph("Unicode-safe selection")
    session = fake_session([paragraph])

    with pytest.raises(AdapterError, match="UNO cursor") as caught:
        create_bookmark(
            session,
            {
                "name": "UnicodeSelection",
                "paragraph_index": 0,
                "start_offset": 0,
                "end_offset": len(paragraph.String),
                "expected_text": paragraph.String,
            },
        )

    assert caught.value.code == "TEXT_RANGE_NOT_FOUND"
    assert not session.doc.bookmarks.values


@pytest.mark.parametrize(
    "action,params",
    [
        (
            "paragraph.apply_numbering",
            {
                "source_index": 2,
                "target_index": 2,
                "level": 0,
                "restart": False,
            },
        ),
        (
            "paragraph.apply_numbering",
            {
                "source_index": 1,
                "target_index": 5,
                "level": 0,
                "restart": False,
                "start_value": 9,
            },
        ),
        (
            "bookmark.create",
            {
                "name": "invalid-name",
                "paragraph_index": 1,
                "start_offset": 0,
                "end_offset": 0,
                "expected_text": "",
            },
        ),
        (
            "cross_reference.insert",
            {
                "bookmark_name": "ValidAnchor",
                "paragraph_index": 3,
                "start_offset": 0,
                "end_offset": 4,
                "expected_text": "five!",
                "display": "number",
            },
        ),
        (
            "text.find",
            {
                "literal": "marker",
                "case_sensitive": False,
                "max_results": 257,
            },
        ),
    ],
)
def test_native_reference_contracts_fail_closed(
    action: str, params: dict[str, Any]
) -> None:
    with pytest.raises(AdapterError):
        validate_action_params(action, params)


class FormattingCursor(FakeCursor):
    def gotoRange(self, offset, expand):
        if not expand:
            self.selection_start = offset
        self.selection_end = offset
        self.position = offset

    def __getattr__(self, name):
        if not name.startswith("Char"):
            raise AttributeError(name)
        values = [
            item[name]
            for item in self.paragraph.formats[
                self.selection_start : self.selection_end
            ]
        ]
        return (
            values[0] if values and all(item == values[0] for item in values) else None
        )

    def __setattr__(self, name, value):
        if name.startswith("Char"):
            for item in self.paragraph.formats[
                self.selection_start : self.selection_end
            ]:
                item[name] = value
        else:
            super().__setattr__(name, value)


class FormattingParagraph(FakeParagraph):
    def __init__(self, text):
        super().__init__(text)
        self.formats = [
            {
                "CharHeight": 18.0,
                "CharHeightAsian": 18.0,
                "CharHeightComplex": 18.0,
                "CharWeight": 100.0,
                "CharPosture": "NONE",
                "CharEscapement": 0,
                "CharEscapementHeight": 100,
            }
            for _ in text
        ]

    def getText(self):
        return SimpleNamespace(
            createTextCursorByRange=lambda _start: FormattingCursor(self)
        )

    def createEnumeration(self):
        boundaries = [0]
        for index in range(1, len(self.String)):
            if self.formats[index] != self.formats[index - 1]:
                boundaries.append(index)
        boundaries.append(len(self.String))
        portions = []
        for start, end in zip(boundaries, boundaries[1:]):
            cursor = FormattingCursor(self)
            cursor.selection_start = start
            cursor.selection_end = end
            cursor.getStart = lambda start=start: start
            portions.append(cursor)
        return FakeEnumeration(portions)


def formatting_session(paragraph):
    session = fake_session([paragraph])
    selected = []
    commands = []
    session.doc.getCurrentController = lambda: SimpleNamespace(
        select=lambda cursor: selected.append(cursor)
    )

    def dispatch(command):
        commands.append(command)
        selected[-1].CharEscapement = -25 if command == ".uno:SubScript" else 33

    session.dispatch = dispatch
    session.commands = commands
    return session


def formatting_params(**fields):
    return {
        "paragraph_index": 0,
        "start_offset": 6,
        "end_offset": 7,
        "expected_text": "X",
        **fields,
    }


@pytest.mark.parametrize("script", ["subscript", "superscript", "normal"])
def test_explicit_character_script_changes_only_the_selected_range(script):
    paragraph = FormattingParagraph("value X and X")
    session = formatting_session(paragraph)
    before = copy.deepcopy(paragraph.formats)
    params = formatting_params(script=script)
    original = copy.deepcopy(params)

    first = set_text_format(session, params)
    second = set_text_format(session, params)

    assert first["format"]["script"] == script
    assert second["format"]["script"] == script
    assert params == original and paragraph.String == "value X and X"
    assert paragraph.formats[:6] == before[:6]
    assert paragraph.formats[7:] == before[7:]
    assert len(session.commands) == (0 if script == "normal" else 1)


def test_explicit_character_format_preserves_text_and_other_ranges(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "uno", SimpleNamespace(Enum=lambda _type, value: value)
    )
    paragraph = FormattingParagraph("value X and X")
    before = copy.deepcopy(paragraph.formats)
    params = formatting_params(font_size=21.5, bold=True, italic=True)

    result = set_text_format(formatting_session(paragraph), params)

    assert result["format"] == {
        "font_size": 21.5,
        "bold": True,
        "italic": True,
        "script": "normal",
    }
    assert paragraph.String == "value X and X"
    assert paragraph.formats[:6] == before[:6] and paragraph.formats[7:] == before[7:]
    assert paragraph.formats[6]["CharHeightAsian"] == 21.5
    assert paragraph.formats[6]["CharHeightComplex"] == 21.5


def test_character_format_rejects_stale_text_before_mutating():
    paragraph = FormattingParagraph("value Y and X")
    before = copy.deepcopy(paragraph.formats)
    with pytest.raises(AdapterError, match="expected_text"):
        set_text_format(formatting_session(paragraph), formatting_params(bold=True))
    assert paragraph.formats == before


@pytest.mark.parametrize("verified", [True, False])
def test_character_format_feedback_keeps_native_range_and_save_evidence(verified):
    result = {
        "paragraph_index": 3,
        "start_offset": 7,
        "end_offset": 12,
        "text": "label",
        "format": {
            "font_size": 23.5,
            "bold": False,
            "italic": True,
            "script": "normal",
        },
        "text_unchanged": True,
        "saved": {
            "path": "/tmp/typography.odt",
            "exists": True,
            "valid": True,
            "size": 2345,
        },
    }
    body = {
        "result": result,
        "verification": {"passed": verified},
        "logs": [{"message": "transport detail"}],
    }
    original = copy.deepcopy(body)

    hint = adapter_context_hint("libreoffice_writer", "text.set_format", body)

    assert hint == {**result, "verification_passed": verified}
    assert compact_context_hint_for_model(hint, remaining_chars=1000) == hint
    assert body == original


def test_character_format_error_explains_both_lengths_without_rewriting():
    params = formatting_params()
    params.update(expected_text="label", start_offset=7, end_offset=11, font_size=23.5)
    original = copy.deepcopy(params)

    with pytest.raises(AdapterError) as caught:
        validate_action_params("text.set_format", params)

    assert {key: caught.value.details[key] for key in ("range_length", "text_length")} == {
        "range_length": 4, "text_length": 5,
    }
    assert "end-exclusive" in str(caught.value)
    assert "text.find" in str(caught.value)
    assert params == original


@pytest.mark.parametrize(
    "fields",
    [
        {"script": "subscript"},
        {"font_size": 16.25},
        {"bold": False, "italic": True},
    ],
)
def test_character_format_schema_uses_one_owner_and_preserves_arguments(fields):
    params = formatting_params(**fields)
    original = copy.deepcopy(params)
    owner = STRICT_ACTION_PARAM_SCHEMAS["text.set_format"]
    assert "text.set_format" in ACTIONS and "text.set_format" in GENERIC_ACTIONS
    assert "text.set_format" not in NO_AUTO_SAVE_ACTIONS
    assert DIRECT_ACTION_SCHEMAS["libreoffice_writer"]["text.set_format"] == owner
    jsonschema.validate(params, owner)
    validate_action_params("text.set_format", params)
    assert params == original


@pytest.mark.parametrize(
    "fields", [{}, {"script": "lower"}, {"bold": 1}, {"font_size": 0}]
)
def test_character_format_rejects_invalid_format_fields(fields):
    params = formatting_params(**fields)
    with pytest.raises(AdapterError):
        validate_action_params("text.set_format", params)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(params, STRICT_ACTION_PARAM_SCHEMAS["text.set_format"])


def test_character_format_is_retrievable_for_generic_subscript_requests():
    matches = search_actions(
        "libreoffice_writer", "subscript character formatting", strict_generic=True
    )
    assert any(item["action"] == "text.set_format" for item in matches)


def test_find_current_format_reports_exact_ranges_without_mutation():
    paragraph = FormattingParagraph("regular token and token")
    for char in paragraph.formats[8:13]:
        char["CharPosture"] = "ITALIC"
        char["CharHeight"] = 16.5
    before = copy.deepcopy(paragraph.formats)
    params = {"format": {"italic": True, "font_size": 16.5}, "max_results": 7}
    original_params = copy.deepcopy(params)
    result = find_text(formatting_session(paragraph), params)

    assert result["returned_count"] == 1 and result["has_more"] is False
    assert result["matches"] == [
        {
            "paragraph_index": 0,
            "start_offset": 8,
            "end_offset": 13,
            "matched_text": "token",
            "format": {
                "italic": True,
                "font_size": 16.5,
                "bold": False,
                "script": "normal",
            },
        }
    ]
    assert paragraph.formats == before and params == original_params
    hint = adapter_context_hint("libreoffice_writer", "text.find", {"result": result})
    assert hint["format"] == params["format"]
    projected = compact_context_hint_for_model(hint, remaining_chars=5000)
    assert projected["matches"] == result["matches"]


def test_literal_and_format_search_require_both_conditions():
    paragraph = FormattingParagraph("token TOKEN token")
    for char in paragraph.formats[6:11]:
        char["CharWeight"] = 150.0
    result = find_text(
        formatting_session(paragraph),
        {
            "literal": "token",
            "case_sensitive": False,
            "format": {"bold": True},
            "max_results": 4,
        },
    )
    assert result["returned_count"] == 1
    assert result["matches"][0]["matched_text"] == "TOKEN"
    assert result["matches"][0]["start_offset"] == 6
    assert result["matches"][0]["format"]["bold"] is True


def test_format_search_result_limit_and_unknown_values_are_truthful():
    first = FormattingParagraph("first")
    unknown = FormattingParagraph("unknown")
    for char in unknown.formats:
        char["CharWeight"] = None
    last = FormattingParagraph("last")
    session = fake_session([first, unknown, last])
    result = find_text(session, {"format": {"bold": False}, "max_results": 1})
    assert result["returned_count"] == 1 and result["has_more"] is True
    complete = find_text(session, {"format": {"bold": False}, "max_results": 5})
    assert [item["paragraph_index"] for item in complete["matches"]] == [0, 2]
    assert complete["has_more"] is False


def test_model_selected_format_search_can_be_composed_with_explicit_setter():
    paragraph = FormattingParagraph("value X and X")
    for char in paragraph.formats[6:7]:
        char["CharPosture"] = "ITALIC"
    session = formatting_session(paragraph)
    before = copy.deepcopy(paragraph.formats)
    initial = find_text(session, {"format": {"italic": True}, "max_results": 3})
    match = initial["matches"][0]
    set_text_format(
        session,
        {
            "paragraph_index": match["paragraph_index"],
            "start_offset": match["start_offset"],
            "end_offset": match["end_offset"],
            "expected_text": match["matched_text"],
            "font_size": 23.5,
        },
    )
    read_back = find_text(session, {"format": {"italic": True}, "max_results": 3})
    assert read_back["matches"][0]["format"]["font_size"] == 23.5
    assert paragraph.formats[:6] == before[:6] and paragraph.formats[7:] == before[7:]
    assert paragraph.String == "value X and X" and session.commands == []


@pytest.mark.parametrize(
    "params",
    [
        {"format": {"italic": True}, "max_results": 9},
        {"format": {"bold": False, "script": "normal"}, "max_results": 4},
        {
            "format": {"font_size": 16.5},
            "literal": "anchor",
            "case_sensitive": True,
            "max_results": 3,
        },
    ],
)
def test_format_search_schema_and_adapter_contract_agree(params):
    original = copy.deepcopy(params)
    owner = STRICT_ACTION_PARAM_SCHEMAS["text.find"]
    assert DIRECT_ACTION_SCHEMAS["libreoffice_writer"]["text.find"] == owner
    jsonschema.validate(params, owner)
    validate_action_params("text.find", params)
    assert params == original


@pytest.mark.parametrize(
    "params",
    [
        {"max_results": 3},
        {"format": {}, "max_results": 3},
        {"format": {"italic": "true"}, "max_results": 3},
        {"format": {"replacement_size": 20}, "max_results": 3},
        {"format": {"italic": True}, "literal": "word", "max_results": 3},
    ],
)
def test_incomplete_format_search_returns_a_schema_error(params):
    with pytest.raises(AdapterError):
        validate_action_params("text.find", params)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(params, STRICT_ACTION_PARAM_SCHEMAS["text.find"])


def test_format_search_and_setter_are_both_retrievable():
    matches = search_actions(
        "libreoffice_writer", "italicized words current font size", strict_generic=True
    )
    assert {"text.find", "text.set_format"} <= {item["action"] for item in matches}


def test_format_summary_counts_observed_groups_only_within_returned_matches():
    paragraphs = [FormattingParagraph(word) for word in ("first", "second", "third")]
    for index, paragraph in enumerate(paragraphs):
        for char in paragraph.formats:
            char["CharPosture"] = "ITALIC"
            char["CharHeight"] = 23.5 if index == 1 else 18.0
    session = fake_session(paragraphs)
    complete = find_text(session, {"format": {"italic": True}, "max_results": 4})
    assert {
        row["format"]["font_size"]: row["match_count"]
        for row in complete["format_counts"]
    } == {18.0: 2, 23.5: 1}
    limited = find_text(session, {"format": {"italic": True}, "max_results": 2})
    assert (
        limited["has_more"] is True
        and limited["format_counts_scope"] == "returned_matches"
    )
    assert sum(row["match_count"] for row in limited["format_counts"]) == 2
    hint = adapter_context_hint("libreoffice_writer", "text.find", {"result": complete})
    projected = compact_context_hint_for_model(hint, remaining_chars=5000)
    assert projected["format_counts"] == complete["format_counts"]
    assert projected["matches"] == complete["matches"]
