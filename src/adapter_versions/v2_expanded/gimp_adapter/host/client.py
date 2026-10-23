from __future__ import annotations

from typing import Any
from uuid import uuid4

import requests

from gimp_adapter.schema import ADAPTER_NAME


class GimpAdapterClient:
    def __init__(self, base_url: str, timeout: float = 50.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        response = requests.get(f"{self.base_url}/health", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def prepare(self, timeout_ms: int = 30_000) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/v1/prepare",
            json={"timeout_ms": timeout_ms},
            timeout=max(self.timeout, timeout_ms / 1000 + 5),
        )
        response.raise_for_status()
        return response.json()

    def shutdown(self, timeout_ms: int = 10_000) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/v1/shutdown",
            json={"timeout_ms": timeout_ms},
            timeout=max(self.timeout, timeout_ms / 1000 + 5),
        )
        response.raise_for_status()
        return response.json()

    def action(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        target: dict[str, Any] | None = None,
        verify: list[dict[str, Any]] | None = None,
        timeout_ms: int = 45_000,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/v1/actions",
            json={
                "request_id": request_id or str(uuid4()),
                "adapter": ADAPTER_NAME,
                "action": action,
                "timeout_ms": timeout_ms,
                "target": target or {},
                "params": params or {},
                "verify": verify or [],
            },
            timeout=max(self.timeout, timeout_ms / 1000 + 5),
        )
        if response.status_code >= 400:
            try:
                raise RuntimeError(response.json())
            except ValueError:
                response.raise_for_status()
        return response.json()
