from datetime import date
from types import SimpleNamespace

import pytest

from calc_adapter import uno_worker


def _cell(
    serial=2,
    *,
    kind="VALUE",
    format_key=2,
    formula_result="VALUE",
    error=0,
):
    return SimpleNamespace(
        NumberFormat=format_key,
        CellBackColor=0xFFFFFF,
        CharColor=0,
        CharWeight=100,
        FormulaResultType=formula_result,
        getType=lambda: kind,
        getValue=lambda: serial,
        getString=lambda: "2000-01-03",
        getFormula=lambda: "=1+1" if kind == "FORMULA" else "",
        getError=lambda: error,
    )


def _read(cells, *, base=date(2000, 1, 1), settings_only=False):
    formats = {
        key: SimpleNamespace(
            Type=key,
            FormatString="YYYY-MM-DD",
            Locale=SimpleNamespace(Language="en", Country="US"),
        )
        for key in (2, 4, 6, 16)
    }
    # Unknown native type remains unknown even with a date-looking format.
    formats[99] = SimpleNamespace(
        FormatString="YYYY-MM-DD", Locale=SimpleNamespace(Language="en", Country="US")
    )
    doc = SimpleNamespace(
        getNumberFormats=lambda: SimpleNamespace(getByKey=lambda key: formats[key]),
    )
    if base is not None:
        native_base = SimpleNamespace(Year=base.year, Month=base.month, Day=base.day)
        if settings_only:
            doc.getNumberFormatSettings = lambda: SimpleNamespace(
                getPropertyValue=lambda name: native_base if name == "NullDate" else None
            )
        else:
            doc.NullDate = native_base
    target = SimpleNamespace(
        getRangeAddress=lambda: SimpleNamespace(
            StartColumn=2, EndColumn=2 + len(cells) - 1, StartRow=4, EndRow=4
        ),
        getCellByPosition=lambda column, row: cells[column],
    )
    session = SimpleNamespace(
        doc=doc,
        sheet=lambda _: SimpleNamespace(getCellRangeByName=lambda _: target),
    )
    cell_range = "C5" if len(cells) == 1 else f"C5:{chr(ord('C') + len(cells) - 1)}5"
    return uno_worker._read(session, {"sheet": "Records", "range": cell_range})


@pytest.mark.parametrize(
    "format_key,serial,base,expected",
    [
        (2, 2, date(2000, 1, 1), {"date": "2000-01-03", "weekday": "Monday"}),
        (6, 2.75, date(2000, 1, 1), {"date": "2000-01-03", "weekday": "Monday"}),
        (2, 0, date(1904, 1, 1), {"date": "1904-01-01", "weekday": "Friday"}),
        (6, -0.25, date(2000, 1, 1), {"date": "1999-12-31", "weekday": "Friday"}),
    ],
)
def test_native_date_uses_document_epoch_and_the_serial_day(format_key, serial, base, expected):
    result = _read([_cell(serial, format_key=format_key)], base=base)
    assert result["date_cells"] == {"C5": expected}
    assert result["values"] == [[serial]]
    assert result["display_text"] == [["2000-01-03"]]
    assert result["number_formats"][0][0]["type"] == format_key


def test_native_date_reads_document_number_format_settings_when_needed():
    result = _read([_cell(0)], base=date(1904, 1, 1), settings_only=True)
    assert result["date_cells"] == {"C5": {"date": "1904-01-01", "weekday": "Friday"}}


def test_native_date_does_not_guess_from_text_general_time_or_unknown_formats():
    result = _read([
        _cell(kind="TEXT"),
        _cell(format_key=16),
        _cell(0.5, format_key=4),
        _cell(format_key=99),
        _cell(kind="EMPTY"),
    ])
    assert result["date_cells"] == {}


def test_native_date_requires_a_known_epoch_and_representable_finite_value():
    assert _read([_cell()], base=None)["date_cells"] == {}
    result = _read([_cell(float("nan")), _cell(float("inf")), _cell(1e100)])
    assert result["date_cells"] == {}


def test_native_date_includes_only_confirmed_numeric_formula_results():
    result = _read([
        _cell(kind="FORMULA"),
        _cell(kind="FORMULA", formula_result=1),
        _cell(kind="FORMULA", formula_result="TEXT"),
        _cell(kind="FORMULA", error=522),
        _cell(kind="FORMULA", formula_result=None),
    ])
    assert result["date_cells"] == {
        "C5": {"date": "2000-01-03", "weekday": "Monday"},
        "D5": {"date": "2000-01-03", "weekday": "Monday"},
    }
