"""Report concrete omissions from observed cells and native chart bindings."""
from __future__ import annotations

import re
from typing import Any

from .completion_policy import action_is_read_only, action_is_save


def observed_calc_issues(state: Any) -> list[dict]:
    from .completion_outcomes import _events, _complete_rows, rectangle, _issue
    instruction = str(state.instruction)
    requested_headers = {m.casefold() for m in re.findall(r'["“]([^"”]+)["”]', instruction)}
    calculates = bool(re.search(r'(?i)\b(?:calculate|compute)\b', instruction))
    axis = re.search(r'(?i)["“]([^"”]+)["”]\s+(?:column\s+)?on\s+(?:the\s+)?x[- ]axis', instruction)
    single_chart = bool(re.search(r'(?i)\b(?:a|one)\s+(?:line|bar|column)\s+chart\b', instruction))
    reads: dict[tuple, tuple] = {}
    charts: dict[tuple, tuple] = {}
    for event, action, args, result in _events(state):
        if action == 'gui' or action.startswith('uncertain:'):
            reads.clear()
            charts.clear()
            continue
        if not action_is_read_only(action) and not action_is_save(action):
            reads.clear()  # Never reject completion from cells read before an edit.
            if action != 'chart.create':
                charts.clear()
        if action == 'range.read':
            area = result.get('range', args.get('range'))
            rows = _complete_rows(result, rectangle(area))
            if rows:
                reads[(result.get('sheet', args.get('sheet')), area)] = (event.step, rows)
        if action == 'chart.create':
            charts[(result.get('sheet'), result.get('name'))] = (event.step, result)
        if action == 'workbook.inspect':
            for sheet in result.get('sheets', []):
                for chart in sheet.get('charts', []):
                    charts[(sheet.get('name'), chart.get('name'))] = (event.step, chart)
    issues = []
    if calculates:
        for (sheet, area), (step, rows) in reads.items():
            if len(rows) < 2 or not any(str(v or '').strip() for row in rows[1:] for v in row):
                continue
            for column, label in enumerate(rows[0]):
                if (str(label).casefold() in requested_headers
                    and all(not str(row[column] or '').strip() for row in rows[1:])):
                    issues.append(_issue('table.empty_requested_column', {'sheet': sheet, 'range': area, 'header': label},
                        'calculated table includes data for this explicitly requested header', 'all observed data cells are blank',
                        actions=('range.read', 'range.write', 'cells.set_formulas'), step=step, mismatch=True))
    if axis and single_chart:
        for (sheet, name), (step, chart) in charts.items():
            labels = [str(label).casefold() for series in chart.get('data_series', []) for label in series.get('labels', [])]
            if chart.get('category_axes') == [] and axis[1].casefold() in labels:
                issues.append(_issue('chart.category_is_value_series', {'sheet': sheet, 'chart': name},
                    f'{axis[1]} on the X axis', f'{axis[1]} is plotted as a numeric series and no category axis is bound',
                    actions=('range.read', 'chart.create'), step=step, mismatch=True))
                issues[-1]['message'] += '. Re-read the source and replace the same chart with the appropriate header binding; for column-oriented data row_headers=true binds the first selected column as categories.'
    return issues
