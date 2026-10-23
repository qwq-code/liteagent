from __future__ import annotations

import csv
import hashlib
import io
import json
import mailbox
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable

from .errors import AdapterError
from .filter_contract import validate_local_folder_name


PROFILE_ROOT = Path.home() / ".thunderbird"
OSWORLD_PROFILE = PROFILE_ROOT / "t5q2a5hp.default-release"
PREF_PATTERN = re.compile(
    r'^user_pref\("(?P<key>(?:[^"\\]|\\.)+)",\s*(?P<value>.+)\);\s*$'
)

CONTACT_CSV_FIELDS = (
    ("First Name", "FirstName"),
    ("Last Name", "LastName"),
    ("Display Name", "DisplayName"),
    ("Nickname", "NickName"),
    ("Primary Email", "PrimaryEmail"),
    ("Secondary Email", "SecondEmail"),
    ("Screen Name", "_AimScreenName"),
    ("Work Phone", "WorkPhone"),
    ("Home Phone", "HomePhone"),
    ("Fax Number", "FaxNumber"),
    ("Pager Number", "PagerNumber"),
    ("Mobile Number", "CellularNumber"),
    ("Home Address", "HomeAddress"),
    ("Home Address 2", "HomeAddress2"),
    ("Home City", "HomeCity"),
    ("Home State", "HomeState"),
    ("Home ZipCode", "HomeZipCode"),
    ("Home Country", "HomeCountry"),
    ("Work Address", "WorkAddress"),
    ("Work Address 2", "WorkAddress2"),
    ("Work City", "WorkCity"),
    ("Work State", "WorkState"),
    ("Work ZipCode", "WorkZipCode"),
    ("Work Country", "WorkCountry"),
    ("Job Title", "JobTitle"),
    ("Department", "Department"),
    ("Organization", "Company"),
    ("Web Page 1", "WebPage1"),
    ("Web Page 2", "WebPage2"),
    ("Birth Year", "BirthYear"),
    ("Birth Month", "BirthMonth"),
    ("Birth Day", "BirthDay"),
    ("Custom 1", "Custom1"),
    ("Custom 2", "Custom2"),
    ("Custom 3", "Custom3"),
    ("Custom 4", "Custom4"),
    ("Notes", "Notes"),
)

BUILTIN_ADDRESS_BOOKS = {
    "personal address book": ("Personal Address Book", "abook.sqlite"),
    "collected addresses": ("Collected Addresses", "history.sqlite"),
}


def find_profile(path: str | Path | None = None) -> Path:
    if path is not None:
        profile = Path(path).expanduser()
    elif OSWORLD_PROFILE.is_dir():
        profile = OSWORLD_PROFILE
    else:
        profile = _profile_from_ini(PROFILE_ROOT / "profiles.ini")
    if not profile.is_dir():
        raise AdapterError(
            "PROFILE_NOT_FOUND",
            f"Thunderbird profile not found: {profile}",
            http_status=404,
        )
    return profile.resolve()


def _profile_from_ini(path: Path) -> Path:
    if not path.is_file():
        raise AdapterError(
            "PROFILE_NOT_FOUND", f"profiles.ini not found: {path}", http_status=404
        )
    current: dict[str, str] = {}
    sections: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            if current:
                sections.append(current)
            current = {"section": line[1:-1]}
        elif "=" in line:
            key, value = line.split("=", 1)
            current[key] = value
    if current:
        sections.append(current)
    profiles = [
        item for item in sections if item.get("section", "").startswith("Profile")
    ]
    selected = next(
        (item for item in profiles if item.get("Default") == "1"),
        profiles[0] if profiles else None,
    )
    if not selected or not selected.get("Path"):
        raise AdapterError(
            "PROFILE_NOT_FOUND",
            "profiles.ini contains no usable profile",
            http_status=404,
        )
    candidate = Path(selected["Path"])
    return candidate if candidate.is_absolute() else path.parent / candidate


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(mode)
    os.replace(temporary, path)


