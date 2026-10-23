from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from calc_adapter import uno_worker
from calc_adapter.errors import AdapterError


class _Cell:
    def __init__(self, *, formula: str = "", cell_type: str = "EMPTY") -> None:
        self._formula = formula
        self._cell_type = cell_type

    def getFormula(self) -> str:
        return self._formula

    def getType(self) -> str:
        return self._cell_type


class _Range:
    def __init__(
        self,
        *,
        column: int = 0,
        row: int = 0,
        cell: _Cell | None = None,
        merged: bool = False,
    ) -> None:
        self._column = column
        self._row = row
        self._cell = cell or _Cell()
        self.IsMerged = merged

    def getCellAddress(self) -> SimpleNamespace:
        return SimpleNamespace(Column=self._column, Row=self._row)

    def getRangeAddress(self) -> SimpleNamespace:
        return SimpleNamespace(
            StartColumn=self._column,
            StartRow=self._row,
            EndColumn=self._column,
            EndRow=self._row,
        )

    def getCellByPosition(self, column: int, row: int) -> _Cell:
        assert (column, row) == (0, 0)
        return self._cell


class _Pivot:
    def __init__(self, output: SimpleNamespace) -> None:
        self._output = output

    def getOutputRange(self) -> SimpleNamespace:
        return self._output


class _Tables:
    def __init__(self, outputs: dict[str, SimpleNamespace] | None = None) -> None:
        self._outputs = outputs or {}

    def getElementNames(self) -> tuple[str, ...]:
        return tuple(self._outputs)

    def getByName(self, name: str) -> _Pivot:
        return _Pivot(self._outputs[name])

    def add(self, name: str, output: SimpleNamespace) -> None:
        self._outputs[name] = output

    def hasByName(self, name: str) -> bool:
        return name in self._outputs

    def removeByName(self, name: str) -> None:
        del self._outputs[name]


class _Sheet:
    def __init__(
        self,
        target: _Range | dict[str, _Range],
        tables: _Tables | None = None,
    ) -> None:
        self._targets = target if isinstance(target, dict) else {"A1": target}
        self._tables = tables or _Tables()

    def getCellRangeByName(self, name: str) -> _Range:
        return self._targets[name]

    def getDataPilotTables(self) -> _Tables:
        return self._tables


def _params(**overrides: object) -> dict[str, object]:
    params: dict[str, object] = {
        "source_sheet": "Data",
        "source_range": "A1:D41",
        "destination_sheet": "Summary",
        "destination": "A1",
        "fields": ["Region"],
    }
    params.update(overrides)
    return params


@pytest.mark.parametrize(
    ("cell", "merged"),
    [
        (_Cell(formula="Heading", cell_type="TEXT"), False),
        (_Cell(formula="42", cell_type="VALUE"), False),
        (_Cell(formula="=SUM(B2:B4)", cell_type="FORMULA"), False),
        (_Cell(), True),
    ],
)
def test_explicit_destination_rejects_live_non_pivot_content(
    cell: _Cell, merged: bool
) -> None:
    params = _params()
    original = deepcopy(params)
    sheet = _Sheet(_Range(cell=cell, merged=merged))

    with pytest.raises(AdapterError) as caught:
        uno_worker._assert_stacked_pivot_anchor_available(
            sheet,
            params,
            column=0,
            row=0,
            existing_outputs=[],
        )

    assert caught.value.code == "CONFLICT"
    assert caught.value.http_status == 409
    assert caught.value.details["destination"] == "A1"
    assert params == original


def test_replace_does_not_authorize_overwriting_non_pivot_content() -> None:
    params = _params(replace=True)
    sheet = _Sheet(_Range(cell=_Cell(formula="Keep me", cell_type="TEXT")))

    with pytest.raises(AdapterError, match="live worksheet content"):
        uno_worker._assert_stacked_pivot_anchor_available(
            sheet,
            params,
            column=0,
            row=0,
            existing_outputs=[],
        )


def test_blank_explicit_destination_and_semantic_placement_are_allowed() -> None:
    sheet = _Sheet(_Range(cell=_Cell()))
    uno_worker._assert_stacked_pivot_anchor_available(
        sheet,
        _params(),
        column=0,
        row=0,
        existing_outputs=[],
    )
    placement_params = _params(placement="below_existing_content")
    placement_params.pop("destination")
    uno_worker._assert_stacked_pivot_anchor_available(
        sheet,
        placement_params,
        column=0,
        row=1,
        existing_outputs=[],
    )


