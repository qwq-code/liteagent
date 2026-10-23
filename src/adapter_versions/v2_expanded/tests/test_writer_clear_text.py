from copy import deepcopy
from types import SimpleNamespace

import jsonschema
import pytest

from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools, public_actions
from writer_adapter import uno_worker
from writer_adapter.errors import AdapterError
from writer_adapter.schema import ACTIONS, validate_action_params
from writer_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


ACTION = "paragraph.clear_text"


class Cursor:
    def __init__(self, paragraph):
        self.paragraph = paragraph

    def gotoRange(self, end, expand):
        assert end is self.paragraph
        assert expand is True

    @property
    def String(self):
        return self.paragraph.String

    @String.setter
    def String(self, value):
        if not self.paragraph.ignore_write:
            self.paragraph.String = value


class Paragraph:
    def __init__(self, body, text):
        self.body = body
        self.String = text
        self.ignore_write = False
        self.ParaStyleName = "Body"
        self.ParaAdjust = 2
        self.ParaLineSpacing = SimpleNamespace(Mode=0, Height=150)

    def getText(self):
        return self.body

    def getStart(self):
        return self

    def getEnd(self):
        return self


@pytest.fixture
def session(monkeypatch):
    body = SimpleNamespace(createTextCursorByRange=Cursor)
    body.paragraphs = [
        Paragraph(body, text)
        for text in ("Keep heading", "Remove note", "", "Keep body", "Remove footer")
    ]
    monkeypatch.setattr(uno_worker, "_paragraphs", lambda text: list(text.paragraphs))
    return SimpleNamespace(doc=SimpleNamespace(Text=body))


@pytest.mark.parametrize("forwarded", [False, True])
def test_clear_text_is_public_with_one_required_explicit_selector(forwarded):
    if forwarded:
        tool = constrain_adapter_call_routes(
            build_tools("multi_apps", ["adapter.call"], include_gui=False),
            [("libreoffice_writer", ACTION)],
        )[0]
        schema = tool["function"]["parameters"]["oneOf"][0]["properties"]["payload"][
            "properties"
        ]["params"]
    else:
        schema = build_tools(
            "libreoffice_writer", [ACTION], include_gui=False,
            include_control_tools=False,
        )[0]["function"]["parameters"]
    assert schema["properties"] == STRICT_ACTION_PARAM_SCHEMAS[ACTION]["properties"]
    assert schema["required"] == ["indices"]
    params = {"indices": [4, 1, 2]}
    original = deepcopy(params)
    jsonschema.validate(params, schema)
    validate_action_params(ACTION, params)
    assert params == original
    assert ACTION in ACTIONS & uno_worker.GENERIC_ACTIONS.keys()
    assert ACTION in public_actions("libreoffice_writer")


@pytest.mark.parametrize(
    "params",
    [{}, {"indices": []}, {"indices": [1, 1]}, {"indices": [-1]},
     {"indices": [True]}, {"nonempty_ordinals": [1]}],
)
def test_clear_text_never_defaults_or_reinterprets_an_invalid_selector(params):
    original = deepcopy(params)
    with pytest.raises(AdapterError, match="indices"):
        validate_action_params(ACTION, params)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(params, STRICT_ACTION_PARAM_SCHEMAS[ACTION])
    assert params == original


def test_clear_text_preserves_unselected_text_boundaries_and_paragraph_format(session):
    paragraphs = list(session.doc.Text.paragraphs)
    before_format = [
        (p.ParaStyleName, p.ParaAdjust, p.ParaLineSpacing.Mode, p.ParaLineSpacing.Height)
        for p in paragraphs
    ]
    params = {"indices": [4, 1, 2]}
    original = deepcopy(params)

    result = uno_worker.GENERIC_ACTIONS[ACTION](session, params)

    assert params == original
    assert session.doc.Text.paragraphs == paragraphs
    assert [p.String for p in paragraphs] == ["Keep heading", "", "", "Keep body", ""]
    assert [
        (p.ParaStyleName, p.ParaAdjust, p.ParaLineSpacing.Mode, p.ParaLineSpacing.Height)
        for p in paragraphs
    ] == before_format
    assert result == {
        "indices": [4, 1, 2],
        "paragraph_count_before": 5,
        "paragraph_count_after": 5,
        "paragraph_details": [
            {"index": index, "text_length": 0} for index in (4, 1, 2)
        ],
    }


def test_clear_text_resolves_all_indices_before_mutating_any_paragraph(session):
    before = [p.String for p in session.doc.Text.paragraphs]

    with pytest.raises(AdapterError) as caught:
        uno_worker.GENERIC_ACTIONS[ACTION](session, {"indices": [1, 90]})

    assert caught.value.code == "PARAGRAPH_NOT_FOUND"
    assert [p.String for p in session.doc.Text.paragraphs] == before


def test_clear_text_reports_a_native_write_that_did_not_clear_the_text(session):
    session.doc.Text.paragraphs[1].ignore_write = True

    with pytest.raises(AdapterError) as caught:
        uno_worker.GENERIC_ACTIONS[ACTION](session, {"indices": [1]})

    assert caught.value.code == "VERIFICATION_FAILED"
    assert caught.value.details["paragraph_count_after"] == 5
    assert caught.value.details["paragraph_details"] == [
        {"index": 1, "text_length": len("Remove note")}
    ]
