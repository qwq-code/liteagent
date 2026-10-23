from __future__ import annotations

from typing import Any


class AdapterError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        details: Any = None,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.status_code = status_code

    def payload(self, request_id: str | None = None) -> dict[str, Any]:
        return {
            "status": "error",
            "request_id": request_id,
            "error_code": self.code,
            "error": self.message,
            "details": self.details,
        }
