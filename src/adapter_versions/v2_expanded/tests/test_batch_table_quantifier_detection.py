from __future__ import annotations

import pytest

from integrations.lite_agent.batch_table_semantics import (
    requests_one_record_per_input,
)


@pytest.mark.parametrize(
    "instruction",
    [
        (
            "For each source PDF, extract the records and fill the spreadsheet "
            "already open in Calc."
        ),
        "Extract labels from every listed image and put one record per image in the table.",
        "Create a workbook with one row per source document.",
        "Put a record for each input file in the spreadsheet.",
        "Make a table with one row per each PDF file in the folder.",
        "For each source PDF, create a new spreadsheet.",
    ],
)
def test_explicit_input_cardinality_requests_batch_table(
    instruction: str,
) -> None:
    assert requests_one_record_per_input(instruction)


@pytest.mark.parametrize(
    "instruction",
    [
        (
            "The annual reports are PDF files. Each report has a breakdown table "
            "with disciplines as rows. Extract the requested values for each year "
            "and organize the result in a workbook."
        ),
        (
            "The source PDFs contain a separate table for each year. Summarize "
            "the yearly values in a spreadsheet."
        ),
        (
            "Review each employee's data in the PDF and place the aggregate result "
            "in a workbook."
        ),
        (
            "Transfer the data into standardized PDF forms. Each PDF file is named "
            "according to the employee and the final workbook is saved separately."
        ),
        "For each source PDF, extract the text and return it in the response.",
    ],
)
def test_unrelated_or_non_tabular_quantifiers_do_not_request_batch_table(
    instruction: str,
) -> None:
    assert not requests_one_record_per_input(instruction)
