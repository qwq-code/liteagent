"""Strict generic-only completion evidence evaluation.

This module intentionally has no dependency on RuntimeState implementation
details beyond the public event/evidence methods used by the completion
contract.  Task-shaped completion predicates remain in the legacy Runtime
path and are never consulted by strict episodes.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any

from .completion_policy import (
    collect_initial_completion_evidence,
    command_is_read_only,
    completion_claim_contract_errors,
    completion_claim_contradictions,
    effective_adapter_action,
    requires_readback_action,
)


STRICT_COMPLETION_DONE = "done"
STRICT_COMPLETION_READBACK = "readback"
STRICT_COMPLETION_PERSIST = "persist"
STRICT_COMPLETION_PERSIST_AND_READBACK = "persist_and_readback"


def _normalized_requirement(value: Any) -> str:
    return str(value).casefold().replace("read-back", "read back")


def _requires_persistence(value: Any) -> bool:
    """Recognize an explicit save/persist command, not a passive saved-state mention."""
    normalized = _normalized_requirement(value)
    without_readback_prerequisites = re.sub(
        r"\bafter\s+(?:the\s+)?(?:latest\s+|final\s+|successful\s+)?"
        r"(?:mutation\s+and\s+)?(?:save|saving|persist(?:ence|ing)?)\b",
        "",
        normalized,
    )
    return bool(re.search(r"\b(?:save|persist)\b", without_readback_prerequisites))


def _requires_readback(value: Any) -> bool:
    return requires_readback_action(value)


def _semantic_mutation_actions(
    state: Any,
    *,
    instruction_actions: Callable[[str, str], Iterable[str]],
    legacy_actions: Iterable[str],
    is_read_only_action: Callable[[str], bool],
) -> set[str]:
    legacy = set(legacy_actions)
    return {
        action
        for action in instruction_actions(state.domain, state.instruction)
        if action not in legacy and not is_read_only_action(action)
    }


def _observed_mutation_actions(state: Any) -> set[str]:
    return {
        effective_adapter_action(event, state.domain)[1]
        for event in state.successful_adapter_events()
    }


def _missing_semantic_actions(
    semantic_actions: set[str],
    observed_actions: set[str],
    equivalents: dict[str, set[str]],
) -> set[str]:
    return {
        action
        for action in semantic_actions
        if action not in observed_actions
        and not observed_actions.intersection(equivalents.get(action, set()))
    }


def _audited_gui_completion_available(
    state: Any,
    is_read_only_action: Callable[[str], bool],
    is_save_action: Callable[[str], bool],
) -> bool:
    if not getattr(state, "defer_terminal_audit", False) or getattr(
        state, "pending_model_audit", None
    ):
        return False
    for event in reversed(state.events):
        if not event.executed:
            continue
        proposed = event.proposed
        if proposed.get("kind") == "adapter":
            _domain, action, arguments = effective_adapter_action(event, state.domain)
            # Saving persists GUI work; exporting can replace it with another artifact.
            persist_only = is_save_action(action) and action.endswith(".save")
            if (
                not is_read_only_action(action)
                and not persist_only
                and not command_is_read_only(action, arguments)
            ):
                return False
        elif proposed.get("kind") == "gui":
            return bool(
                proposed.get("delegation") in {"planner_to_holo", "qwen_to_holo"}
                and event.validated
                and event.audit_completed
                and event.screenshot_after
                and isinstance(event.result, dict)
                and event.result.get("environment_acknowledged") is True
            )
    return False


def strict_completion_gate(
    state: Any,
    completion: dict[str, Any] | None,
    *,
    instruction_actions: Callable[[str, str], Iterable[str]],
    legacy_actions: Iterable[str],
    is_read_only_action: Callable[[str], bool],
    is_save_action: Callable[[str], bool],
    relevance_score: Callable[[str, str, str], int],
    semantic_requirement_errors: Callable[[Any], Iterable[str]] | None = None,
    semantic_action_equivalents: Callable[[Any], dict[str, set[str]]] | None = None,
) -> dict[str, Any]:
    """Apply generic mutation, persistence, and read-back evidence only."""
    # GUI outcomes are reviewed visually by the planner, not an invented API mutation.
    # Only an explicit claim enters the existing deferred terminal-audit path.
    if completion is not None and _audited_gui_completion_available(
        state, is_read_only_action, is_save_action
    ):
        missing = completion_claim_contract_errors(completion)
        missing.extend(completion_claim_contradictions(completion))
        return {
            "passed": not missing,
            "missing": missing,
            "evidence_source": "audited_holo_gui",
        }
    semantic_actions = _semantic_mutation_actions(
        state,
        instruction_actions=instruction_actions,
        legacy_actions=legacy_actions,
        is_read_only_action=is_read_only_action,
    )
    _successful, mutations, missing, _required_mutations = (
        collect_initial_completion_evidence(
            state,
            completion,
            is_read_only_action=is_read_only_action,
            is_save_action=is_save_action,
            relevance_score=relevance_score,
            required_mutations=semantic_actions,
        )
    )
    if semantic_actions:
        observed_actions = {
            effective_adapter_action(event, state.domain)[1] for event in mutations
        }
        equivalents = (
            semantic_action_equivalents(state)
            if semantic_action_equivalents is not None
            else {}
        )
        missing_actions = _missing_semantic_actions(
            semantic_actions, observed_actions, equivalents
        )
        if missing_actions:
            missing.append(
                "perform every instruction-relevant generic Adapter action; the public "
                f"actions {sorted(missing_actions)} have not succeeded"
            )
    if semantic_requirement_errors is not None:
        missing.extend(semantic_requirement_errors(state))
    return {"passed": not missing, "missing": list(dict.fromkeys(missing))}


def strict_completion_phase(
    state: Any,
    gate: dict[str, Any],
    *,
    instruction_actions: Callable[[str, str], Iterable[str]],
    legacy_actions: Iterable[str],
    is_read_only_action: Callable[[str], bool],
    is_save_action: Callable[[str], bool] | None = None,
    relevance_score: Callable[[str, str, str], int] | None = None,
    semantic_action_equivalents: Callable[[Any], dict[str, set[str]]] | None = None,
) -> str | None:
    """Select a proactive completion phase from public actions and real events."""
    semantic_actions = _semantic_mutation_actions(
        state,
        instruction_actions=instruction_actions,
        legacy_actions=legacy_actions,
        is_read_only_action=is_read_only_action,
    )
    observed_actions = _observed_mutation_actions(state)
    equivalents = (
        semantic_action_equivalents(state)
        if semantic_action_equivalents is not None
        else {}
    )
    if semantic_actions:
        if _missing_semantic_actions(semantic_actions, observed_actions, equivalents):
            return None
    else:
        # Some generic facades (notably ``multi_apps``) intentionally leave
        # instruction parsing open-ended.  Once a completion claim has been
        # rejected, retain the evidence collector's relevance-derived mutation
        # set so persistence/read-back recovery can still be bounded without
        # guessing a task-specific action sequence.
        rejected_completion = any(
            event.proposed.get("kind") == "completion"
            and not event.executed
            and isinstance(event.error, dict)
            and event.error.get("status") == "rejected"
            for event in state.events
        )
        if not rejected_completion:
            return None
        if is_save_action is None or relevance_score is None:
            # Keep direct callers of the historical helper source-compatible;
            # strict runtime callers pass the maintained callbacks explicitly.
            from .completion_policy import action_is_save
            from .tool_catalog import action_relevance_score

            is_save_action = action_is_save
            relevance_score = action_relevance_score
        _successful, relevant_mutations, _missing, _required = (
            collect_initial_completion_evidence(
                state,
                None,
                is_read_only_action=is_read_only_action,
                is_save_action=is_save_action,
                relevance_score=relevance_score,
                required_mutations=(),
            )
        )
        if not relevant_mutations:
            return None
    if gate.get("passed") is True:
        return STRICT_COMPLETION_DONE
    missing = gate.get("missing")
    if not isinstance(missing, list) or not missing:
        return None
    readback_missing = any(_requires_readback(item) for item in missing)
    persistence_missing = any(_requires_persistence(item) for item in missing)
    if not all(
        _requires_readback(item) or _requires_persistence(item) for item in missing
    ):
        return None
    if persistence_missing and readback_missing:
        return STRICT_COMPLETION_PERSIST_AND_READBACK
    if persistence_missing:
        return STRICT_COMPLETION_PERSIST
    if readback_missing:
        return STRICT_COMPLETION_READBACK
    return None
