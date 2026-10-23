from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .completion_policy import (
    COMPLETION_RECOVERY_READBACK_ONLY,
    COMPLETION_RECOVERY_TASK_STATE,
    action_is_read_only,
    action_is_save,
    classify_completion_recovery,
    command_is_read_only,
    completion_recovery_guidance,
    collect_initial_completion_evidence,
    cross_app_presentation_completion_status,
    effective_canonical_action,
)
from .tool_catalog import (
    INSPECT_ACTIONS,
    FORBIDDEN_DATASET_ACTIONS,
    SAVE_ACTIONS,
    action_relevance_score,
    action_from_tool_name,
    build_tools,
)
from .generic_routing import discovered_adapter_routes
from .search_recovery_tools import constrain_adapter_call_routes
from .tool_catalog import tool_name
from .generic_completion import (
    STRICT_COMPLETION_DONE,
    STRICT_COMPLETION_PERSIST,
    STRICT_COMPLETION_PERSIST_AND_READBACK,
    STRICT_COMPLETION_READBACK,
    strict_completion_phase,
)
from . import source_execution_semantics


def pending_completion_recovery(events: Iterable[Any]) -> dict[str, Any] | None:
    """Keep recovery active across rejected, non-executed hidden tool attempts."""
    for event in reversed(list(events)):
        if event.executed:
            return None
        if (
            event.proposed.get("kind") == "completion"
            and isinstance(event.error, dict)
            and event.error.get("status") == "rejected"
        ):
            recovery = event.error.get("recovery")
            if isinstance(recovery, dict):
                return recovery
            return recovery_details(COMPLETION_RECOVERY_TASK_STATE)
    return None


def pending_completion_recovery_mode(events: Iterable[Any]) -> str | None:
    recovery = pending_completion_recovery(events)
    mode = recovery.get("mode") if recovery is not None else None
    return str(mode) if mode is not None else None


def recovery_details(mode: str) -> dict[str, str]:
    return {"mode": mode, "guidance": completion_recovery_guidance(mode)}


def _multi_apps_completion_tools(
    state: Any,
    phase: str,
) -> list[dict[str, Any]] | None:
    """Expose only discovered owning routes during Multi-Apps recovery.

    The facade has no native ``spreadsheet.save`` or ``inspect_current``
    actions.  Completion recovery must therefore keep the model on the single
    ``adapter.call`` surface and constrain it to route pairs that a prior
    model-authored catalog search actually returned.  When the required route
    has not been discovered yet, the only useful next choice is a bounded
    ``tools_search`` (plus ``fail_task``); no downstream action is synthesized.
    """
    _successful, mutations, _missing, _required = collect_initial_completion_evidence(
        state,
        None,
        is_read_only_action=action_is_read_only,
        is_save_action=action_is_save,
        relevance_score=action_relevance_score,
        required_mutations=(),
    )
    if not mutations:
        return None
    mutation_domain, _mutation_action, _arguments = effective_canonical_action(
        mutations[-1], state.domain
    )
    presentation_status = cross_app_presentation_completion_status(state, mutations, _successful)
    if presentation_status is not None and not all(presentation_status):
        mutation_domain = "libreoffice_impress"
    discovered = discovered_adapter_routes(state)
    if not discovered:
        discovered = []
    if phase in {STRICT_COMPLETION_PERSIST, STRICT_COMPLETION_PERSIST_AND_READBACK}:
        needs_persist = True
    else:
        needs_persist = False
    if phase in {
        STRICT_COMPLETION_READBACK,
        STRICT_COMPLETION_PERSIST,
        STRICT_COMPLETION_PERSIST_AND_READBACK,
    }:
        needs_readback = True
    else:
        needs_readback = False
    source_phase = source_execution_semantics.workflow_state(state).phase

    def route_allowed(route: tuple[str, str]) -> bool:
        domain, action = route
        source_capture_route = (
            source_phase == source_execution_semantics.CAPTURE_OUTPUT
            and route == ("os", "command.run")
        )
        source_readback_route = (
            source_phase == source_execution_semantics.READ_OUTPUT
            and route == ("vs_code", "file.read_text")
        )
        # Source editing, execution and text readback have different owners.
        # Keep those discovered workflow routes across the mutation boundary.
        if (needs_persist and source_capture_route) or (
            needs_readback and source_readback_route
        ):
            return True
        if domain != mutation_domain:
            return False
        return (needs_persist and action_is_save(action)) or (
            needs_readback and action_is_read_only(action)
        )

    routes = [route for route in discovered if route_allowed(route)]
    tools = build_tools(
        "multi_apps",
        ["adapter.call"] if routes else [],
        include_gui=False,
        include_control_tools=True,
        strict_generic=True,
    )
    if routes:
        tools = constrain_adapter_call_routes(tools, routes)
        adapter_call_name = tool_name("adapter.call")
        for tool in tools:
            function = tool.get("function")
            if isinstance(function, dict) and function.get("name") == adapter_call_name:
                function["description"] += (
                    " Completion recovery is limited to the discovered persistence/read-back "
                    "route(s); select one complete downstream call with unchanged arguments."
                )
                break
    return [
        tool
        for tool in tools
        if isinstance(tool.get("function"), dict)
        and tool["function"].get("name")
        in {tool_name("adapter.call"), "tools_search", "fail_task"}
    ]


