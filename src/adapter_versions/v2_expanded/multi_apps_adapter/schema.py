from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

from .errors import AdapterError
from .tool_manifest import DOWNSTREAM_ADAPTER_DOMAINS


ADAPTER_NAME = "multi_apps"
MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 900_000
DEFAULT_TIMEOUT_MS = 120_000
ACTIONS = frozenset({"adapter.call"})


@dataclass(frozen=True)
class ActionRequest:
    request_id: str
    adapter: str
    action: str
    timeout_ms: int
    params: dict[str, Any]
    verify: list[dict[str, Any]]


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise AdapterError("INVALID_REQUEST", f"{field} must be an object")
    return dict(value)


def _string(data: Mapping[str, Any], field: str, prefix: str = "params") -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.{field} must be a non-empty string"
        )
    return value


def _verification(value: Any) -> list[dict[str, Any]]:
    if value is None or value == []:
        return []
    raise AdapterError(
        "INVALID_REQUEST",
        "top-level Multi-Apps verification is unavailable; use payload.verify on the owning Adapter",
    )


def validate_action_params(action: str, params: Mapping[str, Any]) -> None:
    if action not in ACTIONS:
        raise AdapterError(
            "UNSUPPORTED_ACTION",
            "unsupported generic-only Multi-Apps action",
            {"action": action},
            404,
        )

    unexpected = sorted(set(params) - {"adapter", "action", "payload"})
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            "adapter.call contains unsupported fields",
            {"unsupported_fields": unexpected},
        )
    adapter = _string(params, "adapter")
    if adapter not in DOWNSTREAM_ADAPTER_DOMAINS:
        raise AdapterError(
            "INVALID_ADAPTER",
            "unknown downstream Adapter",
            {"adapter": adapter},
        )
    _string(params, "action")

    if "payload" not in params:
        return
    payload = _mapping(params["payload"], "params.payload")
    unexpected_payload = sorted(
        set(payload) - {"params", "target", "document", "verify", "timeout_ms"}
    )
    if unexpected_payload:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.payload contains unsupported fields",
            {"unsupported_fields": unexpected_payload},
        )
    for field in ("params", "target", "document"):
        if field in payload:
            _mapping(payload[field], f"params.payload.{field}")
    if "verify" in payload:
        verify = payload["verify"]
        if not isinstance(verify, list) or any(
            not isinstance(check, Mapping) for check in verify
        ):
            raise AdapterError(
                "INVALID_REQUEST", "params.payload.verify must be an object array"
            )
    if "timeout_ms" in payload:
        timeout_ms = payload["timeout_ms"]
        if (
            isinstance(timeout_ms, bool)
            or not isinstance(timeout_ms, int)
            or not MIN_TIMEOUT_MS <= timeout_ms <= MAX_TIMEOUT_MS
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.payload.timeout_ms must be from {MIN_TIMEOUT_MS} to {MAX_TIMEOUT_MS}",
            )


def parse_action_request(raw: Any) -> ActionRequest:
    data = _mapping(raw, "request")
    request_id = data.get("request_id") or str(uuid4())
    if not isinstance(request_id, str) or not request_id.strip():
        raise AdapterError("INVALID_REQUEST", "request_id must be a non-empty string")
    adapter = data.get("adapter", ADAPTER_NAME)
    if adapter != ADAPTER_NAME:
        raise AdapterError("INVALID_REQUEST", f"adapter must be {ADAPTER_NAME}")
    action = data.get("action")
    if action not in ACTIONS:
        raise AdapterError(
            "UNSUPPORTED_ACTION",
            "unsupported generic-only Multi-Apps action",
            {"action": action},
            404,
        )
    timeout_ms = data.get("timeout_ms", DEFAULT_TIMEOUT_MS)
    if (
        isinstance(timeout_ms, bool)
        or not isinstance(timeout_ms, int)
        or not MIN_TIMEOUT_MS <= timeout_ms <= MAX_TIMEOUT_MS
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            f"timeout_ms must be from {MIN_TIMEOUT_MS} to {MAX_TIMEOUT_MS}",
        )
    params = _mapping(data.get("params"), "params")
    validate_action_params(action, params)
    return ActionRequest(
        request_id=request_id,
        adapter=adapter,
        action=action,
        timeout_ms=timeout_ms,
        params=params,
        verify=_verification(data.get("verify")),
    )
