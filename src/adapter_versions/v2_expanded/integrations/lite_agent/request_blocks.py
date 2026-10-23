"""Lifecycle rules for repeated-request blocks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .completion_policy import (
    action_is_read_only,
    action_is_save,
    effective_canonical_action,
)

if TYPE_CHECKING:
    from .state_model import ExecutionEvent


def event_changes_application_state(event: ExecutionEvent) -> bool:
    """Return whether a successful event can make an earlier request valid again."""

    if not event.executed:
        return False
    kind = event.proposed.get("kind")
    if kind == "gui":
        return True
    if kind != "adapter":
        return False
    _domain, action, _arguments = effective_canonical_action(event, "")
    # An image export creates a new external artifact. It must invalidate a
    # prior failed request that was caused only by that artifact being absent,
    # even though the generic ``.export`` suffix is otherwise treated like a
    # save operation.
    if action == "shape.export_image":
        return True
    return bool(
        isinstance(action, str)
        and action
        and not action_is_read_only(action)
        and not action_is_save(action)
    )


def request_block_is_stale(
    events: list[ExecutionEvent], *, blocked_at_step: int
) -> bool:
    """Expire a request block after a later successful application mutation."""

    return any(
        event.step > blocked_at_step and event_changes_application_state(event)
        for event in events
    )
