"""LibreOffice Impress color semantics shared by routing and evidence checks."""

from __future__ import annotations

import copy
import re
from typing import Any

from impress_adapter.tool_manifest import RGB_COLOR


CSS_BASIC_COLORS = {
    "black": "#000000",
    "blue": "#0000FF",
    "gray": "#808080",
    "green": "#008000",
    "orange": "#FFA500",
    "purple": "#800080",
    "red": "#FF0000",
    "white": "#FFFFFF",
    "yellow": "#FFFF00",
}


LIBREOFFICE_IMPRESS_PALETTE_COLORS = {
    "dark red 2": "#C9211E",
    "green": "#00A933",
    "orange": "#FF8000",
}


IMPRESS_NAMED_COLORS = {
    **CSS_BASIC_COLORS,
    "cyan": "#00FFFF",
    "grey": "#808080",
    "magenta": "#FF00FF",
    **LIBREOFFICE_IMPRESS_PALETTE_COLORS,
}


def normalize_impress_color(value: Any) -> str | None:
    """Normalize a public Impress color value to an uppercase RGB string."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 0 <= value <= 0xFFFFFF:
        return f"#{value:06X}"
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.casefold().split())
    if re.fullmatch(r"#[0-9a-f]{6}", normalized):
        return normalized.upper()
    return IMPRESS_NAMED_COLORS.get(normalized)


def model_color_schema() -> dict[str, Any]:
    """Return a compact model-facing schema that preserves semantic color names."""
    schema = copy.deepcopy(RGB_COLOR)
    schema["description"] = (
        "Solid background color. If the instruction names a color, pass that exact "
        "color name instead of guessing an RGB value; use #RRGGBB only when the "
        "instruction gives an exact RGB color."
    )
    return schema
