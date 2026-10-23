from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from . import batch_table_semantics
from .adapter_results import a1_geometry, column_label, column_number
from .calc_column_reorder import parse_column_reorder_intent
from .calc_scaled_display import parse_scaled_display_intent
from .completion_policy import action_is_read_only, action_is_save


DATA_ACTIONS = frozenset(
    {
        "range.write",
        "cells.set_formulas",
        "range.copy",
        "range.merge",
        "range.fill_down",
        "range.text_transform",
        "range.format",
        "range.set_scaled_display",
        "range.set_decimal_separator",
        "chart.create",
        "pivot.create",
        "table.reorder_columns",
        "table.sort",
        "rows.set_hidden",
        "view.freeze_range",
    }
)

_CHART_REQUEST_RE = re.compile(r"(?i)\b(?:charts?|graphs?)\b")
_NEW_SHEET_REQUEST_RE = re.compile(
    r"(?i)\b(?:new|separate)\s+(?:sheet|worksheet|tab)\b"
)
_BELOW_EXISTING_CONTENT_RE = re.compile(
    r"(?is)\b(?:below|underneath)\s+(?:the\s+)?(?:existing|current)\s+"
    r"(?:content|data|table|output|values?)\b|"
    r"\b(?:below|underneath)\s+(?:the\s+)?(?:last|final)\s+"
    r"(?:(?:used|populated|non[- ]empty)\s+)?(?:row|cell|content|data|table|output)\b"
)
_HIDE_ROWS_REQUEST_RE = re.compile(
    r"(?is)\b(?:hide|hidden|conceal|mask)\b.{0,120}"
    r"\b(?:row|rows|record|records|data|entries)\b|"
    r"\b(?:row|rows|record|records|data|entries)\b.{0,120}"
    r"\b(?:hide|hidden|conceal|mask)\b"
)


def requests_year_over_year_summary(instruction: str) -> bool:
    """Recognize an explicit multi-column year-over-year summary operation class."""
    normalized = re.sub(r"[-_]", " ", instruction.casefold())
    has_operation = re.search(
        r"\b(?:calculate|compute|create|derive|make|produce|show)\b", normalized
    )
    has_percentage_change = bool(
        re.search(r"\bpercent(?:age)?\b|%", normalized)
        and re.search(r"\b(?:change|changes|delta|difference|growth)\b", normalized)
    )
    prior_comparison = bool(
        re.search(r"\byear\s+over\s+year\b|\byoy\b", normalized)
        or (
            re.search(r"\b(?:annual|yearly|year)\b", normalized)
            and re.search(r"\b(?:last|previous|prior|preceding)\s+year\b", normalized)
        )
    )
    summary_shape = bool(
        _NEW_SHEET_REQUEST_RE.search(instruction)
        or re.search(r"\b(?:summary|table|headers?)\b", normalized)
    )
    return bool(
        has_operation and has_percentage_change and prior_comparison and summary_shape
    )


def chart_required_actions(instruction: str) -> list[str]:
    """Return reusable Calc actions implied by a chart instruction.

    This identifies only operation classes. The model remains responsible for
    selecting both actions and supplying every sheet, range, and chart argument.
    """
    if _CHART_REQUEST_RE.search(instruction) is None:
        return []
    actions = ["range.read", "chart.create"]
    if _NEW_SHEET_REQUEST_RE.search(instruction) is not None:
        actions.insert(0, "sheet.create")
    return actions


