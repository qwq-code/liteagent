from __future__ import annotations

from typing import Any
from uuid import uuid4

import requests


class MultiAppsAdapterClient:
    def __init__(self, base_url: str, timeout: float = 300) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        response = requests.get(self.base_url + "/health", timeout=10)
        response.raise_for_status()
        return response.json()

    def action(
        self, action: str, params: dict[str, Any], timeout_ms: int = 120_000
    ) -> dict[str, Any]:
        response = requests.post(
            self.base_url + "/v1/actions",
            json={
                "request_id": str(uuid4()),
                "adapter": "multi_apps",
                "action": action,
                "timeout_ms": timeout_ms,
                "params": params,
            },
            timeout=max(self.timeout, timeout_ms / 1000 + 10),
        )
        if response.status_code >= 400:
            raise RuntimeError(response.json())
        return response.json()
