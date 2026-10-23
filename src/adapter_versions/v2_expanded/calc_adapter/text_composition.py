from __future__ import annotations

from typing import Any


FIELD_SEPARATOR_STYLES = {
    "comma_space": ", ",
    "comma": ",",
    "semicolon_space": "; ",
    "semicolon": ";",
    "pipe_space": " | ",
    "pipe": "|",
}

LABEL_SEPARATOR_STYLES = {
    "colon_space": ": ",
    "colon": ":",
    "equals_space": " = ",
    "equals": "=",
}


def resolve_text_separator(
    params: dict[str, Any],
    *,
    literal_key: str,
    style_key: str,
    styles: dict[str, str],
    default: str,
) -> str:
    """Resolve a model-selected semantic style or a legacy literal separator."""
    style = params.get(style_key)
    if style is not None:
        return styles[str(style)]
    return str(params.get(literal_key, default))
