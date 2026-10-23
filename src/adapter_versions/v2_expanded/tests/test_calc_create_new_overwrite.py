from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from calc_adapter import uno_worker
from calc_adapter.errors import AdapterError


@pytest.fixture
def replacement(monkeypatch, tmp_path):
    output_path = tmp_path / "output.ods"
    with zipfile.ZipFile(output_path, "w") as package:
        package.writestr("content.xml", "original workbook")
    original_bytes = output_path.read_bytes()
    case = SimpleNamespace(
        output_path=output_path, original_bytes=original_bytes,
        events=[], cells={}, stage_failure=False, commit_failure=False,
    )

    def document(url, name):
        doc = SimpleNamespace(
            URL=url, closed=False,
            supportsService=lambda service: service == "com.sun.star.sheet.SpreadsheetDocument",
        )

        def close(_deliver_ownership):
            case.events.append(f"close_{name}")
            doc.closed = True

        doc.close = close
        return doc

    case.target = document(output_path.as_uri(), "target")
    case.unrelated = document((tmp_path / "elsewhere" / "output.ods").as_uri(), "unrelated")
    case.created = document("", "created")
    case.reopened = document(output_path.as_uri(), "reopened")

    def cell(column, row):
        return SimpleNamespace(
            setString=lambda value: case.cells.__setitem__((column, row), value),
            setValue=lambda value: case.cells.__setitem__((column, row), value),
        )

    sheet = SimpleNamespace(getName=lambda: "Data", getCellByPosition=cell)
    sheets = SimpleNamespace(
        getByIndex=lambda index: sheet, getElementNames=lambda: ("Data",),
    )
    case.created.getSheets = lambda: sheets
    case.created.calculateAll = lambda: None

    def store(url, properties):
        path = uno_worker._url_path(url)
        assert dict(properties) == {"FilterName": "calc8", "Overwrite": True}
        if url == output_path.as_uri():
            assert case.target.closed, "the destination is still held by its open workbook"
            case.events.append("commit")
            if case.commit_failure:
                path.write_bytes(b"interrupted replacement")
                raise RuntimeError("synthetic commit failure")
        else:
            case.events.append("stage")
            if case.stage_failure:
                path.write_bytes(b"invalid staged package")
                return
        with zipfile.ZipFile(path, "w") as package:
            package.writestr("content.xml", "replacement workbook")
        case.created.URL = url

    case.created.storeAsURL = store

    def load(url, _target, _flags, _properties):
        if url == "private:factory/scalc":
            return case.created
        assert url == output_path.as_uri()
        assert output_path.read_bytes() == original_bytes
        case.events.append("reopen")
        return case.reopened

    def enumeration():
        remaining = [case.unrelated, case.target]
        return SimpleNamespace(
            hasMoreElements=lambda: bool(remaining), nextElement=lambda: remaining.pop(0),
        )

    case.session = object.__new__(uno_worker.CalcSession)
    case.session.doc = None
    case.session.desktop = SimpleNamespace(
        loadComponentFromURL=load,
        getComponents=lambda: SimpleNamespace(createEnumeration=enumeration),
    )
    case.params = {
        "output_path": str(output_path), "overwrite": True,
        "sheet_name": "Data", "headers": ["Label", "Count"], "rows": [["sample", 7]],
    }
    monkeypatch.setattr(uno_worker, "_file_url", lambda path: Path(path).resolve().as_uri())
    monkeypatch.setattr(uno_worker, "_property", lambda name, value: (name, value))
    return case


@pytest.mark.parametrize("selected", [None, "unrelated"])
def test_create_new_replaces_only_open_destination_after_staging(replacement, selected):
    case = replacement
    case.session.doc = getattr(case, selected) if selected else None
    original_params = deepcopy(case.params)

    result = uno_worker._create_new(case.session, case.params)

    assert result["saved"] is True
    assert result["row_count"] == 1
    assert case.session.doc is case.created
    assert case.events.index("stage") < case.events.index("close_target")
    assert case.events.index("close_target") < case.events.index("commit")
    assert case.events.count("close_target") == 1
    assert case.unrelated.closed is False
    assert case.created.closed is False
    assert case.cells == {(0, 0): "Label", (1, 0): "Count", (0, 1): "sample", (1, 1): 7}
    with zipfile.ZipFile(case.output_path) as package:
        assert package.read("content.xml") == b"replacement workbook"
    assert case.params == original_params
    assert list(case.output_path.parent.iterdir()) == [case.output_path]


@pytest.mark.parametrize("failure", ["stage", "commit"])
def test_create_new_failure_preserves_original_file_and_unrelated_document(
    replacement, failure,
):
    case = replacement
    setattr(case, f"{failure}_failure", True)
    original_params = deepcopy(case.params)

    with pytest.raises(AdapterError) as raised:
        uno_worker._create_new(case.session, case.params)

    assert raised.value.code == "DOCUMENT_CREATE_FAILED"
    assert case.output_path.read_bytes() == case.original_bytes
    assert case.unrelated.closed is False
    assert case.created.closed is True
    assert case.params == original_params
    if failure == "stage":
        assert case.target.closed is False
        assert "commit" not in case.events
        assert case.session.doc is None
    else:
        assert case.target.closed is True
        assert case.events.index("close_created") < case.events.index("reopen")
        assert case.session.doc is case.reopened
    assert list(case.output_path.parent.iterdir()) == [case.output_path]
