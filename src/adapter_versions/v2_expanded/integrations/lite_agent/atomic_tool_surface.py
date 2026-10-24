"""Project a discovered single route as one typed operation at the LLM boundary.

This changes serialization only. The execution engine still receives and checks
the original adapter.call contract; no action selection or parameters are inferred.
"""
from __future__ import annotations

import copy
import hashlib
import re
from typing import Any


OPTIONS_FIELD = "request_options"


def _has_reference(value: Any) -> bool:
    if isinstance(value, dict):
        return "$ref" in value or "$dynamicRef" in value or any(
            _has_reference(child) for child in value.values()
        )
    return isinstance(value, list) and any(_has_reference(child) for child in value)


def _atomic_route_function(
    source_function: dict[str, Any],
    adapter: str,
    action: str,
    payload: dict[str, Any],
    used_names: set[str],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Build one typed provider tool for a closed, single downstream route."""
    if (
        payload.get("additionalProperties") is not False
        or set(payload).difference(
            {"type", "description", "properties", "required", "additionalProperties"}
        )
    ):
        return None
    properties = payload.get("properties")
    params = properties.get("params") if isinstance(properties, dict) else None
    if (
        not isinstance(params, dict)
        or params.get("type") != "object"
        or params.get("additionalProperties") is not False
        or not isinstance(params.get("properties"), dict)
        or OPTIONS_FIELD in params["properties"]
        or any(
            key in params
            for key in (
                "minProperties", "maxProperties", "propertyNames",
                "patternProperties", "unevaluatedProperties",
            )
        )
        or _has_reference(params)
    ):
        return None

    identity = f"{adapter}.{action}"
    digest = hashlib.sha256(identity.encode()).hexdigest()[:8]
    name = "atomic__" + re.sub(r"[^a-zA-Z0-9_]", "_", identity)[:45] + "_" + digest
    if name in used_names:
        return None

    atomic_schema = copy.deepcopy(params)
    options = copy.deepcopy(payload)
    options["properties"].pop("params", None)
    options["required"] = [
        key for key in payload.get("required", []) if key != "params"
    ]
    options["description"] = (
        "Optional request metadata; action arguments belong at the top level."
    )
    if options["properties"]:
        atomic_schema["properties"][OPTIONS_FIELD] = options
        if options["required"]:
            atomic_schema.setdefault("required", []).append(OPTIONS_FIELD)

    function = copy.deepcopy(source_function)
    function["name"] = name
    function["description"] = (
        f"Execute exactly one {identity} operation. Supply its action arguments directly; "
        f"put document/target/verification/timeout metadata in {OPTIONS_FIELD} if needed. "
        "Do not supply adapter, action, payload, or params wrappers. "
        + str(params.get("description", ""))
    )
    function["parameters"] = atomic_schema
    return function, {
        "adapter": adapter,
        "action": action,
        "schema": atomic_schema,
    }


def atomic_provider_surface(
    tools: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Flatten only a fixed route with a closed, fully typed params object.

    Ambiguous routes and contracts that cannot be projected losslessly retain
    the existing wrapper. Request metadata remains explicit and optional.
    """
    projected = copy.deepcopy(tools)
    bindings: dict[str, dict[str, Any]] = {}
    names = {tool.get("function", {}).get("name") for tool in tools}
    for tool_index, tool in enumerate(list(projected)):
        function = tool.get("function", {})
        if function.get("name") != "adapter__adapter_call":
            continue
        schema = function.get("parameters", {})
        route = schema.get("x-route")
        if not isinstance(route, dict) and isinstance(schema.get("oneOf"), list):
            routes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for branch in schema["oneOf"]:
                branch_properties = branch.get("properties") if isinstance(branch, dict) else None
                if not isinstance(branch_properties, dict):
                    routes = []
                    break
                adapter_values = branch_properties.get("adapter", {}).get("enum")
                action_values = branch_properties.get("action", {}).get("enum")
                payload = branch_properties.get("payload")
                if (
                    not isinstance(adapter_values, list)
                    or len(adapter_values) != 1
                    or not isinstance(action_values, list)
                    or len(action_values) != 1
                    or not isinstance(payload, dict)
                    or not isinstance(branch.get("required"), list)
                    or not {"adapter", "action", "payload"}.issubset(branch["required"])
                ):
                    routes = []
                    break
                routes.append((
                    {"adapter": adapter_values[0], "action": action_values[0]},
                    payload,
                ))
            if not routes:
                continue
            atomic_tools: list[dict[str, Any]] = []
            atomic_bindings: dict[str, dict[str, Any]] = {}
            candidate_names = names.difference({function.get("name")})
            for identity, payload in routes:
                if not all(
                    isinstance(identity.get(key), str) and identity[key]
                    for key in ("adapter", "action")
                ) or _has_reference(payload):
                    atomic_tools = []
                    break
                projected_route = _atomic_route_function(
                    function,
                    identity["adapter"],
                    identity["action"],
                    payload,
                    candidate_names,
                )
                if projected_route is None:
                    atomic_tools = []
                    break
                projected_function, binding = projected_route
                candidate_names.add(projected_function["name"])
                atomic_tools.append({"type": "function", "function": projected_function})
                atomic_bindings[projected_function["name"]] = binding
            if atomic_tools:
                projected[tool_index : tool_index + 1] = atomic_tools
                bindings.update(atomic_bindings)
                names = candidate_names
            continue
        if not isinstance(route, dict) or not all(
            isinstance(route.get(key), str) and route[key] for key in ("adapter", "action")
        ):
            continue
        if schema.get("oneOf") or schema.get("anyOf") or _has_reference(schema):
            continue
        payload = schema.get("properties", {}).get("payload", {})
        params = payload.get("properties", {}).get("params", {})
        if not isinstance(payload, dict):
            continue
        identity = route["adapter"] + "." + route["action"]
        digest = hashlib.sha256(identity.encode()).hexdigest()[:8]
        name = "atomic__" + re.sub(r"[^a-zA-Z0-9_]", "_", identity)[:45] + "_" + digest
        if name in names:
            continue
        atomic_schema = copy.deepcopy(params)
        options = copy.deepcopy(payload)
        options["properties"].pop("params", None)
        options["required"] = [key for key in payload.get("required", []) if key != "params"]
        options["description"] = "Optional request metadata; action arguments belong at the top level."
        if options["properties"]:
            atomic_schema["properties"][OPTIONS_FIELD] = options
            if options["required"]:
                atomic_schema.setdefault("required", []).append(OPTIONS_FIELD)
        function["name"] = name
        function["description"] = (
            f"Execute exactly one {identity} operation. Supply its action arguments directly; "
            f"put document/target/verification/timeout metadata in {OPTIONS_FIELD} if needed. "
            "Do not supply adapter, action, payload, or params wrappers. "
            + str(params.get("description", ""))
        )
        function["parameters"] = atomic_schema
        bindings[name] = {"adapter": route["adapter"], "action": route["action"], "schema": atomic_schema}
        names.add(name)
    return projected, bindings


def restore_adapter_arguments(arguments: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    """Restore a validated atomic call without changing any model-selected value."""
    params = copy.deepcopy(arguments)
    payload = params.pop(OPTIONS_FIELD, {})
    payload["params"] = params
    return {"adapter": binding["adapter"], "action": binding["action"], "payload": payload}
