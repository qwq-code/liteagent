from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AdapterError(Exception):
    code: str
    message: str
    details: Any = None
    http_status: int = 400

    def __str__(self) -> str:
        return self.message


def error_payload(error: AdapterError) -> dict[str, Any]:
    return {
        "code": error.code,
        "message": error.message,
        "details": error.details,
    }
