from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


class SemanticTableError(ValueError):
    """Raised when observed worksheet structure cannot satisfy a semantic action."""


_A1_RANGE = re.compile(
    r"^\$?[A-Za-z]{1,4}\$?[1-9][0-9]*(?::\$?[A-Za-z]{1,4}\$?[1-9][0-9]*)?$"
)


def resolve_sheet_range_reference(
    source_sheet: str, source_range: str
) -> tuple[str, str]:
    """Resolve equivalent Sheet!A1:B2 input without rewriting the public payload."""

    def qualified(value: str) -> tuple[str, str] | None:
        if "!" not in value:
            return None
        sheet, coordinates = value.rsplit("!", 1)
        sheet = sheet.strip()
        coordinates = coordinates.strip()
        if not sheet or not _A1_RANGE.fullmatch(coordinates):
            return None
        if len(sheet) >= 2 and sheet.startswith("'") and sheet.endswith("'"):
            sheet = sheet[1:-1].replace("''", "'")
        return sheet, coordinates

    def normalized_range(value: str) -> str:
        return value.replace("$", "").upper()

    sheet_reference = qualified(source_sheet)
    range_reference = qualified(source_range)
    if sheet_reference is not None:
        resolved_sheet, qualified_range = sheet_reference
        compared_range = range_reference[1] if range_reference else source_range
        if normalized_range(qualified_range) != normalized_range(compared_range):
            raise SemanticTableError(
                "qualified source_sheet range must match source_range"
            )
        if (
            range_reference
            and range_reference[0].casefold() != resolved_sheet.casefold()
        ):
            raise SemanticTableError(
                "qualified source_sheet and source_range must name the same sheet"
            )
        return resolved_sheet, compared_range
    if range_reference is not None:
        qualified_sheet, coordinates = range_reference
        if qualified_sheet.casefold() != source_sheet.strip().casefold():
            raise SemanticTableError(
                "qualified source_range must agree with source_sheet"
            )
        return source_sheet.strip(), coordinates
    return source_sheet.strip(), source_range.strip()


def column_label(index: int) -> str:
    if index < 0:
        raise SemanticTableError("column index must be non-negative")
    label = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def _coordinate(column: int, row: int) -> str:
    return f"{column_label(column)}{row + 1}"


def _range(start_column: int, start_row: int, end_column: int, end_row: int) -> str:
    start = _coordinate(start_column, start_row)
    end = _coordinate(end_column, end_row)
    return start if start == end else f"{start}:{end}"


