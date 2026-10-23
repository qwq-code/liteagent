from __future__ import annotations

from typing import Any


DOWNSTREAM_ADAPTER_DOMAINS = (
    "libreoffice_calc",
    "libreoffice_impress",
    "chrome",
    "gimp",
    "os",
    "libreoffice_writer",
    "vs_code",
    "vlc",
    "thunderbird",
)


STRICT_ACTION_PARAM_SCHEMAS: dict[str, dict[str, Any]] = {
    "adapter.call": {
        "description": (
            "Call one model-selected public action on its owning application Adapter. "
            "Use the exact Adapter, action, and semantic arguments returned by tool search."
        ),
        "properties": {
            "adapter": {
                "type": "string",
                "enum": list(DOWNSTREAM_ADAPTER_DOMAINS),
                "description": "Owning downstream application Adapter returned by tool search.",
            },
            "action": {
                "type": "string",
                "minLength": 1,
                "description": "Exact downstream public action returned by tool search.",
            },
            "payload": {
                "type": "object",
                "description": (
                    "Downstream request fields; put action-specific arguments in payload.params."
                ),
                "properties": {
                    "params": {"type": "object"},
                    "target": {"type": "object"},
                    "document": {"type": "object"},
                    "verify": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "minimum": 100,
                        "maximum": 900_000,
                        "description": (
                            "Execution time limit in milliseconds (default 120000), subject "
                            "to the owning Adapter limit and remaining episode time. For a "
                            "longer operation, set e.g. 300000 here beside params. A timeout "
                            "can leave partial results; inspect current state before retrying."
                        ),
                    },
                },
                "additionalProperties": False,
            },
        },
        "required": ["adapter", "action"],
        "additionalProperties": False,
    }
}
