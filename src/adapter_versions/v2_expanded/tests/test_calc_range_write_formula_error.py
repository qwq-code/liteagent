from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
from typing import Any

import pytest

from calc_adapter import uno_worker
from calc_adapter.errors import AdapterError, error_payload
from integrations.lite_agent.context_projection import sanitize


class _Cell:
    def __init__(
        self,
        *,
        kind: str = "blank",
        value: Any = None,
        formula: str = "",
        number_format: int = 0,
    ) -> None:
        self._kind = kind
        self._value = float(value) if kind == "number" else 0.0
        self._formula = formula
        self._string = str(value) if kind == "string" else ""
        self._error = 0
        self.NumberFormat = number_format
        self.CellBackColor = 0xFFFFFF
        self.CharColor = 0
        self.CharWeight = 100.0
        self.HoriJustify = 0
        self.VertJustify = 0

    def getFormula(self) -> str:
        if self._kind == "formula":
            return self._formula
        if self._kind == "string":
            return self._string
        return ""

    def getType(self) -> str:
        return {
            "blank": "EMPTY",
            "string": "TEXT",
            "number": "VALUE",
            "formula": "FORMULA",
        }[self._kind]

    def getValue(self) -> float:
        return self._value

    def getString(self) -> str:
        if self._error:
            return f"Err:{self._error}"
        if self._kind == "string":
            return self._string
        if self._kind == "number":
            return str(self._value)
        if self._kind == "formula":
            return "calculated"
        return ""

    def getError(self) -> int:
        return self._error

    def setString(self, value: str) -> None:
        self._kind = "blank" if value == "" else "string"
        self._string = value
        self._formula = ""
        self._value = 0.0
        self._error = 0

    def setValue(self, value: float) -> None:
        self._kind = "number"
        self._value = float(value)
        self._formula = ""
        self._string = ""
        self._error = 0

    def setFormula(self, value: str) -> None:
        self._kind = "formula"
        self._formula = value
        self._string = ""
        self._value = 0.0
        self._error = 0


class _NumberFormatRestoreFailureCell(_Cell):
    @property
    def NumberFormat(self) -> int:
        return self._number_format

    @NumberFormat.setter
    def NumberFormat(self, value: int) -> None:
        if getattr(self, "_number_format", None) == 91 and value == 12:
            raise RuntimeError("synthetic number-format restoration failure")
        self._number_format = value


class _Range:
    def __init__(
        self,
        cells: list[list[_Cell]],
        *,
        start_column: int = 0,
        start_row: int = 0,
    ) -> None:
        self.cells = cells
        self._start_column = start_column
        self._start_row = start_row

    def getRangeAddress(self) -> SimpleNamespace:
        return SimpleNamespace(
            StartColumn=self._start_column,
            StartRow=self._start_row,
            EndColumn=self._start_column + len(self.cells[0]) - 1,
            EndRow=self._start_row + len(self.cells) - 1,
        )

    def getCellByPosition(self, column: int, row: int) -> _Cell:
        return self.cells[row][column]


class _NumberFormats:
    def getByKey(self, key: int) -> SimpleNamespace:
        return SimpleNamespace(
            FormatString=f"format-{key}",
            Locale=SimpleNamespace(Language="en", Country="US"),
        )


class _Doc:
    def __init__(self, target: _Range, errors: dict[str, int] | None = None) -> None:
        self.target = target
        self.errors = errors or {}
        self.calculate_calls = 0

    def calculateAll(self) -> None:
        self.calculate_calls += 1
        for row in self.target.cells:
            for cell in row:
                cell._error = self.errors.get(cell.getFormula(), 0)

    def getNumberFormats(self) -> _NumberFormats:
        return _NumberFormats()


def _session(
    cells: list[list[_Cell]],
    *,
    errors: dict[str, int] | None = None,
    start_column: int = 0,
    start_row: int = 0,
) -> tuple[SimpleNamespace, _Range, _Doc]:
    target = _Range(cells, start_column=start_column, start_row=start_row)
    doc = _Doc(target, errors)
    session = SimpleNamespace(
        doc=doc,
        sheet=lambda name: SimpleNamespace(getCellRangeByName=lambda value: target),
    )
    return session, target, doc