def operation_required_actions(
    instruction: str, *, strict_generic: bool = False
) -> list[str]:
    """Return generic Calc operation classes explicitly named by the instruction."""
    actions = chart_required_actions(instruction)
    if strict_generic and _NEW_SHEET_REQUEST_RE.search(instruction) is not None:
        actions.append("sheet.create")
    has_chart_request = _CHART_REQUEST_RE.search(instruction) is not None
    has_freeze_request = (
        re.search(r"(?i)\b(?:freeze|freezing|frozen)\b", instruction) is not None
    )
    if has_freeze_request and re.search(
        r"(?i)\bA1(?::[A-Z]{1,4}[1-9][0-9]*)?\b",
        instruction,
    ):
        actions.append("view.freeze_range" if strict_generic else "view.freeze_panes")
    elif has_freeze_request and re.search(
        r"(?i)\b(?:panes?|rows?|columns?|headers?)\b", instruction
    ):
        actions.append("view.freeze_panes")
    if strict_generic:
        if _HIDE_ROWS_REQUEST_RE.search(instruction) and re.search(
            r"(?i)\b(?:N/?A|missing|blank|empty|incomplete|temporary)\b",
            instruction,
        ):
            # The model still selects the observed row numbers and the sheet;
            # this only tells completion which public mutation represents the
            # requested operation.
            actions.extend(["range.read", "rows.set_hidden"])
        if requests_year_over_year_summary(instruction):
            actions.extend(
                [
                    "workbook.inspect",
                    "range.read",
                    "sheet.create",
                    "range.write",
                    "cells.set_formulas",
                    "range.format",
                ]
            )
        if parse_column_reorder_intent(instruction) is not None:
            actions.append("table.reorder_columns")
        if parse_scaled_display_intent(instruction) is not None:
            actions.append("range.set_scaled_display")
        if re.search(
            r"(?is)\bmerge\b.{0,180}\b(?:write|text|title|heading|label)\b|"
            r"\b(?:write|text|title|heading|label)\b.{0,180}\bmerge\b",
            instruction,
        ):
            actions.extend(["range.merge", "range.write", "range.format"])
        has_multiple_pivots = bool(
            re.search(r"(?i)\bpivot tables?\b", instruction)
            and re.search(
                r"(?i)\b(?:[2-9]|1[0-9]|20|two|three|four|five|multiple|several)\b",
                instruction,
            )
        )
        if has_multiple_pivots and re.search(
            r"(?i)\bpercent(?:age|ages)?\b", instruction
        ):
            actions.append("pivot.create")
        elif has_multiple_pivots and re.search(
            r"(?i)\b(?:total|sum|average|mean|minimum|maximum|min|max|count)\b",
            instruction,
        ):
            actions.append("pivot.create")
        if re.search(
            r"(?is)\b(?:underneath|below|append)\b.{0,80}\brows?\b|"
            r"\brows?\b.{0,40}\bcalled\b",
            instruction,
        ) and re.search(r"(?i)\b(?:growth|change|sum|summary|total)\b", instruction):
            actions.extend(["range.write", "cells.set_formulas"])
            if has_chart_request:
                actions.append("chart.create")
        if re.search(r"(?i)\b(?:highlight|format|color)\b", instruction) and re.search(
            r"(?i)\b(?:highest|lowest|maximum|minimum|max|min)\b", instruction
        ):
            actions.extend(["range.read", "range.format"])
        if re.search(r"(?i)\bperiod\s+rate\b", instruction) and re.search(
            r"(?is)\b(?:calculate|compute|derive)\b.{0,120}\bnew\s+column\b|"
            r"\bnew\s+column\b.{0,120}\bperiod\s+rate\b",
            instruction,
        ):
            actions.extend(["range.write", "range.format"])
        if (
            re.search(r"(?i)\b(?:calculate|compute|derive|work\s+out)\b", instruction)
            and re.search(
                r"(?i)\b(?:date|deadline|due\s+date|end\s+date|expiry|expiration|maturity)\b",
                instruction,
            )
            and re.search(r"(?i)\b(?:new|additional)\s+column\b", instruction)
        ):
            # The model may write every formula explicitly; a derived date
            # column does not by itself require a fill operation.
            actions.extend(["range.read", "range.write", "range.format"])
    if re.search(r"(?i)\bzoom(?:ed|ing)?\b", instruction):
        actions.append("view.set_zoom")
    # A chart request may mention totals (for example, "monthly total costs")
    # without asking the agent to materialize a summary table.  Likewise,
    # "fill missing totals" uses explicit model-authored formula cells. Do not expose the
    # column-aggregation operation for either neighboring intent; doing so
    # makes completion demand an unrelated mutation and pushes a small model
    # toward the wrong tool.
    has_missing_totals_request = bool(
        re.search(r"(?i)\bfill\b", instruction)
        and re.search(r"(?i)\bmissing\b", instruction)
        and re.search(r"(?i)\btotal(?:s| value| values)?\b", instruction)
    )
    if strict_generic and has_missing_totals_request:
        actions.extend(["range.read", "cells.set_formulas"])
    if (
        strict_generic
        and not has_chart_request
        and not has_missing_totals_request
        and re.search(
            r"(?is)\b(?:total|sum|average|count|min(?:imum)?|max(?:imum)?)\b"
            r".{0,100}\b(?:each|every|all)\b.{0,60}\b(?:months?|quarters?|columns?)\b|"
            r"\b(?:months?|quarters?|columns?)\b.{0,100}\b(?:totals?|sums?|averages?)\b",
            instruction,
        )
    ):
        actions.extend(["range.read", "cells.set_formulas"])
    return list(dict.fromkeys(actions))