def _rectangular(matrix: Sequence[Sequence[Any]], *, name: str) -> int:
    if not matrix or not matrix[0]:
        raise SemanticTableError(f"{name} must be a non-empty rectangular matrix")
    width = len(matrix[0])
    if any(len(row) != width for row in matrix):
        raise SemanticTableError(f"{name} must be rectangular")
    return width


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def plan_append_summary_rows(
    display_text: Sequence[Sequence[Any]],
    kinds: Sequence[Sequence[str]],
    *,
    start_column: int,
    start_row: int,
    summaries: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Plan formula-backed rows appended below an observed header/data table."""
    width = _rectangular(display_text, name="display_text")
    if _rectangular(kinds, name="kinds") != width or len(kinds) != len(display_text):
        raise SemanticTableError("display_text and kinds must have identical geometry")
    if len(display_text) < 2:
        raise SemanticTableError("source table needs one header row and one data row")
    if not summaries:
        raise SemanticTableError("summaries must not be empty")

    numeric_columns = [
        column
        for column in range(1, width)
        if any(row[column] in {"number", "formula"} for row in kinds[1:])
    ]
    if not numeric_columns:
        raise SemanticTableError(
            "source table has no numeric data columns after its label column"
        )

    first_data_row = start_row + 1
    last_data_row = start_row + len(display_text) - 1
    next_row = start_row + len(display_text)
    planned: list[dict[str, Any]] = []
    row_by_label: dict[str, int] = {}

    for index, raw in enumerate(summaries):
        label = str(raw.get("label", "")).strip()
        operation = str(raw.get("operation", "")).strip().casefold()
        if not label:
            raise SemanticTableError(f"summaries[{index}].label must not be empty")
        if _normalized(label) in row_by_label:
            raise SemanticTableError("summary labels must be unique")
        destination_row = next_row + index
        cells: list[dict[str, Any]] = [
            {
                "coordinate": _coordinate(start_column, destination_row),
                "kind": "string",
                "value": label,
            }
        ]

        if operation == "column_sum":
            for relative_column in numeric_columns:
                absolute_column = start_column + relative_column
                source = _range(
                    absolute_column,
                    first_data_row,
                    absolute_column,
                    last_data_row,
                )
                cells.append(
                    {
                        "coordinate": _coordinate(absolute_column, destination_row),
                        "kind": "formula",
                        "formula": f"=SUM({source})",
                    }
                )
        elif operation == "period_over_period_change":
            based_on = _normalized(raw.get("based_on", ""))
            base_row = row_by_label.get(based_on)
            if base_row is None:
                raise SemanticTableError(
                    f"summaries[{index}].based_on must name an earlier summary row"
                )
            first_numeric = numeric_columns[0]
            cells.append(
                {
                    "coordinate": _coordinate(
                        start_column + first_numeric, destination_row
                    ),
                    "kind": "blank",
                }
            )
            for previous_relative, current_relative in zip(
                numeric_columns, numeric_columns[1:]
            ):
                previous = _coordinate(start_column + previous_relative, base_row)
                current = _coordinate(start_column + current_relative, base_row)
                destination = _coordinate(
                    start_column + current_relative, destination_row
                )
                cells.append(
                    {
                        "coordinate": destination,
                        "kind": "formula",
                        "formula": f'=IFERROR(({current}-{previous})/{previous};"")',
                    }
                )
        else:
            raise SemanticTableError(
                f"summaries[{index}].operation is unsupported: {operation}"
            )

        planned.append(
            {
                "label": label,
                "operation": operation,
                "row": destination_row,
                "range": _range(
                    start_column,
                    destination_row,
                    start_column + width - 1,
                    destination_row,
                ),
                "cells": cells,
            }
        )
        row_by_label[_normalized(label)] = destination_row
    return planned


def plan_ratio_column(
    display_text: Sequence[Sequence[Any]],
    kinds: Sequence[Sequence[str]],
    *,
    start_column: int,
    start_row: int,
    numerator_header: str,
    denominator_header: str,
) -> dict[str, Any]:
    """Plan a formula-backed numerator/denominator column beside a live table."""
    width = _rectangular(display_text, name="display_text")
    if _rectangular(kinds, name="kinds") != width or len(kinds) != len(display_text):
        raise SemanticTableError("display_text and kinds must have identical geometry")
    if len(display_text) < 2:
        raise SemanticTableError(
            "source table needs a header and at least one data row"
        )
    headers = [_normalized(value) for value in display_text[0]]

    def resolve(name: str) -> int:
        matches = [
            index for index, header in enumerate(headers) if header == _normalized(name)
        ]
        if len(matches) != 1:
            raise SemanticTableError(
                f"header {name!r} must match exactly one source column"
            )
        return matches[0]

    numerator = resolve(numerator_header)
    denominator = resolve(denominator_header)
    if numerator == denominator:
        raise SemanticTableError("numerator and denominator headers must be different")
    for relative_row in range(1, len(display_text)):
        for column, role in ((numerator, "numerator"), (denominator, "denominator")):
            if kinds[relative_row][column] not in {"number", "formula"}:
                raise SemanticTableError(
                    f"{role} column contains a non-numeric data cell at row {start_row + relative_row + 1}"
                )
    destination_column = start_column + width
    formulas = []
    for relative_row in range(1, len(display_text)):
        absolute_row = start_row + relative_row
        numerator_cell = _coordinate(start_column + numerator, absolute_row)
        denominator_cell = _coordinate(start_column + denominator, absolute_row)
        formulas.append(
            {
                "coordinate": _coordinate(destination_column, absolute_row),
                "formula": f"={numerator_cell}/{denominator_cell}",
            }
        )
    return {
        "destination_column": destination_column,
        "header_coordinate": _coordinate(destination_column, start_row),
        "data_range": _range(
            destination_column,
            start_row + 1,
            destination_column,
            start_row + len(display_text) - 1,
        ),
        "output_range": _range(
            destination_column,
            start_row,
            destination_column,
            start_row + len(display_text) - 1,
        ),
        "formulas": formulas,
    }


def plan_date_offset_column(
    display_text: Sequence[Sequence[Any]],
    kinds: Sequence[Sequence[str]],
    date_formatted: Sequence[Sequence[bool]],
    *,
    start_column: int,
    start_row: int,
    date_header: str,
    duration_header: str,
    duration_unit: str,
) -> dict[str, Any]:
    """Plan a formula-backed date-plus-duration column beside a live table."""
    width = _rectangular(display_text, name="display_text")
    if _rectangular(kinds, name="kinds") != width or len(kinds) != len(display_text):
        raise SemanticTableError("display_text and kinds must have identical geometry")
    if _rectangular(date_formatted, name="date_formatted") != width or len(
        date_formatted
    ) != len(display_text):
        raise SemanticTableError(
            "display_text and date_formatted must have identical geometry"
        )
    if len(display_text) < 2:
        raise SemanticTableError(
            "source table needs a header and at least one data row"
        )
    if duration_unit not in {"days", "weeks", "months", "years"}:
        raise SemanticTableError(f"unsupported duration unit: {duration_unit}")

    headers = [_normalized(value) for value in display_text[0]]

    def resolve(name: str) -> int:
        matches = [
            index for index, header in enumerate(headers) if header == _normalized(name)
        ]
        if len(matches) != 1:
            raise SemanticTableError(
                f"header {name!r} must match exactly one source column"
            )
        return matches[0]

    date_column = resolve(date_header)
    duration_column = resolve(duration_header)
    if date_column == duration_column:
        raise SemanticTableError("date and duration headers must be different")
    explicit_units = {
        unit
        for unit, pattern in (
            ("days", r"\bdays?\b"),
            ("weeks", r"\bweeks?\b"),
            ("months", r"\bmonths?\b"),
            ("years", r"\byears?\b"),
        )
        if re.search(pattern, _normalized(duration_header))
    }
    if len(explicit_units) == 1 and duration_unit not in explicit_units:
        observed_unit = next(iter(explicit_units))
        raise SemanticTableError(
            f"duration unit {duration_unit!r} conflicts with header unit {observed_unit!r}"
        )
    for relative_row in range(1, len(display_text)):
        absolute_row = start_row + relative_row + 1
        if kinds[relative_row][date_column] not in {"number", "formula"}:
            raise SemanticTableError(
                f"date column contains a non-numeric data cell at row {absolute_row}"
            )
        if not date_formatted[relative_row][date_column]:
            raise SemanticTableError(
                f"date column contains a non-date-formatted cell at row {absolute_row}"
            )
        if kinds[relative_row][duration_column] not in {"number", "formula"}:
            raise SemanticTableError(
                f"duration column contains a non-numeric data cell at row {absolute_row}"
            )

    destination_column = start_column + width
    formulas: list[dict[str, str]] = []
    for relative_row in range(1, len(display_text)):
        absolute_row = start_row + relative_row
        date_cell = _coordinate(start_column + date_column, absolute_row)
        duration_cell = _coordinate(start_column + duration_column, absolute_row)
        if duration_unit == "days":
            formula = f"={date_cell}+{duration_cell}"
        elif duration_unit == "weeks":
            formula = f"={date_cell}+({duration_cell}*7)"
        elif duration_unit == "months":
            formula = f"=EDATE({date_cell};{duration_cell})"
        else:
            formula = f"=EDATE({date_cell};{duration_cell}*12)"
        formulas.append(
            {
                "coordinate": _coordinate(destination_column, absolute_row),
                "formula": formula,
            }
        )
    return {
        "date_column": date_column,
        "duration_column": duration_column,
        "destination_column": destination_column,
        "header_coordinate": _coordinate(destination_column, start_row),
        "data_range": _range(
            destination_column,
            start_row + 1,
            destination_column,
            start_row + len(display_text) - 1,
        ),
        "output_range": _range(
            destination_column,
            start_row,
            destination_column,
            start_row + len(display_text) - 1,
        ),
        "formulas": formulas,
    }


@dataclass(frozen=True)
class TableBlock:
    title: str
    header_row: int
    first_data_row: int
    last_data_row: int
    category_column: int
    value_column: int


@dataclass(frozen=True)
class SummaryRowChart:
    row_label: str
    row: int
    source_ranges: tuple[str, ...]


def _row_has_content(row: Sequence[Any]) -> bool:
    return any(str(value).strip() for value in row)


def contiguous_table_row_count(
    display_text: Sequence[Sequence[Any]],
    *,
    minimum_rows: int = 2,
    stop_labels: Sequence[str] = (),
) -> int:
    """Return the leading contiguous table height from a live worksheet slice."""
    _rectangular(display_text, name="display_text")
    normalized_stops = {
        _normalized(value) for value in stop_labels if str(value).strip()
    }
    count = 0
    for row in display_text:
        if not _row_has_content(row):
            break
        if count >= minimum_rows and _normalized(row[0]) in normalized_stops:
            break
        count += 1
    if count < minimum_rows:
        raise SemanticTableError(
            f"source table needs at least {minimum_rows} contiguous populated rows"
        )
    return count


def stacked_destination_row(
    requested_row: int,
    requested_column: int,
    existing_outputs: Sequence[Mapping[str, int]],
    *,
    gap_rows: int,
) -> int:
    """Move an append destination below overlapping live table outputs."""
    if requested_row < 0 or requested_column < 0 or gap_rows < 0:
        raise SemanticTableError("stacked destination coordinates must be non-negative")
    next_row = requested_row
    for output in existing_outputs:
        start_column = int(output["start_column"])
        end_column = int(output["end_column"])
        end_row = int(output["end_row"])
        if start_column <= requested_column <= end_column:
            next_row = max(next_row, end_row + gap_rows + 1)
    return next_row


def next_content_row(
    values: Sequence[Sequence[Any]],
    formulas: Sequence[Sequence[Any]] | None = None,
    *,
    start_row: int = 0,
) -> int:
    """Return the zero-based row immediately below the last live value or formula."""
    width = _rectangular(values, name="values")
    if start_row < 0:
        raise SemanticTableError("start_row must be non-negative")
    if formulas is not None:
        if _rectangular(formulas, name="formulas") != width or len(formulas) != len(
            values
        ):
            raise SemanticTableError("values and formulas must have identical geometry")

    def populated(value: Any) -> bool:
        if value is None:
            return False
        return not isinstance(value, str) or bool(value.strip())

    for offset in range(len(values) - 1, -1, -1):
        if any(populated(value) for value in values[offset]):
            return start_row + offset + 1
        if formulas is not None and any(populated(value) for value in formulas[offset]):
            return start_row + offset + 1
    return start_row


def _contiguous_row_blocks(
    display_text: Sequence[Sequence[Any]],
) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    start: int | None = None
    for index, row in enumerate(display_text):
        if _row_has_content(row):
            if start is None:
                start = index
        elif start is not None:
            blocks.append((start, index - 1))
            start = None
    if start is not None:
        blocks.append((start, len(display_text) - 1))
    return blocks


def _resolve_header_column(
    header: Sequence[Any],
    kinds: Sequence[Sequence[str]],
    *,
    selector: str,
    first_data_row: int,
    last_data_row: int,
) -> int:
    normalized_selector = _normalized(selector)
    if normalized_selector == "first":
        return 0
    if normalized_selector == "last":
        numeric = [
            column
            for column in range(len(header))
            if any(
                kinds[row][column] in {"number", "formula"}
                for row in range(first_data_row, last_data_row + 1)
            )
        ]
        if not numeric:
            raise SemanticTableError("table block has no numeric value column")
        return numeric[-1]
    matches = [
        index
        for index, value in enumerate(header)
        if _normalized(value) == normalized_selector
    ]
    if len(matches) != 1:
        raise SemanticTableError(
            f"column selector {selector!r} must match exactly one observed header"
        )
    return matches[0]


def plan_table_block_charts(
    display_text: Sequence[Sequence[Any]],
    kinds: Sequence[Sequence[str]],
    *,
    start_column: int,
    start_row: int,
    category_column: str = "first",
    value_column: str = "last",
) -> list[TableBlock]:
    """Resolve repeated, blank-row-separated vertical tables into one-series charts."""
    width = _rectangular(display_text, name="display_text")
    if _rectangular(kinds, name="kinds") != width or len(kinds) != len(display_text):
        raise SemanticTableError("display_text and kinds must have identical geometry")

    planned: list[TableBlock] = []
    for block_start, block_end in _contiguous_row_blocks(display_text):
        if block_end - block_start + 1 < 2:
            continue
        first_values = [str(value).strip() for value in display_text[block_start]]
        title_values = [value for value in first_values if value]
        has_title_row = len(title_values) == 1 and block_end - block_start + 1 >= 3
        header_row = block_start + 1 if has_title_row else block_start
        first_data_row = header_row + 1
        last_data_row = block_end
        while last_data_row >= first_data_row:
            label = _normalized(display_text[last_data_row][0])
            if not label or label in {"total", "subtotal", "grand total"}:
                last_data_row -= 1
                continue
            break
        if last_data_row < first_data_row:
            continue

        header = display_text[header_row]
        category = _resolve_header_column(
            header,
            kinds,
            selector=category_column,
            first_data_row=first_data_row,
            last_data_row=last_data_row,
        )
        value = _resolve_header_column(
            header,
            kinds,
            selector=value_column,
            first_data_row=first_data_row,
            last_data_row=last_data_row,
        )
        if category == value:
            raise SemanticTableError("category and value columns must be different")
        title = title_values[0] if has_title_row else str(header[value]).strip()
        planned.append(
            TableBlock(
                title=title,
                header_row=start_row + header_row,
                first_data_row=start_row + first_data_row,
                last_data_row=start_row + last_data_row,
                category_column=start_column + category,
                value_column=start_column + value,
            )
        )
    if not planned:
        raise SemanticTableError("source range contains no chartable table blocks")
    return planned


def plan_chart_ranges_by_headers(
    display_text: Sequence[Sequence[Any]],
    *,
    start_column: int,
    start_row: int,
    x_header: str,
    y_headers: Sequence[str],
) -> list[str]:
    """Resolve model-selected header names to existing chart source ranges."""
    width = _rectangular(display_text, name="display_text")
    if len(display_text) < 2:
        raise SemanticTableError(
            "source table needs a header and at least one data row"
        )
    if not y_headers:
        raise SemanticTableError("y_headers must not be empty")
    headers = [_normalized(value) for value in display_text[0]]

    def resolve(name: str) -> int:
        matches = [
            index for index, header in enumerate(headers) if header == _normalized(name)
        ]
        if len(matches) != 1:
            raise SemanticTableError(
                f"header {name!r} must match exactly one source column"
            )
        return matches[0]

    indices = [resolve(x_header), *(resolve(name) for name in y_headers)]
    if len(indices) != len(set(indices)):
        raise SemanticTableError("x_header and y_headers must select distinct columns")
    last_row = start_row + len(display_text) - 1
    return [
        _range(start_column + index, start_row, start_column + index, last_row)
        for index in indices
        if 0 <= index < width
    ]


def plan_summary_row_charts(
    display_text: Sequence[Sequence[Any]],
    *,
    start_column: int,
    start_row: int,
    source_data_rows: int,
    series: Sequence[Mapping[str, Any]],
) -> list[SummaryRowChart]:
    """Resolve named rows below a table to row-oriented chart source ranges."""
    width = _rectangular(display_text, name="display_text")
    if source_data_rows < 2 or source_data_rows > len(display_text):
        raise SemanticTableError("source_data_rows is outside the observed range")
    if not series:
        raise SemanticTableError("series must not be empty")
    headers = [_normalized(value) for value in display_text[0]]
    label_rows: dict[str, list[int]] = {}
    for relative_row in range(source_data_rows, len(display_text)):
        label = _normalized(display_text[relative_row][0])
        if label:
            label_rows.setdefault(label, []).append(relative_row)

    planned = []
    for index, spec in enumerate(series):
        row_label = str(spec.get("row_label", "")).strip()
        matches = label_rows.get(_normalized(row_label), [])
        if len(matches) != 1:
            raise SemanticTableError(
                f"series[{index}].row_label must match exactly one appended row"
            )
        row = matches[0]
        omitted = {_normalized(value) for value in spec.get("omit_categories", [])}
        included_columns = [
            column
            for column in range(1, width)
            if headers[column]
            and headers[column] not in omitted
            and str(display_text[row][column]).strip()
        ]
        if not included_columns:
            raise SemanticTableError(
                f"series[{index}] omits or has a blank value for every observed category column"
            )
        runs: list[tuple[int, int]] = []
        for column in included_columns:
            if runs and column == runs[-1][1] + 1:
                runs[-1] = (runs[-1][0], column)
            else:
                runs.append((column, column))

        def row_ranges(absolute_row: int) -> list[str]:
            resolved = []
            first_start, first_end = runs[0]
            if first_start == 1:
                resolved.append(
                    _range(
                        start_column,
                        absolute_row,
                        start_column + first_end,
                        absolute_row,
                    )
                )
                remaining = runs[1:]
            else:
                resolved.append(
                    _range(start_column, absolute_row, start_column, absolute_row)
                )
                remaining = runs
            resolved.extend(
                _range(
                    start_column + run_start,
                    absolute_row,
                    start_column + run_end,
                    absolute_row,
                )
                for run_start, run_end in remaining
            )
            return resolved

        ranges = (*row_ranges(start_row), *row_ranges(start_row + row))
        planned.append(
            SummaryRowChart(
                row_label=row_label,
                row=start_row + row,
                source_ranges=ranges,
            )
        )
    return planned


def extreme_coordinates(
    values: Sequence[Sequence[Any]],
    kinds: Sequence[Sequence[str]],
    *,
    start_column: int,
    start_row: int,
    mode: str,
    ties: str,
) -> tuple[float, list[str]]:
    """Return coordinates of the observed numeric minimum or maximum."""
    width = _rectangular(values, name="values")
    if _rectangular(kinds, name="kinds") != width or len(kinds) != len(values):
        raise SemanticTableError("values and kinds must have identical geometry")
    candidates: list[tuple[float, str]] = []
    for row, value_row in enumerate(values):
        for column, value in enumerate(value_row):
            if kinds[row][column] not in {"number", "formula"} or isinstance(
                value, bool
            ):
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(numeric):
                candidates.append(
                    (numeric, _coordinate(start_column + column, start_row + row))
                )
    if not candidates:
        raise SemanticTableError("range contains no finite numeric cells")
    if mode == "max":
        extreme = max(value for value, _coordinate_value in candidates)
    elif mode == "min":
        extreme = min(value for value, _coordinate_value in candidates)
    else:
        raise SemanticTableError("mode must be max or min")
    coordinates = [coordinate for value, coordinate in candidates if value == extreme]
    if ties == "first":
        coordinates = coordinates[:1]
    elif ties != "all":
        raise SemanticTableError("ties must be all or first")
    return extreme, coordinates
