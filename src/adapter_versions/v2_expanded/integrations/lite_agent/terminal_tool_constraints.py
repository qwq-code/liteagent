"""Instruction-level schema constraints for terminal provenance."""

from __future__ import annotations

import copy
from typing import Any

from .completion_policy import requires_terminal_provenance


def constrain_terminal_provenance_tools(
    tools: list[dict[str, Any]], instruction: str
) -> list[dict[str, Any]]:
    """Require model-selected shell-history provenance when explicitly requested."""
    if not requires_terminal_provenance(instruction):
        return tools

    constrained = copy.deepcopy(tools)
    def constrain_schema(schema: Any) -> bool:
        if not isinstance(schema, dict):
            return False
        changed = False
        properties = schema.get("properties", {})
        provenance = properties.get("provenance")
        if isinstance(provenance, dict):
            allowed = provenance.get("enum")
            if not isinstance(allowed, list) or "shell_history" in allowed:
                provenance["enum"] = ["shell_history"]
                required = schema.setdefault("required", [])
                if "provenance" not in required:
                    required.append("provenance")
                changed = True
        # Follow schema locations, including routed payload.params, without
        # rewriting enum/const data or inventing arguments for the model.
        for child in properties.values():
            changed = constrain_schema(child) or changed
        for keyword in ("oneOf", "anyOf", "allOf"):
            for branch in schema.get(keyword, []):
                changed = constrain_schema(branch) or changed
        return changed

    for tool in constrained:
        function = tool.get("function", {})
        parameters = function.get("parameters", {})
        if not constrain_schema(parameters):
            continue
        function["description"] = function.get("description", "") + (
            " The instruction explicitly requires command-line or terminal provenance; "
            "select shell_history so the executed command is recorded truthfully."
        )
    return constrained
