from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from integrations.lite_agent.completion_policy import (
    action_is_read_only,
)
from integrations.lite_agent.state_model import ExecutionEvent


OFFICE_DOMAINS = frozenset(
    {"libreoffice_calc", "libreoffice_impress", "libreoffice_writer"}
)
CONNECTION_LOSS_CODES = frozenset(
    {"LIBREOFFICE_NOT_READY", "UNO_CONNECT_FAILED", "UNO_CONNECTION_LOST"}
)
CONNECTION_LOSS_MARKERS = (
    "binary urp bridge disposed",
    "binary urp bridge already disposed",
    "disposed during call",
    "uno connection lost",
    "failed to connect to libreoffice",
)
RECOVERY_SAFE_SETUP_TYPES = frozenset({"open", "sleep", "activate_window"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _walk_values(value: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield None, item
            yield from _walk_values(item)
    else:
        yield None, value


def connection_loss_evidence(error: Any) -> dict[str, Any] | None:
    codes: set[str] = set()
    strings: list[str] = []
    for key, value in _walk_values(error):
        if key == "code" and isinstance(value, str):
            codes.add(value.upper())
        if isinstance(value, str):
            strings.append(value)
    matching_codes = sorted(codes.intersection(CONNECTION_LOSS_CODES))
    combined = "\n".join(strings).casefold()
    matching_markers = [
        marker for marker in CONNECTION_LOSS_MARKERS if marker in combined
    ]
    if not matching_codes and not matching_markers:
        return None
    return {"codes": matching_codes, "markers": matching_markers}


def potentially_mutating_call_before(events: Iterable[ExecutionEvent]) -> bool:
    for event in events:
        kind = event.proposed.get("kind")
        if kind == "gui" and event.validated:
            return True
        if kind != "adapter":
            continue
        action = str(event.proposed.get("action", ""))
        if event.validated and action and not action_is_read_only(action):
            return True
    return False


@dataclass(frozen=True)
class RecoveryDecision:
    eligible: bool
    reason: str
    evidence: dict[str, Any] | None = None


def recovery_decision(
    *,
    domain: str,
    events: list[ExecutionEvent],
    recoveries_attempted: int,
) -> RecoveryDecision:
    if domain not in OFFICE_DOMAINS:
        return RecoveryDecision(False, "non_office_domain")
    if recoveries_attempted:
        return RecoveryDecision(False, "episode_recovery_already_attempted")
    if not events:
        return RecoveryDecision(False, "no_failed_event")
    trigger = events[-1]
    if trigger.executed or trigger.proposed.get("kind") != "adapter":
        return RecoveryDecision(False, "latest_event_is_not_a_failed_adapter_call")
    if not trigger.validated:
        return RecoveryDecision(False, "failed_trigger_was_not_validated")
    evidence = connection_loss_evidence(trigger.error)
    if evidence is None:
        return RecoveryDecision(False, "no_explicit_connection_loss_evidence")
    action = str(trigger.proposed.get("action", ""))
    if not action or not action_is_read_only(action):
        return RecoveryDecision(False, "failed_trigger_is_not_read_only")
    if potentially_mutating_call_before(events[:-1]):
        return RecoveryDecision(False, "potential_mutation_precedes_connection_loss")
    return RecoveryDecision(True, "pre_mutation_office_connection_loss", evidence)


def setup_replay_steps(setup_steps: Any) -> list[dict[str, Any]]:
    if not isinstance(setup_steps, list):
        return []
    first_open = next(
        (
            index
            for index, step in enumerate(setup_steps)
            if isinstance(step, dict) and step.get("type") == "open"
        ),
        None,
    )
    if first_open is None:
        return []
    return [dict(step) for step in setup_steps[first_open:] if isinstance(step, dict)]


def replay_office_setup(
    *,
    setup_controller: Any,
    setup_steps: Any,
    use_proxy: bool,
    allowed_step_types: frozenset[str] | None = None,
) -> dict[str, Any]:
    steps = setup_replay_steps(setup_steps)
    step_types = [str(step.get("type", "")) for step in steps]
    unsupported = (
        sorted(
            {
                step_type
                for step_type in step_types
                if step_type not in allowed_step_types
            }
        )
        if allowed_step_types is not None
        else []
    )
    if unsupported:
        raise RuntimeError(
            "Office recovery setup suffix contains unsupported step types: "
            + ", ".join(unsupported)
        )
    if steps and not setup_controller.setup(steps, use_proxy):
        raise RuntimeError("failed to restore Office setup after lifecycle recovery")
    return {
        "step_count": len(steps),
        "step_types": step_types,
        "replayed": bool(steps),
    }


def _post_lifecycle(
    *,
    adapter_url: str,
    endpoint: str,
    timeout_ms: int,
    attempts: int,
    post: Callable[..., Any],
) -> dict[str, Any]:
    url = adapter_url.rstrip("/") + endpoint
    failures: list[dict[str, Any]] = []
    for attempt in range(1, attempts + 1):
        try:
            response = post(
                url,
                json={"timeout_ms": timeout_ms},
                timeout=max(15.0, timeout_ms / 1000 + 10),
            )
            payload = response.json()
            if not response.ok or not isinstance(payload, dict):
                raise RuntimeError(
                    f"HTTP {getattr(response, 'status_code', 'unknown')}: {payload!r}"
                )
            if payload.get("status") != "ok":
                raise RuntimeError(str(payload))
            return {
                "status": "ok",
                "attempt": attempt,
                "endpoint": endpoint,
                "adapter_status": payload.get("status"),
            }
        except Exception as exc:
            failures.append(
                {
                    "attempt": attempt,
                    "type": type(exc).__name__,
                    "detail": str(exc)[:1000],
                }
            )
            if attempt < attempts:
                time.sleep(min(2 * attempt, 6))
    return {"status": "error", "endpoint": endpoint, "failures": failures}


def recover_office_episode(
    *,
    domain: str,
    adapter_url: str,
    setup_steps: Any,
    setup_controller: Any,
    use_proxy: bool,
    trigger_event: ExecutionEvent,
    recovery_ordinal: int,
    post: Callable[..., Any] = requests.post,
) -> dict[str, Any]:
    error_json = json.dumps(
        trigger_event.error,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    trace: dict[str, Any] = {
        "schema_version": 1,
        "timestamp_utc": utc_now(),
        "domain": domain,
        "trigger_step": trigger_event.step,
        "trigger_action": str(trigger_event.proposed.get("action", "")),
        "trigger_error_sha256": hashlib.sha256(error_json).hexdigest(),
        "recovery_ordinal": recovery_ordinal,
        "task_identity_used": False,
        "evaluator_or_golden_used": False,
        "model_action_replayed": False,
        "model_arguments_rewritten": False,
        "model_arguments_injected": False,
    }
    shutdown = _post_lifecycle(
        adapter_url=adapter_url,
        endpoint="/v1/shutdown",
        timeout_ms=20_000,
        attempts=1,
        post=post,
    )
    trace["shutdown"] = shutdown
    prepare = _post_lifecycle(
        adapter_url=adapter_url,
        endpoint="/v1/prepare",
        timeout_ms=60_000,
        attempts=4,
        post=post,
    )
    trace["prepare"] = prepare
    if prepare["status"] != "ok":
        trace["status"] = "failed"
        trace["failure_stage"] = "prepare"
        return trace
    try:
        setup_replay = replay_office_setup(
            setup_controller=setup_controller,
            setup_steps=setup_steps,
            use_proxy=use_proxy,
            allowed_step_types=RECOVERY_SAFE_SETUP_TYPES,
        )
        trace["setup_replay"] = setup_replay
        if not setup_replay["replayed"]:
            trace["status"] = "failed"
            trace["failure_stage"] = "setup_replay_no_open_step"
            return trace
    except Exception as exc:
        trace["status"] = "failed"
        trace["failure_stage"] = "setup_replay"
        trace["failure"] = {"type": type(exc).__name__, "detail": str(exc)}
        return trace
    trace["status"] = "recovered"
    return trace


def model_visible_recovery_status(trace: dict[str, Any]) -> dict[str, Any]:
    recovered = trace.get("status") == "recovered"
    return {
        "status": "recovered" if recovered else "failed",
        "failed_action_executed": False,
        "failed_action_replayed": False,
        "guidance": (
            "The Office application connection was restored. The failed action was "
            "not executed or retried; select the next action from the current tool surface."
            if recovered
            else "The Office application connection could not be restored."
        ),
    }
