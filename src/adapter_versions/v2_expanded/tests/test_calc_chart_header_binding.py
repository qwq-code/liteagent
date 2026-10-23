from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from calc_adapter import uno_worker
from calc_adapter.errors import AdapterError


@pytest.fixture
def native(monkeypatch):
    state = {"events": [], "existing": set(), "flags": None, "source_ranges": []}
    diagram = SimpleNamespace()

    def set_diagram(value):
        state["events"].append(("diagram", value.DataRowSource))
        state["orientation"] = value.DataRowSource
        # The preserved native incident shows the header roles being transposed
        # when the fresh diagram switches to rows after initial chart creation.
        if value.DataRowSource == "ROWS":
            state["flags"] = tuple(reversed(state["flags"]))

    embedded = SimpleNamespace(
        createInstance=lambda name: diagram,
        setDiagram=set_diagram,
    )

    def column_headers(value):
        state["events"].append(("column_headers", value))
        state["flags"] = (value, state["flags"][1])

    def row_headers(value):
        state["events"].append(("row_headers", value))
        state["flags"] = (state["flags"][0], value)

    def read_header(index):
        if state.get("header_error") == index:
            raise RuntimeError("synthetic native header read failure")
        return state.get("native_flags", state["flags"])[index]

    table_chart = SimpleNamespace(
        getEmbeddedObject=lambda: embedded,
        setHasColumnHeaders=column_headers,
        setHasRowHeaders=row_headers,
        getHasColumnHeaders=lambda: read_header(0),
        getHasRowHeaders=lambda: read_header(1),
    )

    def add_chart(name, rectangle, ranges, columns, rows):
        state["events"].append(("create", name))
        state["existing"].add(name)
        state["flags"] = (columns, rows)
        state["source_ranges"] = [item.selected_range for item in ranges]

    def remove_chart(name):
        state["events"].append(("remove", name))
        state["existing"].remove(name)

    charts = SimpleNamespace(
        hasByName=lambda name: name in state["existing"],
        addNewByName=add_chart,
        removeByName=remove_chart,
        getByName=lambda name: table_chart,
    )

    def source_range(value):
        return SimpleNamespace(
            getRangeAddress=lambda: SimpleNamespace(
                StartRow=3, EndRow=3, StartColumn=2, EndColumn=4,
                selected_range=value,
            ),
        )

    sheet = SimpleNamespace(
        getName=lambda: "Data",
        getCharts=lambda: charts,
        getCellRangeByName=source_range,
    )

    def observe(chart):
        assert chart is embedded
        state["events"].append(("observe", state["flags"]))
        columns, rows = state.get("native_flags", state["flags"])
        categories = columns if state["orientation"] == "ROWS" else rows
        return {
            "data_series_count": 1 if categories else 2,
            "data_series": [{"source_ranges": state["source_ranges"]}],
            "category_axes": [{"labels": ["Cobalt", "Amber", "Teal"]}] if categories else [],
        }

    monkeypatch.setattr(uno_worker, "_chart_series_details", observe)
    monkeypatch.setattr(
        uno_worker,
        "_uno_modules",
        lambda: (
            SimpleNamespace(
                createUnoStruct=lambda name: SimpleNamespace(),
                Enum=lambda name, value: value,
            ), None,
        ),
    )
    return SimpleNamespace(sheet=lambda name: sheet), state


def parameters():
    return {
        "sheet": "Data", "source_sheet": "Data", "name": "Comparison",
        "source_ranges": ["C4:E4", "C8:E8"], "type": "line",
    }


@pytest.mark.parametrize("orientation", ["rows", "columns"])
@pytest.mark.parametrize("headers", [(True, False), (False, True)])
def test_native_header_roles_are_rebound_after_diagram_before_readback(
    native, orientation, headers,
):
    session, state = native
    params = {
        **parameters(), "data_row_source": orientation,
        "column_headers": headers[0], "row_headers": headers[1],
    }
    original = deepcopy(params)

    result = uno_worker._chart_create(session, params)

    assert state["events"] == [
        ("create", "Comparison"), ("diagram", orientation.upper()),
        ("column_headers", headers[0]), ("row_headers", headers[1]),
        ("observe", headers),
    ]
    assert state["source_ranges"] == original["source_ranges"] == result["source_ranges"]
    assert params == original
    assert result["data_row_source"] == orientation
    assert (result["column_headers"], result["row_headers"]) == headers
    has_categories = headers[0] if orientation == "rows" else headers[1]
    assert bool(result["category_axes"]) is has_categories
    assert result["data_series_count"] == (1 if has_categories else 2)


def test_auto_orientation_and_omitted_header_defaults_keep_native_binding(native):
    session, state = native
    params = parameters()
    original = deepcopy(params)

    result = uno_worker._chart_create(session, params)

    assert result["data_row_source"] == "rows"
    assert state["flags"] == (True, True)
    assert result["column_headers"] is True and result["row_headers"] is True
    assert params == original
    assert "column_headers" not in params and "row_headers" not in params


def test_create_returns_observed_native_flags_instead_of_echoing_arguments(native):
    session, state = native
    state["native_flags"] = (False, True)
    params = {**parameters(), "column_headers": True, "row_headers": False}
    original = deepcopy(params)

    result = uno_worker._chart_create(session, params)

    assert result["column_headers"] is False
    assert result["row_headers"] is True
    assert "header_inspect_error" not in result
    assert params == original


@pytest.mark.parametrize("failed_index", [0, 1])
def test_header_read_failure_keeps_created_chart_and_other_native_readback(native, failed_index):
    session, state = native
    state["header_error"] = failed_index
    params = parameters()
    original = deepcopy(params)

    result = uno_worker._chart_create(session, params)

    fields = ("column_headers", "row_headers")
    assert fields[failed_index] not in result
    assert result[fields[1 - failed_index]] is True
    assert result["header_inspect_error"] == {
        fields[failed_index]: "synthetic native header read failure",
    }
    assert result["data_series_count"] == 1
    assert result["category_axes"][0]["labels"] == ["Cobalt", "Amber", "Teal"]
    assert state["existing"] == {"Comparison"}
    assert params == original


def test_conflict_preserves_existing_chart_and_explains_explicit_replace(native):
    session, state = native
    state["existing"].add("Comparison")
    params = parameters()
    original = deepcopy(params)

    with pytest.raises(AdapterError) as caught:
        uno_worker._chart_create(session, params)

    error = caught.value
    assert error.code == "CONFLICT" and error.http_status == 409
    assert "replace=true" in error.message and "different name" in error.message
    assert error.details == {
        "name": "Comparison", "sheet": "Data", "replace_requested": False,
        "existing_chart_removed": False,
    }
    assert state["existing"] == {"Comparison"}
    assert state["events"] == []
    assert params == original


def test_only_explicit_replace_removes_existing_chart(native):
    session, state = native
    state["existing"].update({"Comparison", "Unrelated"})
    params = {**parameters(), "replace": True}
    original = deepcopy(params)

    result = uno_worker._chart_create(session, params)

    assert state["events"][:2] == [("remove", "Comparison"), ("create", "Comparison")]
    assert state["existing"] == {"Comparison", "Unrelated"}
    assert result["name"] == "Comparison"
    assert params == original
