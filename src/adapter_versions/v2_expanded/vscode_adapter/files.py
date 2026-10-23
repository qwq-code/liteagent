from __future__ import annotations

from typing import Any, Final


AUTO_SAVE_MODES: Final[dict[str, str]] = {
    "off": "off",
    "after_delay": "afterDelay",
    "on_focus_change": "onFocusChange",
    "on_window_change": "onWindowChange",
}

HOT_EXIT_MODES: Final[dict[str, str]] = {
    "off": "off",
    "on_exit": "onExit",
    "on_exit_and_window_close": "onExitAndWindowClose",
}

FILES_BOOLEAN_SETTINGS: Final[dict[str, str]] = {
    "insert_final_newline": "files.insertFinalNewline",
    "trim_final_newlines": "files.trimFinalNewlines",
    "trim_trailing_whitespace": "files.trimTrailingWhitespace",
}

FILES_SETTING_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "auto_save",
        "auto_save_delay_ms",
        "hot_exit",
        *FILES_BOOLEAN_SETTINGS,
    }
)


def file_settings(params: dict[str, Any]) -> dict[str, Any]:
    values = {
        setting: params[field]
        for field, setting in FILES_BOOLEAN_SETTINGS.items()
        if field in params
    }
    if "auto_save" in params:
        values["files.autoSave"] = AUTO_SAVE_MODES[str(params["auto_save"])]
    if "auto_save_delay_ms" in params:
        values["files.autoSaveDelay"] = params["auto_save_delay_ms"]
    if "hot_exit" in params:
        values["files.hotExit"] = HOT_EXIT_MODES[str(params["hot_exit"])]
    return values
