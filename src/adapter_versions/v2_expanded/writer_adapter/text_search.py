from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator
from typing import Any

from .errors import AdapterError
from .native_references import _explicit_range
from .text_format import range_format


CONTEXT_RADIUS = 120


def _body_paragraphs(document: Any) -> list[Any]:
    paragraphs = []
    enumeration = document.Text.createEnumeration()
    while enumeration.hasMoreElements():
        item = enumeration.nextElement()
        try:
            if item.supportsService("com.sun.star.text.Paragraph"):
                paragraphs.append(item)
        except Exception:
            continue
    return paragraphs


def _format_runs(paragraph: Any) -> Iterator[tuple[int, int, dict[str, Any]]]:
    paragraph_text = str(paragraph.String)
    portions = paragraph.createEnumeration()
    pending = None
    while portions.hasMoreElements():
        portion = portions.nextElement()
        text = str(portion.String)
        if not text:
            continue
        # Measure native anchors; summing portion lengths can misplace fields/bookmarks.
        prefix = paragraph.getText().createTextCursorByRange(paragraph.getStart())
        prefix.gotoRange(portion.getStart(), True)
        start = len(str(prefix.String))
        end = start + len(text)
        if paragraph_text[start:end] != text:
            raise AdapterError(
                "TEXT_RANGE_NOT_FOUND",
                "native text portion does not match its body paragraph range",
                {"start_offset": start, "end_offset": end},
            )
        observed = range_format(portion)
        if pending is not None and pending[1] == start and pending[2] == observed:
            pending = (pending[0], end, observed)
        else:
            if pending is not None:
                yield pending
            pending = (start, end, observed)
    if pending is not None:
        yield pending


def _matching_ranges(
    paragraph: Any, pattern: Any, format_filter: dict[str, Any] | None
) -> Iterator[tuple[int, int, dict[str, Any] | None]]:
    if pattern is None:
        for start, end, observed in _format_runs(paragraph):
            if all(observed[key] == value for key, value in format_filter.items()):
                yield start, end, observed
        return
    for match in pattern.finditer(str(paragraph.String)):
        start, end = match.span()
        observed = None
        if format_filter is not None:
            cursor = _explicit_range(
                paragraph,
                start_offset=start,
                end_offset=end,
                expected_text=match.group(),
            )
            observed = range_format(cursor)
            if any(observed[key] != value for key, value in format_filter.items()):
                continue
        yield start, end, observed


def summarize_formats(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(tuple(sorted(match["format"].items())) for match in matches)
    return [
        {"format": dict(properties), "match_count": count}
        for properties, count in counts.items()
    ]


def find_text(session: Any, params: dict[str, Any]) -> dict[str, Any]:
    literal = params.get("literal")
    case_sensitive = params.get("case_sensitive") if literal is not None else None
    format_filter = params.get("format")
    max_results = int(params["max_results"])
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(literal), flags) if literal is not None else None
    matches: list[dict[str, Any]] = []
    has_more = False

    for paragraph_index, paragraph in enumerate(_body_paragraphs(session.doc)):
        paragraph_text = str(paragraph.String)
        for start_offset, end_offset, observed in _matching_ranges(
            paragraph, pattern, format_filter
        ):
            if len(matches) >= max_results:
                has_more = True
                break
            item = {
                "paragraph_index": paragraph_index,
                "start_offset": start_offset,
                "end_offset": end_offset,
                "matched_text": paragraph_text[start_offset:end_offset],
            }
            if observed is not None:
                item["format"] = observed
            if literal is not None:
                context_start = max(0, start_offset - CONTEXT_RADIUS)
                context_end = min(len(paragraph_text), end_offset + CONTEXT_RADIUS)
                item.update(
                    {
                        "context": paragraph_text[context_start:context_end],
                        "context_start_offset": context_start,
                        "context_end_offset": context_end,
                        "context_truncated": (
                            context_start > 0 or context_end < len(paragraph_text)
                        ),
                        "paragraph_length": len(paragraph_text),
                    }
                )
            matches.append(item)
        if has_more:
            break

    return {
        "scope": "body_paragraphs",
        "literal": literal,
        "case_sensitive": case_sensitive,
        **({"format": format_filter} if format_filter is not None else {}),
        "max_results": max_results,
        "returned_count": len(matches),
        "has_more": has_more,
        **(
            {
                "format_counts": summarize_formats(matches),
                "format_counts_scope": "returned_matches",
            }
            if format_filter is not None
            else {}
        ),
        "matches": matches,
    }