def completion_rejection_error(
    gate: dict[str, Any],
    structural_gate: dict[str, Any],
    claim_errors: Iterable[str] = (),
    semantic_claim_errors: Iterable[str] = (),
) -> dict[str, Any]:
    structural_missing = structural_gate["missing"]
    claim_errors = [
        *claim_errors,
        *(item for item in gate["missing"] if item not in structural_missing),
    ]
    mode = classify_completion_recovery(
        structural_missing, claim_errors, list(semantic_claim_errors)
    )
    return {
        "status": "rejected",
        "executed": False,
        "passed": False,
        "missing": gate["missing"],
        "recovery": recovery_details(mode),
    }


def completion_parse_error(
    structural_gate: dict[str, Any], error: Exception
) -> dict[str, Any]:
    diagnostic = f"completion arguments could not be parsed: {error}"
    return completion_rejection_error(
        {"passed": False, "missing": [diagnostic]},
        structural_gate,
        [diagnostic],
    )


def readback_recovery_tools(
    domain: str,
    mode: str | None,
    tools: list[dict[str, Any]],
    *,
    is_read_only_action: Callable[[str], bool],
) -> list[dict[str, Any]] | None:
    if mode != COMPLETION_RECOVERY_READBACK_ONLY:
        return None

    def allowed(tool: dict[str, Any]) -> bool:
        name = tool["function"]["name"]
        action = action_from_tool_name(domain, name)
        return name == "fail_task" or (
            action is not None and is_read_only_action(action)
        )

    restricted = [tool for tool in tools if allowed(tool)]
    if not any(
        action_from_tool_name(domain, tool["function"]["name"]) for tool in restricted
    ):
        fallback_actions = [
            action
            for action in INSPECT_ACTIONS.get(domain, ())
            if action not in FORBIDDEN_DATASET_ACTIONS
        ]
        restricted = [
            tool
            for tool in build_tools(domain, fallback_actions, include_gui=False)
            if allowed(tool)
        ]
    if not any(tool["function"]["name"] == "fail_task" for tool in restricted):
        restricted.extend(
            tool
            for tool in build_tools(domain, [], include_gui=False)
            if tool["function"]["name"] == "fail_task"
        )
    for tool in restricted:
        if tool["function"]["name"] != "fail_task":
            tool["function"]["description"] += (
                " Completion recovery is read-only: inspect the final state without repeating the "
                "successful mutation."
            )
    return restricted


