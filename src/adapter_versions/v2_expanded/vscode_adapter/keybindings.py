from __future__ import annotations

from typing import Any


KEYBINDING_OPERATION_SPECS = {
    "find_in_files": ("workbench.action.findInFiles", ""),
    "focus_active_editor": (
        "workbench.action.focusActiveEditorGroup",
        "terminalFocus",
    ),
    "focus_terminal": ("workbench.action.terminal.focus", "editorTextFocus"),
    "quick_open": ("workbench.action.quickOpen", ""),
    "save_file": ("workbench.action.files.save", "editorTextFocus"),
    "show_command_palette": ("workbench.action.showCommands", ""),
    "toggle_terminal": ("workbench.action.terminal.toggleTerminal", ""),
    "tree_view_find": ("list.find", "listFocus && listSupportsFind"),
}

KEYBINDING_OPERATION_COMMANDS = {
    operation: command
    for operation, (command, _when) in KEYBINDING_OPERATION_SPECS.items()
}


def normalize_binding(params: dict[str, Any]) -> dict[str, Any]:
    if "binding" in params:
        return dict(params["binding"])

    if "operation" in params:
        command, when = KEYBINDING_OPERATION_SPECS[str(params["operation"])]
    else:
        command = str(params["command"])
        when = str(params["when"])
    disabled = bool(params["disabled"])
    if (
        disabled
        and "listFocus" in when
        and "listSupportsFind" in when
        and command.removeprefix("-") in {"list.find", "workbench.action.find"}
    ):
        command = "list.find"
    if disabled and not command.startswith("-"):
        command = f"-{command}"
    if not disabled and command.startswith("-"):
        command = command.removeprefix("-")

    binding = {"key": str(params["key"]), "command": command}
    if when:
        binding["when"] = when
    return binding
