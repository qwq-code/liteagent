from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from multi_apps_adapter.route_utils import is_route

from .adapter_results import (
    adapter_context_hint,
    compact_adapter_body,
    utc_now,
)
from .tool_catalog import (
    DIRECT_ACTION_SCHEMAS,
    FORBIDDEN_DATASET_ACTIONS,
)


def _split_argument_conversion(body: Any, *, forwarded: bool) -> tuple[Any, Any]:
    """Keep owner conversion provenance outside model feedback, without editing HTTP data."""
    paths = (
        (
            ("result", "response", "result"),
            ("details", "response", "error", "details"),
            ("details", "error", "details"),
        )
        if forwarded
        else (("result",), ("error", "details"))
    )
    for path in paths:
        owner_result = body
        for key in path:
            owner_result = owner_result.get(key) if isinstance(owner_result, dict) else None
        if not isinstance(owner_result, dict) or not isinstance(
            owner_result.get("argument_conversion"), dict
        ):
            continue
        feedback_body = deepcopy(body)
        feedback_result = feedback_body
        for key in path:
            feedback_result = feedback_result[key]
        return feedback_body, feedback_result.pop("argument_conversion")
    return body, None


class AdapterExecutor:
    """Send structured actions to guest Adapters under a fail-closed policy."""

    def __init__(
        self,
        adapter_urls: dict[str, str],
        trace_path: Path | None = None,
        *,
        allow_legacy_dataset_routes: bool = False,
        deadline_monotonic: float | None = None,
    ):
        if allow_legacy_dataset_routes:
            raise ValueError("legacy dataset routes are not available")
        self.adapter_urls = dict(adapter_urls)
        self.trace_path = trace_path
        self.deadline_monotonic = deadline_monotonic

    def _policy_error(
        self,
        domain: str,
        action: str,
        params: Any,
    ) -> dict[str, str] | None:
        if is_route(action, FORBIDDEN_DATASET_ACTIONS):
            if is_route(action, ("artifact.materialize",)):
                return {
                    "type": "AdapterPolicyViolation",
                    "code": "DATASET_MATERIALIZATION_DISABLED",
                    "detail": (
                        "artifact.materialize is disabled by the generic-only Adapter "
                        "execution policy"
                    ),
                }
            return {
                "type": "AdapterPolicyViolation",
                "code": "TASK_ROUTE_DISABLED",
                "detail": (
                    f"{action} is disabled by the generic-only Adapter execution policy"
                ),
            }
        if (
            is_route(domain, ("multi_apps",))
            and is_route(action, ("adapter.call",))
            and isinstance(params, dict)
        ):
            route_params = params
            if (
                "adapter" not in route_params
                and "action" not in route_params
                and isinstance(route_params.get("params"), dict)
            ):
                route_params = route_params["params"]
            payload = route_params.get("payload")
            nested_payload = payload if isinstance(payload, dict) else {}
            nested_action = nested_payload.get("action", route_params.get("action"))
            nested_domain = nested_payload.get("adapter", route_params.get("adapter"))
            nested_params = nested_payload.get("params")
            if not isinstance(nested_params, dict):
                nested_params = {}
            if is_route(nested_action, FORBIDDEN_DATASET_ACTIONS):
                return {
                    "type": "AdapterPolicyViolation",
                    "code": "NESTED_LEGACY_ACTION_DISABLED",
                    "detail": (
                        f"multi_apps.adapter.call cannot invoke {nested_action} under "
                        "the generic-only Adapter execution policy"
                    ),
                }
            if (
                is_route(nested_domain, ("vlc",))
                and is_route(nested_action, ("media.extract_audio",))
                and "profile" in nested_params
            ):
                return {
                    "type": "AdapterPolicyViolation",
                    "code": "NESTED_DATASET_PROFILE_DISABLED",
                    "detail": (
                        "multi_apps.adapter.call cannot invoke a dataset-specific VLC "
                        "profile under the generic-only Adapter execution policy"
                    ),
                }
        if (
            is_route(domain, ("vlc",))
            and is_route(action, ("media.extract_audio",))
            and isinstance(params, dict)
            and "profile" in params
        ):
            return {
                "type": "AdapterPolicyViolation",
                "code": "DATASET_PROFILE_DISABLED",
                "detail": (
                    "dataset-specific media extraction profiles are disabled by the "
                    "generic-only Adapter execution policy"
                ),
            }
        return None

    def _finish_trace(
        self,
        trace: dict[str, Any],
        result: dict[str, Any],
        started: float,
    ) -> dict[str, Any]:
        trace.update(result)
        trace["duration_seconds"] = round(time.monotonic() - started, 3)
        if self.trace_path:
            self.trace_path.parent.mkdir(parents=True, exist_ok=True)
            with self.trace_path.open("a", encoding="utf-8") as output:
                output.write(json.dumps(trace, ensure_ascii=False, default=str) + "\n")
        return result

    def execute(
        self,
        domain: str,
        action: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        request_id = str(uuid4())
        timeout_ms = int(arguments.get("timeout_ms", 120_000))
        downstream_payload = arguments.get("payload")
        # OCR batches can exceed the generic transport default on large receipts.
        if (
            domain == "multi_apps"
            and action == "adapter.call"
            and arguments.get("action") == "image.extract_text_batch"
            and (
                not isinstance(downstream_payload, dict)
                or "timeout_ms" not in downstream_payload
            )
        ):
            timeout_ms = max(timeout_ms, 300_000)
        if domain == "multi_apps" and action == "adapter.call":
            downstream_payload = arguments.get("payload", downstream_payload)
            if isinstance(downstream_payload, dict):
                selected_timeout_ms = downstream_payload.get("timeout_ms")
                if isinstance(selected_timeout_ms, int):
                    timeout_ms = max(timeout_ms, selected_timeout_ms)
        direct_schema = DIRECT_ACTION_SCHEMAS.get(domain, {}).get(action)
        if direct_schema is not None:
            params: Any = dict(arguments)
            target: Any = {}
            document: Any = {}
            verify: Any = []
        else:
            params = arguments.get("params", {})
            target = arguments.get("target", {})
            document = arguments.get("document", {})
            verify = arguments.get("verify", [])
        payload = {
            "request_id": request_id,
            "adapter": domain,
            "action": action,
            "timeout_ms": timeout_ms,
            "params": params,
            "target": target,
            "document": document,
            "verify": verify,
        }
        started = time.monotonic()
        trace = {
            **context,
            "request_id": request_id,
            "payload": payload,
            "policy_mode": "generic_only",
            "timestamp_utc": utc_now(),
        }

        if policy_error := self._policy_error(domain, action, params):
            return self._finish_trace(
                trace,
                {
                    "status": "error",
                    "executed": False,
                    "error": policy_error,
                },
                started,
            )

        http_timeout_seconds = max(15.0, timeout_ms / 1000 + 15)
        budget = {"requested_ms": timeout_ms, "effective_ms": timeout_ms}
        trace["timeout_budget"] = budget
        if self.deadline_monotonic is not None:
            remaining_seconds = self.deadline_monotonic - time.monotonic()
            budget["episode_remaining_seconds"] = remaining_seconds
            if remaining_seconds < 0.1:
                budget["effective_ms"] = 0
                return self._finish_trace(
                    trace,
                    {
                        "status": "error",
                        "executed": False,
                        "error": {
                            "type": "AgentDeadlineExceeded",
                            "detail": "episode budget expired before Adapter dispatch",
                        },
                    },
                    started,
                )
            # Operational envelope only; retain the model's original arguments.
            payload["timeout_ms"] = min(timeout_ms, int(remaining_seconds * 1000))
            budget["effective_ms"] = payload["timeout_ms"]
            http_timeout_seconds = min(http_timeout_seconds, remaining_seconds)
        budget["http_wait_seconds"] = http_timeout_seconds

        try:
            response = requests.post(
                self.adapter_urls[domain].rstrip("/") + "/v1/actions",
                json=payload,
                timeout=http_timeout_seconds,
            )
            try:
                body = response.json()
            except ValueError:
                body = {"raw_text": response.text[:4000]}
            feedback_body, argument_conversion = _split_argument_conversion(
                body, forwarded=domain == "multi_apps" and action == "adapter.call"
            )
            if argument_conversion is not None:
                trace["argument_conversion"] = argument_conversion
            body_status = body.get("status") if isinstance(body, dict) else None
            executed = bool(response.ok and body_status == "ok")
            context_hint = (
                adapter_context_hint(domain, action, feedback_body) if executed else None
            )
            compact_body = compact_adapter_body(feedback_body)
            result_payload = (
                {"context_hint": context_hint, "adapter_response": compact_body}
                if context_hint is not None
                else compact_body
            )
            result = {
                "status": "ok" if executed else "error",
                "executed": executed,
                "http_status": response.status_code,
                "result": result_payload,
            }
            if not executed:
                # Keep native causes structured until the model-context sanitizer
                # and error-priority fitter apply their existing bounded projection.
                # A legacy JSON-prefix preview is discarded there, losing the cause.
                result["error"] = feedback_body
        except Exception as exc:
            result = {
                "status": "error",
                "executed": False,
                "error": {"type": type(exc).__name__, "detail": str(exc)},
            }
        return self._finish_trace(trace, result, started)
