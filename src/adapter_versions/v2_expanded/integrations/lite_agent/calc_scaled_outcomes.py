"""Verify scaled column outputs from native cells, independently of tool choice."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import re
from typing import Any

from .calc_scaled_display import scaled_display_contract
from .completion_policy import action_is_read_only, action_is_save
from .completion_outcomes import (
    _complete_rows, _events, _issue, _same_document, _used_rectangle, rectangle,
)


REPAIR_ACTIONS = (
    "workbook.inspect", "range.read", "range.copy", "cells.set_formulas",
    "range.write", "range.set_scaled_display", "range.format", "workbook.save",
)


def _column(value: int) -> str:
    label = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return label


def _decimal(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError("not a native value")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("non-finite value")
    return number


def _cells(events: list) -> dict[tuple[str, int, int], list[dict]]:
    """Retain cell observations; partial reads may cover an extent together."""
    cells: dict[tuple[str, int, int], list[dict]] = {}
    for event, action, args, payload in events:
        if not _same_document(events, event, payload):
            continue
        if action == "range.read":
            snapshot = payload
            sheet, area = args.get("sheet"), args.get("range")
            if (payload.get("sheet", sheet) != sheet
                    or rectangle(payload.get("range", area)) != rectangle(area)):
                continue
        elif isinstance(payload.get("readback"), dict):
            snapshot = payload["readback"]
            sheet = payload.get("sheet", payload.get("destination_sheet"))
            area = payload.get("range", payload.get("destination_range"))
        else:
            continue
        rect = rectangle(area)
        rows = _complete_rows(snapshot, rect)
        if not sheet or rows is None:
            continue
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                cell = {"display": str(text), "step": event.step, "action": action}
                for field in ("values", "kinds", "number_formats"):
                    matrix = snapshot.get(field)
                    if (isinstance(matrix, list) and r < len(matrix)
                            and isinstance(matrix[r], list) and c < len(matrix[r])):
                        cell[field] = matrix[r][c]
                cells.setdefault((sheet, rect[0] + c, rect[1] + r), []).append(cell)
    return cells


def _display_matches(text: str, expected: Decimal, output: Any, spec: dict, cell: dict) -> bool:
    separator = spec["separator"]
    suffix = re.escape((separator or "") + output.unit)
    if separator is None:
        suffix = r"\s*" + re.escape(output.unit)
    locale = str((cell.get("number_formats") or {}).get("locale", "en-US"))
    decimal_mark, group = (",", ".") if locale.startswith(("de", "es", "it", "pt")) else (".", ",")
    places = spec["decimal_places"]
    digits = rf"[+-]?\d+(?:{re.escape(group)}\d{{3}})*"
    if places:
        digits += rf"{re.escape(decimal_mark)}\d{{{places}}}"
    match = re.fullmatch(rf"({digits}){suffix}", text)
    if not match:
        return False
    value = _decimal(match[1].replace(group, "").replace(decimal_mark, "."))
    return value == expected


def _valid_value(cell: dict, source: Decimal, scaled: Decimal, rounded: Decimal) -> bool:
    if "values" not in cell or cell.get("kinds") not in {"number", "formula", "string"}:
        return False
    if isinstance(cell["values"], str) and cell["values"] == cell["display"]:
        # TEXT formulas and explicit formatted text are legal representations.
        return True
    try:
        value = _decimal(cell["values"])
    except (ValueError, InvalidOperation):
        return False
    return any(abs(value - candidate) <= max(abs(candidate), Decimal(1)) * Decimal("1e-12")
               for candidate in (source, scaled, rounded))


def _source_touched(action: str, args: dict, sheet: str, column: int, first: int, last: int) -> bool:
    if action_is_read_only(action) or action_is_save(action) or action in {
        "range.set_scaled_display", "range.format", "workbook.inspect",
    }:
        return False
    if action == "range.copy":
        target_sheet, area = args.get("destination_sheet"), args.get("destination")
        rect, source_rect = rectangle(area), rectangle(args.get("source_range"))
        if rect and source_rect:
            width, height = source_rect[2] - source_rect[0], source_rect[3] - source_rect[1]
            if args.get("transpose"):
                width, height = height, width
            rect = (rect[0], rect[1], rect[0] + width, rect[1] + height)
    else:
        target_sheet, rect = args.get("sheet"), rectangle(args.get("range"))
    if action == "cells.set_formulas" and target_sheet == sheet:
        return any((cell := rectangle(write.get("cell"))) and cell[0] == column
                   and first <= cell[1] <= last for write in args.get("writes", []))
    if target_sheet is not None and target_sheet != sheet:
        return False
    if rect:
        return rect[0] <= column <= rect[2] and rect[1] <= last and rect[3] >= first
    return True  # Unknown mutations and GUI actions invalidate source evidence.


def scaled_display_issues(state: Any) -> list[dict]:
    spec = scaled_display_contract(str(state.instruction))
    if spec is None:
        return []
    events = _events(state)
    mutations = [(e, a, ar) for e, a, ar, _ in events
                 if not action_is_read_only(a) and not action_is_save(a)]
    if not mutations:
        return []
    cells = _cells(events)
    headers = [(key, observations[0]) for key, observations in cells.items()
               if observations[0]["action"] == "range.read"
               and observations[0]["display"].strip().casefold() == spec["source_header"].casefold()]
    targets = {"source_header": spec["source_header"],
               "output_columns": [output.destination_column for output in spec["outputs"]]}

    def issue(code, target, expected, observed, **kwargs):
        return _issue("scaled_display." + code, target, expected, observed,
                      actions=REPAIR_ACTIONS, **kwargs)

    if len(headers) != 1:
        return [issue("source_unverified", targets, "read the uniquely named source column including its header and all rows",
                      {"matching_headers": len(headers)})]
    (sheet, column, header_row), _ = headers[0]
    extent = next((used for _, action, _, p in events if action == "workbook.inspect"
                   for s in p.get("sheets", []) if s.get("name") == sheet
                   and (used := _used_rectangle(s)) and used[0] <= column <= used[2]), None)
    if extent is None:
        return [issue("source_extent_unverified", targets, "workbook.inspect with the source used range", None)]
    first, last = header_row + 1, extent[3]
    source = {}
    for row in range(first, last + 1):
        observations = [c for c in cells.get((sheet, column, row), []) if c["action"] == "range.read"]
        if not observations:
            return [issue("source_unverified", {**targets, "sheet": sheet, "cell": f"{_column(column)}{row}"},
                          "read every source row in the observed used extent", None)]
        baseline = observations[0]
        changed = max((e.step for e, action, args in mutations
                       if _source_touched(action, args, sheet, column, row, row)), default=0)
        if changed >= observations[-1]["step"]:
            return [issue("source_unverified", {"sheet": sheet, "cell": f"{_column(column)}{row}"},
                          "read source values after the latest possible source change", None)]
        if baseline.get("kinds") == "blank":
            continue
        try:
            if baseline.get("kinds") not in {"number", "formula"}:
                raise ValueError("source is not numeric")
            source[row] = _decimal(baseline.get("values"))
            if _decimal(observations[-1].get("values")) != source[row]:
                raise ValueError("source numeric value changed")
        except (ValueError, InvalidOperation):
            return [issue("source_value_unverified", {"sheet": sheet, "cell": f"{_column(column)}{row}"},
                          "original native numeric source value", baseline.get("values"))]
    if not source:
        return [issue("source_unverified", targets, "nonempty numeric source column", None)]
    last_mutation = max(e.step for e, _, _ in mutations)
    after = max([last_mutation] + [e.step for e, a, _, _ in events if action_is_save(a)])
    issues = []
    for output in spec["outputs"]:
        destination = rectangle(output.destination_column + "1")[0]
        target = {"sheet": sheet, "range": f"{output.destination_column}{min(source)}:{output.destination_column}{max(source)}"}
        wrong, unseen = [], []
        for row, value in source.items():
            address = f"{output.destination_column}{row}"
            observations = cells.get((sheet, destination, row), [])
            cell = observations[-1] if observations else None
            with localcontext() as context:
                context.prec = 64
                scaled = value / Decimal(output.divisor)
                rounded = scaled.quantize(Decimal(1).scaleb(-spec["decimal_places"]), rounding=ROUND_HALF_UP)
            expected = f"{rounded:.{spec['decimal_places']}f}{spec['separator'] or ''}{output.unit}"
            if cell is None or cell["step"] < last_mutation:
                unseen.append(address)
                continue
            try:
                correct = (_display_matches(cell["display"], rounded, output, spec, cell)
                           and _valid_value(cell, value, scaled, rounded))
            except (InvalidOperation, ValueError, TypeError):
                correct = False
            if not correct:
                wrong.append({"cell": address, "source_cell": f"{_column(column)}{row}",
                              "source_value": str(value), "expected_display": expected,
                              "observed_display": cell["display"], "observed_value": cell.get("values"),
                              "observed_kind": cell.get("kinds")})
            elif cell["step"] <= after:
                unseen.append(address)
        if wrong:
            issues.append(issue("output_mismatch", target,
                                "populate each target from its source, then match scale, precision, unit and spacing; formatting alone does not transfer values",
                                {"wrong_cells": wrong}, step=max(c["step"] for key, cs in cells.items()
                                    if key[0] == sheet and key[1] == destination for c in cs), mismatch=True))
        if unseen:
            issues.append(issue("output_unverified", target, "read every target's native value and display after final mutation and save",
                                {"unverified_cells": unseen, "after_step": after}))
    return issues
