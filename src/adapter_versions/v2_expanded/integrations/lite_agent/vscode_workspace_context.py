from __future__ import annotations

import re
from typing import Any


WORKSPACE_MUTATION_ACTIONS = frozenset(
    {
        "workspace.write",
        "workspace.set_folders",
        "workspace.add_folders",
    }
)

_FOLDER_ADDITION_RE = re.compile(
    r"(?is)\b(?:add|append|include|insert)\b.{0,160}\bfolders?\b|"
    r"\bfolders?\b.{0,160}\b(?:add|append|include|insert)\b"
)


def requests_workspace_folder_addition(instruction: str) -> bool:
    """Recognize an instruction that explicitly asks to add workspace folders."""
    return bool(_FOLDER_ADDITION_RE.search(str(instruction)))


def has_successful_workspace_inspect(state: Any) -> bool:
    return any(
        getattr(event, "executed", False)
        and not getattr(event, "error", None)
        and isinstance(getattr(event, "proposed", None), dict)
        and event.proposed.get("action") == "workspace.inspect"
        for event in getattr(state, "events", ())
    )


def observed_workspace_file(state: Any) -> str | None:
    """Return the exact saved workspace file from the latest inspect result."""
    hint_getter = getattr(state, "latest_context_hint", None)
    hint = hint_getter("workspace.inspect") if callable(hint_getter) else {}
    if isinstance(hint, dict):
        path = hint.get("workspace_file")
        if isinstance(path, str) and path.strip():
            return path
    return None


def has_verified_workspace_addition(state: Any) -> bool:
    """Recognize a saved folder addition confirmed by Adapter verification."""
    for event in getattr(state, "events", ()):
        proposed = getattr(event, "proposed", None)
        result = getattr(event, "result", None)
        if (
            not getattr(event, "executed", False)
            or getattr(event, "error", None)
            or not isinstance(proposed, dict)
            or proposed.get("action") != "workspace.add_folders"
            or not isinstance(result, dict)
        ):
            continue
        response = result.get("adapter_response")
        if isinstance(response, dict):
            verification = response.get("verification")
            if isinstance(verification, dict) and verification.get("passed") is True:
                return True
    return False


def constrain_workspace_add_tools(tools: list[dict[str, Any]], state: Any) -> list[dict[str, Any]]:
    """Bind workspace.add_folders to an observed saved workspace and stage recovery."""
    if (
        getattr(state, "domain", None) != "vs_code"
        or not requests_workspace_folder_addition(str(getattr(state, "instruction", "")))
        or not has_successful_workspace_inspect(state)
    ):
        return tools
    if has_verified_workspace_addition(state):
        return [
            tool for tool in tools
            if isinstance(tool.get("function"), dict)
            and tool["function"].get("name") in {"propose_done", "fail_task"}
        ]
    workspace_file = observed_workspace_file(state)
    if not workspace_file:
        return tools
    staged: list[dict[str, Any]] = []
    for tool in tools:
        function = tool.get("function")
        name = function.get("name") if isinstance(function, dict) else None
        if name == "tools_search":
            # The owning mutation is already public and grounded by inspect.
            continue
        if isinstance(name, str) and name.startswith("adapter__") and name != "adapter__workspace_add_folders":
            continue
        if name != "adapter__workspace_add_folders":
            staged.append(tool)
            continue
        parameters = function.get("parameters")
        properties = parameters.get("properties") if isinstance(parameters, dict) else None
        path_schema = properties.get("path") if isinstance(properties, dict) else None
        if isinstance(path_schema, dict):
            path_schema["const"] = workspace_file
            path_schema["description"] = (
                "Exact saved workspace file returned by the successful workspace.inspect: "
                f"{workspace_file}. Do not use the workspace root directory."
            )
        folders_schema = properties.get("folders") if isinstance(properties, dict) else None
        items = folders_schema.get("items") if isinstance(folders_schema, dict) else None
        item_properties = items.get("properties") if isinstance(items, dict) else None
        if (
            isinstance(item_properties, dict)
            and not re.search(r"(?i)\b(?:display|custom)\s+names?\b|\bnamed?\b", state.instruction)
        ):
            item_properties.pop("name", None)
            required = items.get("required")
            if isinstance(required, list):
                items["required"] = [field for field in required if field != "name"]
            items["additionalProperties"] = False
        function["description"] = (
            str(function.get("description", "")).rstrip()
            + " The active workspace was inspected successfully; use its exact observed "
            "workspace_file for path and provide only the requested folders."
        )
        staged.insert(0, tool)
    return staged


def workspace_mutation_context(
    action: str,
    result: dict[str, Any],
    verification: Any,
) -> dict[str, Any] | None:
    if action not in WORKSPACE_MUTATION_ACTIONS:
        return None
    workspace = result.get("workspace")
    if not isinstance(workspace, dict) or not isinstance(
        workspace.get("folders"), list
    ):
        return None

    active = result.get("active_workspace")
    active = active if isinstance(active, dict) else {}
    passed = verification.get("passed") if isinstance(verification, dict) else None
    context = {
        "workspace_file": result.get("path"),
        "workspace_name": active.get("workspace_name"),
        "resolution_source": active.get("resolution_source"),
        "final_folders": workspace["folders"],
        "verification_passed": passed,
    }
    for key in (
        "added_folders",
        "already_present_folders",
    ):
        if key in result:
            context[key] = result[key]
    if isinstance(active.get("workspace_roots"), list):
        context["source_workspace_roots"] = active["workspace_roots"]

    if passed is not True:
        context["guidance"] = (
            "The workspace mutation is not verified. Inspect the reported state and replan; "
            "do not claim completion."
        )
    elif action == "workspace.add_folders":
        context["guidance"] = (
            "The requested folders are now present in the verified saved workspace. "
            "If adding these folders was the whole instruction, propose completion now; "
            "do not repeat this mutation or guess another workspace path."
        )
    else:
        context["guidance"] = (
            "The selected workspace file and final folder list were structurally verified. "
            "If this workspace mutation was the whole instruction, propose completion now; "
            "do not repeat an equivalent write."
        )
    return context


__all__ = [
    "WORKSPACE_MUTATION_ACTIONS",
    "constrain_workspace_add_tools",
    "has_successful_workspace_inspect",
    "has_verified_workspace_addition",
    "observed_workspace_file",
    "requests_workspace_folder_addition",
    "workspace_mutation_context",
]
