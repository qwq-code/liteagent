from __future__ import annotations

import pytest

from os_adapter.errors import AdapterError
from os_adapter.pdf_tables import inspect_pdf_table


fitz = pytest.importorskip("fitz")


def _draw_table(page, xs, ys, rows, merges=()):
    covered = set()
    rectangles = []
    for row, column, row_span, column_span in merges:
        rectangles.append(
            (
                row,
                column,
                fitz.Rect(
                    xs[column], ys[row], xs[column + column_span], ys[row + row_span]
                ),
            )
        )
        covered.update(
            (r, c)
            for r in range(row, row + row_span)
            for c in range(column, column + column_span)
        )
    for row in range(len(ys) - 1):
        for column in range(len(xs) - 1):
            if (row, column) not in covered:
                rectangles.append(
                    (
                        row,
                        column,
                        fitz.Rect(xs[column], ys[row], xs[column + 1], ys[row + 1]),
                    )
                )
    for row, column, rectangle in rectangles:
        page.draw_rect(rectangle, width=0.5)
        value = rows[row][column]
        if value:
            page.insert_text((rectangle.x0 + 7, rectangle.y0 + 15), value, fontsize=10)


@pytest.fixture
def table_pdf(tmp_path):
    path = tmp_path / "synthetic tables.pdf"
    document = fitz.open()
    first_page = document.new_page(width=600, height=700)
    _draw_table(
        first_page,
        [40, 180, 320, 460],
        [50, 95, 155, 215],
        [
            ["Combined heading", None, "Separate"],
            ["plain words", "first line\nsecond line", ""],
            ["end row", "ordinary value", "tail"],
        ],
        merges=[(0, 0, 1, 2)],
    )
    _draw_table(
        first_page,
        [70, 250, 470],
        [350, 400, 450],
        [
            ["Another table", "Right cell"],
            ["more text", "last cell"],
        ],
    )
    second_page = document.new_page(width=600, height=700)
    _draw_table(
        second_page,
        [35, 140, 280],
        [70, 115, 160, 205],
        [
            ["Vertical", "upper"],
            [None, "middle"],
            ["bottom left", "lower"],
        ],
        merges=[(0, 0, 2, 1)],
    )
    empty_page = document.new_page(width=600, height=700)
    empty_page.insert_text(
        (40, 60), "This page contains ordinary prose without a table."
    )
    document.save(path)
    document.close()
    return path


def test_preserves_native_matrix_and_merged_header(table_pdf):
    original = table_pdf.read_bytes()
    result = inspect_pdf_table({"input_path": str(table_pdf)}, 10)
    assert result["page_count"] == 3
    assert result["page"] == 1
    assert result["table_count"] == 2
    assert result["row_count"] == 3
    assert result["column_count"] == 3
    assert result["rows"] == [
        ["Combined heading", None, "Separate"],
        ["plain words", "first line\nsecond line", ""],
        ["end row", "ordinary value", "tail"],
    ]
    assert result["merged_cells"] == [
        {"row": 0, "column": 0, "row_span": 1, "column_span": 2}
    ]
    assert result["bbox"] == [40, 50, 460, 215]
    assert result["next_row_offset"] is None
    assert result["truncated"] is False
    assert table_pdf.read_bytes() == original


def test_row_pagination_keeps_full_table_coordinates(table_pdf):
    first = inspect_pdf_table({"input_path": str(table_pdf), "max_rows": 1}, 10)
    assert first["next_row_offset"] == 1
    assert first["truncated"] is True
    following = inspect_pdf_table(
        {"input_path": str(table_pdf), "row_offset": 1, "max_rows": 2}, 10
    )
    assert following["row_offset"] == 1
    assert len(following["rows"]) == 2
    assert following["rows"][0][1] == "first line\nsecond line"
    assert following["row_count"] == 3
    assert following["merged_cells"] == first["merged_cells"]
    assert following["next_row_offset"] is None
    assert following["truncated"] is False
    exhausted = inspect_pdf_table({"input_path": str(table_pdf), "row_offset": 3}, 10)
    assert exhausted["rows"] == []
    assert exhausted["next_row_offset"] is None


def test_selects_one_table_and_one_page(table_pdf):
    other_table = inspect_pdf_table(
        {"input_path": str(table_pdf), "table_index": 1}, 10
    )
    assert other_table["rows"] == [
        ["Another table", "Right cell"],
        ["more text", "last cell"],
    ]
    assert other_table["merged_cells"] == []
    other_page = inspect_pdf_table({"input_path": str(table_pdf), "page": 2}, 10)
    assert other_page["table_count"] == 1
    assert other_page["rows"] == [
        ["Vertical", "upper"],
        [None, "middle"],
        ["bottom left", "lower"],
    ]
    assert other_page["merged_cells"] == [
        {"row": 0, "column": 0, "row_span": 2, "column_span": 1}
    ]


def test_no_detected_table_is_an_empty_observation(table_pdf):
    result = inspect_pdf_table({"input_path": str(table_pdf), "page": 3}, 10)
    assert result["table_count"] == result["row_count"] == result["column_count"] == 0
    assert result["rows"] == result["merged_cells"] == []
    assert result["next_row_offset"] is None
    assert result["truncated"] is False


@pytest.mark.parametrize(
    ("params", "error"),
    [
        ({"page": 4}, "PAGE_RANGE_OUT_OF_BOUNDS"),
        ({"table_index": 2}, "PDF_TABLE_INDEX_OUT_OF_BOUNDS"),
        ({"page": 3, "table_index": 1}, "PDF_TABLE_INDEX_OUT_OF_BOUNDS"),
        ({"page": 0}, "INVALID_ARGUMENT"),
        ({"max_rows": 101}, "INVALID_ARGUMENT"),
        ({"row_offset": -1}, "INVALID_ARGUMENT"),
    ],
)
def test_selection_bounds_return_actionable_errors(table_pdf, params, error):
    with pytest.raises(AdapterError) as caught:
        inspect_pdf_table({"input_path": str(table_pdf), **params}, 10)
    assert caught.value.code == error


def test_unavailable_table_detection_is_reported(table_pdf, monkeypatch):
    monkeypatch.setattr(fitz.Page, "find_tables", None)
    with pytest.raises(AdapterError) as caught:
        inspect_pdf_table({"input_path": str(table_pdf)}, 10)
    assert caught.value.code == "PDF_TABLE_LIBRARY_UNAVAILABLE"


def test_fresh_worker_returns_valid_json_and_verified_table(table_pdf):
    from os_adapter.schema import parse_action_request
    from os_adapter.worker_runner import WorkerRunner

    request = parse_action_request(
        {
            "action": "pdf.tables.inspect",
            "params": {"input_path": str(table_pdf)},
            "timeout_ms": 15000,
        }
    )
    output = WorkerRunner().run(request)
    assert output["verification"]["passed"] is True
    assert output["result"]["table_count"] == 2
    assert output["result"]["rows"][0] == ["Combined heading", None, "Separate"]
    assert output["result"]["rows"][1][1] == "first line\nsecond line"
