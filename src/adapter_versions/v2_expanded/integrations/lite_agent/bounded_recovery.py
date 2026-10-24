"""Recover from observed repetition without supplying actions or task answers."""
from __future__ import annotations

import copy
import json
from typing import Any

from .completion_policy import action_is_read_only, effective_canonical_action


def _stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def recent_failure(state: Any) -> Any:
    """Search itself cannot erase an unresolved execution error."""
    for event in reversed(list(getattr(state, 'events', ())) [-3:]):
        if event.proposed.get('kind') == 'catalog':
            continue
        return event if event.error and not event.executed else None
    return None


def repeated_route(state: Any) -> tuple[str, str] | None:
    """Detect search/read and search/error cycles without merging different targets."""
    events = list(getattr(state, 'events', ()))[-7:]
    attempts = [e for e in events if e.proposed.get('kind') != 'catalog'][-3:]
    if len(attempts) < 3 or len({getattr(e, 'retry', 0) for e in attempts}) != 1:
        return None
    if not all(e.proposed.get('kind') == 'adapter' for e in attempts):
        return None
    identities = [effective_canonical_action(e, state.domain) for e in attempts]
    if len({_stable(x) for x in identities}) != 1:
        return None
    if (all(not e.executed and isinstance(e.error, dict) for e in attempts)
        and attempts[-1].error.get('type') == 'RepeatedActionBlocked'):
        return identities[-1][:2]
    hints = [(e.result or {}).get('context_hint') for e in attempts]
    if (action_is_read_only(identities[-1][1])
        and all(e.executed and not e.error for e in attempts)
        and all(isinstance(h, dict) and h for h in hints)
        and len({_stable(h) for h in hints}) == 1):
        return identities[-1][:2]
    return None


def repeated_tool(state: Any) -> str | None:
    """Only consecutive, equivalent calls in the same state trigger recovery."""
    if cycling := text_transform_cycle(state):
        return cycling
    if repeated_route(state):
        return next(e.proposed.get('tool') for e in reversed(state.events)
                    if e.proposed.get('kind') == 'adapter')
    events = list(getattr(state, "events", ()))[-3:]
    if len(events) < 3 or len({getattr(e, "retry", 0) for e in events}) != 1:
        return None
    latest = events[-1]
    proposals = [e.proposed for e in events]
    if not all(isinstance(p, dict) for p in proposals):
        return None
    names = {p.get("tool") for p in proposals}
    if len(names) != 1 or not next(iter(names)):
        return None
    requests = [_stable(p.get("arguments")) for p in proposals]
    if len(set(requests)) != 1:
        return None
    if all(p.get("kind") == "catalog" and e.executed and not e.error
           for p, e in zip(proposals, events)):
        results = [e.result for e in events]
        if all(isinstance(result, dict) for result in results) and len(
            {_stable(result) for result in results}
        ) == 1:
            return latest.proposed["tool"]
    routes = [effective_canonical_action(e, state.domain) for e in events]
    if len({_stable(r) for r in routes}) != 1:
        return None
    if all(not e.executed and isinstance(e.error, dict) for e in events):
        if latest.error.get("type") == "RepeatedActionBlocked":
            return latest.proposed["tool"]
    if all(e.executed and not e.error for e in events) and action_is_read_only(routes[-1][1]):
        hints = [(e.result or {}).get("context_hint") for e in events]
        if all(isinstance(h, dict) and h for h in hints) and len({_stable(h) for h in hints}) == 1:
            return latest.proposed["tool"]
    return None


def text_transform_cycle(state: Any) -> str | None:
    """Detect repeated deterministic rewrites of one output, not a batch of cells."""
    events = list(getattr(state, "events", ()))[-6:]
    if len(events) < 6 or len({getattr(e, "retry", 0) for e in events}) != 1:
        return None
    requests = []
    targets = set()
    for event in events:
        if not event.executed or event.error or not isinstance(event.proposed, dict):
            return None
        domain, action, arguments = effective_canonical_action(event, state.domain)
        if domain != "libreoffice_calc" or action != "range.text_transform":
            return None
        targets.add(_stable([arguments.get("destination_sheet"), arguments.get("destination")]))
        request = dict(arguments)
        request.setdefault("skip_blank", False)
        requests.append(_stable(request))
    if len(targets) == 1 and len(set(requests)) <= 3:
        return events[-1].proposed.get("tool")
    return None


