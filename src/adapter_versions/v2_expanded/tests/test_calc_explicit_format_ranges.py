from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from calc_adapter import uno_worker
from calc_adapter.errors import AdapterError


class Target:
    def __init__(self, label, addresses, state):
        self.label = label
        self.addresses = addresses
        self.state = state

    def getRangeAddress(self):
        first, last = self.addresses[0][0], self.addresses[-1][-1]
        return SimpleNamespace(
            StartColumn=ord(first[0]) - ord("A"), StartRow=int(first[1:]) - 1,
            EndColumn=ord(last[0]) - ord("A"), EndRow=int(last[1:]) - 1,
        )

    @property
    def CellBackColor(self):
        return self.state["colors"][self.addresses[0][0]]

    @CellBackColor.setter
    def CellBackColor(self, value):
        self.state["events"].append(("apply", self.label, value))
        for row in self.addresses:
            for address in row:
                self.state["colors"][address] = value
                if self.state["apply_error"] == self.label:
                    raise RuntimeError("synthetic native property failure")


@pytest.fixture
def native(monkeypatch):
    state = {
        "events": [],
        "colors": dict.fromkeys(["D4", "D9", "E9", "D10", "E10", "F12", "E4"], 0xFFFFFF),
        "apply_error": None,
        "readback_error": None,
    }
    first = Target("d4", [["D4"]], state)
    rectangle = Target("$D$9:E10", [["D9", "E9"], ["D10", "E10"]], state)
    targets = {
        "d4": first,
        "D4": first,
        "NamedArea": first,
        "$D$9:E10": rectangle,
        "F12": Target("F12", [["F12"]], state),
    }

    def resolve(raw):
        state["events"].append(("resolve", raw))
        if raw not in targets:
            raise RuntimeError("synthetic native range lookup failure")
        return targets[raw]

    document = object()
    session = SimpleNamespace(doc=document, sheet=lambda name: SimpleNamespace(getCellRangeByName=resolve))

    def snapshot(target, doc=None):
        assert doc is document
        state["events"].append(("readback", target.label))
        if state["readback_error"] == target.label:
            raise RuntimeError("synthetic native read-back failure")
        return {
            "styles": [
                [{"background_color": f'#{state["colors"][address]:06x}'} for address in row]
                for row in target.addresses
            ],
            "display_text": [[f"visible {address}" for address in row] for row in target.addresses],
            "background_cells": {
                address: f'#{state["colors"][address]:06x}'
                for row in target.addresses for address in row
            },
            "date_cells": (
                {"D4": {"date": "2032-04-09", "weekday": "Friday"}}
                if target.label == "d4" else {}
            ),
        }

    monkeypatch.setattr(uno_worker, "_range_snapshot", snapshot)
    monkeypatch.setattr(uno_worker, "_uno_modules", lambda: (SimpleNamespace(), None))
    return session, state


def parameters(raw):
    return {"sheet": "Data", "range": raw, "format": {"background_color": "#abcdef"}}


def test_explicit_areas_resolve_before_shared_format_and_keep_order_and_raw_values(native):
    session, state = native
    params = parameters("d4, $D$9:E10,d4")
    original = deepcopy(params)

    result = uno_worker._format_range(session, params)

    assert state["events"][:4] == [
        ("resolve", original["range"]),
        ("resolve", "d4"), ("resolve", "$D$9:E10"), ("resolve", "d4"),
    ]
    assert [event[:2] for event in state["events"][4:7]] == [
        ("apply", "d4"), ("apply", "$D$9:E10"), ("apply", "d4"),
    ]
    assert params == original
    assert result["range"] == original["range"]
    assert result["formatted_ranges"] == ["d4", "$D$9:E10", "d4"]
    assert [item["range"] for item in result["range_results"]] == result["formatted_ranges"]
    assert [len(item["styles"]) for item in result["range_results"]] == [1, 2, 1]
    assert result["range_results"][1]["display_text"] == [
        ["visible D9", "visible E9"], ["visible D10", "visible E10"],
    ]
    assert result["background_cells"] == dict.fromkeys(["D4", "D9", "E9", "D10", "E10"], "#abcdef")
    assert result["date_cells"] == {"D4": {"date": "2032-04-09", "weekday": "Friday"}}
    assert "styles" not in result
    assert state["colors"]["E4"] == 0xFFFFFF
    assert state["colors"]["F12"] == 0xFFFFFF


@pytest.mark.parametrize("raw", ["D4", "NamedArea"])
def test_existing_native_single_and_named_ranges_keep_their_original_path(native, raw):
    session, state = native
    params = parameters(raw)
    original = deepcopy(params)

    result = uno_worker._format_range(session, params)

    assert [event for event in state["events"] if event[0] == "resolve"] == [("resolve", raw)]
    assert result["range"] == raw
    assert result["formatted_ranges"] == [raw]
    assert result["styles"] == [[{"background_color": "#abcdef"}]]
    assert "truncated" not in result
    assert "readback_range" not in result["range_results"][0]
    assert params == original