def stage_new_sheet_prerequisites(
    state: Any,
    actions: list[str],
    required_actions: list[str],
) -> list[str]:
    """Stage explicit new-sheet workflows without choosing any model argument."""
    if (
        getattr(state, "domain", None) != "libreoffice_calc"
        or _NEW_SHEET_REQUEST_RE.search(str(getattr(state, "instruction", ""))) is None
        or "sheet.create" not in required_actions
    ):
        return actions

    successful = state.successful_action_events
    if not successful("sheet.create"):
        if not successful("workbook.inspect") and "workbook.inspect" in actions:
            return ["workbook.inspect"]
        if "sheet.create" in actions:
            return ["sheet.create"]
        return actions

    if (
        "range.read" in required_actions
        and not successful("range.read")
        and "range.read" in actions
    ):
        return ["range.read"]
    pending_data_actions = [
        action
        for action in required_actions
        if action in DATA_ACTIONS and action in actions and not successful(action)
    ]
    if pending_data_actions:
        return pending_data_actions
    return actions


def constrain_stacked_aggregate_tool_schema(
    function: dict[str, Any],
    instruction: str,
    pivot_count: int | None,
) -> None:
    """Constrain only instruction-explicit cardinality and placement representation."""
    if function.get("name") != "adapter__pivot_create_stacked_aggregate":
        return
    parameters = function["parameters"]
    properties = parameters["properties"]
    if pivot_count is not None and 2 <= pivot_count <= 20:
        group_fields = properties["group_fields"]
        group_fields["minItems"] = pivot_count
        group_fields["maxItems"] = pivot_count
        group_fields["description"] += (
            f" This instruction requires exactly {pivot_count} pivots, so submit exactly "
            f"{pivot_count} freely selected observed grouping headers in this one call."
        )
        function["description"] += (
            f" Complete all {pivot_count} requested grouping dimensions in this one call; "
            "do not split them across turns."
        )
    if _BELOW_EXISTING_CONTENT_RE.search(instruction) is not None:
        properties.pop("destination", None)
        parameters.pop("oneOf", None)
        parameters["required"] = list(
            dict.fromkeys([*parameters["required"], "placement"])
        )
        properties["placement"]["description"] += (
            " The instruction explicitly requests output below existing content; select "
            "this representation instead of inventing an exact cell."
        )
        function["description"] += (
            " This stage requires semantic placement because the instruction explicitly "
            "requests output below existing content."
        )


@dataclass(frozen=True)
class SortIntent:
    """Application-level meaning of an explicit single-column Calc sort request."""

    clause: str
    ascending: bool
    contains_header: bool
    column_letter_hint: str | None = None