def test_existing_pivot_output_keeps_append_semantics() -> None:
    params = _params()
    sheet = _Sheet(_Range(cell=_Cell(formula="Region", cell_type="TEXT")))
    existing = [{"start_column": 0, "start_row": 0, "end_column": 1, "end_row": 3}]

    uno_worker._assert_stacked_pivot_anchor_available(
        sheet,
        params,
        column=0,
        row=0,
        existing_outputs=existing,
    )
    assert uno_worker.stacked_destination_row(0, 0, existing, gap_rows=1) == 5


@pytest.mark.parametrize(
    ("action", "action_params"),
    [
        (
            uno_worker._pivot_create_stacked,
            _params(),
        ),
        (
            uno_worker._pivot_create_stacked_aggregate,
            _params(
                fields=None,
                group_fields=["Region"],
                value_field="Sales",
                aggregation="sum",
            ),
        ),
    ],
)
def test_both_stacked_pivot_actions_check_destination_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
    action: object,
    action_params: dict[str, object],
) -> None:
    source = _Range()
    destination = _Sheet(
        _Range(cell=_Cell(formula="Protected title", cell_type="TEXT"))
    )
    session = SimpleNamespace(
        doc=object(),
        sheet=lambda name: source if name == "Data" else destination,
    )
    monkeypatch.setattr(
        uno_worker,
        "_expanded_contiguous_source",
        lambda *_args, **_kwargs: (
            source,
            {"display_text": [["Region", "Sales"]], "kinds": [["string", "string"]]},
        ),
    )
    monkeypatch.setattr(
        uno_worker,
        "resolve_stacked_aggregate_fields",
        lambda *_args, **_kwargs: SimpleNamespace(
            group_fields=("Region",), value_field="Sales", aggregation="sum"
        ),
    )

    with pytest.raises(AdapterError) as caught:
        action(session, action_params)

    assert caught.value.code == "CONFLICT"


def test_auto_shifted_destination_is_checked_after_existing_pivot_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _Range()
    tables = _Tables(
        {"Existing": SimpleNamespace(StartColumn=0, StartRow=0, EndColumn=1, EndRow=3)}
    )
    destination = _Sheet(
        {
            "A1": _Range(cell=_Cell(formula="Region", cell_type="TEXT")),
            "A6": _Range(row=5, cell=_Cell(formula="Keep me", cell_type="TEXT")),
        },
        tables,
    )
    session = SimpleNamespace(
        doc=object(),
        sheet=lambda name: source if name == "Data" else destination,
    )
    monkeypatch.setattr(
        uno_worker,
        "_expanded_contiguous_source",
        lambda *_args, **_kwargs: (source, {}),
    )

    with pytest.raises(AdapterError) as caught:
        uno_worker._pivot_create_stacked(session, _params(gap_rows=1))

    assert caught.value.code == "CONFLICT"
    assert caught.value.details["destination"] == "A6"
    assert tables.getElementNames() == ("Existing",)


def test_later_pivot_destination_conflict_rolls_back_created_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _Range()
    tables = _Tables()
    destination = _Sheet(
        {
            "A1": _Range(cell=_Cell()),
            "A6": _Range(row=5, cell=_Cell(formula="Keep me", cell_type="TEXT")),
        },
        tables,
    )
    session = SimpleNamespace(
        doc=object(),
        sheet=lambda name: source if name == "Data" else destination,
    )
    monkeypatch.setattr(
        uno_worker,
        "_expanded_contiguous_source",
        lambda *_args, **_kwargs: (source, {}),
    )
    calls: list[str] = []

    def create_pivot(_session: object, params: dict[str, object]) -> dict[str, object]:
        calls.append(str(params["destination"]))
        tables.add(
            str(params["name"]),
            SimpleNamespace(StartColumn=0, StartRow=0, EndColumn=1, EndRow=3),
        )
        return {
            "name": params["name"],
            "source_range": params["source_range"],
            "destination": params["destination"],
        }

    monkeypatch.setattr(uno_worker, "_pivot_create", create_pivot)

    with pytest.raises(AdapterError) as caught:
        uno_worker._pivot_create_stacked(
            session,
            _params(fields=["Region", "Tier"], gap_rows=1),
        )

    assert caught.value.code == "CONFLICT"
    assert caught.value.details["destination"] == "A6"
    assert calls == ["A1"]
    assert tables.getElementNames() == ()
