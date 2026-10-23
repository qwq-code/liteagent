from __future__ import annotations

from typing import Any


class AdapterError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: Any = None,
        http_status: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.http_status = http_status


def error_payload(error: AdapterError) -> dict[str, Any]:
    return {
        "code": error.code,
        "message": error.message,
        "details": error.details,
    }