_SORT_VERB_RE = re.compile(r"(?i)\bsort(?:ed|ing)?\b")
_SORT_CLAUSE_END_RE = re.compile(
    r"(?i)(?:,\s*)?\b(?:and\s+then|then)\b|"
    r"(?:,\s*)?\band\s+(?:save|export|persist|write|open)\b|"
    r",\s*(?:save|export|persist|write|open)\b|[.;\n]"
)
_DESCENDING_RE = re.compile(
    r"(?i)\b(?:descending|decreasing|reverse\s+chronological)\b|"
    r"\b(?:largest|highest|newest|z)\s+to\s+(?:smallest|lowest|oldest|a)\b"
)
_NO_HEADER_RE = re.compile(r"(?i)\b(?:without|no)\s+(?:a\s+)?header(?:\s+row)?\b")
_COLUMN_LETTER_RE = re.compile(r"(?i)\bcolumn\s+([a-z]{1,3})\b")


def parse_sort_intent(instruction: str) -> SortIntent | None:
    """Parse an explicit Calc sort without consulting task identity or expected state."""
    match = _SORT_VERB_RE.search(instruction)
    if match is None:
        return None
    tail = instruction[match.start() :]
    clause = _SORT_CLAUSE_END_RE.split(tail, maxsplit=1)[0].strip(" ,")
    descending = bool(_DESCENDING_RE.search(clause))
    direction = not descending
    column_match = _COLUMN_LETTER_RE.search(clause)
    return SortIntent(
        clause=clause,
        ascending=direction,
        contains_header=not bool(_NO_HEADER_RE.search(clause)),
        column_letter_hint=(
            column_match.group(1).upper() if column_match is not None else None
        ),
    )


def resolve_sort_column(
    intent: SortIntent,
    headers: list[str],
    *,
    start_column: int,
    width: int,
) -> int | None:
    """Resolve a sort target to a zero-based column inside the observed table range."""
    normalized_headers = [re.sub(r"\s+", " ", str(value)).strip() for value in headers]
    hint = intent.column_letter_hint
    if hint is not None:
        header_matches = [
            index
            for index, header in enumerate(normalized_headers[:width])
            if header.casefold() == hint.casefold()
        ]
        if len(header_matches) == 1:
            return header_matches[0]
        absolute_index = _column_index(hint)
        relative_index = absolute_index - start_column
        if 0 <= relative_index < width:
            return relative_index

    clause = re.sub(r"\s+", " ", intent.clause).strip()
    header_matches = [
        index
        for index, header in enumerate(normalized_headers[:width])
        if header
        and re.search(
            rf"(?i)(?<!\w){re.escape(header)}(?!\w)",
            clause,
        )
    ]
    if not header_matches:
        clause_tokens = {
            _singular_sort_token(token)
            for token in re.findall(r"[A-Za-z0-9]+", clause.casefold())
        }
        header_matches = [
            index
            for index, header in enumerate(normalized_headers[:width])
            if header
            and {
                _singular_sort_token(token)
                for token in re.findall(r"[A-Za-z0-9]+", header.casefold())
            }.issubset(clause_tokens)
        ]
    return header_matches[0] if len(header_matches) == 1 else None


