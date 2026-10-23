from __future__ import annotations

import ast
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import time
import urllib.request
from pathlib import Path
from typing import Any

from .archive import inspect_zip
from .command import CommandRunner
from .desktop import mime_association_state
from .errors import AdapterError
from .permissions import PERMISSION_TARGET_SAMPLE_LIMIT


def path_state(path: str) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"path": str(target), "exists": False}
    info = target.lstat()
    return {
        "path": str(target),
        "exists": True,
        "is_file": target.is_file(),
        "is_directory": target.is_dir(),
        "is_symlink": target.is_symlink(),
        "mode": stat.S_IMODE(info.st_mode),
        "size_bytes": info.st_size,
        "owner_uid": info.st_uid,
        "owner_gid": info.st_gid,
    }


def directory_state(path: str, recursive: bool = False) -> dict[str, Any]:
    root = Path(path)
    if not root.is_dir():
        return {"path": str(root), "exists": root.exists(), "children": []}
    if recursive:
        children = sorted(
            str(item.relative_to(root)) for item in root.rglob("*") if item != root
        )
    else:
        children = sorted(item.name for item in root.iterdir())
    return {"path": str(root), "exists": True, "children": children}


def gsettings_value(runner: CommandRunner, schema: str, key: str) -> str:
    return runner.run(
        ["gsettings", "get", schema, key],
        error_code="SETTING_UNAVAILABLE",
        error_message="failed to read GNOME setting",
    )["stdout"].strip()


def trash_entries(runner: CommandRunner) -> list[dict[str, str]]:
    """Return the exact GIO trash identifiers without resolving a target."""
    listing = runner.run(["gio", "trash", "--list"], check=False)["stdout"]
    entries = []
    for line in listing.splitlines():
        fields = line.split("\t", 1)
        if len(fields) == 2:
            entries.append({"trash_uri": fields[0], "original_path": fields[1]})
    return sorted(
        entries, key=lambda item: (item["original_path"], item["trash_uri"])
    )


def volume_state(runner: CommandRunner, sink: str = "@DEFAULT_SINK@") -> dict[str, Any]:
    output = runner.run(
        ["pactl", "get-sink-volume", sink],
        error_code="AUDIO_UNAVAILABLE",
        error_message="failed to read sink volume",
    )["stdout"]
    percentages = [int(value) for value in re.findall(r"/\s*(\d+)%", output)]
    return {"sink": sink, "percentages": percentages, "raw": output.strip()}


def timezone_state(runner: CommandRunner) -> dict[str, Any]:
    timezone = runner.run(["timedatectl", "show", "--property=Timezone", "--value"])[
        "stdout"
    ].strip()
    status = runner.run(["timedatectl", "status"])["stdout"]
    offset_match = re.search(r"Time zone:.*\(([^,]+),\s*([+-]\d{4})\)", status)
    return {
        "timezone": timezone,
        "offset": offset_match.group(2) if offset_match else None,
        "status": status,
    }


TERMINAL_OUTPUT_TIMEOUT_SECONDS = 15.0


def terminal_output(
    url: str = "http://127.0.0.1:5000/terminal",
    *,
    timeout: float = TERMINAL_OUTPUT_TIMEOUT_SECONDS,
) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.load(response)
        return payload.get("output")
    except Exception:
        return None


def terminal_size_probe(
    runner: CommandRunner, columns: int, rows: int
) -> dict[str, Any]:
    destination = Path(f"/tmp/osworld-os-terminal-size-{os.getpid()}.txt")
    destination.unlink(missing_ok=True)
    title = f"OSWorld terminal size probe {os.getpid()}"
    runner.run(
        [
            "gnome-terminal",
            f"--title={title}",
            "--",
            "bash",
            "-lc",
            f"stty size > {destination}",
        ],
        timeout=10,
        error_code="TERMINAL_UNAVAILABLE",
        error_message="failed to open terminal size probe",
    )
    deadline = time.monotonic() + 10
    content = ""
    while time.monotonic() < deadline:
        if destination.is_file():
            content = destination.read_text(encoding="utf-8").strip()
            if content:
                break
        time.sleep(0.1)
    destination.unlink(missing_ok=True)
    return {"observed": content, "expected": f"{rows} {columns}"}


