from copy import deepcopy
from types import SimpleNamespace

import pytest

from writer_adapter import uno_worker
from writer_adapter.errors import AdapterError


ACTION = "table.convert_text"


class Enumeration:
    def __init__(self, elements):
        self.elements = list(elements)
        self.index = 0

    def hasMoreElements(self):
        return self.index < len(self.elements)

    def nextElement(self):
        item = self.elements[self.index]
        self.index += 1
        return item


class Paragraph:
    def __init__(self, text):
        self._text = text
        self.ParaStyleName = "Existing source style"

    @property
    def String(self):
        return self._text

    @String.setter
    def String(self, value):
        pytest.fail("conversion must not retype or clear the source")

    def supportsService(self, service):
        return service == "com.sun.star.text.Paragraph"

    def getStart(self):
        return self

    def getEnd(self):
        return self


class Table:
    def __init__(self, name, rows):
        self.Name = name
        self.values = rows
        self.Rows = SimpleNamespace(Count=len(rows))
        self.Columns = SimpleNamespace(Count=len(rows[0]))

    def supportsService(self, service):
        return service == "com.sun.star.text.TextTable"

    def getCellByPosition(self, column, row):
        return SimpleNamespace(String=self.values[row][column])


class Selection:
    def __init__(self, start):
        self.start = start
        self.end = start

    def gotoRange(self, end, expand):
        assert expand is True
        self.end = end


class Session:
    def __init__(self, source_rows, delimiter):
        self.source_rows = deepcopy(source_rows)
        self.source = [Paragraph(delimiter.join(row)) for row in source_rows]
        self.header = Paragraph("Outside heading")
        self.footer = Paragraph("Outside ending")
        self.existing_table = Table("Existing table", [["Keep exact\u00a0text"]])
        self.body = SimpleNamespace(
            elements=[self.existing_table, self.header, *self.source, self.footer],
            createTextCursorByRange=Selection,
        )
        self.body.createEnumeration = lambda: Enumeration(self.body.elements)
        self.selection = None
        self.calls = []
        self.mode = "convert"
        self.added_end_paragraphs = []
        self.controller = SimpleNamespace(select=self.select)
        self.doc = SimpleNamespace(
            Text=self.body,
            getCurrentController=lambda: self.controller,
            getTextTables=self.table_collection,
        )

    def select(self, selection):
        self.selection = selection
        return True

    def table_collection(self):
        tables = {item.Name: item for item in self.body.elements if isinstance(item, Table)}
        return SimpleNamespace(getElementNames=lambda: list(tables), getByName=tables.get)

    def dispatch(self, command, arguments):
        self.calls.append((command, arguments))
        assert [paragraph.String for paragraph in self.source] == [
            arguments[0].Value.join(row) for row in self.source_rows
        ]
        if self.mode == "no_op":
            return
        rows = deepcopy(self.source_rows)
        if self.mode == "normalize_spaces":
            rows[0][0] = rows[0][0].replace("\u00a0", " ")
        table = Table("Native generated table", rows)
        if self.mode == "append_only":
            self.body.elements.append(table)
            return
        start = self.body.elements.index(self.selection.start)
        end = self.body.elements.index(self.selection.end)
        self.body.elements[start:end + 1] = [table]
        self.body.elements.extend(Paragraph(text) for text in self.added_end_paragraphs)


@pytest.fixture(autouse=True)
def property_values(monkeypatch):
    monkeypatch.setattr(
        uno_worker, "_property", lambda name, value: SimpleNamespace(Name=name, Value=value)
    )


@pytest.mark.parametrize("delimiter", [",", "|", ";", "\t"])
def test_conversion_selects_exact_native_span_and_preserves_source_characters(delimiter):
    rows = [["A\u00a0  B", "雪🙂", ""], ["  Keep  spacing ", "MixedCase", "tail"]]
    session = Session(rows, delimiter)
    params = {"start_index": 1, "end_index": 2, "delimiter": delimiter}
    original = deepcopy(params)
    source_texts = [paragraph.String for paragraph in session.source]

    result = uno_worker.GENERIC_ACTIONS[ACTION](session, params)

    assert params == original
    assert len(session.calls) == 1
    command, arguments = session.calls[0]
    assert command == ".uno:ConvertTextToTable"
    assert [(arg.Name, arg.Value) for arg in arguments] == [("Delimiter", delimiter)]
    assert session.selection.start is session.source[0]
    assert session.selection.end is session.source[1]
    assert session.body.elements[0] is session.existing_table
    assert session.existing_table.values == [["Keep exact\u00a0text"]]
    assert [p.String for p in uno_worker._paragraphs(session.body)] == [
        "Outside heading", "Outside ending",
    ]
    assert session.header.ParaStyleName == session.footer.ParaStyleName == "Existing source style"
    assert result == {
        "name": "Native generated table", "start_index": 1, "end_index": 2,
        "delimiter": delimiter, "rows": 2, "columns": 3,
        "source_text_char_count": sum(map(len, source_texts)), "text_preserved": True,
    }