def test_formula_error_restores_mixed_target_atomically_and_preserves_args() -> None:
    cells = [
        [
            _Cell(kind="string", value="Err:508", number_format=4),
            _Cell(kind="number", value=17, number_format=7),
            _Cell(kind="formula", formula="=A1+1", number_format=9),
            _Cell(kind="string", value="=keep", number_format=11),
        ]
    ]
    session, target, doc = _session(
        cells,
        errors={'=TEXT(A1,"0.00")': 508},
        start_column=1,
        start_row=2,
    )
    params = {
        "sheet": "Synthetic",
        "range": "B3:E3",
        "values": [
            {"kind": "string", "value": "changed"},
            {"kind": "formula", "value": '=TEXT(A1,"0.00")'},
            {"kind": "number", "value": 99},
            {"kind": "string", "value": "temporary"},
        ],
    }
    original_params = deepcopy(params)

    with pytest.raises(AdapterError) as caught:
        uno_worker._write(session, params)

    assert caught.value.code == "FORMULA_ERROR"
    assert caught.value.http_status == 422
    assert caught.value.details["cells"] == [
        {"cell": "C3", "kind": "formula", "error_code": 508}
    ]
    assert caught.value.details["recovery"] == (
        "retry with a locale-compatible formula or the formatted_text "
        "typed-cell representation"
    )
    assert target.cells[0][0].getString() == "Err:508"
    assert target.cells[0][1].getValue() == 17
    assert target.cells[0][2].getFormula() == "=A1+1"
    assert target.cells[0][3].getType() == "TEXT"
    assert target.cells[0][3].getString() == "=keep"
    assert [cell.NumberFormat for cell in target.cells[0]] == [4, 7, 9, 11]
    assert doc.calculate_calls == 2
    assert params == original_params


def test_formula_error_restores_number_format_applied_by_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cell = _Cell(kind="number", value=3.5, number_format=12)
    session, _, _ = _session([[cell]], errors={"=INVALID()": 519})
    monkeypatch.setattr(
        uno_worker,
        "_apply_number_format",
        lambda _doc, target, _code, _locale=None: setattr(target, "NumberFormat", 91),
    )
    params = {
        "sheet": "Synthetic",
        "range": "A1",
        "values": [
            {"kind": "formula", "value": "=INVALID()", "number_format": "0.000"}
        ],
    }

    with pytest.raises(AdapterError) as caught:
        uno_worker._write(session, params)

    assert caught.value.code == "FORMULA_ERROR"
    assert cell.getType() == "VALUE"
    assert cell.getValue() == 3.5
    assert cell.NumberFormat == 12


def test_formula_batch_error_is_reported_and_restored() -> None:
    cells = [[
        _Cell(kind="number", value=7, number_format=3),
        _Cell(kind="string", value="keep", number_format=4),
    ]]
    base_session, target, doc = _session(
        cells,
        errors={"=BAD()": 508},
        start_column=1,
        start_row=5,
    )
    sheet = SimpleNamespace(
        getCellRangeByName=lambda value: cells[0][0]
        if value == "B6"
        else cells[0][1]
    )
    session = SimpleNamespace(doc=base_session.doc, sheet=lambda _: sheet)
    params = {
        "sheet": "Synthetic",
        "writes": [
            {"cell": "B6", "formula": "=BAD()"},
            {"cell": "C6", "formula": "=1+1"},
        ],
    }
    original_params = deepcopy(params)

    with pytest.raises(AdapterError) as caught:
        uno_worker._set_formulas(session, params)

    error = caught.value
    assert error.code == "FORMULA_ERROR"
    assert error.http_status == 422
    assert error.details["cells"] == [
        {"cell": "B6", "kind": "formula", "error_code": 508}
    ]
    assert "Read back the result" in error.details["recovery"]
    assert target.cells[0][0].getType() == "VALUE"
    assert target.cells[0][0].getValue() == 7
    assert target.cells[0][1].getType() == "TEXT"
    assert target.cells[0][1].getString() == "keep"
    assert [cell.NumberFormat for cell in target.cells[0]] == [3, 4]
    assert doc.calculate_calls == 2
    assert params == original_params