def user_state(runner: CommandRunner, username: str) -> dict[str, Any]:
    passwd = runner.run(["getent", "passwd", username], check=False)
    if passwd["returncode"] != 0 or not passwd["stdout"].strip():
        return {"username": username, "exists": False}
    fields = passwd["stdout"].strip().split(":")
    password_status = runner.sudo(
        ["passwd", "-S", username],
        error_code="USER_OPERATION_FAILED",
        error_message="failed to inspect account password status",
    )["stdout"].split()
    home = Path(fields[5])
    home_info = path_state(str(home))
    return {
        "username": username,
        "exists": True,
        "uid": int(fields[2]),
        "gid": int(fields[3]),
        "home": fields[5],
        "shell": fields[6],
        "password_status": password_status[1] if len(password_status) > 1 else None,
        "home_state": home_info,
    }


def package_state(
    runner: CommandRunner, package: str, executable: str | None = None
) -> dict[str, Any]:
    snap = runner.run(["snap", "list", package], check=False)
    executable_name = executable or package
    executable_path = shutil.which(executable_name)
    return {
        "package": package,
        "snap_installed": snap["returncode"] == 0,
        "snap_output": snap["stdout"].strip(),
        "executable": executable_name,
        "executable_path": executable_path,
    }


def clipboard_state(runner: CommandRunner) -> dict[str, Any]:
    if shutil.which("xsel"):
        backend = "xsel"
        argv = ["xsel", "--clipboard", "--output"]
    elif shutil.which("xclip"):
        backend = "xclip"
        argv = ["xclip", "-selection", "clipboard", "-out"]
    else:
        return {"available": False, "backend": None, "text": None}
    completed = runner.run(
        argv,
        check=False,
        error_code="CLIPBOARD_FAILED",
        error_message="failed to inspect the desktop clipboard",
    )
    return {
        "available": completed["returncode"] == 0,
        "backend": backend,
        "text": completed["stdout"] if completed["returncode"] == 0 else None,
        "returncode": completed["returncode"],
    }