def _singular_sort_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def sort_table_spec(state: Any) -> dict[str, Any] | None:
    """Resolve an explicit sort against the table observed by a runtime state."""
    intent = parse_sort_intent(state.instruction)
    if state.domain == "multi_apps" and intent is not None:
        table = batch_table_semantics.observed_created_table(state)
        if table is None:
            return None
        geometry = a1_geometry(str(table.get("range", "")))
        headers = table.get("headers")
        if geometry is None or not isinstance(headers, list):
            return None
        start_column, _start_row, end_column, _end_row = geometry
        width = column_number(end_column) - column_number(start_column) + 1
        column = resolve_sort_column(
            intent,
            [str(value) for value in headers],
            start_column=column_number(start_column) - 1,
            width=width,
        )
        if column is None:
            return None
        return {
            "sheet": table["sheet"],
            "range": table["range"],
            "keys": [{"column": column, "ascending": intent.ascending}],
            "contains_header": intent.contains_header,
        }
    used_range = state.latest_workbook_used_range()
    if state.domain != "libreoffice_calc" or intent is None or used_range is None:
        return None
    sheet, cell_range = used_range
    geometry = a1_geometry(cell_range)
    if geometry is None:
        return None
    start_column, start_row, end_column, _end_row = geometry
    width = column_number(end_column) - column_number(start_column) + 1
    for event in state.successful_action_events("range.read"):
        arguments = event.proposed.get("arguments", {})
        if str(arguments.get("sheet", "")) != sheet:
            continue
        read_geometry = a1_geometry(str(arguments.get("range", "")))
        if read_geometry is None:
            continue
        read_start_column, read_start_row, read_end_column, _read_end_row = (
            read_geometry
        )
        if (
            read_start_column != start_column
            or read_end_column != end_column
            or read_start_row != start_row
        ):
            continue
        column = resolve_sort_column(
            intent,
            _first_display_row(event.result),
            start_column=column_number(start_column) - 1,
            width=width,
        )
        if column is not None:
            return {
                "sheet": sheet,
                "range": cell_range,
                "keys": [{"column": column, "ascending": intent.ascending}],
                "contains_header": intent.contains_header,
            }
    for event in reversed(state.successful_action_events("table.sort")):
        arguments = event.proposed.get("arguments", {})
        if not isinstance(arguments, dict):
            continue
        spec = _model_selected_observed_sort_spec(state, arguments)
        if spec is not None:
            return spec
    return None


def _model_selected_observed_sort_spec(
    state: Any, arguments: dict[str, Any]
) -> dict[str, Any] | None:
    """Validate a model-selected sort against live bounds when headers are unread."""
    used_range = state.latest_workbook_used_range()
    intent = parse_sort_intent(state.instruction)
    if state.domain != "libreoffice_calc" or used_range is None or intent is None:
        return None
    sheet, cell_range = used_range
    geometry = a1_geometry(cell_range)
    keys = arguments.get("keys")
    if (
        geometry is None
        or not isinstance(keys, list)
        or len(keys) != 1
        or not isinstance(keys[0], dict)
    ):
        return None
    key = keys[0]
    column = key.get("column")
    if isinstance(column, bool) or not isinstance(column, int):
        return None
    start_column, _start_row, end_column, _end_row = geometry
    width = column_number(end_column) - column_number(start_column) + 1
    if not (
        arguments.get("sheet") == sheet
        and arguments.get("range") == cell_range
        and arguments.get("contains_header", True) == intent.contains_header
        and 0 <= column < width
        and key.get("ascending", True) == intent.ascending
        and key.get("case_sensitive", False) is False
        and key.get("type", "automatic") in {"automatic", "alphanumeric", "numeric"}
    ):
        return None
    return {
        "sheet": sheet,
        "range": cell_range,
        "keys": [{"column": column, "ascending": intent.ascending}],
        "contains_header": intent.contains_header,
    }


def sort_arguments_match(state: Any, arguments: dict[str, Any]) -> bool:
    spec = sort_table_spec(state)
    keys = arguments.get("keys")
    if not isinstance(keys, list) or len(keys) != 1 or not isinstance(keys[0], dict):
        return False
    key = keys[0]
    column = key.get("column")
    if isinstance(column, bool) or not isinstance(column, int):
        return False
    if key.get("case_sensitive", False) is not False or key.get(
        "type", "automatic"
    ) not in {"automatic", "alphanumeric", "numeric"}:
        return False
    if spec is None:
        return _model_selected_observed_sort_spec(state, arguments) is not None
    expected_key = spec["keys"][0]
    return bool(
        arguments.get("sheet") == spec["sheet"]
        and arguments.get("range") == spec["range"]
        and arguments.get("contains_header", True) == spec["contains_header"]
        and column == expected_key["column"]
        and key.get("ascending", True) == expected_key["ascending"]
    )


