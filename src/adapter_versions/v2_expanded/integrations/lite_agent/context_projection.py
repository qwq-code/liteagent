"""Bounded, model-facing projections for Adapter observations.

Adapter results remain complete in the event trace.  This module only builds a
small, JSON-safe view for the next model request.  It deliberately knows
nothing about task identity, evaluators, or application-specific workflows.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

from multi_apps_adapter.route_utils import (
    contains_route_in_prose,
    decode_text,
    has_unresolved_encoding,
    normalize_route,
)

MODEL_CONTEXT_HINT_DEFAULT_MAX_CHARS = 5_000
MODEL_CONTEXT_HINT_MAX_CHARS = 65_000
MODEL_CONTEXT_HINT_TOTAL_MAX_CHARS = 65_000
MODEL_CONTEXT_HINT_MIN_CHARS = 64
MODEL_CONTEXT_MAX_LIST_ITEMS = 12
# A single diagnostic/detail string must not crowd out selectors and paths.
MODEL_CONTEXT_MAX_STRING_CHARS = 1_200

_HIDDEN_KEYS = frozenset(
    {
        "answer",
        "answer_sheet",
        "answer_url",
        "cloud_file",
        "dataset_id",
        "dataset_order",
        "evaluation_examples",
        "evaluator",
        "evaluator_config",
        "evaluator_url",
        "expected",
        "expected_getter",
        "expected_state",
        "expected_value",
        "golden",
        "golden_file",
        "golden_hash",
        "golden_url",
        "postconfig",
        "reference_artifact",
        "reference_profile",
        "result_getter",
        "argument_signature",
        "error_signature",
        "request_id",
        "reasoning_effort_effective",
        "reasoning_effort_requested",
        "reasoning_mode_effective",
        "reasoning_mode_requested",
        "reasoning_observed",
        "model_actual",
        "task_id",
        "task_uuid",
        "taskid",
        "task_prefix",
        "uuid",
    }
)
_HIDDEN_KEYS_NORMALIZED = {normalize_route(key) for key in _HIDDEN_KEYS}
# Runtime metadata often arrives with a known sensitive suffix (for example
# ``answer_value`` or ``evaluator_url``).  Matching every key that merely
# starts with ``answer``/``task`` is unsafe: ordinary application fields such
# as ``answer_format`` and ``task_name`` are valid model observations.  Keep a
# small, explicit suffix vocabulary and leave unrelated user fields intact.
_HIDDEN_KEY_FAMILIES = frozenset(
    {
        "answer",
        "cloudfile",
        "dataset",
        "evaluation",
        "evaluator",
        "expected",
        "golden",
        "reference",
        "resultgetter",
        "task",
    }
)
_HIDDEN_KEY_SUFFIXES = frozenset(
    {
        "artifact",
        "file",
        "getter",
        "hash",
        "id",
        "order",
        "path",
        "prefix",
        "profile",
        "secret",
        "state",
        "url",
        "value",
    }
)
_HIDDEN_MARKERS = (
    "artifact.materialize",
    "artifact_materialize",
    "evaluation_examples",
    "evaluator_config",
    "evaluator_url",
    "expected_getter",
    "result_getter",
    "golden_file",
    "golden_hash",
    "golden_url",
    "task_manifest.json",
    "task-manifest",
    "taskid",
    "task_id",
    "task uuid",
    "task_uuid",
    "task.execute",
    "task.inspect",
    "task_execute",
    "task_inspect",
    "assessment.grade_multiple_choice_documents",
    "assessment_grade_multiple_choice_documents",
    "osworld_baby_justin_bieber",
    "evaluator_url",
    "expected_state",
    "reference_profile",
    "answer_url",
    "ubuntu_osworld_file_cache",
    "xlang-ai/osworld",
    "xlangai/osworld",
)
_HIDDEN_MARKERS_NORMALIZED = frozenset(
    normalize_route(marker) for marker in _HIDDEN_MARKERS
)
# These words are only meaningful as hidden metadata when they occur in a
# structured error/metadata field.  They must not erase ordinary document
# prose (for example, ``The answer column is on the right``).
# Standalone ``expected``/``reference`` are also ordinary error vocabulary.
_SENSITIVE_WORD_MARKERS = (
    "answer",
    "dataset",
    "golden",
    "evaluator",
)
_SENSITIVE_CONTEXT_KEYS = frozenset(
    {
        "error",
        "errorcode",
        "details",
        "cause",
        "previouserror",
        "exception",
        "failure",
    }
)
_SENSITIVE_IDENTIFIER_RE = re.compile(
    r"(?i)^(?:answer|expected|reference|dataset|golden|evaluator)"
    r"(?:[_:.\-/](?:artifact|file|getter|hash|id|order|path|prefix|"
    r"profile|secret|state|url|value))+$"
)
_FORBIDDEN_ACTIONS = frozenset(
    {
        "artifact.materialize",
        "task.execute",
        "task.inspect",
        "assessment.grade_multiple_choice_documents",
    }
)
_FORBIDDEN_ACTIONS_NORMALIZED = {
    normalize_route(action) for action in _FORBIDDEN_ACTIONS
}
_KEY_PRIORITY = {
    "status": 100,
    "routing_guidance": 99,
    "verification_passed": 100,
    "passed": 100,
    "error_code": 99,
    "path": 98,
    "url": 98,
    "media_url": 98,
    "range": 97,
    "sheet": 97,
    "active_sheet": 97,
    "action": 96,
    "adapter": 96,
    "selector": 95,
    "media_shapes": 95,
    "handle": 95,
    "source": 94,
    "destination": 94,
    "target": 94,
    # A1 coordinates are positional metadata for Calc matrices.  Keep them
    # alongside the observed matrix so a bounded projection cannot force the
    # model to infer a cell address from row/column offsets.
    "cell_addresses": 86,
    # Formatting previews must retain coverage before their partial cell maps.
    "readback_range": 97,
    "truncated": 89,
    "background_cells_truncated": 89,
    "date_cells_truncated": 89,
    "range_results": 88,
    "formatted_ranges": 87,
    "background_cells": 87,
    "date_cells": 86,
    "title": 92,
    "name": 91,
    "kind": 91,
    "index": 90,
    "nonempty_ordinal": 90,
    "count": 88,
    "matches": 87,
    "files": 87,
    "slides": 87,
    "rows": 86,
    "columns": 86,
    "line_spacing": 85,
    "display_text": 84,
    "formulas": 84,
    "content": 84,
    "text": 84,
    "notes": 84,
    # Batch continuation metadata must survive a bounded retry fit.
    "observation_type": 96,
    "input_pattern": 95,
    "start_page": 94,
    "page_count": 94,
    "matched_count": 93,
    "files_omitted": 90,
    "context_files_omitted": 90,
    "chunks": 89,
    "offset_basis": 88,
    "start_char": 87,
    "end_char": 87,
    "paragraph_start": 87,
    "next_paragraph_start": 87,
    "paragraph_limit": 86,
    "has_more": 86,
    "context_truncated": 86,
    "context_has_more": 86,
    "source_has_more": 86,
    # Guidance is useful, but it remains below executable selectors and
    # observed paths for ordinary (non-batch) contexts.
    "guidance": 70,
}
_UUID_RE = re.compile(
    r"(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])"
)
_UUID_PREFIX_RE = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{8}(?![0-9a-f])")
_ERROR_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,119}$")


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str))


def _priority(key: str) -> int:
    folded = key.casefold()
    return _KEY_PRIORITY.get(
        folded,
        84 if folded.endswith("_count") else 70 if folded.endswith("_omitted") else 50,
    )


def _error_priority(key: str) -> int:
    # Error causes and process diagnostics must survive before wrapper logs.
    return {
        "error": 110,
        "previous_error": 110,
        "code": 109,
        "type": 109,
        "message": 108,
        "detail": 108,
        "returncode": 107,
        "stderr": 106,
        "stdout": 105,
        "details": 104,
        "response": 104,
        "cause": 104,
    }.get(key.casefold(), _priority(key))


def _normalized_key(key: Any) -> str:
    return normalize_route(key)


def is_hidden_key(key: Any) -> bool:
    """Return whether a field belongs to a forbidden runtime metadata family."""
    normalized = _normalized_key(key)
    if normalized in _HIDDEN_KEYS_NORMALIZED:
        return True
    for family in _HIDDEN_KEY_FAMILIES:
        if (
            normalized.startswith(family)
            and normalized[len(family) :] in _HIDDEN_KEY_SUFFIXES
        ):
            return True
    return any(marker in normalized for marker in _HIDDEN_MARKERS_NORMALIZED)


def _contains_hidden_marker(value: Any, *, sensitive_context: bool = False) -> bool:
    if not isinstance(value, (str, bytes, bytearray)):
        return False
    if has_unresolved_encoding(value):
        return True
    decoded = decode_text(value)
    folded = decoded.casefold()
    normalized = _normalized_key(decoded)
    # Document prose may contain words that become a forbidden route only
    # after punctuation is removed (for example, "task, execute subtasks").
    # Keep fail-closed matching for structured/error fields, while requiring
    # a route to remain within one prose clause for ordinary observed text.
    # Ordinary filenames may contain unrelated UUIDs. Actual task identity
    # is removed by result sanitation and checked at the final request boundary.
    explicit = bool(
        (
            sensitive_context
            and (_UUID_RE.search(decoded) or _UUID_PREFIX_RE.search(decoded))
        )
        or any(marker.casefold() in folded for marker in _HIDDEN_MARKERS)
        or (
            any(marker in normalized for marker in _HIDDEN_MARKERS_NORMALIZED)
            if sensitive_context
            else contains_route_in_prose(decoded, _HIDDEN_MARKERS)
        )
    )
    if explicit:
        return True
    if _SENSITIVE_IDENTIFIER_RE.fullmatch(decoded.strip()):
        return True
    return bool(
        sensitive_context
        and any(
            re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(marker)}(?=$|[^A-Za-z0-9_])",
                decoded,
                re.IGNORECASE,
            )
            for marker in _SENSITIVE_WORD_MARKERS
        )
    )


def _safe_action(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    folded = value.casefold()
    normalized = _normalized_key(value)
    if (
        folded in _FORBIDDEN_ACTIONS
        or normalized in _FORBIDDEN_ACTIONS_NORMALIZED
        or _contains_hidden_marker(value)
    ):
        return "public_action"
    return value


def sanitize(
    value: Any,
    *,
    depth: int = 0,
    sensitive_context: bool = False,
) -> Any:
    """Return a model-safe copy, dropping internal metadata recursively."""
    if depth > 12:
        return "<nested-context-omitted>"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            normalized = _normalized_key(key)
            if is_hidden_key(key):
                continue
            # ``compact()`` in the legacy trace path uses a JSON prefix under
            # ``preview``.  It is not a reliable observation and can be
            # malformed; keep the truncation flag, but never pass the opaque
            # prefix to the model.
            if normalized == "preview" and value.get("truncated") is True:
                continue
            child_sensitive_context = (
                sensitive_context or normalized in _SENSITIVE_CONTEXT_KEYS
            )
            result[key] = (
                _safe_action(item)
                if normalized in {"action", "tool", "actionname", "toolname"}
                else sanitize(
                    item,
                    depth=depth + 1,
                    sensitive_context=child_sensitive_context,
                )
            )
        return result
    if isinstance(value, (list, tuple)):
        return [
            sanitize(item, depth=depth + 1, sensitive_context=sensitive_context)
            for item in value
        ]
    if isinstance(value, (str, bytes, bytearray)):
        return (
            "<internal-benchmark-metadata>"
            if _contains_hidden_marker(value, sensitive_context=sensitive_context)
            else (
                decode_text(value) if isinstance(value, (bytes, bytearray)) else value
            )
        )
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _fit_string(value: str, budget: int) -> str | None:
    if _json_size(value) <= budget:
        # Keep ordinary result strings bounded even when the enclosing object
        # has ample room; this leaves room for neighboring state fields.
        if len(value) <= MODEL_CONTEXT_MAX_STRING_CHARS:
            return value
        value = value[:MODEL_CONTEXT_MAX_STRING_CHARS]
    if budget < MODEL_CONTEXT_HINT_MIN_CHARS:
        return None
    marker = "...<truncated>..."
    room = min(MODEL_CONTEXT_MAX_STRING_CHARS, max(0, budget - 2)) - len(marker)
    if room <= 0:
        return None
    head = (room + 1) // 2
    tail = room - head
    candidate = value[:head] + marker + (value[-tail:] if tail else "")
    while _json_size(candidate) > budget and head + tail > 0:
        if head >= tail:
            head -= 1
        else:
            tail -= 1
        candidate = value[:head] + marker + (value[-tail:] if tail else "")
    return candidate if _json_size(candidate) <= budget else None


def _fit(
    value: Any,
    budget: int,
    *,
    depth: int = 0,
    key_priority: Callable[[str], int] = _priority,
) -> Any | None:
    if budget <= 0:
        return None
    if _json_size(value) <= budget and not (
        isinstance(value, str) and len(value) > MODEL_CONTEXT_MAX_STRING_CHARS
    ):
        return value
    if isinstance(value, str):
        return _fit_string(value, budget)
    if isinstance(value, list):
        if not value:
            return []
        if all(isinstance(row, list) for row in value):
            # Matrix coordinates are positional: sampling a tail or dropping
            # interior cells would present them as different rows/columns.
            result = []
            for row in value[:MODEL_CONTEXT_MAX_LIST_ITEMS]:
                if _json_size([*result, row]) > budget:
                    break
                result.append(row)
            return result
        count = min(len(value), MODEL_CONTEXT_MAX_LIST_ITEMS)
        if len(value) > count:
            head = count // 2
            indices = [*range(head), *range(len(value) - (count - head), len(value))]
        else:
            indices = list(range(len(value)))
        item_budget = max(MODEL_CONTEXT_HINT_MIN_CHARS, (budget - 2) // len(indices))
        result = [
            item
            for index in indices
            if (
                item := _fit(
                    value[index],
                    item_budget,
                    depth=depth + 1,
                    key_priority=key_priority,
                )
            )
            is not None
        ]
        while _json_size(result) > budget and result:
            result.pop(len(result) // 2)
        return result if _json_size(result) <= budget else None
    if isinstance(value, dict):
        result: dict[str, Any] = {"context_truncated": True}
        omitted = 0
        batch_context = _is_text_batch_context(value)
        paragraph_context = (
            isinstance(value.get("index"), int)
            and isinstance(value.get("text_length"), int)
            and isinstance(value.get("text"), str)
        )

        def item_priority(pair: tuple[Any, Any]) -> int:
            key = str(pair[0])
            priority = key_priority(key)
            if paragraph_context and key in {"index", "text_length", "text"}:
                # Keep the observed paragraph and its address before optional
                # formatting; an index without its source text is not a useful read.
                priority = max(priority, {"index": 97, "text_length": 96, "text": 95}[key])
            if value.get("observation_type") == "pdf_table" and key in {
                "input_path", "page", "table_index", "table_count", "row_offset",
                "row_count", "column_count", "next_row_offset", "truncated",
                "merged_cells", "guidance",
            }:
                priority = max(priority, 93)
            if batch_context and key.casefold() == "guidance":
                # A recovery batch must retain the instruction for consuming
                # ``next_start_char`` even when optional chunks are trimmed.
                priority = max(priority, 93)
            return -priority

        items = sorted(value.items(), key=item_priority)
        for raw_key, raw_item in items:
            key = str(raw_key)
            if key == "context_truncated":
                continue
            if is_hidden_key(key):
                omitted += 1
                continue
            available = budget - _json_size(result) - _json_size(key) - 4
            if available < MODEL_CONTEXT_HINT_MIN_CHARS:
                omitted += 1
                continue
            child_priority = (
                _error_priority
                if key.casefold() in {"error", "previous_error"}
                else key_priority
            )
            item = _fit(raw_item, available, depth=depth + 1, key_priority=child_priority)
            # An observed JSON null is data, not a failed fit.
            if item is None and raw_item is not None:
                omitted += 1
                continue
            result[key] = item
        # Calc range.read exposes an A1 address matrix alongside the observed
        # matrices.  Each field is fitted independently above, so make their
        # visible prefix identical before returning the bounded projection;
        # otherwise an address row could be paired with the wrong value row.
        matrix_keys = (
            "cell_addresses",
            "display_text",
            "values",
            "formulas",
            "kinds",
            "number_format_ids",
        )
        matrices = [
            result[key]
            for key in matrix_keys
            if isinstance(result.get(key), list)
            and all(isinstance(row, list) for row in result[key])
        ]
        if len(matrices) >= 2:
            row_count = min(len(matrix) for matrix in matrices)
            width_by_row = [
                min(
                    (len(matrix[row_index]) for matrix in matrices),
                    default=0,
                )
                for row_index in range(row_count)
            ]
            for key in matrix_keys:
                matrix = result.get(key)
                if not (
                    isinstance(matrix, list)
                    and all(isinstance(row, list) for row in matrix)
                ):
                    continue
                result[key] = [
                    row[: width_by_row[row_index]]
                    for row_index, row in enumerate(matrix[:row_count])
                ]
        if omitted and _json_size({**result, "omitted_keys_count": omitted}) <= budget:
            result["omitted_keys_count"] = omitted
        while _json_size(result) > budget and result:
            removable = min(result, key=lambda key: (key_priority(key), key.casefold()))
            result.pop(removable)
        return result if _json_size(result) <= budget else None
    return _fit_string(str(value), budget)


def declared_budget(value: dict[str, Any]) -> int:
    candidates = [value]
    downstream = value.get("downstream_context")
    if isinstance(downstream, dict):
        candidates.append(downstream)
    for candidate in candidates:
        budget = candidate.get("context_char_budget")
        if isinstance(budget, int) and not isinstance(budget, bool) and budget > 0:
            return min(budget + 1_000, MODEL_CONTEXT_HINT_MAX_CHARS)
    return MODEL_CONTEXT_HINT_DEFAULT_MAX_CHARS


# Keep a useful, bounded window per file during a recovery turn.  The hard
# budget below may shorten this further, but it should not erase every source
# row merely because an unrelated ledger entry is present.
_BATCH_RECOVERY_TEXT_CHARS = 320
_BATCH_RECOVERY_TABLE_ROW_CHARS = 480
_BATCH_RECOVERY_MAX_FILES = 20
_BATCH_RECOVERY_MAX_CHUNKS = 2
# ``history_summary`` is built before the protocol-recovery projection.  A
# fixed small history budget would discard the batch text before the latter
# gets a chance to preserve it, so batch histories use a separate bounded
# envelope while ordinary histories retain their smaller footprint.
_BATCH_HISTORY_OBSERVATION_BUDGET = 16_000
_BATCH_HISTORY_SUMMARY_BUDGET = 20_000
_FINANCIAL_LABEL_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])(TAKE[- ]?OUT\s+TOTAL|AMOUNT\s+DUE|BALANCE|TOTAL|PAID)\b"
)
_FINANCIAL_AMOUNT_RE = re.compile(
    r"(?<![A-Za-z0-9])[$€£]?\s*[-+]?\d[\d,]*(?:\.\d{1,2})?(?![A-Za-z0-9])"
)
_SUBTOTAL_RE = re.compile(r"(?i)^\s*SUBTOTAL\b")
_TAX_RE = re.compile(r"(?i)^\s*TAX(?:ES)?\b")


def _financial_amount_hint(text: str) -> dict[str, Any] | None:
    """Derive a bounded final-payment hint from ordinary OCR labels."""
    lines = text.splitlines()
    labeled: list[tuple[int, str, float, str]] = []
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        match = _FINANCIAL_LABEL_RE.search(line)
        if not match:
            continue
        label = re.sub(r"\s+", " ", match.group(1)).upper()
        remainder = line[match.end() :].strip()
        if label == "TOTAL" and re.match(
            r"(?i)^(?:TAX|SAVINGS|NUMBER|ITEMS?)\b", remainder
        ):
            continue
        candidates = _FINANCIAL_AMOUNT_RE.findall(line[match.end() :])
        evidence = line
        if not candidates:
            for following in lines[index + 1 : index + 9]:
                following = following.strip()
                if not following:
                    continue
                candidates = _FINANCIAL_AMOUNT_RE.findall(following)
                if candidates:
                    evidence = f"{line} {following}"
                    break
        if len(candidates) != 1:
            # A row with several numeric columns is not one payment amount.
            # Preserve its raw table evidence for the model to interpret.
            continue
        raw_amount = candidates[-1].replace(",", "").replace(" ", "")
        try:
            amount = float(raw_amount.lstrip("$€£"))
        except ValueError:
            continue
        labeled.append((index, label, amount, evidence[:240]))
    if labeled:
        priority = {
            "TAKE-OUT TOTAL": 5,
            "AMOUNT DUE": 5,
            "BALANCE": 4,
            "PAID": 3,
            "TOTAL": 2,
        }
        _, label, amount, evidence = max(
            labeled, key=lambda item: (priority.get(item[1], 0), item[0])
        )
        return {"amount": amount, "label": label, "evidence": evidence}

    subtotal = tax = None
    subtotal_evidence = tax_evidence = ""
    for raw_line in lines:
        line = raw_line.strip()
        if _SUBTOTAL_RE.match(line):
            values = _FINANCIAL_AMOUNT_RE.findall(line)
            if len(values) == 1:
                subtotal = float(values[-1].replace(",", "").replace(" ", "").lstrip("$€£"))
                subtotal_evidence = line
        elif _TAX_RE.match(line):
            values = _FINANCIAL_AMOUNT_RE.findall(line)
            if len(values) == 1:
                tax = float(values[-1].replace(",", "").replace(" ", "").lstrip("$€£"))
                tax_evidence = line
    if subtotal is not None and tax is not None:
        return {
            "amount": round(subtotal + tax, 2),
            "label": "SUBTOTAL + TAX",
            "evidence": f"{subtotal_evidence}; {tax_evidence}"[:240],
        }

    currency_values = []
    for raw_line in lines:
        for value in _FINANCIAL_AMOUNT_RE.findall(raw_line):
            if any(symbol in value for symbol in "$€£"):
                try:
                    currency_values.append((float(value.replace(",", "").replace(" ", "").lstrip("$€£")), raw_line.strip()))
                except ValueError:
                    pass
    if len(currency_values) == 1:
        amount, evidence = currency_values[0]
        return {"amount": amount, "label": "CURRENCY AMOUNT", "evidence": evidence[:240]}
    return None


TEXT_BATCH_READING_GUIDANCE = (
    "Use files[].handle.path. If context_truncated=true, narrow input_pattern to one "
    "observed basename, keeping cwd unchanged. If source_has_more=true, use "
    "next_start_char as start_char. Respect max_chars_per_file's limit. Interpret "
    "each table column from its headers; receipt amounts require payment evidence."
)
TEXT_FILE_READING_GUIDANCE = (
    "Use file.read_text with files[0].handle.path. For hidden middle text, set "
    "start_char to the first chunk's end_char and request a smaller max_chars window. "
    "For unread source use next_start_char. Offsets count Unicode characters. "
    "Read relevant sibling_file_paths explicitly when needed. "
    "This read returns text in this observation; it does not set the system clipboard. "
    "Before GUI paste, use clipboard.set with the exact literal text you select. "
    "This is saved disk text; an unsaved editor buffer can differ. These file APIs "
    "do not synchronize that buffer. Copy old from this latest disk text with its "
    "exact whitespace and newlines, not from the screenshot. "
    "For an edit, file.replace_literal replaces only old, not surrounding lines; "
    "include the complete current block in old to replace a whole block."
)
WRITER_TEXT_READING_GUIDANCE = (
    "Use document.read_file(path, start_char, max_chars) with the exact observed "
    "files[0].handle.path. context_has_more=true means returned text is hidden here: "
    "continue at the visible head chunk's end_char with a smaller max_chars window. "
    "next_start_char points after the native returned window; it can be null at "
    "source EOF even when context_has_more=true. Offsets count writer_body_text "
    "characters. This background read does not activate the document. Before editing "
    "or exporting it, use os.desktop.open_path with the observed path, then "
    "document.inspect to verify the active source."
)
_BATCH_RECOVERY_KEYS = (
    "reader_action",
    "sibling_file_paths",
    "sibling_file_count",
    "sibling_files_omitted_from_context",
    "sibling_files_truncated",
    "input_directory",
    "input_pattern",
    "start_page",
    "page_count",
    "max_pages_per_pdf",
    "max_pages",
    "ocr_engine",
    "ocr_language",
    "matched_count",
    "context_char_budget",
    "source_has_more",
    "context_has_more",
    "context_files_omitted",
)
_BATCH_RECOVERY_METADATA_KEYS = (
    "status",
    "source_kind",
    "pages_processed",
    "returned_chars",
    "extracted_chars",
    "raw_extracted_chars",
    "source_truncated",
    "source_start_char",
    "source_end_char",
    "source_total_chars",
    "next_start_char",
    "offset_basis",
    "empty_text",
)
_BATCH_RECOVERY_FILE_KEYS = (
    "source_start_char",
    "source_end_char",
    "source_total_chars",
    "next_start_char",
    "offset_basis",
    "source_has_more",
    "context_has_more",
)
_BATCH_RECOVERY_CHUNK_KEYS = (
    "type",
    "offset_basis",
    "index",
    "start_char",
    "end_char",
    "total_chars",
    "source_has_more",
    "context_has_more",
    "has_more",
)
_BATCH_RECOVERY_ROW_KEYS = (
    "type",
    "offset_basis",
    "index",
    "start_char",
    "end_char",
    "total_chars",
    "line_end_char",
    "source_has_more",
    "context_has_more",
    "has_more",
)


def _is_text_batch_context(value: Any) -> bool:
    files = value.get("files") if isinstance(value, dict) else None
    return isinstance(value, dict) and (
        value.get("observation_type") == "text_batch"
        or any(
            isinstance(item, dict)
            and isinstance(item.get("path"), str)
            and ("chunks" in item or "text" in item)
            for item in files or []
        )
    )


def _contains_batch_context(value: Any) -> bool:
    if _is_text_batch_context(value):
        return True
    if isinstance(value, dict):
        return any(_contains_batch_context(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_batch_context(item) for item in value)
    return False


def contains_text_batch_context(value: Any) -> bool:
    """Return whether a model-facing value contains a typed text-batch observation.

    Recovery callers use this only to choose a bounded projection budget.  It
    does not inspect the instruction, task identity, or any expected result.
    """
    return _contains_batch_context(value)


def _compact_batch_chunk(
    value: dict[str, Any], *, source_total_chars: Any = None
) -> dict[str, Any]:
    chunk = {key: value[key] for key in _BATCH_RECOVERY_CHUNK_KEYS if key in value}
    chunk.setdefault("type", "text")
    source_has_more = value.get("source_has_more")
    source_has_more = source_has_more if isinstance(source_has_more, bool) else False
    context_has_more = value.get("context_has_more")
    if not isinstance(context_has_more, bool):
        # Older projections overloaded ``has_more``.  Once a file-level source
        # flag is available, an unqualified chunk flag is only context loss.
        context_has_more = bool(value.get("has_more")) and not source_has_more
    text = value.get("text")
    if not isinstance(text, str) or not text or "...<truncated>..." in text:
        chunk["source_has_more"] = source_has_more
        chunk["context_has_more"] = context_has_more
        chunk["has_more"] = source_has_more
        return chunk
    # A complete requested window need not cover the whole source document.
    # Keep it intact when it fits; the final batch fitter enforces the total budget.
    total_chars = value.get("total_chars", source_total_chars)
    complete_chunk = (
        not context_has_more
        and isinstance(value.get("start_char"), int)
        and not isinstance(value.get("start_char"), bool)
        and isinstance(value.get("end_char"), int)
        and not isinstance(value.get("end_char"), bool)
        and isinstance(total_chars, int)
        and not isinstance(total_chars, bool)
        and value["start_char"] >= 0
        and value["end_char"] - value["start_char"] == len(text)
        and total_chars >= value["end_char"]
    )
    if len(text) > _BATCH_RECOVERY_TEXT_CHARS and not complete_chunk:
        start, end = value.get("start_char"), value.get("end_char")
        tail = (
            value.get("index") == 1 and isinstance(start, int) and isinstance(end, int)
        )
        text = (
            text[-_BATCH_RECOVERY_TEXT_CHARS:]
            if tail
            else text[:_BATCH_RECOVERY_TEXT_CHARS]
        )
        if isinstance(start, int) and isinstance(end, int) and end >= start:
            chunk["start_char"] = end - len(text) if tail else start
            chunk["end_char"] = end if tail else start + len(text)
        context_has_more = True
    chunk["text"] = text
    chunk["source_has_more"] = source_has_more
    chunk["context_has_more"] = context_has_more
    chunk["has_more"] = source_has_more
    return chunk


def _compact_batch_row(value: dict[str, Any]) -> dict[str, Any] | None:
    """Keep one observed tabular line with truthful absolute offsets."""
    text = value.get("text")
    if not isinstance(text, str) or not text:
        return None
    row = {key: value[key] for key in _BATCH_RECOVERY_ROW_KEYS if key in value}
    row.setdefault("type", "table_row")
    source_has_more = value.get("source_has_more")
    source_has_more = source_has_more if isinstance(source_has_more, bool) else False
    context_has_more = value.get("context_has_more")
    context_has_more = context_has_more if isinstance(context_has_more, bool) else False
    if len(text) > _BATCH_RECOVERY_TABLE_ROW_CHARS:
        text = text[:_BATCH_RECOVERY_TABLE_ROW_CHARS]
        context_has_more = True
    row["text"] = text
    start = row.get("start_char")
    end = row.get("end_char")
    if isinstance(start, int) and not isinstance(start, bool):
        row["end_char"] = max(start, start + len(text))
    elif isinstance(end, int) and not isinstance(end, bool):
        row["start_char"] = max(0, end - len(text))
    row["source_has_more"] = source_has_more
    row["context_has_more"] = context_has_more
    row["has_more"] = source_has_more
    return row


def _compact_batch_file(value: dict[str, Any]) -> dict[str, Any] | None:
    path = value.get("path")
    if not isinstance(path, str) or not path:
        observed_handle = value.get("handle")
        if isinstance(observed_handle, dict):
            path = observed_handle.get("path")
    if not isinstance(path, str) or not path:
        return None
    observed = value.get("handle")
    handle = (
        {"kind": observed.get("kind", "file"), "path": observed["path"]}
        if isinstance(observed, dict) and isinstance(observed.get("path"), str)
        else {"kind": "file", "path": path}
    )
    result: dict[str, Any] = {"handle": handle, "path": path}
    # Preserve structured OCR interpretation through recovery turns. These
    # bounded fields are produced by the generic reader and prevent later
    # projections from falling back to unrelated file metadata.
    for key in ("financial_amount_hint", "expense_entry"):
        item = value.get(key)
        if isinstance(item, dict):
            result[key] = {
                field: item[field]
                for field in ("amount", "label", "evidence", "type")
                if field in item and isinstance(item[field], (str, int, float, bool))
            }
    for key in _BATCH_RECOVERY_FILE_KEYS:
        item = value.get(key)
        if isinstance(item, (str, int, float, bool)) and not (
            isinstance(item, float) and item != item
        ):
            result[key] = item
    source_has_more = value.get("source_has_more")
    if not isinstance(source_has_more, bool):
        metadata = value.get("metadata")
        source_has_more = bool(
            isinstance(metadata, dict) and metadata.get("source_truncated") is True
        )
    context_has_more = value.get("context_has_more")
    if not isinstance(context_has_more, bool):
        context_has_more = bool(value.get("context_truncated"))
        if not context_has_more and bool(value.get("has_more")) and not source_has_more:
            context_has_more = True
    if not source_has_more and bool(value.get("truncated")):
        context_has_more = True
    raw_chunks = value.get("chunks")
    chunks = (
        [
            _compact_batch_chunk(
                item, source_total_chars=value.get("source_total_chars")
            )
            for item in raw_chunks[:_BATCH_RECOVERY_MAX_CHUNKS]
            if isinstance(item, dict)
        ]
        if isinstance(raw_chunks, list)
        else []
    )
    if not chunks and isinstance(value.get("text"), str):
        text = value["text"]
        source_start = value.get("source_start_char", 0)
        if isinstance(source_start, bool) or not isinstance(source_start, int):
            source_start = 0
        source_start = max(0, source_start)
        source_end = value.get("source_end_char")
        if isinstance(source_end, bool) or not isinstance(source_end, int):
            source_end = source_start + len(text)
        source_end = max(source_end, source_start + len(text))
        source_total = value.get("source_total_chars", value.get("extracted_chars"))
        if isinstance(source_total, bool) or not isinstance(source_total, int):
            source_total = source_end
        source_total = max(source_total, source_end)
        visible = min(len(text), _BATCH_RECOVERY_TEXT_CHARS)
        if visible == len(text):
            raw_chunk_values = [
                {
                    "index": 0,
                    "start_char": source_start,
                    "end_char": source_start + len(text),
                    "total_chars": source_total,
                    "text": text,
                    "source_has_more": source_has_more,
                }
            ]
        else:
            head_length = (visible + 1) // 2
            tail_length = visible - head_length
            raw_chunk_values = [
                {
                    "index": 0,
                    "start_char": source_start,
                    "end_char": source_start + head_length,
                    "total_chars": source_total,
                    "text": text[:head_length],
                    "source_has_more": source_has_more,
                    "context_has_more": True,
                },
                {
                    "index": 1,
                    "start_char": source_end - tail_length,
                    "end_char": source_end,
                    "total_chars": source_total,
                    "text": text[-tail_length:],
                    "source_has_more": source_has_more,
                    "context_has_more": True,
                },
            ]
        chunks = [_compact_batch_chunk(item) for item in raw_chunk_values]
    if chunks:
        result["chunks"] = chunks
        context_has_more = context_has_more or any(
            bool(chunk.get("context_has_more")) for chunk in chunks
        )
    raw_rows = value.get("table_rows")
    rows = (
        [
            row
            for item in raw_rows[:_BATCH_RECOVERY_MAX_CHUNKS]
            if isinstance(item, dict)
            if (row := _compact_batch_row(item)) is not None
        ]
        if isinstance(raw_rows, list)
        else []
    )
    if rows:
        result["table_rows"] = rows
        context_has_more = context_has_more or any(
            bool(row.get("context_has_more")) for row in rows
        )
    observed_metadata = value.get("metadata")
    observed_metadata = (
        observed_metadata if isinstance(observed_metadata, dict) else value
    )
    metadata = {
        key: observed_metadata[key]
        for key in _BATCH_RECOVERY_METADATA_KEYS
        if key in observed_metadata
        and isinstance(observed_metadata[key], (str, int, float, bool))
    }
    if metadata:
        result["metadata"] = metadata
    result["source_has_more"] = source_has_more
    result["context_has_more"] = context_has_more
    result["has_more"] = bool(
        source_has_more
        or context_has_more
        or value.get("truncated")
        or (isinstance(raw_chunks, list) and len(raw_chunks) > len(chunks))
    )
    if isinstance(raw_chunks, list) and len(raw_chunks) > len(chunks):
        result["context_has_more"] = True
        result["has_more"] = True
    return result


def _slim_batch_optional_fields(result: dict[str, Any]) -> None:
    """Release envelope overhead before shrinking observed source text."""
    for key in (
        "context_char_budget",
        "ocr_engine",
        "ocr_language",
        "max_pages_per_pdf",
        "page_count",
        "start_page",
    ):
        result.pop(key, None)
    for file in result.get("files", []):
        if not isinstance(file, dict):
            continue
        handle = file.get("handle")
        if isinstance(handle, dict) and handle.get("path") == file.get("path"):
            # ``handle.path`` is the executable continuation target; the
            # duplicate path field is optional under a tight retry budget.
            file.pop("path", None)
        metadata = file.get("metadata")
        if isinstance(metadata, dict):
            keep = {
                "status",
                "source_kind",
                "pages_processed",
                "source_truncated",
                "extracted_chars",
                "next_start_char",
            }
            reduced = {
                key: value
                for key, value in metadata.items()
                if key in keep and value is not None
            }
            if reduced.get("extracted_chars") == file.get("source_total_chars"):
                reduced.pop("extracted_chars", None)
            if reduced.get("next_start_char") == file.get("next_start_char"):
                reduced.pop("next_start_char", None)
            if reduced:
                file["metadata"] = reduced
            else:
                file.pop("metadata", None)
        for part in [*file.get("chunks", []), *file.get("table_rows", [])]:
            if not isinstance(part, dict):
                continue
            if part.get("total_chars") == file.get("source_total_chars"):
                part.pop("total_chars", None)
            if part.get("offset_basis") == file.get("offset_basis"):
                part.pop("offset_basis", None)
            if part.get("has_more") == part.get("source_has_more"):
                part.pop("has_more", None)


def _assign_batch_chunk_text(
    chunk: dict[str, Any], original: str, length: int, end_char: int | None
) -> None:
    """Set a prefix/suffix window while keeping its recorded offsets truthful."""
    length = max(0, min(length, len(original)))
    if chunk.get("index") == 1 and isinstance(end_char, int):
        chunk["text"] = original[-length:] if length else ""
        chunk["start_char"] = end_char - length
    else:
        chunk["text"] = original[:length]
        start_char = chunk.get("start_char")
        if isinstance(start_char, int):
            chunk["end_char"] = start_char + length
    chunk["context_has_more"] = length < len(original)


def _fit_batch_text_windows(result: dict[str, Any], budget: int) -> None:
    """Fairly fit all batch windows instead of starving early files."""
    chunks = [
        chunk
        for file in result.get("files", [])
        if isinstance(file, dict)
        for chunk in file.get("chunks", [])
        if isinstance(chunk, dict) and isinstance(chunk.get("text"), str)
    ]
    if not chunks:
        return
    originals = [chunk["text"] for chunk in chunks]
    prior_context_loss = [bool(chunk.get("context_has_more")) for chunk in chunks]
    ends = [chunk.get("end_char") for chunk in chunks]
    for chunk in chunks:
        _assign_batch_chunk_text(chunk, chunk["text"], 0, chunk.get("end_char"))
    if _json_size(result) >= budget:
        return

    capacities = [len(text) for text in originals]
    low, high = 0, max(capacities, default=0)
    while low < high:
        candidate = (low + high + 1) // 2
        for chunk, original, end_char in zip(chunks, originals, ends, strict=True):
            _assign_batch_chunk_text(
                chunk, original, min(candidate, len(original)), end_char
            )
        if _json_size(result) <= budget:
            low = candidate
        else:
            high = candidate - 1

    for chunk, original, end_char in zip(chunks, originals, ends, strict=True):
        _assign_batch_chunk_text(chunk, original, min(low, len(original)), end_char)

    # Spend any leftover characters round-robin.  A bounded loop keeps the
    # helper cheap even when a caller supplies a very large recovery budget.
    lengths = [min(low, len(original)) for original in originals]
    for index, (chunk, original, end_char) in enumerate(
        zip(chunks, originals, ends, strict=True)
    ):
        while lengths[index] < len(original):
            next_length = lengths[index] + 1
            _assign_batch_chunk_text(chunk, original, next_length, end_char)
            if _json_size(result) > budget:
                _assign_batch_chunk_text(chunk, original, lengths[index], end_char)
                break
            lengths[index] = next_length
    for chunk, was_truncated in zip(chunks, prior_context_loss, strict=True):
        if was_truncated:
            chunk["context_has_more"] = True


def _compact_batch(value: dict[str, Any], budget: int) -> dict[str, Any]:
    if budget < MODEL_CONTEXT_HINT_MIN_CHARS:
        return {}
    raw_files = value.get("files")
    raw_files = raw_files if isinstance(raw_files, list) else []
    previous = value.get("context_files_omitted", value.get("files_omitted"))
    previous = (
        previous if isinstance(previous, int) and not isinstance(previous, bool) else 0
    )
    reader_action = value.get("reader_action")
    guidance = (
        WRITER_TEXT_READING_GUIDANCE
        if reader_action == "document.read_file"
        else value.get("guidance")
    )
    result: dict[str, Any] = {
        "observation_type": "text_batch",
        **{key: value[key] for key in _BATCH_RECOVERY_KEYS if key in value},
        "files": [],
        "files_omitted": max(
            previous, max(0, len(raw_files) - _BATCH_RECOVERY_MAX_FILES)
        ),
        "context_files_omitted": max(
            previous, max(0, len(raw_files) - _BATCH_RECOVERY_MAX_FILES)
        ),
        "guidance": (
            guidance[
                :1200
                if reader_action in {"file.read_text", "document.read_file"}
                else 320
            ]
            if isinstance(guidance, str) and guidance
            else TEXT_BATCH_READING_GUIDANCE
        ),
    }
    result["context_truncated"] = bool(
        value.get("context_truncated") or result["files_omitted"]
    )
    result["has_more"] = bool(value.get("has_more") or result["context_truncated"])
    for raw in raw_files[:_BATCH_RECOVERY_MAX_FILES]:
        file = _compact_batch_file(raw) if isinstance(raw, dict) else None
        if file is None:
            result["files_omitted"] += 1
            result["context_files_omitted"] += 1
        else:
            result["files"].append(file)
    result["context_truncated"] = bool(
        result.get("context_truncated")
        or result["files_omitted"]
        or any(
            file.get("context_has_more") or file.get("context_truncated")
            for file in result["files"]
        )
    )
    result["context_has_more"] = bool(
        result.get("context_has_more")
        or result["context_truncated"]
        or any(
            file.get("context_has_more") or file.get("context_truncated")
            for file in result["files"]
        )
    )
    result["has_more"] = bool(result.get("has_more") or result["context_truncated"])
    result["source_has_more"] = bool(
        value.get("source_has_more")
        or any(bool(file.get("source_has_more")) for file in result["files"])
    )
    slimmed = False
    text_fitted = False
    while _json_size(result) > budget:
        if not slimmed:
            _slim_batch_optional_fields(result)
            slimmed = True
            continue
        if not text_fitted and any(
            isinstance(chunk.get("text"), str)
            for file in result["files"]
            for chunk in file.get("chunks", [])
            if isinstance(chunk, dict)
        ):
            _fit_batch_text_windows(result, budget)
            # The final fit can hide text after the earlier parent aggregation.
            # These existing false-to-true flags shrink the encoded envelope.
            for file in result["files"]:
                if any(
                    chunk.get("context_has_more") for chunk in file.get("chunks", [])
                ):
                    file["context_has_more"] = True
                    file["has_more"] = True
                    result["context_has_more"] = True
                    result["context_truncated"] = True
                    result["has_more"] = True
            text_fitted = True
            continue
        metadata_files = [file for file in result["files"] if "metadata" in file]
        if metadata_files:
            for file in metadata_files:
                file.pop("metadata", None)
            continue
        path_files = [file for file in result["files"] if "path" in file]
        if path_files:
            for file in path_files:
                file.pop("path", None)
            continue
        chunk_files = [
            file
            for file in result["files"]
            if isinstance(file.get("chunks"), list) and file.get("chunks")
        ]
        if chunk_files:
            # Preserve every executable handle before considering omission of a
            # file record.  Text is useful, but an empty chunk list plus an
            # exact handle is still a recoverable observation.
            for file in chunk_files:
                file.pop("chunks", None)
                file["chunk_count"] = 0
                file["context_truncated"] = True
                file["context_has_more"] = True
                file["has_more"] = bool(file.get("source_has_more"))
            continue
        if len(result["files"]) > 1:
            result["files"].pop(len(result["files"]) // 2)
            result["files_omitted"] += 1
            result["context_files_omitted"] += 1
            result["context_truncated"] = True
            result["context_has_more"] = True
            result["has_more"] = True
            continue
        break
    if _json_size(result) <= budget:
        return result
    marker = {
        "observation_type": "text_batch",
        "files": [],
        "files_omitted": max(1, len(raw_files)),
        "context_files_omitted": max(1, len(raw_files)),
        "source_has_more": bool(value.get("source_has_more")),
        "context_has_more": True,
        "context_truncated": True,
        "has_more": True,
    }
    fitted = _fit(marker, budget)
    return fitted if isinstance(fitted, dict) else {}


def _replace_batch_contexts(value: Any, budget: int) -> Any:
    if _is_text_batch_context(value):
        return _compact_batch(value, budget)
    if isinstance(value, dict):
        return {
            key: _replace_batch_contexts(item, budget) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_batch_contexts(item, budget) for item in value]
    return value


def _compact_recovery_summary(value: list[Any], max_chars: int) -> list[dict[str, Any]]:
    safe = sanitize(value)
    indices = (
        [index for index, item in enumerate(safe) if _contains_batch_context(item)]
        if isinstance(safe, list)
        else []
    )
    if not indices:
        fitted = _fit(safe, max_chars)
        return fitted if isinstance(fitted, list) else []
    # A retry needs the latest source observation and the failure that caused
    # the retry.  Older batch snapshots are less useful than the intervening
    # action ledger and can otherwise consume the entire compact budget.
    batch_index = indices[-1]
    others = [
        index
        for index in range(len(safe))
        if index != batch_index and not _contains_batch_context(safe[index])
    ][-4:]
    failure_index = next(
        (index for index in reversed(others)
         if isinstance(safe[index], dict) and safe[index].get("error")),
        None,
    )
    # Reserve the most recent failure before allocating source text. Otherwise
    # a long read leaves only an action label, with the cause of the next
    # recovery decision silently removed from the model's actual request.
    failure_budget = (
        min(_json_size(safe[failure_index]), max_chars // 3)
        if failure_index is not None else 0
    )
    # The batch observation is the durable work set.  Give it most of the
    # retry budget and trim ordinary history entries first; splitting the
    # budget evenly through ``_fit`` would make each nested file compete with
    # unrelated one-line events and silently drop observed handles.
    batch_budget = max(
        MODEL_CONTEXT_HINT_MIN_CHARS,
        min(max(0, max_chars - failure_budget - 256), max_chars * 9 // 10),
    )
    fitted_batch = _fit(
        _replace_batch_contexts(safe[batch_index], batch_budget), batch_budget
    )
    # The batch cap is not a reservation: a short source must release unused
    # space so recent tool catalogs and errors remain usable.
    batch_size = _json_size(fitted_batch) if fitted_batch is not None else 0
    other_budget = max(0, max_chars - batch_size - 2 * len(others) - 2)
    failure_fit = (
        _fit(safe[failure_index], failure_budget, key_priority=_error_priority)
        if failure_index is not None else None
    )
    if failure_fit is not None:
        other_budget -= _json_size(failure_fit)
    ordinary_count = len(others) - (failure_index is not None)
    per_other = max(0, other_budget) // ordinary_count if ordinary_count else 0
    selected = {batch_index, *others}
    entries = []
    for index, item in enumerate(safe):
        if index not in selected:
            continue
        fitted = (
            fitted_batch if index == batch_index
            else failure_fit if index == failure_index
            else _fit(item, per_other)
        )
        if fitted is not None:
            entries.append(fitted)
    projected = list(entries)
    while _json_size(projected) > max_chars:
        non_batch = [
            index
            for index, item in enumerate(projected)
            if not _contains_batch_context(item)
        ]
        if not non_batch:
            break
        # Remove the oldest ordinary ledger entry first.  The batch and the
        # most recent failure remain available for the repair turn whenever
        # the hard budget permits them.
        projected.pop(non_batch[0])
    if _json_size(projected) <= max_chars and any(
        _contains_batch_context(item) for item in projected
    ):
        return projected
    # An unusually small caller budget may still be unable to hold the batch
    # entry alongside its wrapper.  Fit that entry alone, preserving the
    # typed batch marker rather than falling back to a generic list truncation.
    batch_entry = next(
        (item for item in entries if _contains_batch_context(item)), None
    )
    if batch_entry is not None:
        fitted_batch = _fit(batch_entry, max_chars - 2)
        if isinstance(fitted_batch, dict) and _json_size(fitted_batch) <= max_chars - 2:
            return [fitted_batch]
    fallback = _replace_batch_contexts(safe[batch_index], max_chars - 2)
    return (
        [fallback]
        if isinstance(fallback, dict) and _json_size(fallback) <= max_chars - 2
        else []
    )


def compact_hint(value: dict[str, Any], *, remaining_chars: int) -> dict[str, Any]:
    budget = min(declared_budget(value), max(0, remaining_chars))
    if budget <= 0:
        return {}
    safe = sanitize(value)
    # Do not apply the recovery batch's smaller chunk cap when the complete
    # raw text observation already fits the caller's truthful budget. Existing
    # chunked observations retain their independent chunk-count contract.
    raw_files = safe.get("files") if isinstance(safe, dict) else None
    has_raw_text = isinstance(raw_files, list) and any(
        isinstance(item, dict) and isinstance(item.get("text"), str)
        for item in raw_files
    )
    if has_raw_text and _json_size(safe) <= budget:
        return safe
    if budget < 18_000:
        if _is_text_batch_context(safe):
            return _compact_batch(safe, budget)
        nested = safe.get("downstream_context")
        if isinstance(nested, dict) and _is_text_batch_context(nested):
            wrapper = {
                key: item for key, item in safe.items() if key != "downstream_context"
            }
            nested_budget = max(
                MODEL_CONTEXT_HINT_MIN_CHARS, budget - _json_size(wrapper) - 24
            )
            nested_files = nested.get("files")
            nested_has_raw_text = isinstance(nested_files, list) and any(
                isinstance(item, dict) and isinstance(item.get("text"), str)
                for item in nested_files
            )
            if nested_has_raw_text and _json_size(nested) <= nested_budget:
                wrapper["downstream_context"] = nested
                return wrapper
            wrapper["downstream_context"] = _compact_batch(nested, nested_budget)
            if _json_size(wrapper) <= budget:
                return wrapper
            return _compact_batch(nested, budget)
    projected = _fit(safe, budget)
    if isinstance(projected, dict):
        return projected
    return {}


def compact_execution_summary_for_model(
    value: Any, *, max_chars: int = 9_000
) -> list[dict[str, Any]]:
    """Keep a valid, small execution transcript for protocol recovery.

    A normal turn benefits from the larger truthful context budget.  When a
    model has returned no structured call, repeating that large prompt can
    consume the entire reasoning budget before it reaches a function call.
    This helper only changes the retry projection; the complete event trace is
    still retained for auditing and later state updates.
    """
    if max_chars <= 0 or not isinstance(value, list):
        return []
    if any(_contains_batch_context(item) for item in value):
        return _compact_recovery_summary(value, max_chars)
    safe = sanitize(value)
    if _json_size(safe) <= max_chars:
        return safe
    # A soft-restart projection prepends the successful mutation ledger so the
    # next model turn can continue with the remaining observed target.  Keep
    # that model-selected record intact while compressing the surrounding
    # history; newest-first allocation otherwise spends the budget on later
    # observations and leaves only an empty ledger marker.
    protected = [
        item
        for item in safe
        if isinstance(item, dict)
        and isinstance(item.get("recovery_mutation_ledger"), list)
    ]
    protected_size = sum(_json_size(item) for item in protected)
    if protected and protected_size + len(protected) - 1 <= max_chars - 2:
        remainder = [item for item in safe if item not in protected]
        remainder_budget = max_chars - protected_size - len(protected) + 1
        compact_remainder = compact_execution_summary_for_model(
            remainder, max_chars=remainder_budget
        )
        projected = [*protected, *compact_remainder]
        if _json_size(projected) <= max_chars:
            return projected
    # Equal shares can discard most of the latest observation while leaving
    # unused space. Charge actual sizes newest-first, then restore chronology.
    remaining = max(0, max_chars - 2)
    reservations = [
        min(_json_size(item), 2 * MODEL_CONTEXT_HINT_MIN_CHARS) + 2 for item in safe
    ]
    projected = []
    for index in range(len(safe) - 1, -1, -1):
        reserve = min(sum(reservations[:index]), remaining // 2)
        fitted = _fit(safe[index], remaining - reserve)
        if fitted is not None:
            projected.append(fitted)
            remaining -= _json_size(fitted) + 2
    return list(reversed(projected))


def safe_action(value: Any) -> Any:
    """Keep forbidden/internal action names out of model-visible state."""
    return _safe_action(value)


def action_label(event: Any) -> str:
    proposed = getattr(event, "proposed", {})
    if not isinstance(proposed, dict):
        return ""
    for key in ("downstream_action", "action", "tool"):
        value = proposed.get(key)
        if isinstance(value, str) and value:
            return safe_action(value)
    return ""


def _safe_error_token(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip()
    decoded = decode_text(token)
    if (
        not _ERROR_TOKEN_RE.fullmatch(token)
        or _UUID_RE.search(decoded)
        or _UUID_PREFIX_RE.search(decoded)
        or _contains_hidden_marker(token, sensitive_context=True)
    ):
        return None
    return token


def _error_type(error: Any) -> str | None:
    if not isinstance(error, dict):
        return None
    # Adapter errors often wrap a specific code in a generic outer exception.
    # Prefer the nested code, but expose only a bounded token.
    for nested_key in (
        "error",
        "previous_error",
        "cause",
        "details",
        "response",
        "data",
    ):
        nested = error.get(nested_key)
        if not isinstance(nested, dict):
            continue
        if (token := _error_type(nested)) and token != "structured_error":
            return token
    for key in ("code", "error_code", "type"):
        if token := _safe_error_token(error.get(key)):
            return token
    return "structured_error"


def failure_summary(event: Any) -> dict[str, Any] | None:
    if getattr(event, "executed", False):
        return None
    error_type = _error_type(getattr(event, "error", None))
    if error_type is None:
        return None
    proposed = getattr(event, "proposed", {})
    arguments = proposed.get("arguments", {}) if isinstance(proposed, dict) else {}
    fields = (
        sorted(str(key) for key in arguments if not is_hidden_key(key))[:24]
        if isinstance(arguments, dict)
        else []
    )
    return {
        "step": getattr(event, "step", None),
        "action": action_label(event),
        "error_type": error_type,
        "argument_fields": fields,
    }


def _events_contain_batch_context(events: list[Any]) -> bool:
    """Return whether an event history carries a typed batch observation hint."""
    for event in events:
        result = getattr(event, "result", None)
        if not isinstance(result, dict):
            continue
        hint = result.get("context_hint")
        if isinstance(hint, dict) and _contains_batch_context(hint):
            return True
    return False


def _fingerprint(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        sanitize(value), ensure_ascii=False, sort_keys=True, default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _durable_observation_key(event: Any, projected: dict[str, Any]) -> str:
    observation = projected.get("downstream_context")
    if not isinstance(observation, dict):
        observation = projected
    identity = observation.get("identity")
    identity = identity if isinstance(identity, dict) else {}
    resources = [
        value
        for value in (
            observation.get("path"),
            observation.get("url"),
            identity.get("url"),
        )
        if isinstance(value, str) and value
    ]
    files = observation.get("files")
    if _is_text_batch_context(observation) and isinstance(files, list):
        resources.extend(
            item["path"]
            for item in files
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        )
    return _fingerprint(
        {
            "action": action_label(event),
            "adapter": projected.get("downstream_adapter"),
            "downstream_action": projected.get("downstream_action"),
            "resources": sorted(set(resources)),
        }
    )


def durable_observations(
    events: list[Any],
    domain: str,
    *,
    strict_generic: bool,
    budget: int,
    context_hint_for_model: Callable[..., dict[str, Any]],
) -> list[dict[str, Any]]:
    """Retain the latest observation per owning route and observed resource."""
    latest: dict[str, tuple[Any, dict[str, Any]]] = {}
    for event in events:
        result = getattr(event, "result", None)
        if not getattr(event, "executed", False) or not isinstance(result, dict):
            continue
        hint = result.get("context_hint")
        if not isinstance(hint, dict) or not action_label(event):
            continue
        projected = context_hint_for_model(
            domain,
            action_label(event),
            hint,
            strict_generic=strict_generic,
        )
        latest[_durable_observation_key(event, projected)] = (event, projected)
    if not latest or budget <= 0:
        return []
    batch_keys = [
        key
        for key, (_event, projected) in latest.items()
        if _contains_batch_context(projected)
    ]
    non_batch_keys = [key for key in latest if key not in batch_keys]
    if batch_keys:
        # A batch observation carries many independent handles.  Give it a
        # dominant share of the history budget so the generic per-action split
        # cannot collapse every source window to an empty chunk.  A small
        # remainder still carries the latest ordinary error/action ledger.
        batch_budget = max(
            MODEL_CONTEXT_HINT_MIN_CHARS * len(batch_keys),
            budget * 39 // 40,
        )
        per_batch = max(MODEL_CONTEXT_HINT_MIN_CHARS, batch_budget // len(batch_keys))
        # Small batches release unused space to later ordinary result receipts.
        non_batch_budget = max(
            0,
            budget
            - sum(min(_json_size(latest[key][1]), per_batch) for key in batch_keys),
        )
        per_non_batch = (
            max(MODEL_CONTEXT_HINT_MIN_CHARS, non_batch_budget // len(non_batch_keys))
            if non_batch_keys
            else 0
        )
        entry_budgets = {
            key: per_batch if key in batch_keys else per_non_batch for key in latest
        }
    else:
        needs = {
            key: min(_json_size(projected), declared_budget(projected))
            for key, (_event, projected) in latest.items()
        }
        # Small receipts release their unused share to larger observations.
        # The existing total and each observation's declared cap stay unchanged.
        ordered = sorted(needs, key=needs.get)
        entry_budgets = {}
        remaining = budget
        for index, key in enumerate(ordered):
            allocated = min(needs[key], remaining // (len(ordered) - index))
            entry_budgets[key] = allocated
            remaining -= allocated
    observations = []
    seen: set[str] = set()
    for key, (event, projected) in sorted(
        latest.items(), key=lambda pair: getattr(pair[1][0], "step", 0)
    ):
        fingerprint = _fingerprint(projected)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        observations.append(
            {
                "step": getattr(event, "step", None),
                "action": action_label(event),
                "observation": compact_hint(
                    projected,
                    remaining_chars=entry_budgets[key],
                ),
            }
        )
    return observations


def history_summary(
    events: list[Any],
    domain: str,
    *,
    limit: int,
    strict_generic: bool,
    context_hint_for_model: Callable[..., dict[str, Any]],
) -> dict[str, Any] | None:
    older = events[:-limit] if limit > 0 and len(events) > limit else []
    if not older:
        return None
    successful = []
    failures = []
    for event in older:
        proposed = getattr(event, "proposed", {})
        if (
            getattr(event, "executed", False)
            and isinstance(proposed, dict)
            and proposed.get("kind") in {"adapter", "gui"}
        ):
            arguments = proposed.get("arguments", {})
            safe_args = _fit(sanitize(arguments), 500)
            successful.append(
                {
                    "step": getattr(event, "step", None),
                    "action": action_label(event),
                    "arguments": safe_args if isinstance(safe_args, dict) else {},
                }
            )
        if failure := failure_summary(event):
            failures.append(failure)
    result: dict[str, Any] = {
        "history_summary": True,
        "omitted_events": len(older),
        "successful_actions": successful[-24:],
    }
    if failures:
        result["failed_actions"] = failures[-12:]
    batch_history = _events_contain_batch_context(older)
    observations = durable_observations(
        older,
        domain,
        strict_generic=strict_generic,
        budget=(_BATCH_HISTORY_OBSERVATION_BUDGET if batch_history else 8_000),
        context_hint_for_model=context_hint_for_model,
    )
    if observations:
        result["durable_observations"] = observations
    projected = _fit(
        sanitize(result),
        _BATCH_HISTORY_SUMMARY_BUDGET if batch_history else 12_000,
    )
    return projected if isinstance(projected, dict) else result


def summarize_events(
    events: list[Any],
    domain: str,
    *,
    limit: int = 12,
    strict_generic: bool = False,
    context_hint_for_model: Callable[..., dict[str, Any]],
) -> list[dict[str, Any]]:
    live = events[-limit:] if limit > 0 else []
    history = history_summary(
        events,
        domain,
        limit=limit,
        strict_generic=strict_generic,
        context_hint_for_model=context_hint_for_model,
    )
    history_budget = _json_size(history) if history is not None else 0
    # Reserve space for the durable summary before distributing the live
    # event budget.  The final structural fit below is a second hard guard.
    live_budget = max(
        MODEL_CONTEXT_HINT_MIN_CHARS,
        MODEL_CONTEXT_HINT_TOTAL_MAX_CHARS - min(history_budget, 12_000),
    )
    hints = [
        event
        for event in live
        if isinstance(getattr(event, "result", None), dict)
        and isinstance(event.result.get("context_hint"), dict)
    ]
    per_hint = live_budget // len(hints) if hints else 0
    summary: list[dict[str, Any]] = []
    for event in live:
        result = getattr(event, "result", None)
        if isinstance(result, dict) and isinstance(result.get("context_hint"), dict):
            hint = context_hint_for_model(
                domain,
                action_label(event),
                result["context_hint"],
                strict_generic=strict_generic,
            )
            result = {
                "context_hint": compact_hint(
                    hint,
                    remaining_chars=min(per_hint, declared_budget(hint))
                    if per_hint
                    else 0,
                )
            }
        else:
            if (
                isinstance(result, dict)
                and result.get("routing_guidance")
                and isinstance(result.get("matches"), list)
            ):
                result = {
                    "status": result.get("status"),
                    "executed": result.get("executed"),
                    "routing_guidance": result["routing_guidance"],
                    "matches": [
                        {
                            key: item[key]
                            for key in ("action", "adapter", "downstream_action", "tool_name")
                            if isinstance(item, dict) and key in item
                        }
                        for item in result["matches"]
                        if isinstance(item, dict)
                    ],
                }
            result = _fit(sanitize(result), min(1_200, live_budget))
        proposed = getattr(event, "proposed", {})
        proposed = proposed if isinstance(proposed, dict) else {}
        arguments = _fit(sanitize(proposed.get("arguments", {})), 800)
        visible_tool = safe_action(proposed.get("tool"))
        if (
            proposed.get("kind") == "catalog"
            and bool(getattr(event, "executed", False))
            and isinstance(getattr(event, "result", None), dict)
            and event.result.get("routing_guidance")
        ):
            visible_tool = "catalog_result"
            arguments = {}
        entry = {
            "step": getattr(event, "step", None),
            "tool": visible_tool,
            "action": safe_action(proposed.get("action")),
            "arguments": arguments if isinstance(arguments, dict) else {},
            "executed": bool(getattr(event, "executed", False)),
            "result": result,
            "error": _fit(
                sanitize(getattr(event, "error", None)),
                1_200,
                key_priority=_error_priority,
            ),
        }
        summary.append(sanitize(entry))
    if history is not None:
        summary.insert(0, history)
    projected = _fit(summary, MODEL_CONTEXT_HINT_TOTAL_MAX_CHARS)
    return projected if isinstance(projected, list) else []
