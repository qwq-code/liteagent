from __future__ import annotations

from typing import Any, Final


EDITOR_BOOLEAN_SETTINGS: Final[dict[str, str]] = {
    "minimap_enabled": "editor.minimap.enabled",
    "smooth_scrolling": "editor.smoothScrolling",
    "sticky_scroll_enabled": "editor.stickyScroll.enabled",
    "wrap_tabs": "workbench.editor.wrapTabs",
}

EDITOR_ENUM_SETTINGS: Final[dict[str, tuple[str, dict[str, str]]]] = {
    "line_numbers": (
        "editor.lineNumbers",
        {
            "off": "off",
            "on": "on",
            "relative": "relative",
            "interval": "interval",
        },
    ),
    "render_whitespace": (
        "editor.renderWhitespace",
        {
            "none": "none",
            "boundary": "boundary",
            "selection": "selection",
            "trailing": "trailing",
            "all": "all",
        },
    ),
    "word_wrap": (
        "editor.wordWrap",
        {
            "off": "off",
            "on": "on",
            "at_column": "wordWrapColumn",
            "bounded": "bounded",
        },
    ),
}

EDITOR_INTEGER_SETTINGS: Final[dict[str, str]] = {
    "word_wrap_column": "editor.wordWrapColumn",
}

EDITOR_SETTING_FIELDS: Final[frozenset[str]] = frozenset(
    {
        *EDITOR_BOOLEAN_SETTINGS,
        *EDITOR_ENUM_SETTINGS,
        *EDITOR_INTEGER_SETTINGS,
    }
)


def editor_settings(params: dict[str, Any]) -> dict[str, Any]:
    values = {
        setting: params[field]
        for field, setting in EDITOR_BOOLEAN_SETTINGS.items()
        if field in params
    }
    values.update(
        {
            setting: choices[str(params[field])]
            for field, (setting, choices) in EDITOR_ENUM_SETTINGS.items()
            if field in params
        }
    )
    values.update(
        {
            setting: params[field]
            for field, setting in EDITOR_INTEGER_SETTINGS.items()
            if field in params
        }
    )
    return values