def sort_event_matches(state: Any, event: Any) -> bool:
    arguments = event.proposed.get("arguments", {})
    return bool(
        event.executed
        and isinstance(arguments, dict)
        and sort_arguments_match(state, arguments)
    )


def sort_mutation_satisfied(state: Any) -> bool:
    if parse_sort_intent(state.instruction) is None:
        return True
    return any(
        sort_event_matches(state, event)
        for event in state.successful_action_events("table.sort")
    )


def sort_readback_satisfied(state: Any) -> bool:
    spec = sort_table_spec(state)
    if spec is None:
        return False
    sort_events = [
        event
        for event in state.successful_action_events("table.sort")
        if sort_event_matches(state, event)
    ]
    if not sort_events:
        return False
    latest_mutation_step = max(
        (
            event.step
            for event in state.successful_adapter_events()
            if not action_is_read_only(str(event.proposed.get("action", "")))
            and not action_is_save(str(event.proposed.get("action", "")))
        ),
        default=sort_events[-1].step,
    )
    save_steps = [
        event.step
        for event in state.successful_adapter_events()
        if action_is_save(str(event.proposed.get("action", "")))
        and event.step > latest_mutation_step
    ]
    geometry = a1_geometry(spec["range"])
    if not save_steps or geometry is None:
        return False
    start_column, start_row, end_column, end_row = geometry
    expected_width = column_number(end_column) - column_number(start_column) + 1
    expected_rows = end_row - start_row + 1
    key_column = int(spec["keys"][0]["column"])
    if state.domain == "multi_apps":
        rows = batch_table_semantics.latest_readback_rows(
            state,
            sheet=spec["sheet"],
            cell_range=spec["range"],
            after_step=save_steps[-1],
        )
        data_rows = rows[1:] if spec["contains_header"] else rows
        return bool(
            len(rows) == expected_rows
            and all(len(row) >= expected_width for row in rows)
            and data_rows
            and all(key_column < len(row) for row in data_rows)
            and sorted_sequence_state(
                [row[key_column] for row in data_rows],
                ascending=bool(spec["keys"][0]["ascending"]),
            )
            is True
        )
    for event in reversed(state.successful_action_events("range.read")):
        arguments = event.proposed.get("arguments", {})
        read_geometry = a1_geometry(str(arguments.get("range", "")))
        projection = _sort_readback_projection(
            geometry,
            read_geometry,
            key_column=key_column,
        )
        if event.step <= save_steps[-1] or arguments.get("sheet") != spec["sheet"]:
            continue
        if projection is None:
            continue
        value_column, expected_read_width = projection
        rows = _display_rows(event.result)
        data_rows = rows[1:] if spec["contains_header"] else rows
        if (
            len(rows) == expected_rows
            and all(len(row) >= expected_read_width for row in rows)
            and data_rows
            and all(value_column < len(row) for row in data_rows)
            and sorted_sequence_state(
                [row[value_column] for row in data_rows],
                ascending=bool(spec["keys"][0]["ascending"]),
            )
            is True
        ):
            return True
    return False


def _sort_readback_projection(
    table_geometry: tuple[str, int, str, int],
    read_geometry: tuple[str, int, str, int] | None,
    *,
    key_column: int,
) -> tuple[int, int] | None:
    """Return the value index and width for a complete sort-proof projection."""
    if read_geometry is None:
        return None
    start_column, start_row, end_column, end_row = table_geometry
    table_width = column_number(end_column) - column_number(start_column) + 1
    if not 0 <= key_column < table_width:
        return None
    if read_geometry == table_geometry:
        return key_column, table_width
    absolute_key_column = column_label(column_number(start_column) + key_column)
    if read_geometry == (
        absolute_key_column,
        start_row,
        absolute_key_column,
        end_row,
    ):
        return 0, 1
    return None


