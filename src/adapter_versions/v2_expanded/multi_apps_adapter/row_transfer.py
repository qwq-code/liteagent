from __future__ import annotations

from typing import Any, Mapping

from .errors import AdapterError


def _display_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


def _normalized(value: Any, *, case_sensitive: bool) -> str:
    text = _display_text(value).strip()
    return text if case_sensitive else text.casefold()


def select_matching_rows(
    workbook: Mapping[str, Any], params: Mapping[str, Any]
) -> dict[str, Any]:
    """Select displayed spreadsheet rows using only explicit model parameters."""
    sheets = workbook.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        raise AdapterError(
            "SOURCE_EMPTY",
            "the spreadsheet reader returned no sheets",
            {"path": workbook.get("path")},
            422,
        )
    if workbook.get("truncated"):
        raise AdapterError(
            "SOURCE_TRUNCATED",
            "the spreadsheet source was truncated; provide a narrower sheet or range",
            {
                "path": workbook.get("path"),
                "sheet_count": workbook.get("sheet_count"),
                "returned_sheet_count": workbook.get("returned_sheet_count"),
            },
            422,
        )

    wanted_header = _normalized(params["match_column"], case_sensitive=False)
    requested_header_row = params.get("header_row")
    header_matches: list[tuple[dict[str, Any], int, int, list[list[Any]]]] = []
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        matrix = sheet.get("display_text")
        if not isinstance(matrix, list):
            continue
        candidate_indices = (
            [requested_header_row - 1]
            if isinstance(requested_header_row, int)
            and 0 < requested_header_row <= len(matrix)
            else range(len(matrix))
            if requested_header_row is None
            else []
        )
        for row_index in candidate_indices:
            row = matrix[row_index]
            if not isinstance(row, list):
                continue
            for column_index, value in enumerate(row):
                if _normalized(value, case_sensitive=False) == wanted_header:
                    header_matches.append((sheet, row_index, column_index, matrix))

    if not header_matches:
        raise AdapterError(
            "HEADER_NOT_FOUND",
            "params.match_column did not identify a spreadsheet header",
            {
                "match_column": params["match_column"],
                "header_row": requested_header_row,
                "sheet_names": [
                    sheet.get("name") for sheet in sheets if isinstance(sheet, dict)
                ],
            },
            404,
        )
    if len(header_matches) != 1:
        raise AdapterError(
            "HEADER_NOT_UNIQUE",
            "params.match_column matched more than one spreadsheet header",
            {
                "match_column": params["match_column"],
                "matches": [
                    {
                        "sheet": sheet.get("name"),
                        "row": row_index + 1,
                        "column": column_index + 1,
                    }
                    for sheet, row_index, column_index, _matrix in header_matches
                ],
            },
            422,
        )

    sheet, header_index, match_column_index, matrix = header_matches[0]
    header = matrix[header_index]
    if not isinstance(header, list) or not header:
        raise AdapterError(
            "SOURCE_EMPTY", "the matched header row is empty", status_code=422
        )

    value_case_sensitive = bool(params.get("value_case_sensitive", False))
    wanted_values = {
        _normalized(value, case_sensitive=value_case_sensitive): _display_text(value)
        for value in params["match_values"]
    }
    selected: list[list[Any]] = []
    found_values: set[str] = set()
    available_values: list[str] = []
    for row_number, row in enumerate(
        matrix[header_index + 1 :], start=header_index + 2
    ):
        if not isinstance(row, list) or match_column_index >= len(row):
            raise AdapterError(
                "SOURCE_NOT_RECTANGULAR",
                "a spreadsheet data row is shorter than the matched header column",
                {"sheet": sheet.get("name"), "row": row_number},
                422,
            )
        if len(row) != len(header):
            raise AdapterError(
                "SOURCE_NOT_RECTANGULAR",
                "the spreadsheet source is not rectangular",
                {
                    "sheet": sheet.get("name"),
                    "row": row_number,
                    "header_columns": len(header),
                    "row_columns": len(row),
                },
                422,
            )
        actual_text = _display_text(row[match_column_index])
        if len(available_values) < 100:
            available_values.append(actual_text)
        normalized_value = _normalized(
            row[match_column_index], case_sensitive=value_case_sensitive
        )
        if normalized_value in wanted_values:
            selected.append(row)
            found_values.add(normalized_value)

    missing = [
        original
        for normalized, original in wanted_values.items()
        if normalized not in found_values
    ]
    if missing:
        raise AdapterError(
            "ROWS_NOT_FOUND",
            "one or more params.match_values were not found below the matched header",
            {
                "match_column": params["match_column"],
                "missing_values": missing,
                "available_values": available_values,
                "sheet": sheet.get("name"),
            },
            404,
        )

    output_rows = ([header] if params.get("include_header", True) else []) + selected
    if not output_rows:
        raise AdapterError(
            "ROWS_NOT_FOUND",
            "the requested selection produced no output rows",
            {"match_column": params["match_column"]},
            404,
        )
    if len(output_rows) > 200:
        raise AdapterError(
            "OUTPUT_TOO_LARGE",
            "the selected table exceeds the Writer limit of 200 rows",
            {
                "selected_rows": len(selected),
                "include_header": bool(params.get("include_header", True)),
            },
            422,
        )

    return {
        "rows": output_rows,
        "source_path": workbook.get("path"),
        "source_sheet": sheet.get("name"),
        "source_range": sheet.get("returned_range"),
        "header_row": header_index + 1,
        "match_column": _display_text(header[match_column_index]),
        "match_column_index": match_column_index + 1,
        "requested_values": [_display_text(value) for value in params["match_values"]],
        "selected_row_count": len(selected),
        "include_header": bool(params.get("include_header", True)),
    }