def _atomic_write_bytes(path: Path, data: bytes, *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not path.is_file():
        raise AdapterError(
            "INVALID_REQUEST",
            f"attachment output path is not a regular file: {path}",
        )
    if path.exists() and not overwrite:
        raise AdapterError(
            "PATH_EXISTS",
            f"attachment output already exists: {path}",
            http_status=409,
        )
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(mode)
    os.replace(temporary, path)


def read_preferences(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        match = PREF_PATTERN.match(line.strip())
        if not match:
            continue
        try:
            values[match.group("key")] = json.loads(match.group("value"))
        except json.JSONDecodeError:
            continue
    return values


def resolve_filter_rules_path(profile: Path) -> Path:
    """Resolve one configured incoming account's filter file from live profile data."""
    preferences = read_preferences(profile / "prefs.js")
    account_servers = {
        match.group(1): str(value).strip()
        for key, value in preferences.items()
        if isinstance(value, str)
        and (match := re.fullmatch(r"mail\.account\.(account\d+)\.server", key))
        and re.fullmatch(r"server\d+", value.strip())
    }
    configured_accounts = [
        value.strip()
        for value in str(preferences.get("mail.accountmanager.accounts", "")).split(",")
        if value.strip()
    ]
    active_accounts = configured_accounts or sorted(account_servers)
    server_ids = list(
        dict.fromkeys(
            account_servers[account]
            for account in active_accounts
            if account in account_servers
        )
    )

    targets: dict[Path, list[str]] = {}
    for server_id in server_ids:
        prefix = f"mail.server.{server_id}."
        server_type = str(preferences.get(prefix + "type", "")).strip().casefold()
        hostname = str(preferences.get(prefix + "hostname", "")).strip()
        if server_type in {"local", "none"} or hostname.casefold() == "local folders":
            continue

        directories: set[Path] = set()
        relative = preferences.get(prefix + "directory-rel")
        if isinstance(relative, str) and relative.startswith("[ProfD]"):
            suffix = relative[len("[ProfD]") :].lstrip("/\\")
            if suffix:
                directories.add(profile / suffix)
        absolute = preferences.get(prefix + "directory")
        if isinstance(absolute, str) and absolute.strip():
            directory = Path(absolute).expanduser()
            if directory.is_absolute():
                directories.add(directory)

        if not directories and hostname:
            if server_type == "imap":
                directories.add(profile / "ImapMail" / hostname)
            elif server_type == "pop3":
                directories.add(profile / "Mail" / hostname)
            else:
                directories.update(
                    {
                        profile / "ImapMail" / hostname,
                        profile / "Mail" / hostname,
                    }
                )

        for directory in directories:
            if not directory.is_dir():
                continue
            target = directory.resolve() / "msgFilterRules.dat"
            targets.setdefault(target, []).append(server_id)

    if not targets:
        raise AdapterError(
            "FILTER_TARGET_NOT_FOUND",
            "no active Thunderbird account has a usable message-filter storage directory",
            {
                "profile": str(profile),
                "active_accounts": active_accounts,
                "server_ids": server_ids,
            },
            404,
        )
    if len(targets) != 1:
        raise AdapterError(
            "AMBIGUOUS_FILTER_TARGET",
            "multiple active Thunderbird accounts have message-filter storage directories",
            {
                "profile": str(profile),
                "targets": [
                    {"path": str(path), "server_ids": targets[path]}
                    for path in sorted(targets, key=str)
                ],
            },
            409,
        )
    return next(iter(targets))


def update_preferences(
    path: Path,
    values: dict[str, Any] | None = None,
    remove_keys: Iterable[str] = (),
    remove_prefixes: Iterable[str] = (),
) -> dict[str, Any]:
    values = dict(values or {})
    removals = set(remove_keys)
    prefixes = tuple(remove_prefixes)
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    emitted: set[str] = set()
    output: list[str] = []
    for line in lines:
        match = PREF_PATTERN.match(line.strip())
        if not match:
            output.append(line)
            continue
        key = match.group("key")
        if key in removals or key.startswith(prefixes):
            continue
        if key in values:
            if key not in emitted:
                output.append(
                    f"user_pref({json.dumps(key)}, {json.dumps(values[key], ensure_ascii=True)});"
                )
                emitted.add(key)
            continue
        output.append(line)
    for key, value in values.items():
        if key not in emitted:
            output.append(
                f"user_pref({json.dumps(key)}, {json.dumps(value, ensure_ascii=True)});"
            )
    _atomic_write(path, "\n".join(output).rstrip() + "\n")
    observed = read_preferences(path)
    return {
        "path": str(path),
        "values": {key: observed.get(key) for key in values},
        "removed": sorted(removals),
    }


def update_json_path(path: Path, keys: list[str], value: Any) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    cursor = data
    for key in keys[:-1]:
        child = cursor.get(key)
        if not isinstance(child, dict):
            child = {}
            cursor[key] = child
        cursor = child
    cursor[keys[-1]] = value
    _atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return {"path": str(path), "keys": keys, "value": value}


def ensure_local_folders(profile: Path, names: Iterable[str]) -> dict[str, Any]:
    root = profile / "Mail" / "Local Folders"
    root.mkdir(parents=True, exist_ok=True)
    created = []
    for raw_name in names:
        name = validate_local_folder_name(raw_name)
        mbox_path = root / name
        index_path = root / f"{name}.msf"
        mbox_path.touch(exist_ok=True)
        index_path.touch(exist_ok=True)
        created.append({"name": name, "mbox": str(mbox_path), "index": str(index_path)})
    return {"root": str(root), "folders": created}


def _quote_filter(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def write_filters(path: Path, filters: list[dict[str, str]]) -> dict[str, Any]:
    """Upsert one named rule without replacing unrelated filter blocks."""
    if len(filters) != 1:
        raise AdapterError("INVALID_REQUEST", "write_filters requires exactly one rule")
    item = filters[0]
    name_line = f'name="{_quote_filter(str(item["name"]))}"'
    original = path.read_text(encoding="utf-8") if path.is_file() else 'version="9"\nlogging="no"\n'
    lines = original.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.rstrip("\r\n").startswith('name=')]
    matching = [i for i in starts if lines[i].rstrip("\r\n") == name_line]
    if len(matching) > 1:
        raise AdapterError("AMBIGUOUS_FILTER", "Multiple existing rules have this name; choose a unique name")
    block = "".join(
        f'{key}="{_quote_filter(str(item[key]))}"\n'
        for key in ("name", "enabled", "type", "action", "actionValue", "condition")
    )
    if matching:
        start = matching[0]
        end = next((i for i in starts if i > start), len(lines))
        output = "".join(lines[:start]) + block + "".join(lines[end:])
    else:
        output = original + ("\n" if original and not original.endswith("\n") else "") + block
    _atomic_write(path, output)
    return {"path": str(path), "filters": filters}


def export_mbox_messages(source: Path, destination: Path) -> dict[str, Any]:
    if not source.is_file():
        raise AdapterError(
            "PATH_NOT_FOUND", f"mailbox does not exist: {source}", http_status=404
        )
    if destination.exists() and not destination.is_dir():
        raise AdapterError(
            "INVALID_REQUEST",
            f"EML export destination is not a directory: {destination}",
        )
    destination.mkdir(parents=True, exist_ok=True)
    conflicts = sorted(
        path for path in destination.iterdir() if path.suffix.casefold() == ".eml"
    )
    if conflicts:
        raise AdapterError(
            "PATH_EXISTS",
            "EML export destination already contains .eml entries",
            {
                "destination": str(destination),
                "conflicts": [str(path) for path in conflicts],
            },
            409,
        )
    exported = []
    counts: dict[str, int] = {}
    box = mailbox.mbox(source, create=False)
    try:
        for index, message in enumerate(box):
            subject = (
                str(
                    make_header(decode_header(message.get("Subject", "message")))
                ).strip()
                or "message"
            )
            safe = (
                re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", subject).strip(" .") or "message"
            )
            counts[safe] = counts.get(safe, 0) + 1
            suffix = "" if counts[safe] == 1 else f"-{counts[safe]}"
            output = destination / f"{safe}{suffix}.eml"
            try:
                with output.open("xb") as stream:
                    stream.write(message.as_bytes(unixfrom=False))
            except FileExistsError as exc:
                raise AdapterError(
                    "PATH_EXISTS",
                    f"EML export output already exists: {output}",
                    http_status=409,
                ) from exc
            exported.append({"index": index, "subject": subject, "path": str(output)})
    finally:
        box.close()
    if not exported:
        raise AdapterError(
            "MAILBOX_EMPTY", f"no messages found in {source}", http_status=422
        )
    return {
        "source": str(source),
        "destination": str(destination),
        "count": len(exported),
        "messages": exported,
    }


def _decoded_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except (LookupError, UnicodeError):
        return value.strip()


def _mailbox_folder_path(profile: Path, folder_name: str) -> Path:
    raw_parts = folder_name.strip().split("/")
    if (
        not raw_parts
        or any(not part or part in {".", ".."} for part in raw_parts)
        or "\\" in folder_name
        or "\x00" in folder_name
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            "folder_name must be a Thunderbird folder name or slash-separated folder path",
        )
    if raw_parts[0].casefold() == "local folders":
        raw_parts = raw_parts[1:]
    if not raw_parts:
        raise AdapterError("INVALID_REQUEST", "folder_name must identify a folder")

    requested = "/".join(raw_parts).casefold()
    roots = []
    for parent_name in ("Mail", "ImapMail"):
        parent = profile / parent_name
        if parent.is_dir():
            roots.extend(path for path in parent.iterdir() if path.is_dir())

    matches: set[Path] = set()
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.name.endswith(".msf"):
                continue
            relative = path.relative_to(root)
            logical_parts = [
                part[:-4] if part.casefold().endswith(".sbd") else part
                for part in relative.parts
            ]
            logical = "/".join(logical_parts).casefold()
            if logical == requested or (
                len(raw_parts) == 1 and logical_parts[-1].casefold() == requested
            ):
                matches.add(path.resolve())

    if not matches:
        raise AdapterError(
            "FOLDER_NOT_FOUND",
            f"Thunderbird mailbox folder not found: {folder_name}",
            http_status=404,
        )
    if len(matches) > 1:
        raise AdapterError(
            "AMBIGUOUS_FOLDER",
            f"Thunderbird folder name is ambiguous: {folder_name}",
            {"matches": sorted(str(path) for path in matches)},
            409,
        )
    return next(iter(matches))


def export_folder_messages(
    profile: Path, folder_name: str, destination: Path
) -> dict[str, Any]:
    """Export a visible Thunderbird folder without exposing profile storage paths."""
    return export_mbox_messages(_mailbox_folder_path(profile, folder_name), destination)


def _date_boundary(value: str | None, field: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdapterError(
            "INVALID_REQUEST",
            f"params.{field} must be an ISO-8601 date or date-time",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _message_date(message: Message) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(message.get("Date", ""))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _addresses(message: Message, header: str) -> list[dict[str, str]]:
    values = [_decoded_header(value) for value in message.get_all(header, [])]
    return [
        {"name": _decoded_header(name), "address": address.strip()}
        for name, address in getaddresses(values)
        if address.strip()
    ]


def _attachment_names(message: Message) -> list[str]:
    attachments = []
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        if filename is not None:
            attachments.append(_decoded_header(filename))
        elif disposition == "attachment":
            attachments.append("")
    return attachments


def _normalized_message_id(message: Message) -> str:
    """Return a usable Message-ID, treating a missing header as absent."""
    value = message.get("Message-ID", "")
    if not isinstance(value, str):
        return ""
    return value.strip().strip("<>")


def query_messages(
    profile: Path,
    folder_name: str,
    *,
    limit: int = 50,
    select_from: str = "latest",
    order: str = "descending",
    sender_contains: str | None = None,
    subject_contains: str | None = None,
    after: str | None = None,
    before: str | None = None,
    has_attachments: bool | None = None,
) -> dict[str, Any]:
    """Query one local Thunderbird mailbox without exposing message bodies."""
    source = _mailbox_folder_path(profile, folder_name)
    after_date = _date_boundary(after, "after")
    before_date = _date_boundary(before, "before")
    sender_filter = sender_contains.casefold() if sender_contains else None
    subject_filter = subject_contains.casefold() if subject_contains else None
    messages: list[dict[str, Any]] = []
    box = mailbox.mbox(source, create=False)
    try:
        for index, message in enumerate(box):
            subject = _decoded_header(message.get("Subject"))
            senders = _addresses(message, "From")
            sender = senders[0] if senders else {"name": "", "address": ""}
            message_date = _message_date(message)
            attachments = _attachment_names(message)
            sender_text = f"{sender['name']} {sender['address']}".casefold()
            if sender_filter and sender_filter not in sender_text:
                continue
            if subject_filter and subject_filter not in subject.casefold():
                continue
            if after_date and (message_date is None or message_date < after_date):
                continue
            if before_date and (message_date is None or message_date >= before_date):
                continue
            if has_attachments is not None and bool(attachments) is not has_attachments:
                continue
            cc = _addresses(message, "Cc")
            to = _addresses(message, "To")
            row = {
                "mailbox_index": index,
                "date": message_date.isoformat().replace("+00:00", "Z")
                if message_date
                else None,
                "sender_name": sender["name"],
                "sender_address": sender["address"],
                "subject": subject,
                "to": ", ".join(item["address"] for item in to),
                "cc": ", ".join(item["address"] for item in cc),
                "number_of_attachments": len(attachments),
                "attachment_names": attachments,
                "_sort_timestamp": message_date.timestamp()
                if message_date
                else float("-inf"),
            }
            message_id = _normalized_message_id(message)
            if message_id:
                row["message_id"] = message_id
            messages.append(row)
    finally:
        box.close()

    matched_count = len(messages)
    messages.sort(key=lambda item: (item["_sort_timestamp"], item["mailbox_index"]))
    selected = messages[-limit:] if select_from == "latest" else messages[:limit]
    if order == "descending":
        selected.reverse()
    for item in selected:
        item.pop("_sort_timestamp", None)
    return {
        "folder": folder_name,
        "source": str(source),
        "matched_count": matched_count,
        "returned_count": len(selected),
        "select_from": select_from,
        "order": order,
        "messages": selected,
    }


def save_attachment(
    profile: Path,
    folder_name: str,
    output_path: Path,
    *,
    message_id: str | None = None,
    mailbox_index: int | None = None,
    attachment_name: str | None = None,
    attachment_index: int | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Save one MIME attachment selected from a queried local mailbox message."""
    source = _mailbox_folder_path(profile, folder_name)
    output = output_path.expanduser()
    if not output.is_absolute():
        raise AdapterError(
            "INVALID_REQUEST",
            "output_path must be absolute or begin with ~/",
        )

    normalized_message_id = (
        message_id.strip().strip("<>") if isinstance(message_id, str) else None
    )
    selected_message: Message | None = None
    selected_mailbox_index: int | None = None
    box = mailbox.mbox(source, create=False)
    try:
        for index, message in enumerate(box):
            observed_message_id = message.get("Message-ID", "").strip().strip("<>")
            if mailbox_index is not None and index != mailbox_index:
                continue
            if normalized_message_id is not None and (
                observed_message_id != normalized_message_id
            ):
                continue
            if selected_message is not None:
                raise AdapterError(
                    "AMBIGUOUS_MESSAGE",
                    "message selector matched more than one mailbox message",
                    {"folder_name": folder_name, "message_id": normalized_message_id},
                    409,
                )
            selected_message = message
            selected_mailbox_index = index

        if selected_message is None:
            raise AdapterError(
                "MESSAGE_NOT_FOUND",
                "no mailbox message matched the supplied query result selector",
                {
                    "folder_name": folder_name,
                    "message_id": normalized_message_id,
                    "mailbox_index": mailbox_index,
                },
                404,
            )

        attachments: list[dict[str, Any]] = []
        for part in selected_message.walk():
            if part.is_multipart():
                continue
            raw_filename = part.get_filename()
            disposition = part.get_content_disposition()
            if raw_filename is None and disposition != "attachment":
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                raw_payload = part.get_payload()
                if not isinstance(raw_payload, str):
                    raise AdapterError(
                        "ATTACHMENT_DECODE_FAILED",
                        "selected attachment has no decodable payload",
                        http_status=422,
                    )
                payload = raw_payload.encode(part.get_content_charset() or "utf-8")
            attachments.append(
                {
                    "attachment_index": len(attachments),
                    "attachment_name": _decoded_header(raw_filename),
                    "content_type": part.get_content_type(),
                    "payload": payload,
                }
            )
    finally:
        box.close()

    candidates = attachments
    if attachment_index is not None:
        candidates = [
            item for item in candidates if item["attachment_index"] == attachment_index
        ]
    if attachment_name is not None:
        requested_name = attachment_name.strip().casefold()
        candidates = [
            item
            for item in candidates
            if str(item["attachment_name"]).casefold() == requested_name
        ]
    if not candidates:
        raise AdapterError(
            "ATTACHMENT_NOT_FOUND",
            "no attachment matched the supplied query result selector",
            {
                "attachment_name": attachment_name,
                "attachment_index": attachment_index,
                "available": [
                    {
                        "attachment_index": item["attachment_index"],
                        "attachment_name": item["attachment_name"],
                    }
                    for item in attachments
                ],
            },
            404,
        )
    if len(candidates) > 1:
        raise AdapterError(
            "AMBIGUOUS_ATTACHMENT",
            "attachment selector matched more than one attachment; provide attachment_name or attachment_index",
            {
                "available": [
                    {
                        "attachment_index": item["attachment_index"],
                        "attachment_name": item["attachment_name"],
                    }
                    for item in candidates
                ]
            },
            409,
        )

    selected = candidates[0]
    payload = selected.pop("payload")
    output_existed = output.exists()
    _atomic_write_bytes(output, payload, overwrite=overwrite)
    message_id = _normalized_message_id(selected_message)
    result = {
        "folder": folder_name,
        "source": str(source),
        "mailbox_index": selected_mailbox_index,
        "subject": _decoded_header(selected_message.get("Subject")),
        **selected,
        "output_path": str(output),
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "overwritten": output_existed,
    }
    if message_id:
        result["message_id"] = message_id
    return result


def _vcard_text(value: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != "\\" or index + 1 >= len(value):
            output.append(value[index])
            index += 1
            continue
        escaped = value[index + 1]
        output.append("\n" if escaped in {"n", "N"} else escaped)
        index += 2
    return "".join(output)


def _vcard_components(value: str) -> list[str]:
    components: list[str] = []
    current: list[str] = []
    escaped = False
    for char in value:
        if escaped:
            current.extend(("\\", char))
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ";":
            components.append(_vcard_text("".join(current)))
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    components.append(_vcard_text("".join(current)))
    return components


def _vcard_entries(raw: str) -> list[tuple[str, set[str], str]]:
    unfolded: list[str] = []
    for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    entries: list[tuple[str, set[str], str]] = []
    for line in unfolded:
        if ":" not in line:
            continue
        head, value = line.split(":", 1)
        parts = head.split(";")
        name = parts[0].rsplit(".", 1)[-1].upper()
        types: set[str] = set()
        for parameter in parts[1:]:
            raw_types = parameter.split("=", 1)[-1]
            types.update(
                item.strip().casefold() for item in raw_types.split(",") if item.strip()
            )
        entries.append((name, types, value))
    return entries


def _set_missing(contact: dict[str, str], key: str, value: str) -> None:
    if value and not contact.get(key):
        contact[key] = value


def _contact_from_properties(properties: dict[str, str]) -> dict[str, str]:
    contact = {
        key: str(value)
        for key, value in properties.items()
        if key != "_vCard" and value is not None
    }
    for name, types, raw_value in _vcard_entries(properties.get("_vCard", "")):
        value = _vcard_text(raw_value)
        if name == "N":
            parts = _vcard_components(raw_value) + [""] * 5
            _set_missing(contact, "LastName", parts[0])
            _set_missing(contact, "FirstName", parts[1])
        elif name == "FN":
            _set_missing(contact, "DisplayName", value)
        elif name == "NICKNAME":
            _set_missing(contact, "NickName", value.split(",", 1)[0])
        elif name == "EMAIL":
            if value in {contact.get("PrimaryEmail"), contact.get("SecondEmail")}:
                continue
            if ("pref" in types or "1" in types) and not contact.get("PrimaryEmail"):
                contact["PrimaryEmail"] = value
            elif not contact.get("PrimaryEmail"):
                contact["PrimaryEmail"] = value
            else:
                _set_missing(contact, "SecondEmail", value)
        elif name in {"IMPP", "X-AIM", "X-AIMSCREENNAME"}:
            _set_missing(contact, "_AimScreenName", value.rsplit(":", 1)[-1])
        elif name == "TEL":
            key = (
                "CellularNumber"
                if {"cell", "mobile"} & types
                else "FaxNumber"
                if "fax" in types
                else "PagerNumber"
                if "pager" in types
                else "HomePhone"
                if "home" in types
                else "WorkPhone"
            )
            _set_missing(contact, key, value)
        elif name == "ADR":
            parts = _vcard_components(raw_value) + [""] * 7
            prefix = "Home" if "home" in types else "Work"
            _set_missing(contact, f"{prefix}Address", parts[2])
            _set_missing(contact, f"{prefix}Address2", parts[1])
            _set_missing(contact, f"{prefix}City", parts[3])
            _set_missing(contact, f"{prefix}State", parts[4])
            _set_missing(contact, f"{prefix}ZipCode", parts[5])
            _set_missing(contact, f"{prefix}Country", parts[6])
        elif name == "TITLE":
            _set_missing(contact, "JobTitle", value)
        elif name == "ORG":
            parts = _vcard_components(raw_value) + [""] * 2
            _set_missing(contact, "Company", parts[0])
            _set_missing(contact, "Department", parts[1])
        elif name == "URL":
            _set_missing(contact, "WebPage2" if "home" in types else "WebPage1", value)
        elif name == "BDAY":
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 8:
                _set_missing(contact, "BirthYear", str(int(digits[:4])))
                _set_missing(contact, "BirthMonth", str(int(digits[4:6])))
                _set_missing(contact, "BirthDay", str(int(digits[6:8])))
        elif name == "NOTE":
            _set_missing(contact, "Notes", value)
        elif name.startswith("X-CUSTOM") and name[-1:] in {"1", "2", "3", "4"}:
            _set_missing(contact, f"Custom{name[-1]}", value)
    if not contact.get("DisplayName"):
        contact["DisplayName"] = " ".join(
            item
            for item in (contact.get("FirstName", ""), contact.get("LastName", ""))
            if item
        )
    return contact


def _address_book_database(profile: Path, requested_name: str) -> tuple[str, Path]:
    books = dict(BUILTIN_ADDRESS_BOOKS)
    preferences = read_preferences(profile / "prefs.js")
    identifiers = {
        match.group(1)
        for key in preferences
        if (
            match := re.match(
                r"ldap_2\.servers\.([^.]+)\.(?:description|filename)$", key
            )
        )
    }
    for identifier in identifiers:
        description = str(
            preferences.get(f"ldap_2.servers.{identifier}.description", identifier)
        )
        filename = str(
            preferences.get(
                f"ldap_2.servers.{identifier}.filename", f"{identifier}.sqlite"
            )
        )
        books[description.casefold()] = (description, filename)
    requested = requested_name.strip().casefold()
    selected = books.get(requested)
    if selected is None:
        selected = next(
            (
                item
                for item in books.values()
                if requested
                in {Path(item[1]).name.casefold(), Path(item[1]).stem.casefold()}
            ),
            None,
        )
    if selected is None:
        raise AdapterError(
            "ADDRESS_BOOK_NOT_FOUND",
            f"Thunderbird address book not found: {requested_name}",
            {"available": sorted(item[0] for item in books.values())},
            404,
        )
    display_name, filename = selected
    database = profile / filename
    if not database.is_file():
        raise AdapterError(
            "PATH_NOT_FOUND",
            f"address book database does not exist: {database}",
            http_status=404,
        )
    return display_name, database


def export_contacts_csv(
    profile: Path, address_book: str, output_path: Path
) -> dict[str, Any]:
    output_path = output_path.expanduser()
    if not output_path.is_absolute():
        raise AdapterError(
            "INVALID_REQUEST", "output_path must be absolute or begin with ~/"
        )
    if output_path.suffix.casefold() != ".csv":
        raise AdapterError(
            "INVALID_REQUEST", "contacts.export_csv requires a .csv output_path"
        )
    display_name, database = _address_book_database(profile, address_book)
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True, timeout=30)
    try:
        rows = connection.execute(
            "SELECT card, name, value FROM properties ORDER BY rowid"
        ).fetchall()
    finally:
        connection.close()
    grouped: dict[str, dict[str, str]] = {}
    for card, name, value in rows:
        grouped.setdefault(str(card), {})[str(name)] = (
            "" if value is None else str(value)
        )
    if not grouped:
        raise AdapterError(
            "ADDRESS_BOOK_EMPTY",
            f"address book has no contacts: {display_name}",
            http_status=422,
        )
    contacts = [_contact_from_properties(properties) for properties in grouped.values()]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow([header for header, _key in CONTACT_CSV_FIELDS])
    for contact in contacts:
        writer.writerow([contact.get(key, "") for _header, key in CONTACT_CSV_FIELDS])
    _atomic_write(output_path, stream.getvalue())
    return {
        "address_book": display_name,
        "database": str(database),
        "output_path": str(output_path),
        "contact_count": len(contacts),
        "columns": [header for header, _key in CONTACT_CSV_FIELDS],
    }


def remove_account(
    profile: Path, email: str, hostname: str | None = None
) -> dict[str, Any]:
    prefs_path = profile / "prefs.js"
    prefs = read_preferences(prefs_path)
    server_ids = {
        match.group(1)
        for key, value in prefs.items()
        if value == email
        and (match := re.match(r"mail\.server\.(server\d+)\.userName$", key))
    }
    resolved_hostnames = {
        str(prefs.get(f"mail.server.{server_id}.hostname", "")).strip()
        for server_id in server_ids
    }
    resolved_hostnames.discard("")
    if hostname:
        resolved_hostnames.add(hostname)

    logins_path = profile / "logins.json"
    removed_logins = 0
    if logins_path.is_file():
        data = json.loads(logins_path.read_text(encoding="utf-8"))
        before = list(data.get("logins", []))
        domains = {".".join(value.split(".")[-2:]) for value in resolved_hostnames}
        kept = [
            item
            for item in before
            if not any(domain in str(item.get("hostname", "")) for domain in domains)
        ]
        removed_logins = len(before) - len(kept)
        data["logins"] = kept
        _atomic_write(
            logins_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        )
    identities = {
        match.group(1)
        for key, value in prefs.items()
        if value == email
        and (match := re.match(r"mail\.identity\.(id\d+)\.useremail$", key))
    }
    accounts = {
        match.group(1)
        for key, value in prefs.items()
        if key.startswith("mail.account.")
        and (match := re.match(r"mail\.account\.(account\d+)\.server$", key))
        and value in server_ids
    }
    prefixes = [
        *(f"mail.server.{item}." for item in server_ids),
        *(f"mail.identity.{item}." for item in identities),
        *(f"mail.account.{item}." for item in accounts),
    ]
    update_preferences(prefs_path, remove_prefixes=prefixes)
    updated = read_preferences(prefs_path)
    account_list = [
        item
        for item in str(updated.get("mail.accountmanager.accounts", "")).split(",")
        if item and item not in accounts
    ]
    values: dict[str, Any] = {"mail.accountmanager.accounts": ",".join(account_list)}
    if updated.get("mail.accountmanager.defaultaccount") in accounts:
        values["mail.accountmanager.defaultaccount"] = (
            account_list[0] if account_list else ""
        )
    update_preferences(prefs_path, values)
    return {
        "profile": str(profile),
        "email": email,
        "hostname": hostname,
        "hostnames": sorted(resolved_hostnames),
        "removed_logins": removed_logins,
        "removed_accounts": sorted(accounts),
        "removed_servers": sorted(server_ids),
        "removed_identities": sorted(identities),
    }