def validate_sort_arguments(state: Any, action: str, arguments: dict[str, Any]) -> bool:
    """Validate a sort call and return whether this semantic contract applied."""
    if action != "table.sort" or parse_sort_intent(state.instruction) is None:
        return False
    spec = sort_table_spec(state)
    if spec is None and state.latest_workbook_used_range() is None:
        raise ValueError(
            "create or inspect the complete table before sorting so the requested "
            "column and table bounds can be resolved"
        )
    if not sort_arguments_match(state, arguments):
        if spec is None:
            raise ValueError(
                "table.sort must use the complete observed table, a zero-based "
                "in-range column selected by the model, and the instruction's "
                "direction and header semantics"
            )
        raise ValueError(
            "table.sort must use the instruction- and observation-derived table, "
            f"column, and direction: {spec!r}"
        )
    return True


def constrain_sort_tool_schema(function: dict[str, Any], state: Any) -> None:
    if function.get("name") != "adapter__table_sort":
        return
    spec = sort_table_spec(state)
    if spec is None:
        used_range = state.latest_workbook_used_range()
        intent = parse_sort_intent(state.instruction)
        if state.domain != "libreoffice_calc" or used_range is None or intent is None:
            return
        sheet, cell_range = used_range
        geometry = a1_geometry(cell_range)
        if geometry is None:
            return
        start_column, _start_row, end_column, _end_row = geometry
        width = column_number(end_column) - column_number(start_column) + 1
        properties = function["parameters"]["properties"]
        properties["sheet"]["enum"] = [sheet]
        properties["range"]["enum"] = [cell_range]
        properties["contains_header"]["enum"] = [intent.contains_header]
        key_properties = properties["keys"]["items"]["properties"]
        key_properties["column"]["maximum"] = width - 1
        key_properties["ascending"]["enum"] = [intent.ascending]
        key_properties["case_sensitive"]["enum"] = [False]
        properties["keys"]["maxItems"] = 1
        properties["keys"]["items"]["required"] = ["column", "ascending"]
        function["parameters"]["required"] = [
            "sheet",
            "range",
            "keys",
            "contains_header",
        ]
        function["description"] += (
            " The schema fixes the complete live table, direction, and header flag. "
            f"Select one zero-based relative column between 0 and {width - 1}; "
            "choose automatic, alphanumeric, or numeric comparison from the live "
            "column semantics."
        )
        return
    properties = function["parameters"]["properties"]
    properties["sheet"]["enum"] = [spec["sheet"]]
    properties["range"]["enum"] = [spec["range"]]
    properties["contains_header"]["enum"] = [spec["contains_header"]]
    key_properties = properties["keys"]["items"]["properties"]
    expected_key = spec["keys"][0]
    key_properties["column"]["enum"] = [expected_key["column"]]
    key_properties["ascending"]["enum"] = [expected_key["ascending"]]
    key_properties["case_sensitive"]["enum"] = [False]
    properties["keys"]["maxItems"] = 1
    properties["keys"]["items"]["required"] = ["column", "ascending"]
    function["parameters"]["required"] = [
        "sheet",
        "range",
        "keys",
        "contains_header",
    ]
    function["description"] += (
        " The schema fixes the full observed table, zero-based relative sort column, "
        "direction, and header flag from the explicit sort clause: "
        f"{spec!r}."
    )


def sort_completion_missing(state: Any) -> list[str]:
    if parse_sort_intent(state.instruction) is None:
        return []
    spec = sort_table_spec(state)
    if spec is None:
        return [
            "create or inspect the complete spreadsheet table so the requested sort column, "
            "direction, and table bounds can be resolved"
        ]
    if not sort_mutation_satisfied(state):
        return [
            "sort the complete observed table with table.sort using the requested "
            f"column and direction: {spec!r}"
        ]
    if not sort_readback_satisfied(state):
        return [
            "after the final mutation and save, read back every row of the selected "
            "sort key (or the complete sorted table); the key must be monotonic in "
            "the requested direction"
        ]
    return []