def test_conversion_rejects_nonrectangular_source_before_selection_or_dispatch():
    session = Session([["a", "b"], ["c"]], "|")

    with pytest.raises(AdapterError, match="different cell counts") as caught:
        uno_worker.GENERIC_ACTIONS[ACTION](
            session, {"start_index": 1, "end_index": 2, "delimiter": "|"}
        )

    assert caught.value.details["column_counts"] == [2, 1]
    assert session.selection is None
    assert session.calls == []


def test_conversion_resolves_entire_paragraph_range_before_native_selection():
    session = Session([["a", "b"], ["c", "d"]], ",")

    with pytest.raises(AdapterError) as caught:
        uno_worker.GENERIC_ACTIONS[ACTION](
            session, {"start_index": 1, "end_index": 90, "delimiter": ","}
        )

    assert caught.value.code == "PARAGRAPH_NOT_FOUND"
    assert session.selection is None
    assert session.calls == []


def test_raw_paragraph_range_must_not_enclose_an_existing_table():
    session = Session([["a", "b"], ["c", "d"]], ",")
    session.body.elements.insert(3, Table("Interleaved table", [["Untouched"]]))

    with pytest.raises(AdapterError, match="contains a table"):
        uno_worker.GENERIC_ACTIONS[ACTION](
            session, {"start_index": 1, "end_index": 2, "delimiter": ","}
        )

    assert session.selection is None
    assert session.calls == []


@pytest.mark.parametrize("mode", ["no_op", "normalize_spaces", "append_only"])
def test_conversion_does_not_claim_success_without_exact_in_place_native_readback(mode):
    session = Session([["a\u00a0b", "c"], ["d", "e"]], ";")
    session.mode = mode

    with pytest.raises(AdapterError) as caught:
        uno_worker.GENERIC_ACTIONS[ACTION](
            session, {"start_index": 1, "end_index": 2, "delimiter": ";"}
        )

    assert caught.value.code == "VERIFICATION_FAILED"
    assert len(session.calls) == 1
    if mode == "normalize_spaces":
        assert caught.value.details["cell_text_matches"] is False
    elif mode == "append_only":
        assert caught.value.details["outside_text_unchanged"] is False


@pytest.mark.parametrize("whole_body", [False, True])
def test_conversion_at_body_end_accepts_one_native_empty_paragraph(whole_body):
    session = Session([["a\u00a0b", "🙂"], ["", "  雪"]], "|")
    session.body.elements.remove(session.footer)
    if whole_body:
        session.body.elements = list(session.source)
    session.added_end_paragraphs = [""]
    start = 0 if whole_body else 1

    result = uno_worker.GENERIC_ACTIONS[ACTION](
        session, {"start_index": start, "end_index": start + 1, "delimiter": "|"}
    )

    assert result["text_preserved"] is True
    assert [p.String for p in uno_worker._paragraphs(session.body)] == (
        [""] if whole_body else ["Outside heading", ""]
    )
    assert isinstance(session.body.elements[-2], Table)
    assert session.body.elements[-2].Name == result["name"]


def test_conversion_before_outside_text_does_not_allow_an_added_empty_paragraph():
    session = Session([["a", "b"], ["c", "d"]], "|")
    session.added_end_paragraphs = [""]

    with pytest.raises(AdapterError) as caught:
        uno_worker.GENERIC_ACTIONS[ACTION](
            session, {"start_index": 1, "end_index": 2, "delimiter": "|"}
        )

    assert caught.value.details["outside_text_unchanged"] is False


def test_last_raw_paragraph_before_existing_table_is_not_the_body_end():
    session = Session([["a", "b"], ["c", "d"]], "|")
    session.body.elements.remove(session.footer)
    session.body.elements.append(Table("Existing terminal table", [["Untouched"]]))
    session.added_end_paragraphs = [""]

    with pytest.raises(AdapterError) as caught:
        uno_worker.GENERIC_ACTIONS[ACTION](
            session, {"start_index": 1, "end_index": 2, "delimiter": "|"}
        )

    assert caught.value.details["outside_text_unchanged"] is False


def test_conversion_at_body_end_does_not_allow_two_extra_empty_paragraphs():
    session = Session([["a", "b"], ["c", "d"]], "|")
    session.body.elements.remove(session.footer)
    session.added_end_paragraphs = ["", ""]

    with pytest.raises(AdapterError) as caught:
        uno_worker.GENERIC_ACTIONS[ACTION](
            session, {"start_index": 1, "end_index": 2, "delimiter": "|"}
        )

    assert caught.value.details["outside_text_unchanged"] is False
