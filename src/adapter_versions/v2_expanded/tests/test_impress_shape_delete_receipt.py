from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from impress_adapter import uno_worker


class NativeShape:
    def __init__(self, name, text="", kind="TextShape"):
        self.name, self.text, self.kind = name, text, kind
        self.disposed = False

    @property
    def Name(self):
        assert not self.disposed
        return self.name

    @property
    def ShapeType(self):
        assert not self.disposed
        return f"com.sun.star.drawing.{self.kind}"

    def getText(self):
        assert not self.disposed
        return SimpleNamespace(getString=lambda: self.text)

    @property
    def Position(self):
        raise AssertionError("a deletion receipt does not need geometry or full metadata")


class NativeContainer:
    def __init__(self, shapes):
        self.shapes = list(shapes)

    def getCount(self):
        return len(self.shapes)

    def getByIndex(self, index):
        return self.shapes[index]

    def remove(self, shape):
        self.shapes.remove(shape)
        shape.disposed = True


def _session(pages):
    session = uno_worker.ImpressSession.__new__(uno_worker.ImpressSession)
    session.doc = SimpleNamespace(getDrawPages=lambda: NativeContainer(pages))
    return session


@pytest.mark.parametrize(
    "selector",
    [
        {"index": 1},
        {"path": [1]},
        {"name": "Middle"},
        {"path": [1], "name": "Middle", "text": "Observed label", "kind": "TextShape"},
    ],
)
def test_delete_receipt_captures_actual_object_before_disposal(selector):
    first = NativeShape("First")
    middle = NativeShape("Middle", "Observed label")
    last = NativeShape("Last")
    page = NativeContainer([first, middle, last])
    untouched = NativeContainer([NativeShape("Elsewhere")])
    params = {"slide": 1, "selector": selector}
    original = deepcopy(params)

    result = uno_worker._delete_shape(_session([untouched, page]), params)

    assert result["deleted_shape"] == {
        "index": 1, "path": [1], "name": "Middle", "text": "Observed label",
        "kind": "com.sun.star.drawing.TextShape",
    }
    assert result["slide"] == 1
    assert result["display_slide_number"] == 2
    assert result["requested_selector"] == original["selector"]
    assert result["count"] == 2
    assert "indices and paths may have shifted" in result["guidance"]
    assert page.shapes == [first, last]
    assert untouched.getCount() == 1
    assert middle.disposed
    assert params == original


def test_reusing_an_index_reports_each_actual_deleted_object_without_retargeting():
    page = NativeContainer([
        NativeShape("Alpha", "First label"),
        NativeShape("Beta", "Second label"),
        NativeShape("Gamma", "Third label"),
    ])
    session = _session([page])
    params = {"slide": 0, "selector": {"index": 1}}

    first = uno_worker._delete_shape(session, params)
    second = uno_worker._delete_shape(session, params)

    assert first["deleted_shape"]["name"] == "Beta"
    assert first["deleted_shape"]["text"] == "Second label"
    assert second["deleted_shape"]["name"] == "Gamma"
    assert second["deleted_shape"]["text"] == "Third label"
    assert first["deleted_shape"]["path"] == second["deleted_shape"]["path"] == [1]
    assert (first["count"], second["count"]) == (2, 1)
    assert first["requested_selector"] == second["requested_selector"] == {"index": 1}
    assert page.getByIndex(0).Name == "Alpha"


def test_deleting_a_group_reports_its_identity_without_descendant_metadata():
    class NativeGroup(NativeShape, NativeContainer):
        def __init__(self):
            NativeShape.__init__(self, "Observed group", kind="GroupShape")
            NativeContainer.__init__(self, [NativeShape("Child", "Nested content")])

    group = NativeGroup()
    page = NativeContainer([group])

    result = uno_worker._delete_shape(
        _session([page]), {"slide": 0, "selector": {"name": "Observed group"}}
    )

    assert result["deleted_shape"] == {
        "index": 0, "path": [0], "name": "Observed group", "text": "",
        "kind": "com.sun.star.drawing.GroupShape",
    }
    assert result["count"] == 0
