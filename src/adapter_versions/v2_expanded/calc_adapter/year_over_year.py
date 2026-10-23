from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any


class YearOverYearError(ValueError):
    """Raised when a live table cannot satisfy a year-over-year summary request."""


MAX_CALC_COLUMNS = 16_384
MAX_CALC_ROWS = 1_048_576


def destination_a1(column: str, row: int) -> str:
    """Convert explicit model-selected Calc placement fields to one A1 cell."""
    if not isinstance(column, str) or re.fullmatch(r"[A-Z]{1,3}", column) is None:
        raise YearOverYearError(
            "destination_column must contain one to three uppercase ASCII letters"
        )
    column_number = 0
    for character in column:
        column_number = column_number * 26 + ord(character) - ord("A") + 1
    if column_number > MAX_CALC_COLUMNS:
        raise YearOverYearError("destination_column exceeds Calc column XFD")
    if (
        isinstance(row, bool)
        or not isinstance(row, int)
        or not 1 <= row <= MAX_CALC_ROWS
    ):
        raise YearOverYearError(
            f"destination_row must be a one-based integer from 1 to {MAX_CALC_ROWS}"
        )
    return f"{column}{row}"


def _rectangular(matrix: Sequence[Sequence[Any]], *, name: str) -> int:
    if not matrix or not matrix[0]:
        raise YearOverYearError(f"{name} must be a non-empty rectangular matrix")
    width = len(matrix[0])
    if any(len(row) != width for row in matrix):
        raise YearOverYearError(f"{name} must be rectangular")
    return width


def _normalized_header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def _canonical_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _normalized_header(value))


def _resolve_header(headers: Sequence[Any], selector: str) -> int:
    normalized = _normalized_header(selector)
    exact = [
        index
        for index, header in enumerate(headers)
        if _normalized_header(header) == normalized
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise YearOverYearError(f"header selector is ambiguous: {selector!r}")

    canonical = _canonical_header(selector)
    fallback = [
        index
        for index, header in enumerate(headers)
        if canonical and _canonical_header(header) == canonical
    ]
    if len(fallback) == 1:
        return fallback[0]
    if len(fallback) > 1:
        raise YearOverYearError(f"header selector is ambiguous: {selector!r}")
    raise YearOverYearError(f"header selector was not found: {selector!r}")


def _parse_year(value: Any) -> int | None:
    match = re.fullmatch(r"\s*([0-9]{1,4})(?:\.0+)?\s*", str(value))
    if match is None:
        return None
    return int(match.group(1))


def _column_label(index: int) -> str:
    if index < 0:
        raise YearOverYearError("column index must be non-negative")
    label = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def _coordinate(column: int, row: int) -> str:
    return f"{_column_label(column)}{row + 1}"


def _range(start_column: int, start_row: int, end_column: int, end_row: int) -> str:
    start = _coordinate(start_column, start_row)
    end = _coordinate(end_column, end_row)
    return start if start == end else f"{start}:{end}"


def _formula_sheet_reference(name: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return name
    return "'" + name.replace("'", "''") + "'"


def plan_year_over_year_summary(
    display_text: Sequence[Sequence[Any]],
    kinds: Sequence[Sequence[Any]],
    *,
    source_sheet: str,
    source_start_column: int,
    source_start_row: int,
    destination_start_column: int,
    destination_start_row: int,
    year_field: str,
    value_fields: Sequence[str],
    output_headers: Sequence[str],
    start_year: int,
    end_year: int,
) -> dict[str, Any]:
    """Plan a formula-backed year-over-year summary from a live table snapshot."""
    width = _rectangular(display_text, name="display_text")
    if _rectangular(kinds, name="kinds") != width or len(kinds) != len(display_text):
        raise YearOverYearError("display_text and kinds must have identical geometry")
    if len(display_text) < 3:
        raise YearOverYearError(
            "source table requires a header and at least two data rows"
        )
    if (
        isinstance(start_year, bool)
        or isinstance(end_year, bool)
        or not isinstance(start_year, int)
        or not isinstance(end_year, int)
        or not 1 <= start_year <= end_year <= 9999
        or end_year - start_year > 200
    ):
        raise YearOverYearError(
            "year interval must be an inclusive range of at most 201 years"
        )
    if not value_fields or any(
        not isinstance(value, str) or not value.strip() for value in value_fields
    ):
        raise YearOverYearError("value_fields must contain non-empty header selectors")
    if len({_normalized_header(value) for value in value_fields}) != len(value_fields):
        raise YearOverYearError("value_fields must be unique")
    if len(output_headers) != len(value_fields) + 1 or any(
        not isinstance(value, str) or not value.strip() for value in output_headers
    ):
        raise YearOverYearError(
            "output_headers must contain the year header followed by one header per value field"
        )
    if len({_normalized_header(value) for value in output_headers}) != len(
        output_headers
    ):
        raise YearOverYearError("output_headers must be unique")

    headers = list(display_text[0])
    year_column = _resolve_header(headers, year_field)
    value_columns = [_resolve_header(headers, field) for field in value_fields]
    if year_column in value_columns or len(set(value_columns)) != len(value_columns):
        raise YearOverYearError(
            "year and value fields must resolve to distinct columns"
        )

    row_by_year: dict[int, int] = {}
    for row_index, row in enumerate(display_text[1:], start=1):
        year = _parse_year(row[year_column])
        if year is None:
            continue
        if year in row_by_year:
            raise YearOverYearError(f"source table contains duplicate year {year}")
        row_by_year[year] = row_index

    years = list(range(start_year, end_year + 1))
    missing = sorted(
        {
            required
            for year in years
            for required in (year - 1, year)
            if required not in row_by_year
        }
    )
    if missing:
        raise YearOverYearError(
            "source table is missing requested or immediately prior years: "
            + ", ".join(str(year) for year in missing)
        )

    source_reference = _formula_sheet_reference(source_sheet)
    rows: list[dict[str, Any]] = []
    for output_offset, year in enumerate(years, start=1):
        current_row_index = row_by_year[year]
        prior_row_index = row_by_year[year - 1]
        formulas = []
        for selector, column_index in zip(value_fields, value_columns, strict=True):
            for row_index in (prior_row_index, current_row_index):
                if str(kinds[row_index][column_index]) not in {"number", "formula"}:
                    raise YearOverYearError(
                        f"value field {selector!r} is nonnumeric for year "
                        f"{_parse_year(display_text[row_index][year_column])}"
                    )
            column = _column_label(source_start_column + column_index)
            current_row = source_start_row + current_row_index + 1
            prior_row = source_start_row + prior_row_index + 1
            formulas.append(
                f"={source_reference}.{column}{current_row}/"
                f"{source_reference}.{column}{prior_row}-1"
            )
        rows.append(
            {
                "year": year,
                "destination_row": destination_start_row + output_offset,
                "source_current_row": source_start_row + current_row_index,
                "source_prior_row": source_start_row + prior_row_index,
                "formulas": formulas,
            }
        )

    end_column = destination_start_column + len(output_headers) - 1
    end_row = destination_start_row + len(years)
    return {
        "resolved_year_field": str(headers[year_column]),
        "resolved_value_fields": [str(headers[index]) for index in value_columns],
        "year_column": year_column,
        "value_columns": value_columns,
        "output_headers": list(output_headers),
        "years": years,
        "rows": rows,
        "output_range": _range(
            destination_start_column, destination_start_row, end_column, end_row
        ),
        "percentage_range": _range(
            destination_start_column + 1,
            destination_start_row + 1,
            end_column,
            end_row,
        ),
    }
