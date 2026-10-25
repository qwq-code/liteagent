from __future__ import annotations

from typing import Any

from .schema import ACTIONS


NONEMPTY_STRING = {"type": "string", "minLength": 1}
RGB_COLOR = {
    "oneOf": [
        {"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$"},
        {"type": "integer", "minimum": 0, "maximum": 16777215},
    ]
}
CELL_FORMAT = {
    "type": "object",
    "minProperties": 1,
    "properties": {
        "background_color": RGB_COLOR,
        "font_color": RGB_COLOR,
        "bold": {"type": "boolean"},
        "number_format": NONEMPTY_STRING,
        "locale": NONEMPTY_STRING,
        "horizontal_alignment": {
            "type": "string",
            "enum": ["left", "center", "right", "standard"],
        },
        "vertical_alignment": {
            "type": "string",
            "enum": ["top", "center", "bottom", "standard"],
        },
    },
    "additionalProperties": False,
}
PIVOT_DATA_FIELD = {
    "type": "object",
    "properties": {
        "field": {
            **NONEMPTY_STRING,
            "description": (
                "Exact source-table header whose values are counted or summed within "
                "each group. For a category frequency distribution, count that category "
                "field and also put it in row_fields; the same field can serve both roles. "
                "Counting a different populated record column can include blank categories "
                "but changes the counted measure and its output heading."
            ),
        },
        "aggregation": {
            "type": "string",
            "enum": ["sum", "count", "average", "max", "min"],
            "description": (
                "count counts non-empty values within each group, including text; "
                "sum adds numeric values. show_data_as changes the displayed measure, "
                "not which records are grouped together."
            ),
        },
        "show_data_as": {
            "type": "string",
            "enum": [
                "none",
                "row_percentage",
                "column_percentage",
                "total_percentage",
                "running_total",
                "item_difference",
                "item_percentage",
                "item_percentage_difference",
                "index",
            ],
            "description": (
                "total_percentage divides each group's aggregate by the grand total: "
                "use it for each category's share of all records. row_percentage "
                "divides by the total within the same row; with one value column, "
                "each non-empty row therefore shows 100%. column_percentage divides "
                "by the total within the same column. Defaults to none."
            ),
        },
        "reference_field": NONEMPTY_STRING,
        "reference_item": NONEMPTY_STRING,
    },
    "required": ["field"],
    "additionalProperties": False,
}
PIVOT_SPEC = {
    "type": "object",
    "properties": {
        "name": {
            **NONEMPTY_STRING,
            "description": "Unique, human-readable pivot table name.",
        },
        "row_fields": {
            "type": "array",
            "uniqueItems": True,
            "items": NONEMPTY_STRING,
        },
        "column_fields": {
            "type": "array",
            "uniqueItems": True,
            "items": NONEMPTY_STRING,
        },
        "page_fields": {
            "type": "array",
            "uniqueItems": True,
            "items": NONEMPTY_STRING,
        },
        "data_fields": {
            "type": "array",
            "minItems": 1,
            "items": PIVOT_DATA_FIELD,
        },
    },
    "required": ["name", "data_fields"],
    "additionalProperties": False,
}
FORMATTED_TEXT_VALUE = {
    "type": "object",
    "description": (
        'Pass {"parts":[{"text":"prefix"},{"cell":"C1","decimal_places":2},'
        '{"text":"suffix"}]}. Each part has exactly one of text or cell. '
        "Include at least one cell part; use kind=string for entirely literal text. "
        "A cell part can reference text labels as well as numbers. A text part is a "
        "literal, not a placeholder that the Adapter replaces with a cell value. "
        "References may use $ to keep a row or column fixed when the formula is "
        "copied with range.fill_down."
    ),
    "properties": {
        "parts": {
            "type": "array",
            "minItems": 1,
            "items": {
                "oneOf": [
                    {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                        "additionalProperties": False,
                    },
                    {
                        "type": "object",
                        "properties": {
                            "cell": {
                                **NONEMPTY_STRING,
                                "description": (
                                    "One A1 cell reference, optionally sheet-qualified. "
                                    "References read that cell's value, including text."
                                ),
                            },
                            "decimal_places": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 12,
                                "description": (
                                    "Exact decimal count for a numeric cell, including "
                                    "trailing zeros in the resulting text. "
                                    "Omit for text references; this field does not "
                                    "convert text to a number."
                                ),
                            },
                        },
                        "required": ["cell"],
                        "additionalProperties": False,
                    },
                ]
            },
        },
    },
    "required": ["parts"],
    "additionalProperties": False,
}
TYPED_CELL = {
    "type": "object",
    "description": (
        "One typed cell. Use formatted_text when concatenated text must preserve "
        "an exact decimal count. Formula strings use the active Calc locale; after a "
        "formula parse error (for example error 508), use formatted_text with explicit "
        "text/cell parts instead of retrying the same formula."
    ),
    "oneOf": [
        {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["blank", "string", "number", "boolean", "date", "formula"],
                },
                "value": {},
                "number_format": {"type": "string"},
                "locale": {"type": "string"},
            },
            "required": ["kind"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["formatted_text"]},
                "value": FORMATTED_TEXT_VALUE,
                "number_format": {"type": "string"},
                "locale": {"type": "string"},
            },
            "required": ["kind", "value"],
            "additionalProperties": False,
        },
    ],
}

