from __future__ import annotations

from typing import Any, Final


DEBUGGING_SETTING_FIELDS: Final[dict[str, str]] = {
    "focus_editor_on_break": "debug.focusEditorOnBreak",
    "inline_values": "debug.inlineValues",
    "internal_console": "debug.internalConsoleOptions",
    "open_debug_view": "debug.openDebug",
    "show_breakpoints_in_overview_ruler": "debug.showBreakpointsInOverviewRuler",
    "show_inline_breakpoint_candidates": "debug.showInlineBreakpointCandidates",
}

INLINE_VALUE_MODES: Final[frozenset[str]] = frozenset({"auto", "off", "on"})
DEBUG_OPEN_MODES: Final[frozenset[str]] = frozenset(
    {"neverOpen", "openOnDebugBreak", "openOnFirstSessionStart", "openOnSessionStart"}
)
INTERNAL_CONSOLE_MODES: Final[frozenset[str]] = frozenset(
    {"neverOpen", "openOnFirstSessionStart", "openOnSessionStart"}
)
DEBUG_WAIT_STATES: Final[frozenset[str]] = frozenset({"paused", "running"})


def debugging_settings(params: dict[str, Any]) -> dict[str, Any]:
    return {
        setting: params[field]
        for field, setting in DEBUGGING_SETTING_FIELDS.items()
        if field in params
    }
