from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from calc_adapter import uno_worker
from calc_adapter.errors import AdapterError, error_payload
from integrations.lite_agent.adapter_results import adapter_context_hint
from integrations.lite_agent.context_projection import sanitize


def _sequence(labels, source_range):
    return SimpleNamespace(
        getData=lambda: tuple(labels),
        getSourceRangeRepresentation=lambda: source_range,
    )


def _chart(category_range, value_ranges):
    categories = _sequence(["North", "South", "West"], category_range)
    series = [
        SimpleNamespace(
            getDataSequences=lambda name=name, source_range=source_range: (
                SimpleNamespace(
                    getLabel=lambda: _sequence([name], ""),
                    getValues=lambda: _sequence([], source_range),
                ),
            ),
        )
        for name, source_range in zip(("Output", "Returns"), value_ranges)
    ]
    coordinate = SimpleNamespace(
        getChartTypes=lambda: (SimpleNamespace(getDataSeries=lambda: tuple(series)),),
        getAxisByDimension=lambda dimension, index: SimpleNamespace(
            getScaleData=lambda: SimpleNamespace(
                Categories=SimpleNamespace(getValues=lambda: categories),
            ),
        ),
    )
    return SimpleNamespace(
        getFirstDiagram=lambda: SimpleNamespace(
            getCoordinateSystems=lambda: (coordinate,),
        ),
    )


@pytest.mark.parametrize(
    ("category_range", "value_ranges"),
    [
        ("$Input.$D$9:$D$11", ["$Input.$E$9:$E$11", "$Input.$F$9:$F$11"]),
        ("$Input.$E$15:$G$15", ["$Input.$E$16:$G$16", "$Input.$E$17:$G$17"]),
    ],
)
def test_chart_observation_reads_native_series_not_range_count(
    category_range,
    value_ranges,
):
    chart = _chart(category_range, value_ranges)

    result = uno_worker._chart_series_details(chart)

    assert result["data_series_count"] == 2
    assert result["data_series"] == [
        {"coordinate_system": 0, "labels": [name], "source_ranges": [source_range]}
        for name, source_range in zip(("Output", "Returns"), value_ranges)
    ]
    assert result["category_axes"] == [
        {
            "coordinate_system": 0,
            "source_range": category_range,
            "labels": ["North", "South", "West"],
            "count": 3,
        }
    ]


def test_chart_create_context_explains_category_is_not_value_series() -> None:
    body = {
        "status": "ok",
        "result": {
            "name": "SalesCOGSChart",
            "type": "column",
            "title": "Sales & COGS",
            "sheet": "Sheet2",
            "source_sheet": "Sheet1",
            "source_ranges": ["A1:A11", "B1:B11", "C1:C11"],
            "data_row_source": "columns",
            "column_headers": True,
            "row_headers": True,
            "data_series_count": 2,
            "data_series": [
                {"labels": ["Sales"], "source_ranges": ["$Sheet1.$B$2:$B$11"]},
                {"labels": ["COGS"], "source_ranges": ["$Sheet1.$C$2:$C$11"]},
            ],
            "category_axes": [
                {
                    "labels": ["Week 1", "Week 2"],
                    "source_range": "$Sheet1.$A$2:$A$11",
                }
            ],
        },
        "verification": {"passed": True},
    }

    hint = adapter_context_hint("libreoffice_calc", "chart.create", body)

    assert hint is not None
    assert hint["column_headers"] is True
    assert hint["row_headers"] is True
    assert hint["data_series_count"] == 2
    assert hint["category_axes"][0]["source_range"] == "$Sheet1.$A$2:$A$11"
    assert "not an additional value series" in hint["guidance"]
    assert "not that the selected data matches the user's request" in hint["guidance"]
    assert "correct your source ranges or header flags" in hint["guidance"]
    assert "Otherwise keep the chart" in hint["guidance"]