def recover_tools(tools: list[dict], state: Any) -> list[dict]:
    repeated = repeated_tool(state)
    if repeated is None:
        return tools
    if repeated == "adapter__adapter_call":
        # Pause only the repeated route, preserving other discovered operations.
        route = repeated_route(state)
        alternatives = []
        for original in tools:
            tool = copy.deepcopy(original)
            function = tool.get('function', {})
            if function.get('name') == repeated and route:
                schema = function.get('parameters', {})
                fixed = schema.get('x-route', {})
                if (fixed.get('adapter'), fixed.get('action')) == route:
                    continue
                if isinstance(schema.get('oneOf'), list):
                    def identity(branch):
                        props = branch.get('properties', {})
                        return tuple(props.get(k, {}).get('enum', [None])[0] for k in ('adapter', 'action'))
                    schema['oneOf'] = [b for b in schema['oneOf'] if identity(b) != route]
                    if not schema['oneOf']:
                        continue
            alternatives.append(tool)
    else:
        alternatives = [t for t in tools if t.get("function", {}).get("name") != repeated]
    # Never replace a solvable action surface with only terminal controls.
    if any(t.get("function", {}).get("name") not in {"propose_done", "fail_task"}
           for t in alternatives):
        return alternatives
    return tools


def recovery_guidance(state: Any) -> str:
    guidance = []
    if text_transform_cycle(state):
        guidance.append(
            "Repeated text transformations are overwriting the same destination. "
            "Each call starts from its source_range; reading the original source again "
            "discards earlier transformations. Inspect the current destination, compare "
            "it with the requested result, then use the previous output as the source "
            "for any remaining operation. Do not recreate the same cycle."
        )
    if repeated_tool(state):
        guidance.append(
            "The last three calls supplied no new information or repeated a rejected request. "
            "That tool may be paused for this turn. Identify the unmet user requirement and "
            "choose a materially different available action, including GUI when exposed. "
            "Do not claim completion merely to escape the loop."
        )
    failure = recent_failure(state)
    if failure is None:
        return " ".join(guidance)
    error = _stable(failure.error).casefold()
    if 'identical successful action' in error:
        guidance.append('This exact operation already succeeded and no later mutation invalidated it. Read back its effect and compare remaining requirements. If all are satisfied, propose_done; repeating save or the same edit is unnecessary.')
    if any(code in error for code in ('range_invalid', 'range_dimensions_mismatch', 'matrix dimensions')):
        guidance.append('The write rectangle and values matrix must have identical row and column counts. Read the intended headers and cells, then regenerate both from the observed data. Do not repeat the mismatched matrix or invent padding values.')
    if any(code in error for code in ('message_not_found', 'message_selector_mismatch')):
        guidance.append('Query the actual mail folder again. mailbox_index is an integer row selector; message_id is the Message-ID header, never a stringified row number. Use fields from the same returned message and omit an absent message_id.')
    if any(code in error for code in ('text_not_found', 'shape_not_found', 'slide_not_found', 'sheet_not_found', 'bookmark_not_found', 'pdf_form_field_not_found')):
        guidance.append('Refresh the owning document inspection or text search. Use an exact returned name, field, index or body-text anchor; window titles are not document text. Deletions can shift indices. If the document is empty, discover an insertion primitive that does not require existing text.')
    if 'no_calc_document' in error:
        guidance.append('No active Calc document exists. Locate and open the intended spreadsheet, or create one when the instruction requests a new workbook, before reading or writing cells.')
    if 'verify' in error and 'unsupported' in error:
        guidance.append('The optional verification metadata was rejected. Consult the action schema and regenerate only documented verification fields, or omit optional verification metadata and perform a separate structural read-back.')
    if any(code in error for code in ("file_not_found", "path_not_found", "no_matches")):
        guidance.append(
            "Discover the actual source with filesystem listing/search or the owning application's "
            "query before retrying. A mailbox folder is not a filesystem directory. Download an "
            "observed attachment before opening it. Use exact observed paths, not invented filenames."
        )
    if "document_open_failed" in error:
        guidance.append(
            "The selected reader could not open this file. Inspect its type and choose the owning "
            "application: spreadsheets use Calc, text documents use Writer, PDFs use a PDF reader. "
            "Do not repeat the same reader on the same unsupported file."
        )
    if "text_mismatch" in error or "expected_text length" in error:
        guidance.append(
            "The observed text range and expected_text do not match. Reuse matched_text and its "
            "paragraph index and offsets from the latest text search result; offsets are zero-based "
            "with an exclusive end. Do not guess a longer range or retry the old arguments."
        )
    if "rectangular" in error:
        guidance.append(
            "Each row of values must have the same number of cells. A formula is ONE cell, "
            "never two cells containing '=' and its expression. Use the exposed formula-write "
            "contract and verify that its target dimensions match the supplied matrix."
        )
    return " ".join(guidance)