@pytest.mark.parametrize("raw", ["d4,Z99,F12", "d4,,F12"])
def test_unresolvable_selection_keeps_all_cells_unchanged_and_native_error(native, raw):
    session, state = native
    params = parameters(raw)
    original = deepcopy(params)

    with pytest.raises(AdapterError) as caught:
        uno_worker._format_range(session, params)

    error = caught.value
    assert error.code == "INTERNAL_ERROR" and error.http_status == 500
    assert error.details["stage"] == "resolve"
    assert error.details["applied_ranges"] == []
    assert "synthetic native range lookup failure" in error.details["native_error"]
    assert "synthetic native range lookup failure" in error.details["traceback"]
    assert "No formatting was applied" in error.message
    assert all(event[0] == "resolve" for event in state["events"])
    assert set(state["colors"].values()) == {0xFFFFFF}
    assert params == original


def test_partial_native_format_error_reports_applied_failed_and_unattempted_areas(native):
    session, state = native
    state["apply_error"] = "$D$9:E10"
    params = parameters("d4,$D$9:E10,F12")
    original = deepcopy(params)

    with pytest.raises(AdapterError) as caught:
        uno_worker._format_range(session, params)

    details = caught.value.details
    assert details["stage"] == "apply"
    assert details["applied_ranges"] == ["d4"]
    assert details["failed_range"] == "$D$9:E10"
    assert details["failed_range_may_be_partially_formatted"] is True
    assert details["unattempted_ranges"] == ["F12"]
    assert details["native_error"] == "synthetic native property failure"
    assert "may be partly changed" in caught.value.message
    assert state["colors"]["D4"] == state["colors"]["D9"] == 0xABCDEF
    assert state["colors"]["E9"] == state["colors"]["F12"] == 0xFFFFFF
    assert params == original


def test_readback_failure_reports_that_all_selected_formats_were_applied(native):
    session, state = native
    state["readback_error"] = "$D$9:E10"

    with pytest.raises(AdapterError) as caught:
        uno_worker._format_range(session, parameters("d4,$D$9:E10,F12"))

    details = caught.value.details
    assert details["stage"] == "readback"
    assert details["failed_range_may_be_partially_formatted"] is False
    assert details["applied_ranges"] == ["d4", "$D$9:E10", "F12"]
    assert details["failed_range"] == "$D$9:E10"
    assert details["unattempted_ranges"] == []
    assert details["native_error"] == "synthetic native read-back failure"
    assert "applied to all selected ranges" in caught.value.message
    assert state["colors"]["F12"] == 0xABCDEF
    assert state["colors"]["E4"] == 0xFFFFFF


def test_existing_adapter_error_keeps_code_message_status_and_original_details(native, monkeypatch):
    session, _state = native
    original_details = {"field": "number_format", "value": "synthetic unsupported format"}
    original_error = AdapterError("INVALID_REQUEST", "unsupported native format", original_details, 400)

    def apply(*args):
        raise original_error

    monkeypatch.setattr(uno_worker, "_apply_format", apply)

    with pytest.raises(AdapterError) as caught:
        uno_worker._format_range(session, parameters("NamedArea"))

    error = caught.value
    assert (error.code, error.message, error.http_status) == (
        original_error.code, original_error.message, original_error.http_status,
    )
    assert error.details["adapter_error_details"] == original_details
    assert original_error.details == original_details
    assert error.details["stage"] == "apply"
    assert error.details["failed_range"] == "NamedArea"
    assert error.details["failed_range_may_be_partially_formatted"] is True
    assert "may be partly changed" in error.details["guidance"]


