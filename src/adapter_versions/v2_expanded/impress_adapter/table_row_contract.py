from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Sequence

from .errors import AdapterError


@dataclass(frozen=True)
class LiveTable:
    path: tuple[int, ...]
    shape: Any
    model: Any
    rows: int
    columns: int


def _positive_count(model: Any, attribute: str, collection: str) -> int:
    value = getattr(model, attribute, None)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    try:
        value = int(getattr(model, collection).getCount())
    except Exception as exc:
        raise AdapterError(
            "UNSUPPORTED_OPERATION",
            "the live table does not expose usable row and column dimensions",
        ) from exc
    if value < 1:
        raise AdapterError(
            "UNSUPPORTED_OPERATION",
            "the live table must contain at least one row and one column",
        )
    return value


def table_dimensions(model: Any) -> tuple[int, int]:
    return (
        _positive_count(model, "RowCount", "Rows"),
        _positive_count(model, "ColumnCount", "Columns"),
    )


def _is_table_shape(shape: Any) -> bool:
    kind = str(
        getattr(shape, "ShapeType", "") or getattr(shape, "ImplementationName", "")
    ).casefold()
    model = getattr(shape, "Model", None)
    return "tableshape" in kind or (
        model is not None and hasattr(model, "getCellByPosition")
    )


def iter_live_tables(
    container: Any, prefix: tuple[int, ...] = ()
) -> Iterator[LiveTable]:
    try:
        count = int(container.getCount())
    except Exception as exc:
        raise AdapterError(
            "UNSUPPORTED_OPERATION",
            "the selected slide does not expose a traversable shape collection",
        ) from exc
    for index in range(count):
        shape = container.getByIndex(index)
        path = (*prefix, index)
        if _is_table_shape(shape):
            model = getattr(shape, "Model", None)
            if model is None or not hasattr(model, "getCellByPosition"):
                raise AdapterError(
                    "UNSUPPORTED_OPERATION",
                    "a live TableShape does not expose an editable table model",
                    {"path": list(path)},
                )
            rows, columns = table_dimensions(model)
            yield LiveTable(path, shape, model, rows, columns)
            continue
        if hasattr(shape, "getCount") and hasattr(shape, "getByIndex"):
            yield from iter_live_tables(shape, path)


def select_unique_live_table(container: Any) -> LiveTable:
    matches = list(iter_live_tables(container))
    if not matches:
        raise AdapterError(
            "TABLE_NOT_FOUND",
            "the selected slide does not contain a live table",
            http_status=404,
        )
    if len(matches) > 1:
        raise AdapterError(
            "TABLE_AMBIGUOUS",
            "the selected slide contains multiple live tables",
            {
                "match_count": len(matches),
                "paths": [list(match.path) for match in matches],
            },
            409,
        )
    return matches[0]


def _cell_string(model: Any, column: int, row: int) -> str:
    return str(getattr(model.getCellByPosition(column, row), "String", ""))


def _restore_row(model: Any, row: int, values: Sequence[str]) -> list[int]:
    failed_columns = []
    for column, value in enumerate(values):
        try:
            model.getCellByPosition(column, row).String = value
        except Exception:
            failed_columns.append(column)
    return failed_columns


def replace_live_table_row(
    table: LiveTable, *, row_number: int, values: Sequence[str]
) -> dict[str, Any]:
    if (
        isinstance(row_number, bool)
        or not isinstance(row_number, int)
        or row_number < 1
    ):
        raise AdapterError(
            "INVALID_REQUEST", "params.row_number must be a positive one-based integer"
        )
    if row_number > table.rows:
        raise AdapterError(
            "TABLE_ROW_NOT_FOUND",
            "the requested one-based row is outside the live table",
            {"row_number": row_number, "rows": table.rows},
            404,
        )
    if not values or any(not isinstance(value, str) for value in values):
        raise AdapterError(
            "INVALID_REQUEST", "params.values must be a non-empty array of strings"
        )
    if len(values) != table.columns:
        raise AdapterError(
            "TABLE_COLUMN_COUNT_MISMATCH",
            "the number of replacement values must equal the live table column count",
            {"value_count": len(values), "columns": table.columns},
            409,
        )

    row = row_number - 1
    previous_values = [
        _cell_string(table.model, column, row) for column in range(table.columns)
    ]
    try:
        for column, value in enumerate(values):
            table.model.getCellByPosition(column, row).String = value
    except Exception as exc:
        rollback_failures = _restore_row(table.model, row, previous_values)
        raise AdapterError(
            "TABLE_WRITE_FAILED",
            "failed to replace the complete table row",
            {"rollback_failed_columns": rollback_failures},
            422,
        ) from exc

    actual_values = [
        _cell_string(table.model, column, row) for column in range(table.columns)
    ]
    verification_passed = actual_values == list(values)
    if not verification_passed:
        rollback_failures = _restore_row(table.model, row, previous_values)
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the table row read-back does not match the requested values",
            {
                "actual_values": actual_values,
                "rollback_failed_columns": rollback_failures,
            },
            409,
        )

    return {
        "path": list(table.path),
        "name": str(getattr(table.shape, "Name", "") or ""),
        "kind": str(
            getattr(table.shape, "ShapeType", "")
            or getattr(table.shape, "ImplementationName", "")
            or ""
        ),
        "rows": table.rows,
        "columns": table.columns,
        "row_number": row_number,
        "previous_values": previous_values,
        "values": list(values),
        "actual_values": actual_values,
        "verification_passed": True,
    }


__all__ = [
    "LiveTable",
    "iter_live_tables",
    "replace_live_table_row",
    "select_unique_live_table",
    "table_dimensions",
]
