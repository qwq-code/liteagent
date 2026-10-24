"""Truthful model-facing constraints derived from a catalog search result."""

from __future__ import annotations

import copy
from typing import Any, Iterable

from integrations.openapa_osworld.tool_catalog import action_signature

from .tool_catalog import DIRECT_ACTION_SCHEMAS, build_tools, tool_name


def _downstream_params_schema(adapter: str, action: str) -> dict[str, Any]:
    if action in DIRECT_ACTION_SCHEMAS.get(adapter, {}):
        downstream_tool = build_tools(
            adapter,
            [action],
            include_gui=False,
            include_control_tools=False,
            strict_generic=True,
        )[0]
        params = copy.deepcopy(downstream_tool["function"]["parameters"])
        if adapter == "libreoffice_calc" and action in {"range.read", "range.write"}:
            # Accept common inspect-result spellings and normalize them at
            # the downstream boundary; the native Adapter still validates the
            # canonical sheet/range pair.
            properties = params.setdefault("properties", {})
            properties["sheet_name"] = copy.deepcopy(properties["sheet"])
            properties["used_range_a1"] = copy.deepcopy(properties["range"])
            params["required"] = ["values"] if action == "range.write" else []
            params.setdefault("allOf", []).extend([
                {"anyOf": [{"required": ["sheet"]}, {"required": ["sheet_name"]}]},
                {"anyOf": [{"required": ["range"]}, {"required": ["used_range_a1"]}]},
            ])
            if action == "range.write":
                properties["format"] = {"type": "object"}
                # Retain adapter-owned descriptions: formula cells, formatted text,
                # and merged ranges have different semantics despite similar JSON.
        description = DIRECT_ACTION_SCHEMAS[adapter][action].get("description")
        if isinstance(description, str) and description:
            params["description"] = description
        if adapter == "libreoffice_calc" and action == "range.write":
            params["description"] = (
                str(params.get("description", ""))
                + " values is a rectangular row-major matrix matching the target range. "
                "A formula occupies one cell: use {kind: formula, value: '=SUM(A1:A3)'} "
                "inside that matrix, never split '=' from its expression. For several "
                "formulas at different cells, discover cells.set_formulas instead. "
                + " For an append, target only rows below the observed used range and provide "
                "exactly one values row per new source record; never copy existing ledger rows "
                "or add a leading blank row. When OCR files[].expense_entry or "
                "financial_amount_hint is present, copy those entries in source-file order, "
                "with Expense amounts negative."
            )
        return params
    return {
        "type": "object",
        "description": (
            f"Exact params for {adapter}.{action}. Public downstream contract: "
            f"{action_signature(adapter, action)}"
        ),
    }


def _route_payload_schema(
    base_payload_schema: dict[str, Any], adapter: str, action: str
) -> dict[str, Any]:
    payload = copy.deepcopy(base_payload_schema)
    properties = payload.setdefault("properties", {})
    properties["params"] = _downstream_params_schema(adapter, action)
    # Zero-argument inspection actions are commonly emitted as payload={};
    # preserve that valid native shape instead of forcing an empty params object.
    payload["required"] = [] if action in {"workbook.inspect", "workbook.save"} else ["params"]
    return payload


def constrain_adapter_call_routes(
    tools: list[dict[str, Any]], routes: Iterable[tuple[str, str]]
) -> list[dict[str, Any]]:
    """Limit ``adapter.call`` to exact route pairs returned by tools_search.

    The function changes only the model-visible schema.  It does not choose a
    route, supply a payload, or rewrite a subsequent model call.
    """
    route_pairs = list(dict.fromkeys(routes))
    if not route_pairs:
        return tools

    constrained = copy.deepcopy(tools)
    adapter_call_name = tool_name("adapter.call")
    for tool in constrained:
        function = tool.get("function")
        if not isinstance(function, dict) or function.get("name") != adapter_call_name:
            continue
        parameters = function.get("parameters")
        if not isinstance(parameters, dict):
            continue
        # A later surface pass may apply this helper again (for example the
        # common recovery constraints after completion recovery). Preserve the
        # narrower schema already present instead of widening it back to every
        # route returned by the catalog.
        existing = parameters.get("oneOf")
        fixed_route = parameters.get("x-route")
        if isinstance(fixed_route, dict):
            fixed_pair = (fixed_route.get("adapter"), fixed_route.get("action"))
            route_pairs = [pair for pair in route_pairs if pair == fixed_pair]
        if isinstance(existing, list):
            existing_pairs = {
                (
                    branch.get("properties", {}).get("adapter", {}).get("enum", [None])[0],
                    branch.get("properties", {}).get("action", {}).get("enum", [None])[0],
                )
                for branch in existing
                if isinstance(branch, dict)
                and isinstance(branch.get("properties"), dict)
            }
            if existing_pairs:
                route_pairs = [pair for pair in route_pairs if pair in existing_pairs]
        if not route_pairs:
            continue
        payload_schema = parameters.get("properties", {}).get("payload", {})
        if len(route_pairs) == 1:
            # A single discovered route is a distinct callable contract. Keep
            # adapter/action in the server-side route identity so a small model
            # only has to produce the downstream payload and cannot select a
            # stale or unrelated action from the old union schema.
            adapter, action = route_pairs[0]
            parameters.pop("oneOf", None)
            parameters["properties"] = {
                # Keep the route identity fixed while accepting the legacy
                # wrapper fields that small providers may still emit.
                "adapter": {"const": adapter},
                "action": {"const": action},
                "payload": _route_payload_schema(payload_schema, adapter, action),
            }
            parameters["required"] = ["payload"]
            parameters["x-route"] = {"adapter": adapter, "action": action}
            parameters["description"] = (
                f"Call the discovered {adapter}.{action} route. "
                "Provide only payload with the documented downstream fields."
            )
        else:
            parameters["oneOf"] = [
                {
                    "properties": {
                        "adapter": {"enum": [adapter]},
                        "action": {"enum": [action]},
                        "payload": _route_payload_schema(payload_schema, adapter, action),
                    },
                    "required": ["adapter", "action", "payload"],
                }
                for adapter, action in route_pairs
            ]
        pairs = ", ".join(f"{adapter}.{action}" for adapter, action in route_pairs)
        function["description"] += (
            f" Currently available downstream routes: {pairs}."
            " If the needed operation is not listed, call tools_search again; "
            "do not substitute a different listed action."
        )
        if route_pairs and all(
            adapter == "os"
            and action in {"image.extract_text_batch", "pdf.extract_text_batch"}
            for adapter, action in route_pairs
        ):
            function["description"] += (
                " A directory was just discovered; content extraction is the required "
                "next step. Call one of these OCR routes before any workbook action."
            )
        break
    return constrained
