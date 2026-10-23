from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .errors import AdapterError
from .route_utils import is_route


ADAPTER_URLS = {
    "libreoffice_calc": "http://127.0.0.1:8765",
    "libreoffice_impress": "http://127.0.0.1:8766",
    "chrome": "http://127.0.0.1:8767",
    "gimp": "http://127.0.0.1:8768",
    "os": "http://127.0.0.1:8769",
    "libreoffice_writer": "http://127.0.0.1:8770",
    "vs_code": "http://127.0.0.1:8771",
    "vlc": "http://127.0.0.1:8772",
    "thunderbird": "http://127.0.0.1:8773",
}
ADAPTER_MAX_TIMEOUT_MS = {
    "libreoffice_calc": 120_000,
    "libreoffice_impress": 120_000,
    "chrome": 120_000,
    "gimp": 180_000,
    "libreoffice_writer": 180_000,
    "os": 900_000,
    "vs_code": 900_000,
    "vlc": 900_000,
    "thunderbird": 900_000,
}
FORBIDDEN_DATASET_ACTIONS = {
    "task.execute",
    "task.inspect",
    "artifact.materialize",
    "assessment.grade_multiple_choice_documents",
}


class MultiAppsActions:
    @staticmethod
    def _effective_downstream_request(
        params: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
        adapter = params.get("adapter")
        action = params.get("action")
        if not isinstance(adapter, str) or not adapter.strip():
            raise AdapterError(
                "INVALID_REQUEST", "params.adapter must be a non-empty string"
            )
        if not isinstance(action, str) or not action.strip():
            raise AdapterError(
                "INVALID_REQUEST", "params.action must be a non-empty string"
            )
        raw_payload = params.get("payload", {})
        if not isinstance(raw_payload, dict):
            raise AdapterError("INVALID_REQUEST", "params.payload must be an object")
        payload = dict(raw_payload)
        payload["adapter"] = adapter
        payload["action"] = action
        action_params = payload.get("params", {})
        if action in {"range.read", "range.write"} and isinstance(action_params, dict):
            action_params = dict(action_params)
            if "sheet" not in action_params and "sheet_name" in action_params:
                action_params["sheet"] = action_params.pop("sheet_name")
            if "range" not in action_params and "used_range_a1" in action_params:
                action_params["range"] = action_params.pop("used_range_a1")
            action_params.pop("format", None)
            if action == "range.write":
                values = action_params.get("values")
                target = action_params.get("range")
                if (
                    isinstance(values, list)
                    and len(values) > 1
                    and isinstance(values[0], list)
                    and values[0]
                    and all(value in (None, "") for value in values[0])
                ):
                    raise AdapterError(
                        "INVALID_REQUEST",
                        "append range begins with an empty row; target only new records and provide one non-empty values row per record",
                        {"conflicting_field": "values[0]", "corrective_action": "remove the leading blank row"},
                    )
                if (
                    isinstance(values, list)
                    and len(values) > 1
                    and isinstance(target, str)
                ):
                    match = re.fullmatch(
                        r"(\$?[A-Za-z]+)(\$?[0-9]+):(\$?[A-Za-z]+)(\$?[0-9]+)",
                        target,
                    )
                    if match:
                        start_row = int(match.group(2).lstrip("$"))
                        end_row = int(match.group(4).lstrip("$"))
                        if end_row < start_row or end_row == start_row:
                            action_params["range"] = (
                                f"{match.group(1)}{match.group(2)}:"
                                f"{match.group(3)}{start_row + len(values) - 1}"
                            )
            payload["params"] = action_params
        if not isinstance(action_params, dict):
            raise AdapterError(
                "INVALID_REQUEST", "params.payload.params must be an object"
            )
        return adapter, action, action_params, payload

    @staticmethod
    def _enforce_downstream_policy(
        adapter: str,
        action: str,
        params: dict[str, Any],
    ) -> None:
        if is_route(action, FORBIDDEN_DATASET_ACTIONS):
            raise AdapterError(
                "POLICY_VIOLATION",
                f"downstream action {action} is disabled in generic-only mode",
                {"adapter": adapter, "action": action},
                403,
            )
        if (
            is_route(adapter, ("vlc",))
            and is_route(action, ("media.extract_audio",))
            and "profile" in params
        ):
            raise AdapterError(
                "POLICY_VIOLATION",
                "dataset-specific VLC profiles are disabled in generic-only mode",
                {"adapter": adapter, "action": action},
                403,
            )

    def call_adapter(
        self, params: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        adapter, action, action_params, payload = self._effective_downstream_request(
            params
        )
        self._enforce_downstream_policy(adapter, action, action_params)
        base_url = ADAPTER_URLS.get(adapter)
        if base_url is None:
            raise AdapterError(
                "INVALID_ADAPTER", "unknown downstream Adapter", {"adapter": adapter}
            )
        requested_timeout_ms = payload.get("timeout_ms")
        payload["timeout_ms"] = min(
            int(timeout_seconds * 1000),
            ADAPTER_MAX_TIMEOUT_MS[adapter],
            requested_timeout_ms
            if requested_timeout_ms is not None
            else ADAPTER_MAX_TIMEOUT_MS[adapter],
        )
        timeout_budget = {
            "requested_ms": requested_timeout_ms,
            "effective_ms": payload["timeout_ms"],
        }
        request = Request(
            base_url + "/v1/actions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                downstream = json.load(response)
        except HTTPError as exc:
            try:
                details = json.loads(exc.read().decode())
            except Exception:
                details = {"status": exc.code, "reason": str(exc)}
            raise AdapterError(
                "DOWNSTREAM_FAILED",
                "downstream Adapter call failed",
                {"adapter": adapter, "response": details, "timeout_budget": timeout_budget},
                502,
            ) from exc
        except Exception as exc:
            raise AdapterError(
                "DOWNSTREAM_FAILED",
                "downstream Adapter call failed",
                {
                    "adapter": adapter,
                    "error": f"{type(exc).__name__}: {exc}",
                    "timeout_budget": timeout_budget,
                },
                502,
            ) from exc
        if downstream.get("status") != "ok":
            raise AdapterError(
                "DOWNSTREAM_FAILED",
                "downstream Adapter returned an error",
                {**downstream, "timeout_budget": timeout_budget},
                502,
            )
        return {
            "adapter": adapter,
            "action": action,
            "base_url": base_url,
            "timeout_budget": timeout_budget,
            "response": downstream,
        }

    def dispatch(
        self, action: str, params: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        if is_route(action, FORBIDDEN_DATASET_ACTIONS):
            raise AdapterError(
                "POLICY_VIOLATION",
                f"downstream action {action} is disabled in generic-only mode",
                {"action": action},
                403,
            )
        if action == "adapter.call":
            return self.call_adapter(params, timeout_seconds)
        raise AdapterError(
            "UNSUPPORTED_ACTION",
            "unsupported generic-only action",
            {"action": action},
            404,
        )
