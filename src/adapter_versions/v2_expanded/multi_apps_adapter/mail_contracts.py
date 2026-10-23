from __future__ import annotations

from typing import Any, Mapping

from .errors import AdapterError


def _nonempty_string(params: Mapping[str, Any], field: str) -> str:
    value = params.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(
            "INVALID_REQUEST", f"params.{field} must be a non-empty string"
        )
    return value


def validate_mail_query_messages_params(params: Mapping[str, Any]) -> None:
    _nonempty_string(params, "folder_name")
    allowed = {
        "folder_name",
        "limit",
        "select_from",
        "order",
        "sender_contains",
        "subject_contains",
        "after",
        "before",
        "has_attachments",
    }
    unexpected = sorted(set(params).difference(allowed))
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            f"mail.query_messages received unsupported parameters: {unexpected}",
        )
    if "limit" in params and (
        isinstance(params["limit"], bool)
        or not isinstance(params["limit"], int)
        or not 1 <= params["limit"] <= 500
    ):
        raise AdapterError(
            "INVALID_REQUEST", "params.limit must be an integer from 1 to 500"
        )
    if params.get("select_from", "latest") not in {"latest", "earliest"}:
        raise AdapterError(
            "INVALID_REQUEST", "params.select_from must be latest or earliest"
        )
    if params.get("order", "descending") not in {"ascending", "descending"}:
        raise AdapterError(
            "INVALID_REQUEST", "params.order must be ascending or descending"
        )
    for field in ("sender_contains", "subject_contains", "after", "before"):
        if field in params:
            _nonempty_string(params, field)
    if "has_attachments" in params and not isinstance(params["has_attachments"], bool):
        raise AdapterError(
            "INVALID_REQUEST", "params.has_attachments must be a boolean"
        )


def validate_mail_query_latest_messages_params(params: Mapping[str, Any]) -> None:
    allowed = {
        "folder_name",
        "limit",
        "arrangement",
        "sender_contains",
        "subject_contains",
        "after",
        "before",
        "has_attachments",
    }
    unexpected = sorted(set(params).difference(allowed))
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            f"mail.query_latest_messages received unsupported parameters: {unexpected}",
        )
    _nonempty_string(params, "folder_name")
    limit = params.get("limit")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise AdapterError(
            "INVALID_REQUEST", "params.limit must be an integer from 1 to 500"
        )
    arrangement = params.get("arrangement")
    if arrangement not in {"earliest_to_latest", "latest_to_earliest"}:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.arrangement must be earliest_to_latest or latest_to_earliest",
        )
    validate_mail_query_messages_params(
        latest_messages_downstream_params(params, validate=False)
    )


def latest_messages_downstream_params(
    params: Mapping[str, Any], *, validate: bool = True
) -> dict[str, Any]:
    if validate:
        validate_mail_query_latest_messages_params(params)
    downstream = {key: value for key, value in params.items() if key != "arrangement"}
    downstream["select_from"] = "latest"
    downstream["order"] = (
        "ascending"
        if params.get("arrangement") == "earliest_to_latest"
        else "descending"
    )
    return downstream


def validate_mail_save_attachment_params(params: Mapping[str, Any]) -> None:
    _nonempty_string(params, "folder_name")
    output_path = _nonempty_string(params, "output_path")
    allowed = {
        "folder_name",
        "message_id",
        "mailbox_index",
        "attachment_name",
        "attachment_index",
        "output_path",
        "overwrite",
    }
    unexpected = sorted(set(params).difference(allowed))
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            f"mail.save_attachment received unsupported parameters: {unexpected}",
        )
    if not any(field in params for field in ("message_id", "mailbox_index")):
        raise AdapterError(
            "INVALID_REQUEST",
            "mail.save_attachment requires message_id or mailbox_index from mail.query_messages",
        )
    if "message_id" in params:
        _nonempty_string(params, "message_id")
    for field in ("mailbox_index", "attachment_index"):
        if field in params and (
            isinstance(params[field], bool)
            or not isinstance(params[field], int)
            or params[field] < 0
        ):
            raise AdapterError(
                "INVALID_REQUEST", f"params.{field} must be a non-negative integer"
            )
    if "attachment_name" in params:
        _nonempty_string(params, "attachment_name")
    if not output_path.startswith(("/", "~/")):
        raise AdapterError(
            "INVALID_REQUEST", "params.output_path must be absolute or begin with ~/"
        )
    if "overwrite" in params and not isinstance(params["overwrite"], bool):
        raise AdapterError("INVALID_REQUEST", "params.overwrite must be a boolean")


def validate_mail_compose_recipients_params(params: Mapping[str, Any]) -> None:
    recipients = params.get("recipients")
    if (
        not isinstance(recipients, list)
        or not recipients
        or any(
            not isinstance(recipient, str) or not recipient.strip()
            for recipient in recipients
        )
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.recipients must be a non-empty string array",
        )
    if len(recipients) > 100:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.recipients must contain at most 100 addresses",
        )
    if len({recipient.strip().casefold() for recipient in recipients}) != len(
        recipients
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.recipients must not contain duplicates",
        )
    if params.get("mode", "append") not in {"append", "replace"}:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.mode must be append or replace",
        )
    if "subject" in params and (
        not isinstance(params["subject"], str) or not params["subject"].strip()
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.subject must be a non-empty string",
        )
    unexpected = sorted(set(params).difference({"recipients", "mode", "subject"}))
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            f"mail.compose_recipients received unsupported parameters: {unexpected}",
        )