def test_range_write_circular_reference_explains_cause_and_restores_cells() -> None:
    formula = "=C4+Inputs.A1"
    session, target, doc = _session(
        [[_Cell(kind="string", value="keep", number_format=4),
          _Cell(kind="number", value=17, number_format=7)]],
        errors={formula: 522}, start_column=1, start_row=3,
    )
    params = {
        "sheet": "Results", "range": "B4:C4",
        "values": ["temporary", {"kind": "formula", "value": formula}],
    }
    original = deepcopy(params)

    with pytest.raises(AdapterError) as caught:
        uno_worker._write(session, params)

    error = caught.value
    assert error.code == "FORMULA_ERROR"
    assert error.http_status == 422
    assert error.details["cells"] == [
        {"cell": "C4", "kind": "formula", "error_code": 522}
    ]
    recovery = error.details["recovery"].lower()
    assert "circular reference" in recovery
    assert "destination sheet" in recovery
    assert target.cells[0][0].getString() == "keep"
    assert target.cells[0][1].getType() == "VALUE"
    assert target.cells[0][1].getValue() == 17
    assert [cell.NumberFormat for cell in target.cells[0]] == [4, 7]
    assert doc.calculate_calls == 2
    assert params == original


def test_formula_batch_circular_reference_explains_cause_and_restores_cells() -> None:
    formula = "=D7+Inputs.A1"
    cells = [[_Cell(kind="number", value=9, number_format=3),
              _Cell(kind="string", value="keep", number_format=6)]]
    base_session, target, doc = _session(
        cells, errors={formula: 522}, start_column=3, start_row=6,
    )
    sheet = SimpleNamespace(
        getCellRangeByName=lambda reference: cells[0][0]
        if reference == "D7" else cells[0][1]
    )
    session = SimpleNamespace(doc=base_session.doc, sheet=lambda _: sheet)
    params = {
        "sheet": "Results",
        "writes": [
            {"cell": "D7", "formula": formula},
            {"cell": "E7", "formula": "=1+1"},
        ],
    }
    original = deepcopy(params)

    with pytest.raises(AdapterError) as caught:
        uno_worker._set_formulas(session, params)

    error = caught.value
    assert error.code == "FORMULA_ERROR"
    assert error.http_status == 422
    assert error.details["cells"] == [
        {"cell": "D7", "kind": "formula", "error_code": 522}
    ]
    recovery = error.details["recovery"].lower()
    assert "circular reference" in recovery
    assert "destination sheet" in recovery
    assert target.cells[0][0].getType() == "VALUE"
    assert target.cells[0][0].getValue() == 9
    assert target.cells[0][1].getString() == "keep"
    assert [cell.NumberFormat for cell in target.cells[0]] == [3, 6]
    assert doc.calculate_calls == 2
    assert params == original


def test_number_format_restore_failure_is_reported_as_rollback_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cell = _NumberFormatRestoreFailureCell(kind="number", value=3.5, number_format=12)
    session, _, _ = _session([[cell]], errors={"=INVALID()": 519})
    monkeypatch.setattr(
        uno_worker,
        "_apply_number_format",
        lambda _doc, target, _code, _locale=None: setattr(target, "NumberFormat", 91),
    )
    params = {
        "sheet": "Synthetic",
        "range": "A1",
        "values": [
            {"kind": "formula", "value": "=INVALID()", "number_format": "0.000"}
        ],
    }

    with pytest.raises(AdapterError) as caught:
        uno_worker._write(session, params)

    assert caught.value.code == "ROLLBACK_FAILED"
    assert caught.value.http_status == 500
    assert "number-format restoration failure" in caught.value.details["rollback_error"]


def test_literal_error_text_is_not_a_formula_failure() -> None:
    session, _, _ = _session([[_Cell()]])
    params = {
        "sheet": "Synthetic",
        "range": "A1",
        "values": [{"kind": "string", "value": "Err:508"}],
    }

    result = uno_worker._write(session, params)

    assert result["display_text"] == [["Err:508"]]
    assert result["kinds"] == [["string"]]


