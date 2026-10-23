"""Instruction-only routing for parameterized VS Code configuration actions."""

from __future__ import annotations

import re


CONFIGURATION_ACTIONS = frozenset(
    {
        "debugging.configure",
        "diagnostics.configure",
        "editor.configure",
        "explorer.set_exclusion",
        "files.configure",
        "keybindings.ensure",
        "settings.update",
    }
)

_EXPLICIT_SETTING_RE = re.compile(
    r"(?i)\b(?:debug|diffEditor|editor|extensions|files|git|http|javascript|python|"
    r"search|security|terminal|typescript|window|workbench)\.[A-Za-z][A-Za-z0-9.]*\b"
)


def required_actions(domain: str, instruction: str) -> list[str]:
    if domain != "vs_code":
        return []

    if _EXPLICIT_SETTING_RE.search(instruction):
        return ["settings.update"]

    if re.search(r"(?i)\b(?:shortcut|keybinding|key\s+binding|hotkey)\b", instruction):
        return ["keybindings.ensure"]

    if re.search(
        r"(?i)\b(?:debug|debugger|debugging|breakpoint)\b", instruction
    ) and re.search(
        r"(?i)\b(?:break|console|cursor|editor|focus|inline|open|ruler|variable)\w*\b",
        instruction,
    ):
        return ["debugging.configure"]

    if re.search(
        r"(?i)\b(?:diagnostic|error|report|severity|warning)\w*\b", instruction
    ) and re.search(
        r"(?i)\b(?:import|module|python|type|undefined|unused|variable)\w*\b",
        instruction,
    ):
        return ["diagnostics.configure"]

    if re.search(r"(?i)\b(?:explorer|file|folder)\w*\b", instruction) and re.search(
        r"(?i)\b(?:exclude|hide|hidden|show|visible)\w*\b",
        instruction,
    ):
        return ["explorer.set_exclusion"]

    if re.search(
        r"(?i)\b(?:auto\s*save|autosave|automatic\s+sav(?:e|ing)|final\s+newline|hot\s+exit|"
        r"trailing\s+whitespace|trim\s+final\s+newlines?)\b",
        instruction,
    ):
        return ["files.configure"]

    if re.search(
        r"(?i)\b(?:line\s+numbers?|minimap|render\s+whitespace|smooth\s+scrolling|"
        r"sticky\s+scroll|tabs?\s+(?:wrap|wrapped|wrapping)|wrap\s+tabs?|"
        r"wrap\w*\b.{0,30}\btabs?|"
        r"word\s+wrap|code\s+wrapping|wrap(?:ping)?\s+(?:column|line)|line\s+length)\b",
        instruction,
    ):
        return ["editor.configure"]

    return []


def stage_actions(
    domain: str, instruction: str, actions: list[str], events: list
) -> list[str]:
    required = required_actions(domain, instruction)
    if not required:
        return actions
    if any(
        event.executed
        and event.proposed.get("kind") == "adapter"
        and event.proposed.get("action") in required
        for event in events
    ):
        return actions
    return [action for action in actions if action in required]
