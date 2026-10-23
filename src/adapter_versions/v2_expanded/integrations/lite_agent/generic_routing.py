"""Conservative, state-derived routing guards for strict LiteAgent episodes.

The router must not try to predict the next argument set.  In particular, a
successful ``command.run`` can be followed by another ``command.run`` with a
different command, and a successful write can be followed by another write
before the final save.  Action-level suppression for those cases silently
turns a valid workflow into a Top-K error.  The executor already blocks exact
duplicate mutations and the recovery protocol handles repeated failures;
this module only removes actions that the state machine has classified as
*fully* blocked (for example, a read action for which multiple argument
variants have independently failed).
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from integrations.openapa_osworld.tool_catalog import public_actions
from multi_apps_adapter.route_utils import is_route, normalize_route

from .impress_image_insertion import is_sized_image_insertion_instruction
from .tool_catalog import (
    DOWNSTREAM_ADAPTER_DOMAINS,
    FORBIDDEN_DATASET_ACTIONS,
    INSPECT_ACTIONS,
)


_FORBIDDEN_ACTIONS_NORMALIZED = {
    normalize_route(item) for item in FORBIDDEN_DATASET_ACTIONS
}


def _proposal(event: Any) -> dict[str, Any]:
    proposed = getattr(event, "proposed", None)
    return proposed if isinstance(proposed, dict) else {}


def _normalized_action(value: Any) -> str:
    return normalize_route(value)


def recovery_blocked_actions(state: Any) -> set[str]:
    """Return only actions that are fully blocked by truthful episode state.

    ``RuntimeState.blocked_actions`` deliberately distinguishes an action from
    an individual failed argument variant.  Keeping that distinction is
    essential for parameterized APIs and multi-step command workflows.
    """
    blocked = getattr(state, "blocked_actions", None)
    return set(blocked()) if callable(blocked) else set()


def recovery_search_actions(state: Any) -> list[str] | None:
    """Return public actions from the latest catalog search.

    When the model explicitly names one or more public actions in its query,
    keep only those exact matches for the next turn.  A query such as
    ``chart.create`` is already an action choice, so mixing the remaining
    fuzzy Top-K back into the model-visible surface only creates another
    routing decision.  Natural-language searches retain the normal ranked
    result set.
    """
    latest = _latest_catalog_event(state)
    if latest is None:
        return None
    proposed = getattr(latest, "proposed", {})
    matches = _catalog_matches(latest)
    available = set(public_actions(getattr(state, "domain", "")))
    recovered = list(
        dict.fromkeys(
            str(match["action"])
            for match in matches
            if isinstance(match, dict) and match.get("action") in available
        )
    )
    arguments = proposed.get("arguments")
    query = str(arguments.get("query", "")) if isinstance(arguments, dict) else ""
    exact = [
        action
        for action in recovered
        if re.search(
            rf"(?<![\w.]){re.escape(action.casefold())}(?![\w.])",
            query.casefold(),
        )
    ]
    return exact or recovered


def recovery_search_routes(state: Any) -> list[tuple[str, str]] | None:
    """Return exact downstream routes from the latest catalog search.

    ``adapter.call`` is a transport facade, not permission to combine any
    Adapter with any public action.  The search result already identifies the
    reusable route pairs that matched the model's query.  Keeping those pairs
    intact lets the next model request expose a truthful, correlated schema
    without selecting a route or filling an argument on the model's behalf.
    """
    latest = _latest_catalog_event(state)
    if latest is None:
        return None
    valid_domains = set(DOWNSTREAM_ADAPTER_DOMAINS)
    routes: list[tuple[str, str]] = []
    for match in _catalog_matches(latest):
        if not isinstance(match, dict) or match.get("action") != "adapter.call":
            continue
        adapter = match.get("adapter")
        action = match.get("downstream_action")
        if not isinstance(adapter, str) or adapter not in valid_domains:
            continue
        if not isinstance(action, str) or not action:
            continue
        if (
            is_route(action, FORBIDDEN_DATASET_ACTIONS)
            or _normalized_action(action) in _FORBIDDEN_ACTIONS_NORMALIZED
            or action not in public_actions(adapter)
        ):
            continue
        route = (adapter, action)
        if route not in routes:
            routes.append(route)
    return routes


def discovered_adapter_routes(state: Any) -> list[tuple[str, str]]:
    """Return public downstream routes explicitly returned by catalog search.

    ``multi_apps.adapter.call`` is a transport facade, so its route must have
    provenance in a model-selected catalog result. This helper scans only
    successful catalog events and validates each pair against the public
    downstream catalog; it never derives a route from the task instruction.
    """
    valid_domains = set(DOWNSTREAM_ADAPTER_DOMAINS)
    latest = _latest_catalog_event(state)
    latest_arguments = (
        getattr(latest, "proposed", {}).get("arguments") if latest is not None else None
    )
    latest_query = (
        latest_arguments.get("query", "")
        if isinstance(latest_arguments, dict)
        else ""
    )
    latest_returned_routes = {
        (match.get("adapter"), match.get("downstream_action"))
        for match in _catalog_matches(latest)
        if isinstance(match, dict) and match.get("action") == "adapter.call"
    }
    # Keep an explicit fully-qualified search atomic across the next tool
    # surface. Without this, the accumulated history widens a later exact
    # route back into a large oneOf wrapper and small providers often emit {}.
    latest_explicit = [
        (adapter, action)
        for adapter in valid_domains
        for action in public_actions(adapter)
        if (adapter, action) in latest_returned_routes and re.search(
            rf"(?<![\w.]){re.escape(adapter)}(?:\.|\s+){re.escape(action)}(?![\w.])",
            str(latest_query).casefold(),
        )
    ]
    if latest_explicit:
        return latest_explicit[:1]
    routes: list[tuple[str, str]] = []
    for event in getattr(state, "events", ()) or ():
        if not getattr(event, "executed", False):
            continue
        proposed = _proposal(event)
        if proposed.get("kind") != "catalog":
            continue
        for match in _catalog_matches(event):
            if not isinstance(match, dict) or match.get("action") != "adapter.call":
                continue
            adapter = match.get("adapter")
            action = match.get("downstream_action")
            if not isinstance(adapter, str) or adapter not in valid_domains:
                continue
            if not isinstance(action, str) or not action:
                continue
            if (
                is_route(action, FORBIDDEN_DATASET_ACTIONS)
                or _normalized_action(action) in _FORBIDDEN_ACTIONS_NORMALIZED
                or action not in public_actions(adapter)
            ):
                continue
            route = (adapter, action)
            if route not in routes:
                routes.append(route)
    return routes


def _latest_catalog_event(state: Any) -> Any | None:
    events = getattr(state, "events", None)
    if not events:
        return None
    for latest in reversed(events):
        proposed = getattr(latest, "proposed", None)
        if (
            getattr(latest, "executed", False)
            and isinstance(proposed, dict)
            and proposed.get("kind") == "catalog"
        ):
            return latest
    return None


def _catalog_matches(event: Any) -> list[Any]:
    result = getattr(event, "result", None)
    matches = result.get("matches") if isinstance(result, dict) else None
    return matches if isinstance(matches, list) else []


def filter_generic_actions(state: Any, actions: Iterable[str]) -> list[str]:
    """Filter only from truthful episode state; never infer task identity."""
    blocked = recovery_blocked_actions(state)
    stage_read_satisfied = getattr(state, "stage_read_satisfied", None)
    selected = [
        action
        for action in actions
        if action not in blocked
        and not (callable(stage_read_satisfied) and stage_read_satisfied(action))
    ]
    instruction = str(getattr(state, "instruction", ""))
    if (
        getattr(state, "domain", None) == "libreoffice_calc"
        and getattr(state, "events", None)
        and re.search(
            r"(?i)\b(?:new|separate)\s+(?:sheet|worksheet|tab)\b", instruction
        )
        and not re.search(
            r"(?i)\b(?:new|create|make)\s+(?:a\s+)?(?:workbook|spreadsheet|file)\b",
            instruction,
        )
    ):
        selected = [action for action in selected if action != "workbook.create_new"]
    return selected


def stage_generic_actions(state: Any, actions: Iterable[str]) -> list[str]:
    """Apply the small, application-semantic discovery stage used by strict mode.

    Calc and Impress operations commonly require an observed sheet/shape before
    any mutation can be parameterized.  Exposing their complete Top-K on the
    first turn makes a small tool-calling model choose a write or GUI action
    before it has state.  The first turn therefore contains only the public
    inspection action; subsequent turns return the normal ranked catalog.  No
    task identity, expected value, or argument is consulted.
    """
    selected = list(actions)
    if getattr(state, "events", None):
        return selected
    domain = getattr(state, "domain", None)
    if domain not in {"libreoffice_calc", "libreoffice_impress"}:
        return selected
    available = set(public_actions(domain))
    candidates = INSPECT_ACTIONS.get(domain, ())
    # Physical image insertion has a complete model-facing contract (path,
    # slide reference, and measurement objects) that must be visible on the
    # first request.  Keep inspection first in the ordered surface, but do not
    # hide the mutation until after a prose-only response; the model still
    # receives the prompt instruction to inspect before using it.
    if (
        domain == "libreoffice_impress"
        and is_sized_image_insertion_instruction(str(getattr(state, "instruction", "")))
        and "shape.insert_image" in selected
    ):
        return [
            action
            for action in (*candidates, "shape.insert_image")
            if action in selected
        ]
    for action in candidates:
        if action in available:
            return [action]
    return selected


def focus_generic_actions(
    state: Any,
    actions: Iterable[str],
    semantic_hints: Iterable[str],
) -> list[str]:
    """Narrow a single-operation workflow without materializing its arguments.

    A small model benefits from seeing one relevant mutation together with the
    read/save actions needed to ground and persist it.  Multi-step workflows
    keep the normal ranked surface, and an omitted action remains discoverable
    through ``tools_search``.  The decision uses only the instruction-derived
    public action names and truthful episode state.
    """
    selected = list(actions)
    domain = getattr(state, "domain", "")
    # Multi-Apps spans every Adapter and therefore has a much larger initial
    # catalog than an application-specific domain. A single semantic facade is
    # enough for its first turn; tools_search remains available for recovery.
    if not getattr(state, "events", None) and domain != "multi_apps":
        return selected
    hinted = list(
        dict.fromkeys(action for action in semantic_hints if action in selected)
    )
    mutation_hints = [
        action
        for action in hinted
        if action not in INSPECT_ACTIONS.get(getattr(state, "domain", ""), ())
        and not action.endswith((".save", ".export"))
    ]
    prioritized_mutations = list(mutation_hints)
    # Export-only tasks are also single-operation workflows; save/export is
    # deliberately treated as the focused mutation in that case.
    if not mutation_hints:
        mutation_hints = [
            action for action in hinted if action.endswith((".save", ".export"))
        ]
    if len(mutation_hints) != 1:
        return selected
    focus = set(mutation_hints)
    focus.update(INSPECT_ACTIONS.get(domain, ()))
    focus.update(action for action in selected if action.endswith((".save", ".export")))
    # Preserve parameterized read actions for grounding (for example Calc
    # range.read) without reintroducing unrelated mutations.
    focus.update(
        action
        for action in selected
        if action.endswith((".read", ".read_file", ".inspect", ".snapshot"))
    )
    narrowed = [*prioritized_mutations]
    narrowed.extend(
        action for action in selected if action in focus and action not in narrowed
    )
    return narrowed or selected
