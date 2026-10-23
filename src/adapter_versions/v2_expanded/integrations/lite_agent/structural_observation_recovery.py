"""Bounded recovery from unchanged structural observations."""

from __future__ import annotations

from typing import Any

from .completion_policy import (
    action_is_read_only,
    action_is_save,
    effective_canonical_action,
)
from .state_model import RuntimeState
from .tool_catalog import action_from_tool_name


def repeated_structural_observation(state: RuntimeState) -> bool:
    """Recognize two identical successful inspections with identical arguments."""
    if len(state.events) < 2:
        return False
    previous, latest = state.events[-2:]
    if not all(event.executed and not event.error for event in (previous, latest)):
        return False
    before = effective_canonical_action(previous, state.domain)
    after = effective_canonical_action(latest, state.domain)
    if before != after or after[1] not in {
        'presentation.inspect', 'document.inspect', 'workbook.inspect',
    }:
        return False
    hints = [event.result.get('context_hint') if isinstance(event.result, dict) else None
             for event in (previous, latest)]
    return bool(isinstance(hints[0], dict) and hints[0] and hints[0] == hints[1])


def recover_structural_tool_surface(
    tools: list[dict[str, Any]], state: RuntimeState,
) -> list[dict[str, Any]]:
    """Pause a repeated direct inspection for one turn, leaving model choices.

    Only a surface with both an edit and catalog escape can use this recovery.
    Any intervening event, changed target, changed result or failed inspection
    restores the normal surface. Forwarded adapter.call routes remain intact.
    """
    if state.domain not in {'libreoffice_calc', 'libreoffice_writer', 'libreoffice_impress'}:
        return tools
    names = [tool.get('function', {}).get('name', '') for tool in tools]
    if 'tools_search' not in names or {'gui_action', 'gui_request'}.intersection(names):
        return tools
    if not repeated_structural_observation(state):
        return tools
    actions = [action_from_tool_name(state.domain, name) for name in names]
    if not any(action and not action_is_read_only(action) and not action_is_save(action)
               for action in actions):
        return tools
    repeated_action = effective_canonical_action(state.events[-1], state.domain)[1]
    return [tool for tool, action in zip(tools, actions) if action != repeated_action]