def test_write_exception_after_partial_mutation_restores_formula_like_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cells = [[_Cell(kind="string", value="first"), _Cell(kind="number", value=2)]]
    session, target, doc = _session(cells)
    params = {
        "sheet": "Synthetic",
        "range": "A1:B1",
        "values": [
            {"kind": "string", "value": "changed"},
            {"kind": "formula", "value": "=A1"},
        ],
    }
    original_set_cell = uno_worker._set_cell
    calls = 0

    def fail_second_write(doc: Any, cell: _Cell, spec: dict[str, Any]) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic write failure")
        original_set_cell(doc, cell, spec)

    monkeypatch.setattr(uno_worker, "_set_cell", fail_second_write)

    with pytest.raises(AdapterError) as caught:
        uno_worker._write(session, params)

    assert caught.value.code == "WRITE_FAILED"
    assert target.cells[0][0].getString() == "first"
    assert target.cells[0][1].getType() == "VALUE"
    assert target.cells[0][1].getValue() == 2
    assert doc.calculate_calls == 1


def test_readback_failure_restores_formula_like_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cell = _Cell(kind="string", value="original", number_format=8)
    session, _, doc = _session([[cell]])
    params = {
        "sheet": "Synthetic",
        "range": "A1",
        "values": [{"kind": "formula", "value": "=6*7"}],
    }
    monkeypatch.setattr(
        uno_worker,
        "_read",
        lambda _session, _params: (_ for _ in ()).throw(
            RuntimeError("synthetic readback failure")
        ),
    )

    with pytest.raises(AdapterError) as caught:
        uno_worker._write(session, params)

    assert caught.value.code == "WRITE_FAILED"
    assert cell.getType() == "TEXT"
    assert cell.getString() == "original"
    assert cell.NumberFormat == 8
    assert doc.calculate_calls == 2


@pytest.mark.parametrize("error_code", [508, 519])
def test_formatted_text_error_is_detected_and_rolled_back(error_code: int) -> None:
    cell = _Cell(kind="string", value="original", number_format=6)
    generated_formula = '="Cost: "&FIXED(A1;2;1)'
    session, _, _ = _session([[cell]], errors={generated_formula: error_code})
    params = {
        "sheet": "Synthetic",
        "range": "A1",
        "values": [
            {
                "kind": "formatted_text",
                "value": {
                    "parts": [
                        {"text": "Cost: "},
                        {"cell": "A1", "decimal_places": 2},
                    ]
                },
            }
        ],
    }

    with pytest.raises(AdapterError) as caught:
        uno_worker._write(session, params)

    assert caught.value.code == "FORMULA_ERROR"
    assert caught.value.details["cells"] == [
        {"cell": "A1", "kind": "formatted_text", "error_code": error_code}
    ]
    recovery = caught.value.details["recovery"]
    assert "referenced cells" in recovery
    assert "omit decimal_places for text" in recovery
    assert "locale-compatible" not in recovery
    projected = sanitize({"error": error_payload(caught.value)})
    assert projected["error"]["details"]["recovery"] == recovery
    assert cell.getString() == "original"
    assert cell.NumberFormat == 6


@pytest.mark.parametrize(
    ("spec", "expected_formula"),
    [
        ({"kind": "formula", "value": "=A1*2"}, "=A1*2"),
        (
            {
                "kind": "formatted_text",
                "value": {
                    "parts": [
                        {"text": "Cost: "},
                        {"cell": "A1", "decimal_places": 2},
                    ]
                },
            },
            '="Cost: "&FIXED(A1;2;1)',
        ),
        (
            {
                "kind": "formatted_text",
                "value": {
                    "parts": [
                        {"cell": "C$1"},
                        {"text": " / "},
                        {"cell": "$D8", "decimal_places": 3},
                    ]
                },
            },
            '=C$1&" / "&FIXED($D8;3;1)',
        ),
    ],
)
def test_valid_formula_like_write_passes_unchanged(
    spec: dict[str, Any], expected_formula: str
) -> None:
    session, target, doc = _session([[_Cell(kind="string", value="old")]])
    params = {"sheet": "Synthetic", "range": "A1", "values": [spec]}
    original_params = deepcopy(params)

    result = uno_worker._write(session, params)

    assert target.cells[0][0].getFormula() == expected_formula
    assert result["formulas"] == [[expected_formula]]
    assert doc.calculate_calls == 1
    assert params == original_params


