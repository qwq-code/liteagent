from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from .errors import AdapterError


FILTER_FIELDS = {
    "subject": "subject",
    "sender": "from",
    "recipient": "to",
    "cc": "cc",
    "body": "body",
}
FILTER_OPERATORS = {
    "contains": "contains",
    "does_not_contain": "doesn't contain",
    "is": "is",
    "is_not": "isn't",
    "begins_with": "begins with",
    "ends_with": "ends with",
}
FILTER_ACTIONS = {
    "move_to_local_folder": "Move to folder",
    "forward": "Forward",
}


def _plain_string(value: Any, field: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdapterError("INVALID_REQUEST", f"{field} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > max_length or any(char in normalized for char in "\r\n\x00"):
        raise AdapterError(
            "INVALID_REQUEST",
            f"{field} must be at most {max_length} characters without line breaks",
        )
    return normalized


def validate_local_folder_name(value: Any, field: str = "folder name") -> str:
    name = _plain_string(value, field, max_length=255)
    if name in {".", ".."} or "/" in name or "\\" in name:
        raise AdapterError(
            "INVALID_REQUEST",
            f"{field} must be one Thunderbird local-folder name, not a path",
        )
    return name


def validate_filter_configuration(params: Mapping[str, Any]) -> None:
    unexpected = sorted(set(params).difference({"filters"}))
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            f"filters.configure received unsupported parameters: {unexpected}",
        )
    filters = params.get("filters")
    if not isinstance(filters, list) or len(filters) != 1:
        raise AdapterError(
            "INVALID_REQUEST", "params.filters must contain exactly one named rule; use separate calls for multiple filters"
        )
    allowed_rule_fields = {
        "name",
        "enabled",
        "match",
        "condition_mode",
        "conditions",
        "action",
        "destination",
    }
    allowed_condition_fields = {"field", "operator", "value"}
    for index, rule in enumerate(filters):
        field = f"params.filters[{index}]"
        if not isinstance(rule, Mapping):
            raise AdapterError("INVALID_REQUEST", f"{field} must be an object")
        unexpected_rule_fields = sorted(set(rule).difference(allowed_rule_fields))
        if unexpected_rule_fields:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{field} contains unsupported fields: {unexpected_rule_fields}",
            )
        _plain_string(rule.get("name"), f"{field}.name", max_length=255)
        if "enabled" in rule and not isinstance(rule["enabled"], bool):
            raise AdapterError("INVALID_REQUEST", f"{field}.enabled must be a boolean")
        if rule.get("match", "all") not in {"all", "any"}:
            raise AdapterError("INVALID_REQUEST", f"{field}.match must be all or any")
        condition_mode = rule.get("condition_mode")
        if condition_mode not in {"criteria", "all_messages"}:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{field}.condition_mode must be criteria or all_messages",
            )
        action = rule.get("action")
        if action not in FILTER_ACTIONS:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{field}.action must be move_to_local_folder or forward",
            )
        destination = _plain_string(
            rule.get("destination"), f"{field}.destination", max_length=512
        )
        if action == "move_to_local_folder":
            validate_local_folder_name(destination, f"{field}.destination")
        conditions = rule.get("conditions")
        if not isinstance(conditions, list) or len(conditions) > 10:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{field}.conditions must be an explicit array with at most 10 items",
            )
        if condition_mode == "criteria" and not conditions:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{field}.conditions must contain at least one item for condition_mode=criteria",
            )
        if condition_mode == "all_messages" and conditions:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{field}.conditions must be empty for condition_mode=all_messages",
            )
        for condition_index, condition in enumerate(conditions):
            condition_field = f"{field}.conditions[{condition_index}]"
            if not isinstance(condition, Mapping):
                raise AdapterError(
                    "INVALID_REQUEST", f"{condition_field} must be an object"
                )
            unexpected_condition_fields = sorted(
                set(condition).difference(allowed_condition_fields)
            )
            if unexpected_condition_fields:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"{condition_field} contains unsupported fields: "
                    f"{unexpected_condition_fields}",
                )
            if condition.get("field") not in FILTER_FIELDS:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"{condition_field}.field is unsupported",
                )
            if condition.get("operator") not in FILTER_OPERATORS:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"{condition_field}.operator is unsupported",
                )
            _plain_string(
                condition.get("value"),
                f"{condition_field}.value",
                max_length=1024,
            )


def _condition_value(value: str) -> str:
    if not any(char in value for char in ',()"'):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def compile_filter_configuration(params: Mapping[str, Any]) -> dict[str, Any]:
    validate_filter_configuration(params)
    raw_filters: list[dict[str, str]] = []
    local_folders: list[str] = []
    for rule in params["filters"]:
        action = str(rule["action"])
        destination = str(rule["destination"]).strip()
        conditions = list(rule["conditions"])
        if rule["condition_mode"] == "criteria":
            connective = "AND" if rule.get("match", "all") == "all" else "OR"
            condition = " ".join(
                f"{connective} ({FILTER_FIELDS[item['field']]},"
                f"{FILTER_OPERATORS[item['operator']]},"
                f"{_condition_value(str(item['value']).strip())})"
                for item in conditions
            )
        else:
            condition = "ALL"
        if action == "move_to_local_folder":
            destination = validate_local_folder_name(destination, "filter destination")
            action_value = "mailbox://nobody@Local%20Folders/" + quote(
                destination, safe=""
            )
            if destination.casefold() not in {
                name.casefold() for name in local_folders
            }:
                local_folders.append(destination)
        else:
            action_value = destination
        default_name = (
            f"Move matching messages to {destination}"
            if action == "move_to_local_folder"
            else f"Forward matching messages to {destination}"
        )
        name = str(rule.get("name", default_name)).strip()
        raw_filters.append(
            {
                "name": name,
                "enabled": "yes" if rule.get("enabled", True) else "no",
                "type": "17",
                "action": FILTER_ACTIONS[action],
                "actionValue": action_value,
                "condition": condition,
            }
        )
    return {"filters": raw_filters, "local_folders": local_folders}