def sorted_sequence_state(values: list[Any], *, ascending: bool) -> bool | None:
    """Return monotonic state when display values have one confidently comparable type."""
    nonblank = [value for value in values if str(value).strip()]
    if len(nonblank) < 2:
        return True
    parsed = [_comparable_value(value) for value in nonblank]
    kinds = {item[0] for item in parsed}
    if len(kinds) != 1:
        return None
    comparable = [item[1] for item in parsed]
    pairs = zip(comparable, comparable[1:])
    return all(left <= right if ascending else left >= right for left, right in pairs)


def _column_index(label: str) -> int:
    value = 0
    for character in label.upper():
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def _comparable_value(value: Any) -> tuple[str, Any]:
    text = str(value).strip()
    displayed_number = _displayed_number(text)
    if displayed_number is not None:
        return "number", displayed_number
    for format_string in (
        "%m/%d/%y %H:%M",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y",
        "%m/%d/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return "datetime", datetime.strptime(text, format_string)
        except ValueError:
            continue
    return "text", text.casefold()


_DISPLAYED_NUMBER_RE = re.compile(
    r"[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?|\.\d+)"
    r"(?:[eE][+-]?\d+)?"
)


def _displayed_number(text: str) -> Decimal | None:
    """Parse a complete numeric spreadsheet display token without digit extraction."""
    token = text.replace("\N{NO-BREAK SPACE}", " ").strip()
    if not token:
        return None

    accounting_negative = token.startswith("(") and token.endswith(")")
    if accounting_negative:
        token = token[1:-1].strip()
    elif "(" in token or ")" in token:
        return None

    percent = token.endswith("%")
    if percent:
        token = token[:-1].strip()
    if "%" in token:
        return None

    sign = ""
    if token[:1] in {"+", "-"}:
        sign, token = token[0], token[1:].strip()

    currency_seen = False
    while token and unicodedata.category(token[0]) == "Sc":
        currency_seen = True
        token = token[1:].strip()
    while token and unicodedata.category(token[-1]) == "Sc":
        currency_seen = True
        token = token[:-1].strip()

    # A currency sign may precede a signed value, as Calc can display "$-45.00".
    if token[:1] in {"+", "-"}:
        if sign:
            return None
        sign, token = token[0], token[1:].strip()

    if any(unicodedata.category(character) == "Sc" for character in token):
        return None
    if currency_seen and percent:
        return None
    if accounting_negative and sign:
        return None

    normalized = sign + token
    if _DISPLAYED_NUMBER_RE.fullmatch(normalized) is None:
        return None
    try:
        number = Decimal(normalized.replace(",", ""))
    except InvalidOperation:
        return None
    if accounting_negative:
        number = -number
    if percent:
        number /= Decimal(100)
    return number


def _first_display_row(value: Any) -> list[str]:
    rows = _display_rows(value)
    return rows[0] if rows else []


def _display_rows(value: Any) -> list[list[str]]:
    if isinstance(value, dict):
        display_text = value.get("display_text")
        if isinstance(display_text, list) and all(
            isinstance(row, list) for row in display_text
        ):
            return [[str(item) for item in row] for row in display_text]
        if value.get("truncated") and isinstance(value.get("preview"), str):
            preview = value["preview"]
            marker = preview.find('"display_text"')
            start = preview.find("[", marker)
            if marker >= 0 and start >= 0:
                try:
                    rows, _end = json.JSONDecoder().raw_decode(preview, start)
                    if isinstance(rows, list) and all(
                        isinstance(row, list) for row in rows
                    ):
                        return [[str(item) for item in row] for row in rows]
                except (ValueError, json.JSONDecodeError):
                    pass
        for nested in value.values():
            rows = _display_rows(nested)
            if rows:
                return rows
    elif isinstance(value, list):
        for nested in value:
            rows = _display_rows(nested)
            if rows:
                return rows
    return []