def test_valid_mixed_write_passes_atomically() -> None:
    session, target, _ = _session([[_Cell(), _Cell(), _Cell()]])
    params = {
        "sheet": "Synthetic",
        "range": "A1:C1",
        "values": [
            {"kind": "string", "value": "label"},
            {"kind": "formula", "value": "=7*6"},
            {"kind": "number", "value": 42},
        ],
    }
    original_params = deepcopy(params)

    result = uno_worker._write(session, params)

    assert result["kinds"] == [["string", "formula", "number"]]
    assert target.cells[0][0].getString() == "label"
    assert target.cells[0][1].getFormula() == "=7*6"
    assert target.cells[0][2].getValue() == 42
    assert params == original_params


def test_literal_cells_use_existing_writers_without_inferred_types() -> None:
    cells = [[_Cell(kind="string", value="old") for _ in range(7)]]
    session, target, _ = _session(cells)
    params = {
        "sheet": "Synthetic",
        "range": "A1:G1",
        "values": ["=2+3", " 2034-05-06\t读数 ", 7.25, True, False, None,
                   {"kind": "formula", "value": "=3*7"}],
    }
    original = deepcopy(params)

    result = uno_worker._write(session, params)

    assert result["kinds"] == [["string", "string", "number", "formula", "formula", "blank", "formula"]]
    assert target.cells[0][0].getString() == "=2+3"
    assert target.cells[0][1].getString() == " 2034-05-06\t读数 "
    assert target.cells[0][2].getValue() == 7.25
    assert result["formulas"][0][3:5] == ["=TRUE()", "=FALSE()"]
    assert target.cells[0][5].getString() == ""
    assert target.cells[0][6].getFormula() == "=3*7"
    assert params == original
    canonical = [[
        {"kind": "string", "value": "=2+3"},
        {"kind": "string", "value": " 2034-05-06\t读数 "},
        {"kind": "number", "value": 7.25},
        {"kind": "boolean", "value": True},
        {"kind": "boolean", "value": False},
        {"kind": "blank"},
        {"kind": "formula", "value": "=3*7"},
    ]]
    conversion = result["argument_conversion"]
    assert conversion["contract"] == "calc.range.write.literal_cells.v1"
    assert conversion["literal_cells"] == 6
    assert (conversion["target_rows"], conversion["target_columns"]) == (1, 7)
    assert conversion["canonical_matrix_sha256"] == hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_literal_write_error_keeps_conversion_without_claiming_rollback(monkeypatch) -> None:
    session, _, _ = _session([[_Cell()]])
    params = {"sheet": "Synthetic", "range": "A1", "values": [17]}
    original = deepcopy(params)

    def fail_write(*_args):
        raise RuntimeError("synthetic write failure")

    monkeypatch.setattr(uno_worker, "_set_cell", fail_write)
    with pytest.raises(AdapterError) as failure:
        uno_worker._write(session, params)

    assert failure.value.code == "WRITE_FAILED"
    assert "restored" not in failure.value.message
    assert failure.value.details["argument_conversion"]["literal_cells"] == 1
    assert params == original


def test_mixed_literal_formula_failure_retains_conversion_and_existing_rollback() -> None:
    session, target, _ = _session(
        [[_Cell(kind="string", value="keep"), _Cell(kind="number", value=23)]],
        errors={"=INVALID()": 519},
    )
    params = {
        "sheet": "Synthetic", "range": "A1:B1",
        "values": ["replacement", {"kind": "formula", "value": "=INVALID()"}],
    }
    original = deepcopy(params)

    with pytest.raises(AdapterError) as failure:
        uno_worker._write(session, params)

    assert failure.value.code == "FORMULA_ERROR"
    assert failure.value.details["cells"] == [{"cell": "B1", "kind": "formula", "error_code": 519}]
    assert failure.value.details["argument_conversion"]["literal_cells"] == 1
    assert target.cells[0][0].getString() == "keep"
    assert target.cells[0][1].getValue() == 23
    assert params == original