def _check(
    spec: dict[str, Any], context: dict[str, Any], runner: CommandRunner
) -> dict[str, Any]:
    check_type = spec["type"]
    if check_type == "path":
        observed = path_state(
            str(spec.get("path") or context.get("path") or context.get("destination"))
        )
        passed = observed["exists"] == spec.get("exists", True)
        if spec.get("kind") == "file":
            passed = passed and observed.get("is_file", False)
        if spec.get("kind") == "directory":
            passed = passed and observed.get("is_directory", False)
    elif check_type == "filesystem_query":
        matches = context.get("matches")
        observed = {
            key: context.get(key)
            for key in (
                "roots",
                "name_patterns",
                "kind",
                "recursive",
                "max_depth",
                "match_count",
                "returned_count",
                "truncated",
            )
        }
        returned_count = context.get("returned_count")
        match_count = context.get("match_count")
        passed = (
            isinstance(matches, list)
            and isinstance(returned_count, int)
            and isinstance(match_count, int)
            and returned_count == len(matches)
            and 0 <= returned_count <= match_count
            and context.get("truncated") == (match_count > returned_count)
            and all(
                observed.get(key) == value
                for key, value in spec.items()
                if key != "type"
            )
            and all(Path(str(root)).is_dir() for root in context.get("roots", []))
        )
    elif check_type == "trash_listing":
        offset = int(spec["offset"])
        max_results = int(spec["max_results"])
        current = trash_entries(runner)
        page = current[offset : offset + max_results]
        observed = {
            "entries": page,
            "entry_count": len(current),
            "offset": offset,
            "max_results": max_results,
        }
        returned_count = len(page)
        truncated = offset + returned_count < len(current)
        passed = (
            context.get("entries") == page
            and context.get("entry_count") == len(current)
            and context.get("offset") == offset
            and context.get("max_results") == max_results
            and context.get("returned_count") == returned_count
            and context.get("truncated") == truncated
            and context.get("next_offset")
            == (offset + returned_count if truncated else None)
        )
    elif check_type == "desktop_favorites_listing":
        offset = int(spec["offset"])
        max_results = int(spec["max_results"])
        current = parse_favorites(
            gsettings_value(runner, "org.gnome.shell", "favorite-apps")
        )
        page = current[offset : offset + max_results]
        observed = {
            "favorites": page,
            "favorite_count": len(current),
            "offset": offset,
            "max_results": max_results,
        }
        returned_count = len(page)
        truncated = offset + returned_count < len(current)
        passed = (
            context.get("favorites") == page
            and context.get("favorite_count") == len(current)
            and context.get("offset") == offset
            and context.get("max_results") == max_results
            and context.get("returned_count") == returned_count
            and context.get("truncated") == truncated
            and context.get("next_offset")
            == (offset + returned_count if truncated else None)
        )
    elif check_type == "desktop_applications_query":
        applications = context.get("applications")
        prefixes = [f"{value.casefold()}/" for value in spec["mime_type_prefixes"]]
        max_results = int(spec["max_results"])
        mime_offset = int(spec["mime_offset"])
        page_size = int(spec["max_mime_types_per_application"])
        observed = {
            key: context.get(key)
            for key in (
                "query",
                "mime_type_prefixes",
                "max_results",
                "mime_offset",
                "max_mime_types_per_application",
                "match_count",
                "truncated",
                "applications",
            )
        }
        structurally_valid = isinstance(applications, list) and all(
            isinstance(item, dict)
            and isinstance(item.get("desktop_id"), str)
            and item["desktop_id"].endswith(".desktop")
            and isinstance(item.get("desktop_file"), str)
            and Path(item["desktop_file"]).is_file()
            and isinstance(item.get("mime_types"), list)
            and len(item["mime_types"]) == item.get("returned_mime_type_count")
            and len(item["mime_types"]) <= page_size
            and item.get("mime_offset") == mime_offset
            and all(
                isinstance(mime_type, str)
                and any(mime_type.casefold().startswith(prefix) for prefix in prefixes)
                for mime_type in item["mime_types"]
            )
            and isinstance(item.get("matching_mime_type_count"), int)
            and item["matching_mime_type_count"] > 0
            and (
                item["matching_mime_type_count"]
                >= mime_offset + len(item["mime_types"])
                if item["mime_types"]
                else mime_offset >= item["matching_mime_type_count"]
            )
            and item.get("mime_types_truncated")
            == (item.get("next_mime_offset") is not None)
            and (
                item.get("next_mime_offset") == mime_offset + len(item["mime_types"])
                if item.get("mime_types_truncated")
                else mime_offset + len(item["mime_types"])
                >= item["matching_mime_type_count"]
            )
            for item in applications
        )
        match_count = context.get("match_count")
        passed = (
            structurally_valid
            and context.get("query") == spec["query"]
            and context.get("mime_type_prefixes") == spec["mime_type_prefixes"]
            and context.get("max_results") == max_results
            and context.get("mime_offset") == mime_offset
            and context.get("max_mime_types_per_application") == page_size
            and isinstance(match_count, int)
            and 0 <= len(applications) <= min(match_count, max_results)
            and context.get("truncated") == (match_count > max_results)
            and len({item["desktop_id"] for item in applications}) == len(applications)
        )
    elif check_type == "pdf_outline_query":
        sections = context.get("sections")
        input_path = Path(str(spec["input_path"]))
        observed = {
            key: context.get(key)
            for key in (
                "input_path",
                "source_sha256",
                "source_page_count",
                "outline_level",
                "section_count",
                "offset",
                "max_sections",
                "returned_count",
                "truncated",
                "next_offset",
                "sections",
            )
        }
        structurally_valid = isinstance(sections, list) and all(
            isinstance(item, dict)
            and isinstance(item.get("index"), int)
            and isinstance(item.get("title"), str)
            and isinstance(item.get("start_page"), int)
            and isinstance(item.get("end_page"), int)
            and item["start_page"] <= item["end_page"]
            and item.get("page_count") == item["end_page"] - item["start_page"] + 1
            for item in sections
        )
        current_sha256 = None
        if input_path.is_file():
            digest = hashlib.sha256()
            with input_path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            current_sha256 = digest.hexdigest()
        returned_count = context.get("returned_count")
        section_count = context.get("section_count")
        offset = context.get("offset")
        passed = (
            structurally_valid
            and current_sha256 == spec["source_sha256"]
            and all(
                context.get(key) == value
                for key, value in spec.items()
                if key != "type"
            )
            and isinstance(returned_count, int)
            and returned_count == len(sections)
            and isinstance(section_count, int)
            and isinstance(offset, int)
            and context.get("truncated") == (offset + returned_count < section_count)
            and context.get("next_offset")
            == (offset + returned_count if context.get("truncated") else None)
        )
    elif check_type == "directory":
        observed = directory_state(str(spec["path"]), bool(spec.get("recursive")))
        expected = sorted(spec.get("children", []))
        passed = observed["exists"] and observed["children"] == expected
    elif check_type == "mode_tree":
        root = Path(str(spec["root"]))
        recursive = bool(spec.get("recursive", True))
        candidates = root.rglob("*") if recursive else root.iterdir()
        observed_modes = {}
        if root.is_dir():
            for path in sorted(candidates):
                try:
                    info = path.lstat()
                except FileNotFoundError:
                    continue
                if stat.S_ISREG(info.st_mode):
                    observed_modes[str(path.relative_to(root))] = stat.S_IMODE(
                        info.st_mode
                    )
        requested_mode = int(spec["mode"])
        mismatched = {
            path: mode
            for path, mode in observed_modes.items()
            if mode != requested_mode
        }
        sample_modes = dict(
            sorted(observed_modes.items())[:PERMISSION_TARGET_SAMPLE_LIMIT]
        )
        observed = {
            "target_count": len(observed_modes),
            "requested_mode": requested_mode,
            "mismatched_count": len(mismatched),
            "mismatched_samples": dict(
                sorted(mismatched.items())[:PERMISSION_TARGET_SAMPLE_LIMIT]
            ),
            "sample_modes": sample_modes,
            "samples_truncated": len(observed_modes) > PERMISSION_TARGET_SAMPLE_LIMIT,
        }
        passed = bool(observed_modes) and not mismatched
    elif check_type == "text":
        path = Path(str(spec["path"]))
        observed = path.read_text(encoding="utf-8") if path.is_file() else None
        passed = observed == spec.get("content")
    elif check_type == "archive_layout":
        old_dir = Path(str(spec["old_directory"]))
        new_dir = Path(str(spec["new_directory"]))
        archives = (
            sorted(path for path in old_dir.rglob("*.gz") if path.is_file())
            if old_dir.is_dir()
            else []
        )
        valid_archives = []
        for path in archives:
            try:
                with gzip.open(path, "rb") as stream:
                    stream.read(1)
                valid_archives.append(str(path))
            except OSError:
                pass
        new_files = (
            sorted(str(path) for path in new_dir.rglob("*") if path.is_file())
            if new_dir.is_dir()
            else []
        )
        observed = {
            "archives": [str(path) for path in archives],
            "valid_archives": valid_archives,
            "new_files": new_files,
        }
        passed = (
            bool(archives) and len(valid_archives) == len(archives) and bool(new_files)
        )
    elif check_type == "zip_archive":
        path = Path(str(spec["path"]))
        members = inspect_zip(path) if path.is_file() else []
        observed = {
            "path": str(path),
            "exists": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else None,
            "members": members,
        }
        expected_members = spec.get("members", [])
        observed_identity = [
            {
                "name": item["name"],
                "kind": item["kind"],
                "size_bytes": item["size_bytes"],
            }
            for item in members
        ]
        passed = path.is_file() and observed_identity == expected_members
    elif check_type == "trash_restored":
        original = str(spec["original_path"])
        trash_uri = str(spec["trash_uri"])
        current = trash_entries(runner)
        observed = {"path": path_state(original), "trash_entries": current}
        passed = (
            observed["path"]["exists"]
            and all(entry["trash_uri"] != trash_uri for entry in current)
            and context.get("original_path") == original
            and context.get("trash_uri") == trash_uri
        )
    elif check_type == "clipboard":
        observed = clipboard_state(runner)
        actual = observed["text"]
        if "max_chars" in spec:
            # Reading may intentionally return only a prefix. Verify that prefix
            # and the reported full length; writes still require exact equality.
            passed = (
                observed["available"]
                and isinstance(actual, str)
                and len(actual) == spec.get("character_count")
                and actual[:int(spec["max_chars"])] == spec.get("text")
            )
        else:
            passed = observed["available"] and actual == spec.get("text")
    elif check_type == "gsettings":
        observed = gsettings_value(runner, str(spec["schema"]), str(spec["key"]))
        passed = observed == str(spec["expected"])
        if not passed:
            try:
                actual_number = Decimal(observed)
                expected_number = Decimal(str(spec["expected"]))
                passed = (
                    actual_number.is_finite()
                    and expected_number.is_finite()
                    and abs(actual_number - expected_number) <= Decimal("1e-12")
                )
            except InvalidOperation:
                pass
    elif check_type == "mime_association":
        observed = mime_association_state(runner, spec["mime_types"])
        passed = bool(observed) and all(
            desktop_id == spec["desktop_id"] for desktop_id in observed.values()
        )
    elif check_type == "volume":
        observed = volume_state(runner, str(spec.get("sink", "@DEFAULT_SINK@")))
        passed = bool(observed["percentages"]) and all(
            value == int(spec["percent"]) for value in observed["percentages"]
        )
    elif check_type == "timezone":
        observed = timezone_state(runner)
        passed = observed["timezone"] == spec["timezone"]
        if "offset" in spec:
            passed = passed and observed["offset"] == spec["offset"]
    elif check_type == "terminal":
        marker = str(spec["contains"])
        terminal = context.get("terminal")
        # Context is this dispatch's result, not event history. A visible
        # command already observed its window and completion marker within
        # its deadline; repeating that accessibility probe can lose a valid
        # observation after the command has successfully finished.
        if (
            context.get("verified") is True
            and context.get("completion_marker") == marker
            and isinstance(context.get("terminal_output"), str)
            and isinstance(terminal, dict)
            and terminal.get("command_completed") is True
            and terminal.get("output_visible") is True
            and bool(terminal.get("windows"))
        ):
            observed = context["terminal_output"]
        else:
            observed = terminal_output()
        passed = observed is not None and marker in observed
    elif check_type == "terminal_launch":
        terminal = context.get("terminal")
        history = context.get("shell_history")
        observed = {
            "argv": context.get("argv"),
            "returncode": context.get("returncode"),
            "terminal_launched": (
                terminal.get("launched") if isinstance(terminal, dict) else None
            ),
            "terminal_windows": (
                terminal.get("windows") if isinstance(terminal, dict) else None
            ),
            "child_status": (
                terminal.get("child_status") if isinstance(terminal, dict) else None
            ),
            "shell_history_recorded": (
                history.get("recorded") if isinstance(history, dict) else False
            ),
        }
        expected_history = bool(spec.get("record_shell_history"))
        passed = (
            observed["argv"] == spec.get("argv")
            and observed["returncode"] in spec.get("returncodes", [0])
            and observed["terminal_launched"] is True
            and isinstance(observed["terminal_windows"], list)
            and bool(observed["terminal_windows"])
            and observed["child_status"] == "not_waited"
            and observed["shell_history_recorded"] is expected_history
        )
    elif check_type == "terminal_size":
        observed = terminal_size_probe(runner, int(spec["columns"]), int(spec["rows"]))
        passed = observed["observed"] == observed["expected"]
    elif check_type == "command_result":
        observed = {
            "argv": context.get("argv"),
            "cwd": context.get("cwd"),
            "returncode": context.get("returncode"),
            "stdout": context.get("stdout", ""),
            "stderr": context.get("stderr", ""),
            "duration_ms": context.get("duration_ms"),
        }
        expected_returncodes = spec.get("returncodes", [0])
        passed = observed["returncode"] in expected_returncodes
        if "argv" in spec:
            passed = passed and observed["argv"] == spec["argv"]
        for value in spec.get("stdout_contains", []):
            passed = passed and value in observed["stdout"]
        for value in spec.get("stdout_excludes", []):
            passed = passed and value not in observed["stdout"]
        for value in spec.get("stderr_contains", []):
            passed = passed and value in observed["stderr"]
        for value in spec.get("stderr_excludes", []):
            passed = passed and value not in observed["stderr"]
    elif check_type == "user":
        observed = user_state(runner, str(spec["username"]))
        passed = observed.get("exists", False)
        passed = passed and observed.get("home") == spec.get("home")
        passed = passed and observed.get("password_status") == "P"
        if "mode" in spec:
            passed = passed and observed.get("home_state", {}).get("mode") == int(
                spec["mode"]
            )
        passed = passed and observed.get("home_state", {}).get(
            "owner_uid"
        ) == observed.get("uid")
    elif check_type == "package":
        observed = package_state(runner, str(spec["package"]), spec.get("executable"))
        passed = observed["snap_installed"] and observed["executable_path"] is not None
    else:
        raise AdapterError(
            "INVALID_ARGUMENT", f"unsupported verifier type: {check_type}"
        )
    return {
        "type": check_type,
        "passed": passed,
        "observed": observed,
        "expected": spec,
    }


def verify_specs(
    specs: list[dict[str, Any]],
    context: dict[str, Any],
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    command = runner or CommandRunner()
    checks = []
    for spec in specs:
        try:
            checks.append(_check(spec, context, command))
        except (AdapterError, OSError, ValueError, KeyError, SyntaxError) as exc:
            checks.append(
                {
                    "type": spec.get("type"),
                    "passed": False,
                    "error": str(exc),
                    "expected": spec,
                }
            )
    passed = bool(checks) and all(check.get("passed", False) for check in checks)
    return {
        "passed": passed,
        "checks": checks,
        "observed_state": context,
        "expected_state": specs,
        "error_code": None if passed else "VERIFICATION_FAILED",
        "details": None if passed else "one or more checks failed",
    }


def parse_favorites(value: str) -> list[str]:
    parsed = ast.literal_eval(value)
    if not isinstance(parsed, list) or any(
        not isinstance(item, str) for item in parsed
    ):
        raise AdapterError(
            "SETTING_UNAVAILABLE", "favorite-apps is not a string list", value, 422
        )
    return parsed
