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


def saved_edit_before_observation(state: RuntimeState) -> tuple[bool, bool]:
    """Return (saved, edited) without interpreting task success from action names."""
    saved = False
    edited = False
    for event in state.events[:-2]:
        kind = event.proposed.get('kind')
        if kind == 'gui' and event.executed:
            saved = False
            edited = True
        if kind != 'adapter':
            continue
        domain, action, _ = effective_canonical_action(event, state.domain)
        if domain != state.domain or action_is_read_only(action):
            continue
        if event.error and event.validated:
            saved = False  # A dispatched failure may have partial effects.
        elif event.executed and not event.error:
            if action_is_save(action):
                saved = True
            else:
                saved = state.event_has_save_evidence(event)
                edited = True
    return saved, edited


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
    if 'tools_search' not in names:
        return tools
    if not repeated_structural_observation(state):
        return tools
    saved, edited = saved_edit_before_observation(state)
    if saved and edited and 'propose_done' in names:
        # One review turn prevents an unchanged observation loop from offering
        # another edit that undoes the saved state. The model still chooses:
        # completion (checked normally), catalog search for unfinished work, or
        # failure. Any intervening event restores ordinary editing tools.
        return [tool for tool in tools if tool.get('function', {}).get('name')
                in {'tools_search', 'propose_done', 'fail_task'}]
    if {'gui_action', 'gui_request'}.intersection(names):
        return tools
    actions = [action_from_tool_name(state.domain, name) for name in names]
    if not any(action and not action_is_read_only(action) and not action_is_save(action)
               for action in actions):
        return tools
    repeated_action = effective_canonical_action(state.events[-1], state.domain)[1]
    return [tool for tool, action in zip(tools, actions)
            if action != repeated_action and not (saved and action_is_save(action or ''))]