def proactive_completion_tools(
    domain: str,
    phase: str | None,
    tools: list[dict[str, Any]],
    *,
    is_read_only_action: Callable[[str], bool],
) -> list[dict[str, Any]] | None:
    """Restrict a successful task to persistence and structural confirmation."""
    if phase == STRICT_COMPLETION_READBACK:
        inspect_actions = set(INSPECT_ACTIONS.get(domain, ()))
        tools = [
            tool
            for tool in tools
            if tool["function"]["name"] == "fail_task"
            or (
                (action := action_from_tool_name(domain, tool["function"]["name"]))
                is not None
                and (
                    action in inspect_actions
                    or (domain == "multi_apps" and is_read_only_action(action))
                )
            )
        ]
        return readback_recovery_tools(
            domain,
            COMPLETION_RECOVERY_READBACK_ONLY,
            tools,
            is_read_only_action=is_read_only_action,
        )
    if phase not in {
        STRICT_COMPLETION_PERSIST,
        STRICT_COMPLETION_PERSIST_AND_READBACK,
    }:
        return None

    def allowed(tool: dict[str, Any]) -> bool:
        name = tool["function"]["name"]
        action = action_from_tool_name(domain, name)
        if name == "fail_task":
            return True
        if action in SAVE_ACTIONS.get(domain, ()) or (
            domain == "multi_apps"
            and action is not None
            and action.endswith((".save", ".export"))
        ):
            return True
        return bool(
            action is not None
            and (
                action in INSPECT_ACTIONS.get(domain, ())
                or (domain == "multi_apps" and is_read_only_action(action))
            )
        )

    restricted = [tool for tool in tools if allowed(tool)]
    if not any(
        (action := action_from_tool_name(domain, tool["function"]["name"]))
        in SAVE_ACTIONS.get(domain, ())
        or (
            domain == "multi_apps"
            and action is not None
            and action.endswith((".save", ".export"))
        )
        for tool in restricted
    ) or (
        INSPECT_ACTIONS.get(domain)
        and not any(
            action_from_tool_name(domain, tool["function"]["name"])
            in INSPECT_ACTIONS[domain]
            for tool in restricted
        )
    ):
        # Persistence wording may also require a post-save inspection. Keep
        # reads available; the unchanged completion gate checks the evidence.
        fallback_actions = [
            *SAVE_ACTIONS.get(domain, ()),
            *INSPECT_ACTIONS.get(domain, ()),
        ]
        restricted = [
            tool
            for tool in build_tools(
                domain,
                fallback_actions,
                include_gui=False,
                strict_generic=True,
            )
            if allowed(tool)
        ]
    for tool in restricted:
        name = tool["function"]["name"]
        action = action_from_tool_name(domain, name)
        if action in SAVE_ACTIONS.get(domain, ()) or (
            domain == "multi_apps"
            and action is not None
            and action.endswith((".save", ".export"))
        ):
            tool["function"]["description"] += (
                " Persist the completed mutation now; do not repeat the mutation or "
                "invent a different output format."
            )
        elif action is not None and is_read_only_action(action):
            tool["function"]["description"] += (
                " Inspect only to confirm the completed mutation; do not repeat it."
            )
    return restricted


def strict_proactive_completion_tools(
    state: Any,
    gate: dict[str, Any],
    instruction_actions: Callable[[str, str], Iterable[str]],
    legacy_actions: Iterable[str],
    is_read_only_action: Callable[[str], bool],
    selected_actions: Callable[[Any], list[str]],
    semantic_action_equivalents: Callable[[Any], dict[str, set[str]]] | None = None,
) -> list[dict[str, Any]] | None:
    """Build the proactive strict completion surface outside the Runtime."""
    # Successful calls do not prove task completion. Only the model's rejected
    # claim starts closing work; a later content change reopens normal tools.
    for event in reversed(state.events):
        kind = event.proposed.get("kind")
        if (
            kind == "completion"
            and not event.executed
            and isinstance(event.error, dict)
            and event.error.get("status") == "rejected"
        ):
            break
        if event.executed and kind == "gui":
            return None
        if event.executed and kind == "adapter":
            _domain, action, arguments = effective_canonical_action(event, state.domain)
            if (
                not is_read_only_action(action)
                and not action_is_save(action)
                and not command_is_read_only(action, arguments)
            ):
                return None
    else:
        return None

    phase = strict_completion_phase(
        state,
        gate,
        instruction_actions=instruction_actions,
        legacy_actions=legacy_actions,
        is_read_only_action=is_read_only_action,
        is_save_action=action_is_save,
        relevance_score=action_relevance_score,
        semantic_action_equivalents=semantic_action_equivalents,
    )
    if phase == STRICT_COMPLETION_DONE:
        # A structural heuristic may authorize a completion claim, but it must
        # never decide that the model has no remaining work. Returning None
        # preserves the normal model-selected inspection and mutation surface.
        return None
    if phase is None:
        return None
    if state.domain == "multi_apps":
        tools = _multi_apps_completion_tools(state, phase)
    else:
        selected = list(selected_actions(state))
        tools = proactive_completion_tools(
            state.domain,
            phase,
            build_tools(
                state.domain,
                list(dict.fromkeys(selected)),
                include_gui=False,
                strict_generic=True,
            ),
            is_read_only_action=is_read_only_action,
        )
    # Later saves/reads can change what is missing without another rejected claim.
    # Explain the same current requirements that selected this recovery surface.
    if gate.get("missing"):
        guidance = " Current completion requirements: " + "; ".join(gate["missing"])
        for tool in tools or []:
            if tool["function"]["name"] != "fail_task":
                tool["function"]["description"] += guidance
    return tools
