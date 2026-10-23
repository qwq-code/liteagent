from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_context_hint_for_model,
)
from writer_adapter import uno_worker


def native_paragraph(value, state="DIRECT_VALUE", *, ignore_writes=False):
    class Cursor:
        CharStrikeout = value

        def getPropertyState(self, name):
            assert name == "CharStrikeout"
            if state is None:
                raise AttributeError(name)
            return SimpleNamespace(value=state)

        def gotoRange(self, end, expand):
            assert end == "end" and expand is True

        def __setattr__(self, name, value):
            if not (ignore_writes and name == "CharStrikeout"):
                super().__setattr__(name, value)

    cursor = Cursor()
    text = SimpleNamespace(createTextCursorByRange=lambda _start: cursor)
    paragraph = SimpleNamespace(
        String="Observed sample paragraph.",
        ParaTabStops=(),
        ParaAdjust=0,
        ParaLineSpacing=SimpleNamespace(Mode=0, Height=100),
        CharHeight=12,
        getText=lambda: text,
        getStart=lambda: "start",
        getEnd=lambda: "end",
    )
    return paragraph, cursor


@pytest.mark.parametrize(
    ("value", "state", "observed"),
    [
        (0, "DIRECT_VALUE", False),
        (1, "DIRECT_VALUE", True),
        (2, "DEFAULT_VALUE", True),
        (0, "AMBIGUOUS_VALUE", "mixed"),
        (3, "DIRECT_VALUE", None),
        (None, "DIRECT_VALUE", None),
        (1, None, None),
    ],
)
def test_paragraph_observes_native_whole_range_strikethrough(value, state, observed):
    paragraph, cursor = native_paragraph(value, state)

    detail = uno_worker._paragraph_detail(paragraph, 2, 1)

    assert detail["strikethrough"] == observed
    assert detail["index"] == 2
    assert paragraph.String == "Observed sample paragraph."
    assert cursor.CharStrikeout == value


@pytest.mark.parametrize("ignore_writes", [False, True])
def test_format_receipt_observes_state_instead_of_echoing_request(monkeypatch, ignore_writes):
    paragraph, _cursor = native_paragraph(0, ignore_writes=ignore_writes)
    monkeypatch.setattr(uno_worker, "_paragraphs", lambda _text: [paragraph])
    session = SimpleNamespace(doc=SimpleNamespace(Text=object()))
    params = {"indices": [0], "strikethrough": True}
    original = deepcopy(params)

    result = uno_worker._set_paragraph_format(session, params)

    assert result["formats"]["strikethrough"] is True
    assert result["paragraph_details"][0]["strikethrough"] is (not ignore_writes)
    assert params == original
    assert paragraph.String == "Observed sample paragraph."


@pytest.mark.parametrize("action", ["document.inspect", "paragraph.set_format"])
@pytest.mark.parametrize("forwarded", [False, True])
def test_native_strikethrough_reaches_model_in_both_existing_responses(action, forwarded):
    paragraphs = [native_paragraph(value, state)[0] for value, state in (
        (0, "DIRECT_VALUE"), (1, "DIRECT_VALUE"), (0, "AMBIGUOUS_VALUE"),
    )]
    result = {
        "paragraphs": [paragraph.String for paragraph in paragraphs],
        "paragraph_details": uno_worker._paragraph_details(paragraphs),
        "paragraph_count": 3,
        "nonempty_paragraph_count": 3,
    }
    original = deepcopy(result)
    body = {"status": "ok", "result": result}
    if forwarded:
        body = {"status": "ok", "result": {
            "adapter": "libreoffice_writer", "action": action, "response": body,
        }}
    hint = adapter_context_hint(
        "multi_apps" if forwarded else "libreoffice_writer",
        "adapter.call" if forwarded else action,
        body,
    )
    projected = compact_context_hint_for_model(hint, remaining_chars=5000)
    context = projected["downstream_context"] if forwarded else projected
    details = context.get("paragraph_details", context.get("formatted_paragraphs"))

    assert [detail["strikethrough"] for detail in details] == [False, True, "mixed"]
    assert result == original