CELL_VALUE = {
    "oneOf": [
        TYPED_CELL,
        {"type": ["string", "number", "boolean", "null"]},
    ],
}

# Structured action contracts used to expose strict native tool schemas. The
# corresponding runtime validation remains in calc_adapter.schema.
_ACTION_PARAM_SCHEMAS: dict[str, dict[str, Any]] = {
    "workbook.save": {
        "description": (
            "Save the active workbook. To save the current file, send an empty "
            "argument object and omit url. Do not put the string '{}' in url. "
            "For Save As, supply an absolute local path, ~/ path, or file URL "
            "ending in .ods or .xlsx. Use workbook.export for CSV or PDF."
        ),
        "properties": {
            "url": {
                "type": "string",
                "pattern": r"^(?:/|~/|file:///).+\.(?:[Oo][Dd][Ss]|[Xx][Ll][Ss][Xx])$",
                "description": "Save As destination only; omit to save the current file.",
            },
            "filter_name": {"type": "string", "minLength": 1},
        },
        "required": [],
    },
    "range.write": {
        "properties": {
            "sheet": {
                **NONEMPTY_STRING,
                "description": "Exact destination worksheet name.",
            },
            "range": {
                **NONEMPTY_STRING,
                "description": (
                    "Exact A1 destination range. To write one value into merged cells, "
                    "target only the top-left cell and pass one value."
                ),
            },
            "values": {
                "type": "array",
                "minItems": 1,
                "description": (
                    "Write JSON literals or typed cells; both may be mixed. Strings are "
                    "exact text, including leading '=' and date-like text; numbers and "
                    "booleans keep their types; null clears the cell. Use typed "
                    "kind=formula or kind=date for formula/date interpretation. "
                    "For a one-row or one-column target, pass a "
                    "flat list and the Adapter derives its orientation from the A1 range. "
                    "For a rectangular target, pass a rectangular list of rows. "
                    'Example: {"sheet":"Summary","range":"B2:C2",'
                    '"values":[["Quantity",12]]}. Use '
                    "kind=string for literal text; use range.format for fonts and colors. "
                    "kind=formatted_text composes text from cell references, not font styling; "
                    "do not repeatedly retry a formula that Calc reports as invalid. "
                    "For a document-to-ledger import, use the document's final paid/total "
                    "amount for one transaction row rather than an individual line item or "
                    "subtotal; represent an expense as a negative amount and Type=Expense. "
                    "Preserve the observed column order and leave optional description or "
                    "category cells blank when the instruction does not request those fields."
                ),
                "items": {
                    "oneOf": [
                        CELL_VALUE,
                        {
                            "type": "array",
                            "minItems": 1,
                            "items": CELL_VALUE,
                        },
                    ]
                },
            },
        },
        "required": ["sheet", "range", "values"],
    },
    "cells.set_formulas": {
        "description": (
            "Use native Calc formulas: =ROUND(C4;3). Semicolons separate function "
            "arguments; punctuation inside quoted strings is literal text and stays "
            "unchanged. ROUND controls numeric precision; it does not preserve trailing "
            "zeros when a number is joined into text. Use TEXT(C4;\"0.000\") for "
            "three decimal places in text. For joining text and formatted cell values, range.write also "
            "accepts kind=formatted_text with explicit parts. "
            "IMPORTANT: for a row labeled Total or Subtotal, write formulas for every "
            "blank numeric period cell and the final Total cell; writing only the final "
            "Total column cell is incomplete. Atomically set model-selected formulas on "
            "an explicit list of non-contiguous "
            "cells in one worksheet. Every cell and formula must be supplied by the model; "
            "the Adapter does not discover targets, calculate formulas, or expand the list. "
            "Every formula value must begin with '='; literal labels or years are values, "
            "not formulas, and belong in range.write. For a percentage change, write the "
            "decimal ratio and use range.format with a percent number format unless the "
            "instruction explicitly requests a numeric percent-point value. When the "
            "observed table has a row labeled Total or Subtotal with blank numeric cells, "
            "fill every blank numeric cell in that row (one cell for each numeric period) "
            "and the final total column with explicit SUM formulas over the observed detail "
            "rows, using only the existing numeric columns inside the observed used range. "
            "Use the contiguous detail rows immediately above the summary row as the source "
            "span (the read result may report this as detail_row_range). "
            "If the read result reports detail_total_cells, those are separate blank trailing "
            "Total cells on detail rows; each uses a horizontal =SUM(first_period_r:last_period_r), "
            "and must also be included when the instruction asks to fill missing totals. "
            "When both summary_rows and detail_total_cells are present, include the union "
            "of both target sets in the same model-selected mutation. The summary entry's "
            "period_cells use vertical SUMs over detail_row_range, while final_total_cell "
            "uses a horizontal SUM across those period_cells. "
            "For a summary row r whose detail rows are s:e, each period cell c_r uses "
            "=SUM(c_s:c_e) (vertical column sum), while the final Total cell uses "
            "=SUM(first_period_r:last_period_r) across that same summary row; do not "
            "use a detail-row horizontal formula in a summary cell. "
            "Do not create new columns or shift the row. A summary row is incomplete if "
            "only its final total cell is written. "
            "For a detail row with a blank Total column immediately after "
            "numeric period columns, include every observed numeric column before it (all "
            "observed quarters/months, through the last one); do not shorten the range; do not "
            "truncate the SUM. A formula result showing Err:<code> is a failed formula, "
            "not a successful write; correct it after reading the model-visible "
            "FORMULA_ERROR feedback. Successful formulas persist. Do not infer that a formula is wrong from its "
            "displayed value alone. For a detail-row total, first confirm that the row has a "
            "detail label and numeric period cells; do not write formulas into header, category, "
            "or separator rows just because the Total cell is blank. Do not repeat or overwrite them, extend into "
            "blank separator rows, or rewrite a just-written Total row unless a read-back "
            "shows it is wrong. Read back before correcting a value. This is guidance only: "
            "the model still selects each cell "
            "and formula."
        ),
        "properties": {
            "sheet": {
                **NONEMPTY_STRING,
                "description": "Exact worksheet name returned by workbook.inspect.",
            },
            "writes": {
                "type": "array",
                "minItems": 1,
                "maxItems": 256,
                        "description": (
                            "Explicit cells and formulas in model-selected order. Every formula "
                            "must begin with '='; use range.write for literal numbers or labels."
                        ),
                "items": {
                    "type": "object",
                    "properties": {
                        "cell": {
                            "type": "string",
                            "pattern": r"^\$?[A-Za-z]{1,4}\$?[1-9][0-9]*$",
                            "description": "One unqualified A1 cell, such as F3.",
                        },
                        "formula": {
                            "type": "string",
                            "pattern": r"^=.+$",
                            "description": (
                                "Exact Calc formula beginning with '='. Separate function "
                                "arguments with semicolons, for example =ROUND(C4;3). "
                                "Commas inside quoted text stay literal commas; do not "
                                "replace text punctuation with argument separators. "
                                "For fixed decimal places in joined text, use "
                                "TEXT(C4;\"0.000\") (three decimals including trailing "
                                "zeros) or range.write formatted_text; ROUND alone "
                                "does not keep trailing zeros."
                            ),
                        },
                    },
                    "required": ["cell", "formula"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["sheet", "writes"],
    },
    "range.set_decimal_separator": {
        "description": (
            "Change the decimal separator for numeric and formula cells in a live range "
            "without changing their values, formulas, or visible decimal-place counts. "
            "Text and date-formatted cells are left unchanged. Use this instead of guessing "
            "a LibreOffice number-format code or locale."
        ),
        "properties": {
            "sheet": {
                **NONEMPTY_STRING,
                "description": (
                    "Exact worksheet name only. For Metrics!C2:F9 pass Metrics here; "
                    "never include the trailing exclamation mark."
                ),
            },
            "range": {
                **NONEMPTY_STRING,
                "description": (
                    "A1 coordinates only. For Metrics!C2:F9 pass C2:F9 here. The range may "
                    "include headers because nonnumeric cells are ignored."
                ),
            },
            "separator": {
                "type": "string",
                "enum": ["comma", "dot"],
                "description": "Requested decimal separator for displayed numeric values.",
            },
        },
        "required": ["sheet", "range", "separator"],
    },
    "workbook.read_file": {
        "properties": {
            "path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/|file:///).+\\.(?:csv|ods|xlsx)$",
                "description": (
                    "Existing local CSV, ODS, or XLSX file to read through LibreOffice "
                    "Calc. Returns the cell text exactly as displayed, including trailing "
                    "zeros. Display text cannot distinguish a numeric cell from digits stored "
                    "as text; use range.read on the open workbook to inspect native cell kinds. "
                    "On FILE_NOT_FOUND, open_documents lists live open workbooks, "
                    "not confirmed substitutes. Choose the intended observed file yourself; "
                    "no alternative path is read automatically."
                ),
            },
            "sheet": {
                **NONEMPTY_STRING,
                "description": (
                    "Optional exact worksheet name. Omit to read a bounded preview of "
                    "each worksheet."
                ),
            },
            "range": {
                **NONEMPTY_STRING,
                "description": (
                    "Optional A1 range. Omit to read from the worksheet used range."
                ),
            },
            "start_row": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1048576,
                "description": "Optional one-based first row; cannot be combined with range.",
            },
            "start_column": {
                "type": "integer",
                "minimum": 1,
                "maximum": 16384,
                "description": (
                    "Optional one-based first column; cannot be combined with range."
                ),
            },
            "max_rows": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1000,
                "description": "Maximum displayed rows returned per worksheet; defaults to 200.",
            },
            "max_columns": {
                "type": "integer",
                "minimum": 1,
                "maximum": 256,
                "description": "Maximum displayed columns returned per worksheet; defaults to 64.",
            },
            "max_sheets": {
                "type": "integer",
                "minimum": 1,
                "maximum": 32,
                "description": "Maximum worksheets returned when sheet is omitted; defaults to 8.",
            },
        },
        "required": ["path"],
        "not": {
            "allOf": [
                {"required": ["range"]},
                {
                    "anyOf": [
                        {"required": ["start_row"]},
                        {"required": ["start_column"]},
                    ]
                },
            ]
        },
    },
    "workbook.create_new": {
        "properties": {
            "output_path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/|file:///).+\\.(?:ods|xlsx)$",
                "description": (
                    "New local ODS or XLSX path. The extension selects the format; "
                    "the action creates parent directories and saves the workbook."
                ),
            },
            "sheet_name": {
                **NONEMPTY_STRING,
                "description": "Optional name for the first worksheet.",
            },
            "headers": {
                "type": "array",
                "minItems": 1,
                "maxItems": 256,
                "uniqueItems": True,
                "items": NONEMPTY_STRING,
                "description": (
                    "Optional table header row. Omit rows to create and save a header-only "
                    "workbook for later explicit range writes. Supply rows, including an empty "
                    "array for an intentionally empty table, to complete the table in one call."
                ),
            },
            "rows": {
                "type": "array",
                "maxItems": 10000,
                "items": {
                    "type": "array",
                    "maxItems": 256,
                    "items": {
                        "oneOf": [
                            {
                                "type": "number",
                                "description": (
                                    "Numeric quantity copied as a JSON number, without quotes. "
                                    "Counts and measurements keep their source numeric type."
                                ),
                            },
                            {
                                "type": "string",
                                "description": (
                                    "Literal text or identifier. Quoted digits remain text cells "
                                    "and are never converted to numeric quantities."
                                ),
                            },
                            {"type": "boolean", "description": "Boolean true or false."},
                            {"type": "null", "description": "Blank cell."},
                        ]
                    },
                },
                "description": (
                    "Optional compact data rows aligned positionally with headers; rows is valid "
                    "only with headers. Values may be strings, numbers, booleans, or null. "
                    "JSON numbers become numeric cells; quoted digits remain text. Preserve "
                    "source numeric types for quantities and keep text identifiers as text: "
                    "for example, [\"item\", 7, \"007\"] stores a number and a text identifier. "
                    "Omit rows for a staged header-only workbook; use [] for a complete table "
                    "that intentionally has no data rows."
                ),
            },
            "overwrite": {
                "type": "boolean",
                "description": "Replace an existing destination only when explicitly true.",
            },
        },
        "required": ["output_path"],
        "oneOf": [
            {
                "required": ["headers", "rows"],
            },
            {
                "required": ["headers"],
                "not": {"required": ["rows"]},
            },
            {
                "not": {
                    "anyOf": [
                        {"required": ["headers"]},
                        {"required": ["rows"]},
                    ]
                }
            },
        ],
    },
    "workbook.convert_file": {
        "properties": {
            "input_path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/|file:///).+\\.(?:csv|ods|xlsx)$",
                "description": (
                    "Existing local CSV, ODS, or XLSX file to open with LibreOffice Calc."
                ),
            },
            "output_path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/|file:///).+\\.(?:csv|ods|xlsx)$",
                "description": (
                    "Different local output path. Its .csv, .ods, or .xlsx extension "
                    "selects the destination format."
                ),
            },
        },
        "required": ["input_path", "output_path"],
    },
    "range.copy": {
        "properties": {
            "source_sheet": NONEMPTY_STRING,
            "source_range": NONEMPTY_STRING,
            "destination_sheet": NONEMPTY_STRING,
            "destination": NONEMPTY_STRING,
            "transpose": {"type": "boolean"},
            "preserve_format": {"type": "boolean"},
        },
        "required": [
            "source_sheet",
            "source_range",
            "destination_sheet",
            "destination",
        ],
    },
    "range.set_scaled_display": {
        "description": (
            "Apply a scaled numeric display format to one explicit existing range. "
            "Displays each cell's current numeric value divided by divisor, with the "
            "selected decimals and unit; stored values and formulas stay unchanged. "
            "Do not divide a formula and then apply the same display divisor: that "
            "scales twice. If cells already contain converted values, use divisor=1 "
            "for decimals and unit only. For example, with decimal_places=1, unit='k' "
            "and separator='space', numeric 8400 with divisor=1000 displays as 8.4 k; "
            "numeric 8.4 needs divisor=1 to display as 8.4 k. "
            "Populate an empty target separately by copying, writing values or "
            "setting formulas; this action does not transfer values."
        ),
        "properties": {
            "sheet": NONEMPTY_STRING,
            "range": NONEMPTY_STRING,
            "divisor": {
                "type": "integer",
                "minimum": 1,
                "description": (
                    "Divide the CURRENT cell value (including a formula result) for "
                    "display by this power of 1000: 1, 1000, 1000000, etc. "
                    "1 adds no further scaling."
                ),
            },
            "decimal_places": {"type": "integer", "minimum": 0, "maximum": 12},
            "unit": {
                **NONEMPTY_STRING,
                "description": "Literal unit suffix selected by the model, such as M or kg.",
            },
            "separator": {
                "type": "string",
                "enum": ["space", "none"],
            },
            "rounding_mode": {"type": "string", "enum": ["half_up"]},
            "locale": NONEMPTY_STRING,
        },
        "required": [
            "sheet",
            "range",
            "divisor",
            "decimal_places",
            "unit",
            "separator",
            "rounding_mode",
        ],
    },
    "range.fill_down": {
        "properties": {
            "sheet": NONEMPTY_STRING,
            "range": {
                **NONEMPTY_STRING,
                "description": (
                    "One A1 range including the source row(s) at the top "
                    "and the cells to fill below."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["previous_nonblank", "formula_pattern"],
                "description": (
                    "previous_nonblank fills each blank from the cell immediately above; "
                    "formula_pattern extends the top source row pattern with relative references. "
                    "formula_pattern requires at least one formula in the top source row(s); "
                    "use range.write first when the source row is currently blank."
                ),
            },
            "source_rows": {
                "type": "integer",
                "minimum": 1,
                "description": "Top pattern row count for formula_pattern; defaults to 1.",
            },
            "only_blank": {
                "type": "boolean",
                "description": "Preserve existing nonblank target cells; defaults to true.",
            },
            "preserve_format": {
                "type": "boolean",
                "description": "Copy source formatting with values/formulas; defaults to false.",
            },
        },
        "required": ["sheet", "range", "mode"],
    },
    "table.reorder_columns": {
        "properties": {
            "sheet": NONEMPTY_STRING,
            "range": {
                **NONEMPTY_STRING,
                "description": (
                    "Rectangular table range including its header row. A header-only range "
                    "automatically expands through contiguous nonblank data rows and stops "
                    "before the first entirely blank row."
                ),
            },
            "headers": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": NONEMPTY_STRING,
                "description": "Every selected table header exactly once, in the desired order.",
            },
        },
        "required": ["sheet", "range", "headers"],
    },
    "range.text_transform": {
        "description": (
            "Apply exactly one text transform to selected cells and write the result "
            "to an explicit destination. Call this action again for each additional "
            "transform in the intended order, using the preceding destination_range "
            "as source_range and the same top-left destination when transforming in place. "
            "title_case changes letter case only and does not trim or collapse whitespace; "
            "a request for both whitespace cleanup and title casing requires separate "
            "collapse_whitespace and title_case calls. "
            "Every selected source cell is transformed; "
            "headers are not detected or skipped automatically. When cleaning data "
            "below existing column headers, select only data rows and keep both "
            "headers unchanged unless the user asks to edit them."
        ),
        "properties": {
            "source_sheet": NONEMPTY_STRING,
            "source_range": {
                **NONEMPTY_STRING,
                "description": (
                    "One contiguous A1 source range. The action transforms every cell "
                    "you include and overwrites the corresponding destination cell. "
                    "For data-only cleaning, start at the first data row below "
                    "the observed header, not at the header itself."
                ),
            },
            "destination_sheet": NONEMPTY_STRING,
            "destination": {
                **NONEMPTY_STRING,
                "description": (
                    "Top-left destination cell only; output dimensions match "
                    "source_range. Select the first output data cell when leaving "
                    "an existing destination header unchanged. "
                    "Do not pass a destination range. Existing destination headers "
                    "are not automatically preserved if they are inside the selected "
                    "output; exclude headers from source_range unless the instruction "
                    "explicitly asks to replace them."
                ),
            },
            "operation": {
                "type": "string",
                "enum": [
                        "trim",
                        "collapse_whitespace",
                        "title_case",
                        "lowercase",
                        "uppercase",
                ],
                "description": (
                    "Apply exactly one operation: trim removes outer whitespace only; "
                    "collapse_whitespace removes outer whitespace and replaces each "
                    "internal whitespace run with one space; title_case changes letter "
                    "case only. For multiple operations, make separate calls using the "
                    "previous output as the next source, and read back each result. "
                    "When the final result belongs in an existing target column, the "
                    "destination may equal the source/output column; do not create "
                    "temporary columns or write outside the requested data range."
                ),
            },
            "skip_blank": {
                "type": "boolean",
                "description": "Leave blank destination cells untouched; defaults to false.",
            },
        },
        "required": [
            "source_sheet",
            "source_range",
            "destination_sheet",
            "destination",
            "operation",
        ],
    },
    "range.merge": {
        "properties": {
            "sheet": NONEMPTY_STRING,
            "range": NONEMPTY_STRING,
            "merge": {"type": "boolean"},
        },
        "required": ["sheet", "range"],
    },
    "range.set_validation": {
        "properties": {
            "sheet": NONEMPTY_STRING,
            "range": NONEMPTY_STRING,
            "values": {
                "type": "array",
                "minItems": 1,
                "items": NONEMPTY_STRING,
            },
            "allow_blank": {"type": "boolean"},
            "show_error": {"type": "boolean"},
        },
        "required": ["sheet", "range", "values"],
    },
    "rows.set_hidden": {
        "properties": {
            "sheet": NONEMPTY_STRING,
            "rows": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "integer", "minimum": 1},
            },
            "hidden": {"type": "boolean"},
        },
        "required": ["sheet", "rows"],
    },
    "sheet.copy": {
        "properties": {
            "sheet": NONEMPTY_STRING,
            "new_name": NONEMPTY_STRING,
            "index": {"type": "integer", "minimum": 0},
        },
        "required": ["sheet", "new_name"],
    },
    "sheet.move": {
        "properties": {
            "sheet": NONEMPTY_STRING,
            "index": {"type": "integer", "minimum": 0},
        },
        "required": ["sheet", "index"],
    },
    "sheet.rename": {
        "properties": {
            "sheet": NONEMPTY_STRING,
            "new_name": NONEMPTY_STRING,
        },
        "required": ["sheet", "new_name"],
    },
    "range.format": {
        "description": (
            "Apply one shared format to explicitly selected cells/ranges on one sheet. "
            "Use one cell or contiguous A1 range, or a comma-separated selection such as "
            "D4,D9:E10; every selected area receives exactly the same format. "
            "Highlight cells by setting format.background_color (background fill); "
            "set font color with format.font_color. Colors accept RGB #RRGGBB or an integer. "
            "Also supports bold, number format, locale and alignment. "
            "Applies to every cell in the selected areas, including blanks. "
            "Choose all areas yourself; cells between separate areas are unchanged. "
            "Returns formatted_ranges and separate per-area read-back. This is not atomic: "
            "an execution error reports applied, failed, and unattempted ranges; inspect "
            "any partially changed area before retrying. Use separate calls for different formats."
        ),
        "properties": {
            "sheet": {**NONEMPTY_STRING},
            "range": {
                **NONEMPTY_STRING,
                "description": (
                    "One cell/range or comma-separated unqualified A1 cells/ranges on sheet, "
                    "for example D4,D9:E10. Existing native named ranges remain supported. "
                    "Selection order and repeated areas are preserved."
                ),
            },
            "format": {
                "type": "object",
                "minProperties": 1,
                "properties": {
                    "background_color": RGB_COLOR,
                    "font_color": RGB_COLOR,
                    "bold": {"type": "boolean"},
                    "number_format": NONEMPTY_STRING,
                    "locale": NONEMPTY_STRING,
                    "horizontal_alignment": {
                        "type": "string",
                        "enum": ["left", "center", "right", "standard"],
                    },
                    "vertical_alignment": {
                        "type": "string",
                        "enum": ["top", "center", "bottom", "standard"],
                    },
                },
                "additionalProperties": False,
            },
        },
        "required": ["sheet", "range", "format"],
    },
    "table.sort": {
        "properties": {
            "sheet": NONEMPTY_STRING,
            "range": NONEMPTY_STRING,
            "keys": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "column": {"type": "integer", "minimum": 0},
                        "ascending": {"type": "boolean"},
                        "case_sensitive": {"type": "boolean"},
                        "type": {
                            "type": "string",
                            "enum": ["automatic", "alphanumeric", "numeric"],
                        },
                    },
                    "required": ["column"],
                    "additionalProperties": False,
                },
            },
            "contains_header": {"type": "boolean"},
        },
        "required": ["sheet", "range", "keys"],
    },
    "view.freeze_panes": {
        "properties": {
            "sheet": NONEMPTY_STRING,
            "columns": {"type": "integer", "minimum": 0},
            "rows": {"type": "integer", "minimum": 0},
        },
        "required": ["sheet"],
    },
    "view.freeze_range": {
        "description": (
            "Freeze every row and column covered by an A1-anchored range so that the range "
            "remains visible while scrolling. The Adapter derives row and column counts from "
            "the live range geometry; use this when the instruction names a range such as "
            "A1:D2 instead of manually converting it to counts."
        ),
        "properties": {
            "sheet": {
                **NONEMPTY_STRING,
                "description": "Exact worksheet name from workbook.inspect.",
            },
            "range": {
                **NONEMPTY_STRING,
                "description": (
                    "Exact A1 range selected by the model. It must start at A1; the bottom-right "
                    "cell determines how many leading rows and columns are frozen."
                ),
            },
        },
        "required": ["sheet", "range"],
    },
    "view.set_zoom": {
        "description": "Set one absolute zoom percentage and return previous and actual zoom. Compare with the request, then save and finish once satisfied; repeated reduction is unnecessary.",
        "properties": {
            "sheet": {
                **NONEMPTY_STRING,
                "description": (
                    "Exact worksheet name from the instruction or workbook.inspect; "
                    "never substitute a default such as Sheet1."
                ),
            },
            "zoom": {"type": "integer", "minimum": 20, "maximum": 600},
        },
        "required": ["sheet", "zoom"],
    },
}


# Keep legacy schemas available as implementation history while exposing only
# actions accepted by the current Adapter contract.
STRICT_ACTION_PARAM_SCHEMAS: dict[str, dict[str, Any]] = {
    action: schema
    for action, schema in _ACTION_PARAM_SCHEMAS.items()
    if action in ACTIONS
}
