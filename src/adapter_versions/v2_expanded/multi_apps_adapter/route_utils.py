"""Small route-name predicates shared by strict model and Adapter boundaries."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any
from urllib.parse import unquote


# A serialized message can contain more than one escaped backslash before a
# Unicode escape (for example after JSON logging).  Decode only a bounded run
# so this remains a boundary normalizer rather than a general escape parser.
_UNICODE_ESCAPE_RE = re.compile(r"\\{1,8}u([0-9a-fA-F]{4})|\\{1,8}U([0-9a-fA-F]{8})")
_UNRESOLVED_PERCENT_RE = re.compile(r"%[0-9a-fA-F]{2}")
_UNRESOLVED_UNICODE_RE = re.compile(r"\\{1,8}[uU][0-9a-fA-F]{4,8}")


def _decode_route_text(value: Any) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    # Decode only explicit, bounded route encodings. Do not run a general
    # escape decoder over arbitrary user text, which could alter arguments.
    # A bounded set of passes catches values that arrived through several
    # transport encoding layers (for example ``%25252e``) without recursively
    # rewriting arbitrary model arguments forever.  Eight layers is enough for
    # nested JSON/URL wrappers while keeping this predicate cheap and bounded.
    for _ in range(8):
        decoded = unquote(text)
        if decoded == text:
            break
        text = decoded

    def replace_escape(match: re.Match[str]) -> str:
        token = match.group(1) or match.group(2)
        try:
            return chr(int(token, 16))
        except (TypeError, ValueError):
            return match.group(0)

    return unicodedata.normalize("NFKC", _UNICODE_ESCAPE_RE.sub(replace_escape, text))


def decode_text(value: Any) -> str:
    """Decode bounded transport/Unicode spellings before boundary checks.

    Route checks and metadata checks must inspect the same decoded text.  This
    helper intentionally exposes the already-bounded decoder without applying
    route normalization, so callers can run their own exact-token predicates
    (for example UUID detection).
    """
    return _decode_route_text(value)


def has_unresolved_encoding(value: Any) -> bool:
    """Return whether bounded decoding left an encoded control sequence.

    Boundary callers use this to fail closed instead of assuming that a fixed
    decode limit is itself proof that an encoded route is harmless.
    """
    decoded = _decode_route_text(value)
    return bool(
        _UNRESOLVED_PERCENT_RE.search(decoded) or _UNRESOLVED_UNICODE_RE.search(decoded)
    )


def normalize_route(value: Any) -> str:
    """Normalize route spelling without changing model-selected arguments."""
    return re.sub(r"[^a-z0-9]", "", _decode_route_text(value).casefold())


def is_route(value: Any, routes: Iterable[str]) -> bool:
    """Match one route token across case and separator variants."""
    routes = tuple(routes)
    if has_unresolved_encoding(value):
        return bool(routes)
    normalized = normalize_route(value)
    return bool(normalized) and any(
        normalized == normalize_route(route) for route in routes
    )


def contains_route(value: Any, routes: Iterable[str]) -> bool:
    """Find a forbidden route embedded in bounded text or serialized JSON."""
    routes = tuple(routes)
    if has_unresolved_encoding(value):
        return bool(routes)
    normalized = normalize_route(value)
    return bool(normalized) and any(
        normalize_route(route) in normalized for route in routes
    )


def contains_route_in_prose(value: Any, routes: Iterable[str]) -> bool:
    """Match route markers without joining punctuation-separated prose clauses."""
    if has_unresolved_encoding(value):
        return bool(tuple(routes))
    decoded = _decode_route_text(value)
    return any(contains_route(part, routes) for part in re.split(r"[,;!?]", decoded))