@pytest.mark.parametrize("series_read_fails", [False, True])
def test_workbook_inspection_preserves_chart_and_native_series(
    monkeypatch,
    series_read_fails,
):
    embedded = _chart("$Input.$D$9:$D$11", ["$Input.$E$9:$E$11", "$Input.$F$9:$F$11"])
    embedded.HasMainTitle = True
    embedded.Title = SimpleNamespace(String="Production")
    embedded.getDiagram = lambda: object()
    if series_read_fails:

        def unavailable():
            raise RuntimeError("Chart data sequences unavailable")

        embedded.getFirstDiagram = unavailable
    table_chart = SimpleNamespace(
        getEmbeddedObject=lambda: embedded,
        getRanges=lambda: (
            SimpleNamespace(Sheet=0, StartColumn=3, StartRow=7, EndColumn=5, EndRow=10),
        ),
        getHasColumnHeaders=lambda: True,
        getHasRowHeaders=lambda: True,
    )
    sheet = SimpleNamespace(
        getName=lambda: "Input",
        getCharts=lambda: SimpleNamespace(
            getElementNames=lambda: ("Plot",),
            getByName=lambda name: table_chart,
        ),
    )
    doc = SimpleNamespace(
        getSheets=lambda: SimpleNamespace(getByIndex=lambda index: sheet),
        getCurrentController=lambda: SimpleNamespace(getActiveSheet=lambda: sheet),
        isModified=lambda: False,
    )
    session = SimpleNamespace(
        doc=doc,
        sheet=lambda name: sheet,
        _identity=lambda doc: {"title": "Production.xlsx"},
    )
    monkeypatch.setattr(uno_worker, "_sheet_names", lambda doc: ["Input"])
    monkeypatch.setattr(uno_worker, "_used_range", lambda sheet: {})
    monkeypatch.setattr(uno_worker, "_hidden_rows_in_used_range", lambda *args: [])
    monkeypatch.setattr(
        uno_worker, "_chart_diagram_details", lambda diagram: {"type": "column"}
    )

    result = uno_worker._inspect(session, {})

    chart = result["sheets"][0]["charts"][0]
    assert chart["title"] == "Production"
    assert chart["source_ranges"] == ["D8:F11"]
    assert "inspect_error" not in chart
    if series_read_fails:
        assert chart["data_series_inspect_error"] == "Chart data sequences unavailable"
        assert "data_series_count" not in chart
    else:
        assert chart["data_series_count"] == 2
        assert chart["data_series"][0]["labels"] == ["Output"]
        assert chart["category_axes"][0]["labels"] == ["North", "South", "West"]
    assert result["modified"] is False


@pytest.mark.parametrize("replace_existing", [False, True])
@pytest.mark.parametrize("empty_chart", [False, True])
def test_chart_create_reports_native_empty_series_without_changing_arguments(
    monkeypatch, replace_existing, empty_chart
):
    params = {
        "sheet": "Output",
        "source_sheet": "Input",
        "name": "Production",
        "source_ranges": ["D8:D11", "E9:F11"],
        "data_row_source": "columns",
        "type": "column",
        "column_headers": True,
        "row_headers": True,
        "replace": replace_existing,
    }
    original = deepcopy(params)
    existing = {"Unrelated"}
    if replace_existing:
        existing.add(params["name"])
    removed = []
    forwarded = []
    diagram = SimpleNamespace()
    embedded = SimpleNamespace(
        createInstance=lambda service: diagram,
        setDiagram=lambda value: None,
        getFirstDiagram=lambda: SimpleNamespace(getCoordinateSystems=lambda: ()),
    )
    if not empty_chart:
        embedded.getFirstDiagram = _chart(
            "$Input.$D$9:$D$11", ["$Input.$E$9:$E$11", "$Input.$F$9:$F$11"]
        ).getFirstDiagram

    def add_chart(name, rectangle, ranges, column_headers, row_headers):
        existing.add(name)
        forwarded.append((ranges, column_headers, row_headers))

    def remove_chart(name):
        existing.remove(name)
        removed.append(name)

    charts = SimpleNamespace(
        hasByName=lambda name: name in existing,
        addNewByName=add_chart,
        removeByName=remove_chart,
        getByName=lambda name: SimpleNamespace(
            getEmbeddedObject=lambda: embedded,
            setHasColumnHeaders=lambda value: None,
            setHasRowHeaders=lambda value: None,
            getHasColumnHeaders=lambda: True,
            getHasRowHeaders=lambda: True,
        ),
    )
    sheet = SimpleNamespace(
        getName=lambda: "Input",
        getCharts=lambda: charts,
        getCellRangeByName=lambda value: SimpleNamespace(getRangeAddress=lambda: value),
    )
    session = SimpleNamespace(sheet=lambda name: sheet)
    monkeypatch.setattr(
        uno_worker,
        "_uno_modules",
        lambda: (
            SimpleNamespace(
                createUnoStruct=lambda name: SimpleNamespace(),
                Enum=lambda name, value: value,
            ),
            None,
        ),
    )

    if empty_chart:
        with pytest.raises(AdapterError) as caught:
            uno_worker._chart_create(session, params)

        assert caught.value.code == "INVALID_REQUEST"
        assert caught.value.http_status == 422
        assert "no data series" in caught.value.message
        assert "same rows" in caught.value.message
        assert "same columns" in caught.value.message
        assert "header row consistently" in caught.value.message
        assert caught.value.details == {
            "name": "Production",
            "source_ranges": original["source_ranges"],
            "data_row_source": "columns",
            "empty_chart_removed": True,
            "previous_chart_removed": replace_existing,
        }
        assert sanitize(error_payload(caught.value))["message"] == caught.value.message
        assert existing == {"Unrelated"}
        assert removed == ["Production"] * (2 if replace_existing else 1)
    else:
        result = uno_worker._chart_create(session, params)
        assert result["data_series_count"] == 2
        assert result["source_ranges"] == original["source_ranges"]
        assert existing == {"Unrelated", "Production"}
        assert removed == (["Production"] if replace_existing else [])
    assert forwarded == [(tuple(original["source_ranges"]), True, True)]
    assert params == original
