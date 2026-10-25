"""Native scaled-cell evidence, ported from liuxv ccd4deb.

Only the scaled-display contract is enabled in this integration. Evidence is
read from public observations; task ids, evaluator data and repairs are absent.
"""
from __future__ import annotations

import re
from typing import Any
from .completion_policy import action_is_read_only, effective_canonical_action

def result_payload(event: Any) -> dict[str, Any]:
    """Prefer full native evidence over the bounded model-context projection."""
    result = event.result
    if not isinstance(result, dict):
        return {}
    response = result.get("adapter_response")
    if isinstance(response, dict) and isinstance(response.get("result"), dict):
        if not response.get("truncated"):
            return response["result"]
        # AdapterExecutor can compact the raw envelope while retaining a
        # larger purpose-built cell/object hint. A raw summary is not fuller
        # evidence merely because it is under adapter_response.result.
        if isinstance(result.get("context_hint"), dict):
            return result["context_hint"]
        return {**response["result"], "context_truncated": True}
    for key in ("result", "context_hint"):
        if isinstance(result.get(key), dict):
            return result[key]
    return result


def _events(state: Any) -> list[tuple[Any, str, dict[str, Any], dict[str, Any]]]:
    events = []
    for event in state.events:
        kind = event.proposed.get("kind")
        if kind == "gui":
            if event.executed or event.validated:
                events.append((event, "gui", {}, {}))
            continue
        if kind != "adapter":
            # Searches, audits and successful completion claims change no file.
            continue
        domain, action, args = effective_canonical_action(event, state.domain)
        if not event.executed or getattr(event, "error", None):
            if domain == "libreoffice_calc" and event.validated and not action_is_read_only(action):
                # A dispatched replacement can remove the old object before
                # failing. Never reuse a snapshot from before that attempt.
                events.append((event, "uncertain:" + action, args, {}))
            continue
        # Opening another workbook invalidates evidence from the previous file.
        if domain == "libreoffice_calc" and action in {"workbook.open", "workbook.create_new"}:
            events = []
        if domain == "libreoffice_calc":
            events.append((event, action, args, result_payload(event)))
    return events


def _issue(code: str, target: Any, expected: Any, observed: Any, *,
           actions: tuple[str, ...], step: int | None = None,
           mismatch: bool = False) -> dict[str, Any]:
    return {
        "code": code,
        "kind": "state_mismatch" if mismatch else "missing_observation",
        "target": target,
        "expected": expected,
        "observed": observed,
        "evidence_step": step,
        "repair_actions": list(actions),
        "message": f"{code}: {target}; required {expected!r}; observed {observed!r}",
    }


def rectangle(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\$?([A-Za-z]+)\$?([1-9]\d*)(?::\$?([A-Za-z]+)\$?([1-9]\d*))?", value)
    if not match:
        return None

    def column(word: str) -> int:
        number = 0
        for char in word.upper():
            number = number * 26 + ord(char) - 64
        return number

    rect = (column(match[1]), int(match[2]), column(match[3] or match[1]), int(match[4] or match[2]))
    return rect if rect[0] <= rect[2] and rect[1] <= rect[3] else None


def _complete_rows(payload: dict[str, Any], rect: Any) -> list | None:
    rows = payload.get("display_text")
    if (not rect or payload.get("truncated") or payload.get("context_truncated")
            or not isinstance(rows, list) or len(rows) != rect[3] - rect[1] + 1
            or any(not isinstance(row, list) or len(row) != rect[2] - rect[0] + 1 for row in rows)):
        return None
    return rows


def _same_document(events: list, event: Any, payload: dict) -> bool:
    inspections = [(e, p.get("url")) for e, a, _, p in events if a == "workbook.inspect" and p.get("url")]
    current_url = inspections[-1][1] if inspections else None
    preceding = [url for e, url in inspections if e.step < event.step]
    read_url = payload.get("workbook_url") or (preceding[-1] if preceding else None)
    return not (current_url and read_url and current_url != read_url)


def _used_rectangle(sheet: dict) -> Any:
    if rect := rectangle(sheet.get("used_range_a1")):
        return rect
    used = sheet.get("used_range")
    if isinstance(used, dict) and all(k in used for k in ("start_column", "start_row", "end_column", "end_row")):
        return tuple(int(used[k]) + 1 for k in ("start_column", "start_row", "end_column", "end_row"))
    return None

def completion_outcome_issues(state: Any) -> list[dict[str, Any]]:
    from .batch_progress import batch_coverage_issues
    issues = batch_coverage_issues(state)
    if state.domain != "libreoffice_calc":
        return issues
    from .calc_scaled_outcomes import scaled_display_issues
    from .calc_observation_checks import observed_calc_issues
    return issues + scaled_display_issues(state) + observed_calc_issues(state)
