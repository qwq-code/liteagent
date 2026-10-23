"""Semantic guards for Impress actions with overlapping movement vocabulary."""

from __future__ import annotations

import re


_SLIDE_ORDINAL = r"(?:page|slide)(?:\s+(?:index|number))?\s+\d+"
_OBJECT_RE = re.compile(
    r"(?i)\b(?:chart|diagram|graphic|image|media|object|photo|picture|shape|"
    r"table|text\s*box|textbox|title|video)\b"
)
_MOVE_RE = re.compile(r"(?i)\b(?:align|move|place|position|put|relocate)\b")
_READ_ONLY_NAVIGATION_RES = (
    re.compile(
        r"(?i)\b(?:display|inspect|navigate|open|select|show|switch|view)\b"
        rf".{{0,40}}\b{_SLIDE_ORDINAL}\b"
    ),
    re.compile(rf"(?i)\b(?:go|jump|move|switch)\s+to\s+{_SLIDE_ORDINAL}\b"),
    re.compile(r"(?i)\b(?:next|previous|prior)\s+(?:page|slide)\b"),
)
_EXPLICIT_SLIDE_REORDER_RES = (
    re.compile(rf"(?i)\b(?:move|place|put)\s+(?:the\s+)?{_SLIDE_ORDINAL}\b"),
    re.compile(
        rf"(?i)\b{_SLIDE_ORDINAL}\b.{{0,40}}\b(?:after|before)\s+"
        rf"{_SLIDE_ORDINAL}\b"
    ),
    re.compile(
        rf"(?i)\b{_SLIDE_ORDINAL}\b.{{0,40}}\b(?:as|at|to)\s+"
        r"(?:the\s+)?(?:beginning|end|first|index|last|position)\b"
    ),
    re.compile(r"(?i)\b(?:rearrange|reorder)\b.{0,50}\b(?:pages|slides)\b"),
)


def _semantic_routing_text(value: str) -> str:
    """Make API-like search syntax readable without changing the model's query."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+|_+", " ", value)).strip()


def suppress_whole_slide_move(query: str, instruction: str = "") -> bool:
    """Return true when the request is not an explicit deck-page reorder."""
    if re.search(r"(?i)(?<![\w.])slide\.move(?![\w.])", query):
        return False
    semantic_query = _semantic_routing_text(query)
    semantic_instruction = _semantic_routing_text(instruction)
    if any(
        pattern.search(semantic_query) or pattern.search(semantic_instruction)
        for pattern in _EXPLICIT_SLIDE_REORDER_RES
    ):
        return False
    if any(pattern.search(semantic_query) for pattern in _READ_ONLY_NAVIGATION_RES):
        return True
    combined = f"{semantic_query}\n{semantic_instruction}"
    return bool(_OBJECT_RE.search(combined) and _MOVE_RE.search(combined))


__all__ = ["suppress_whole_slide_move"]