def _sparse_native_format_fixture(monkeypatch, areas):
    state = {"applied": [], "preview_reads": [], "cell_reads": [], "formats": {}}

    class SparseRange:
        def __init__(self, bounds, source=None):
            self.bounds = bounds
            self.source = source or self

        def getRangeAddress(self):
            left, top, right, bottom = self.bounds
            return SimpleNamespace(
                StartColumn=left, StartRow=top, EndColumn=right, EndRow=bottom,
            )

        @property
        def NumberFormat(self):
            return state["formats"].get(self.source.bounds, 0)

        @NumberFormat.setter
        def NumberFormat(self, value):
            assert self.source is self
            state["applied"].append((self.bounds, value))
            state["formats"][self.bounds] = value

        def getCellByPosition(self, column, row):
            left, top, right, bottom = self.bounds
            assert right - left < 16 and bottom - top < 32
            absolute = (left + column, top + row)
            state["cell_reads"].append(absolute)
            populated = absolute == self.source.bounds[:2]
            return SimpleNamespace(
                getType=lambda: "VALUE" if populated else "EMPTY",
                getValue=lambda: 2.0,
                getString=lambda: "01/01/1900" if populated else "",
                NumberFormat=self.NumberFormat,
                CellBackColor=0xFFFFFF,
                CharColor=0,
                CharWeight=100.0,
            )

    targets = {name: SparseRange(bounds) for name, bounds in areas.items()}

    def preview(*bounds):
        state["preview_reads"].append(bounds)
        source = next(
            target for target in targets.values() if target.bounds[:2] == bounds[:2]
        )
        return SparseRange(bounds, source)

    formats = SimpleNamespace(
        queryKey=lambda code, locale, scan: 10121,
        getByKey=lambda key: SimpleNamespace(
            FormatString="DD/MM/YYYY", Type=2,
            Locale=SimpleNamespace(Language="en", Country="US"),
        ),
    )
    doc = SimpleNamespace(
        NullDate=SimpleNamespace(Year=1899, Month=12, Day=30),
        getNumberFormats=lambda: formats,
    )
    sheet = SimpleNamespace(
        getCellRangeByName=targets.__getitem__, getCellRangeByPosition=preview,
    )
    monkeypatch.setattr(
        uno_worker, "_uno_modules",
        lambda: (SimpleNamespace(createUnoStruct=lambda name: SimpleNamespace()), None),
    )
    return SimpleNamespace(doc=doc, sheet=lambda name: sheet), state


@pytest.mark.parametrize(
    "selected,bounds,preview_range,preview_bounds,date_address",
    [
        ("C:C", (2, 0, 2, 1048575), "C1:C32", (2, 0, 2, 31), "C1"),
        ("7:7", (0, 6, 16383, 6), "A7:P7", (0, 6, 15, 6), "A7"),
        ("LargeNamedArea", (4, 7, 40, 84), "E8:T39", (4, 7, 19, 38), "E8"),
    ],
)
def test_full_native_format_only_bounds_readback(
    monkeypatch, selected, bounds, preview_range, preview_bounds, date_address,
):
    session, state = _sparse_native_format_fixture(monkeypatch, {selected: bounds})
    params = {
        "sheet": "Records", "range": selected,
        "format": {"number_format": "DD/MM/YYYY"},
    }
    before = deepcopy(params)

    result = uno_worker._format_range(session, params)

    assert state["applied"] == [(bounds, 10121)]
    assert state["preview_reads"] == [preview_bounds]
    preview_columns = preview_bounds[2] - preview_bounds[0] + 1
    preview_rows = preview_bounds[3] - preview_bounds[1] + 1
    assert len(state["cell_reads"]) == preview_columns * preview_rows <= 512
    assert result["range"] == selected
    assert result["formatted_ranges"] == [selected]
    area = result["range_results"][0]
    assert area["range"] == selected
    assert area["readback_range"] == preview_range
    assert area["truncated"] is True
    assert len(area["display_text"]) == preview_rows
    assert all(len(row) == preview_columns for row in area["display_text"])
    assert area["display_text"][0][0] == "01/01/1900"
    assert result["date_cells"] == {
        date_address: {"date": "1900-01-01", "weekday": "Monday"},
    }
    assert result["background_cells"] == {}
    assert result["truncated"] is True
    assert result["date_cells_truncated"] is True
    assert result["background_cells_truncated"] is True
    assert result["styles"] == area["styles"]
    assert params == before


def test_mixed_format_areas_keep_full_targets_and_independent_preview_coverage(monkeypatch):
    areas = {"D4": (3, 3, 3, 3), "F10:F500": (5, 9, 5, 499)}
    session, state = _sparse_native_format_fixture(monkeypatch, areas)
    params = {
        "sheet": "Records", "range": "D4,F10:F500,D4",
        "format": {"number_format": "DD/MM/YYYY"},
    }

    result = uno_worker._format_range(session, params)

    assert state["applied"] == [
        (areas["D4"], 10121), (areas["F10:F500"], 10121), (areas["D4"], 10121),
    ]
    assert state["preview_reads"] == [(5, 9, 5, 40)]
    assert len(state["cell_reads"]) == 34
    assert result["formatted_ranges"] == ["D4", "F10:F500", "D4"]
    first, middle, last = result["range_results"]
    assert "readback_range" not in first and "truncated" not in first
    assert first == last
    assert middle["range"] == "F10:F500"
    assert middle["readback_range"] == "F10:F41"
    assert middle["truncated"] is True
    assert set(result["date_cells"]) == {"D4", "F10"}
    assert "styles" not in result
