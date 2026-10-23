from __future__ import annotations

import sys
import time
from contextlib import redirect_stdout
from typing import Any

from .errors import AdapterError
from .pdf_tools import _source_file


def _load_fitz() -> Any:
    try:
        with redirect_stdout(sys.stderr):
            import fitz
    except ImportError as exc:
        raise AdapterError(
            "PDF_TABLE_LIBRARY_UNAVAILABLE",
            "the installed PyMuPDF dependency is required to inspect PDF tables",
            {"import_error": str(exc)},
            503,
        ) from exc
    if not callable(getattr(fitz.Page, "find_tables", None)):
        raise AdapterError(
            "PDF_TABLE_LIBRARY_UNAVAILABLE",
            "the installed PyMuPDF version does not provide Page.find_tables",
            http_status=503,
        )
    return fitz


def _merged_cells(table: Any) -> list[dict[str, int]]:
    # Native rows align cells at their left/top edges; a missing position is None.
    # Count those same grid origins covered by each actual cell rectangle.
    column_starts = sorted({cell[0] for cell in table.cells})
    row_starts = sorted({cell[1] for cell in table.cells})
    merged = []
    for row_index, row in enumerate(table.rows):
        for column_index, cell in enumerate(row.cells):
            if cell is None:
                continue
            x0, y0, x1, y1 = cell
            row_span = sum(y0 <= y < y1 for y in row_starts)
            column_span = sum(x0 <= x < x1 for x in column_starts)
            if row_span > 1 or column_span > 1:
                merged.append(
                    {
                        "row": row_index,
                        "column": column_index,
                        "row_span": row_span,
                        "column_span": column_span,
                    }
                )
    return merged


def inspect_pdf_table(params: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Read one detected table on one page, preserving native cell text and spans."""
    source = _source_file(params["input_path"])
    page_number = params.get("page", 1)
    table_index = params.get("table_index", 0)
    row_offset = params.get("row_offset", 0)
    max_rows = params.get("max_rows", 40)
    for name, value, minimum, maximum in (
        ("page", page_number, 1, None),
        ("table_index", table_index, 0, None),
        ("row_offset", row_offset, 0, None),
        ("max_rows", max_rows, 1, 100),
    ):
        if (
            type(value) is not int
            or value < minimum
            or (maximum is not None and value > maximum)
        ):
            interval = (
                f"from {minimum} to {maximum}"
                if maximum is not None
                else f">= {minimum}"
            )
            raise AdapterError(
                "INVALID_ARGUMENT", f"{name} must be an integer {interval}"
            )
    fitz = _load_fitz()
    deadline = time.monotonic() + max(0.1, timeout)
    try:
        document = fitz.open(str(source))
    except Exception as exc:
        raise AdapterError(
            "INVALID_PDF", "input_path is not a readable PDF", {"error": str(exc)}, 422
        ) from exc
    try:
        if not document.is_pdf:
            raise AdapterError(
                "INVALID_PDF", "input_path must contain a PDF document", http_status=422
            )
        if document.needs_pass:
            raise AdapterError(
                "ENCRYPTED_PDF_UNSUPPORTED",
                "input_path requires a PDF password",
                http_status=422,
            )
        if page_number > document.page_count:
            raise AdapterError(
                "PAGE_RANGE_OUT_OF_BOUNDS",
                "page must select an existing PDF page (numbered from 1)",
                {"page": page_number, "page_count": document.page_count},
                422,
            )
        # PyMuPDF can print a first-use notice; stdout belongs to worker JSON.
        with redirect_stdout(sys.stderr):
            tables = document[page_number - 1].find_tables().tables
        if time.monotonic() >= deadline:
            raise AdapterError(
                "TIMEOUT",
                "PDF table inspection exceeded the operation timeout",
                http_status=504,
            )
        result = {
            "input_path": str(source),
            "page_count": document.page_count,
            "page": page_number,
            "table_count": len(tables),
            "table_index": table_index,
            "row_count": 0,
            "column_count": 0,
            "row_offset": row_offset,
            "next_row_offset": None,
            "truncated": False,
            "rows": [],
            "merged_cells": [],
        }
        if not tables and table_index == 0:
            return result
        if table_index >= len(tables):
            raise AdapterError(
                "PDF_TABLE_INDEX_OUT_OF_BOUNDS",
                "table_index must select a detected table (numbered from 0)",
                {"table_index": table_index, "table_count": len(tables)},
                422,
            )
        table = tables[table_index]
        rows = table.extract()
        selected = rows[row_offset : row_offset + max_rows]
        truncated = row_offset + len(selected) < len(rows)
        result.update(
            {
                "row_count": len(rows),
                "column_count": table.col_count,
                "rows": selected,
                "merged_cells": _merged_cells(table),
                "next_row_offset": row_offset + len(selected) if truncated else None,
                "truncated": truncated,
                "bbox": list(table.bbox),
            }
        )
        return result
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(
            "PDF_TABLE_INSPECTION_FAILED",
            "could not inspect tables on the selected PDF page",
            {"error": str(exc)},
            422,
        ) from exc
    finally:
        document.close()
