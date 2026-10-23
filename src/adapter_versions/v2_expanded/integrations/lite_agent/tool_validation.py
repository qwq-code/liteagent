from __future__ import annotations

from typing import Any

import jsonschema


def validate_model_visible_tool_arguments(
    tools: list[dict[str, Any]],
    tool_name: str,
    arguments: dict[str, Any],
) -> None:
    """Enforce the exact schema exposed to the model for the current turn."""
    function = next(
        (
            item.get("function")
            for item in tools
            if isinstance(item, dict)
            and isinstance(item.get("function"), dict)
            and item["function"].get("name") == tool_name
        ),
        None,
    )
    if function is None:
        raise ValueError(f"tool is not exposed in the current turn: {tool_name}")
    schema = function.get("parameters")
    if not isinstance(schema, dict):
        raise ValueError(f"tool has no valid parameter schema: {tool_name}")
    try:
        jsonschema.validate(arguments, schema)
    except jsonschema.ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path)
        suffix = f" at {location}" if location else ""
        raise ValueError(
            f"arguments violate the current model-visible schema for {tool_name}{suffix}: "
            f"{exc.message}"
        ) from None
