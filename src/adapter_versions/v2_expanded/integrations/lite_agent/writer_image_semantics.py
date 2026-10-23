from __future__ import annotations

import re


_IMAGE_SUBJECT_RE = re.compile(
    r"(?i)(?:\b(?:image|picture|photo|photograph|screenshot|graphic|diagram)\b|"
    r"\b[^\s/\\]+\.(?:png|jpe?g|gif|bmp|webp|tiff?)\b)"
)
_INSERTION_VERB_RE = re.compile(r"(?i)\b(?:insert|paste|place|add|copy)\b")
_CURSOR_TARGET_RE = re.compile(
    r"(?is)\b(?:at|to|into)\s+(?:where\s+)?"
    r"(?:(?:my|the|your|our)\s+)?(?:current\s+)?"
    r"(?:text\s+)?(?:cursor|caret|insertion\s+point)"
    r"(?:\s+(?:is\s+)?(?:located|positioned))?\b"
)
_MULTIPLE_RE = re.compile(
    r"(?i)(?:\b(?:two|three|four|five|six|seven|eight|nine|ten|multiple|several|both)\b|"
    r"\b\d+\s+(?:copies|images|pictures|photos|screenshots|graphics|diagrams)\b|"
    r"\b(?:twice|three\s+times|four\s+times)\b|"
    r"\b(?:images|pictures|photos|screenshots|graphics|diagrams)\b)"
)


def requests_single_cursor_image_insertion(instruction: str) -> bool:
    """Recognize one image placement whose destination is the Writer cursor."""
    if not _INSERTION_VERB_RE.search(instruction):
        return False
    if not _IMAGE_SUBJECT_RE.search(instruction):
        return False
    if not _CURSOR_TARGET_RE.search(instruction):
        return False
    return _MULTIPLE_RE.search(instruction) is None


__all__ = ["requests_single_cursor_image_insertion"]
