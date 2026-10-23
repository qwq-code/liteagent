from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .profile import find_profile, read_preferences, resolve_filter_rules_path
from .ui import accessibility_state


def _result(
    passed: bool, check: dict[str, Any], observed: Any, expected: Any, details: str = ""
) -> dict[str, Any]:
    return {
        "passed": passed,
        "check": check,
        "observed_state": observed,
        "expected_state": expected,
        "error_code": None if passed else "VERIFICATION_FAILED",
        "details": details,
    }


def verify_check(check: dict[str, Any]) -> dict[str, Any]:
    profile = (
        find_profile(check.get("profile")) if check["type"] != "accessibility" else None
    )
    kind = check["type"]
    if kind == "preferences":
        observed = read_preferences(profile / "prefs.js")
        expected = dict(check.get("values", {}))
        absent = list(check.get("absent", []))
        passed = all(
            observed.get(key) == value for key, value in expected.items()
        ) and all(key not in observed for key in absent)
        return _result(
            passed,
            check,
            {
                "values": {key: observed.get(key) for key in expected},
                "absent_present": [key for key in absent if key in observed],
            },
            {"values": expected, "absent": absent},
        )
    if kind == "json_path":
        data = json.loads((profile / check["path"]).read_text(encoding="utf-8"))
        observed: Any = data
        for key in check["keys"]:
            observed = observed.get(key) if isinstance(observed, dict) else None
        return _result(observed == check["value"], check, observed, check["value"])
    if kind == "folders":
        root = profile / "Mail" / "Local Folders"
        observed = {
            name: {
                "mbox": (root / name).is_file(),
                "index": (root / f"{name}.msf").is_file(),
            }
            for name in check["names"]
        }
        return _result(
            all(item["mbox"] and item["index"] for item in observed.values()),
            check,
            observed,
            True,
        )
    if kind == "filters":
        text = resolve_filter_rules_path(profile).read_text(encoding="utf-8")
        expected = check["filters"]

        def serialized(value: Any) -> str:
            return str(value).replace("\\", "\\\\").replace('"', '\\"')

        blocks: list[list[str]] = []
        for line in text.splitlines():
            if line.startswith("name="):
                blocks.append([])
            if blocks:
                blocks[-1].append(line)
        passed = all(
            any(all(f'{key}="{serialized(value)}"' in block for key, value in item.items()) for block in blocks)
            for item in expected
        )
        return _result(passed, check, text, expected)
    if kind == "exported_eml":
        root = Path(check["destination"]).expanduser()
        observed = (
            sorted(path.name for path in root.glob("*.eml")) if root.is_dir() else []
        )
        filenames = list(check.get("filenames", []))
        subjects = list(check.get("subjects", []))
        expected = {"filenames": filenames, "subjects": subjects}
        passed = all(name in observed for name in filenames) and all(
            any(name.startswith(subject) for name in observed) for subject in subjects
        )
        return _result(passed, check, observed, expected)
    if kind == "exported_contacts":
        path = Path(check["path"]).expanduser()
        rows = []
        if path.is_file():
            with path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.reader(stream))
        observed = {
            "path": str(path),
            "columns": rows[0] if rows else [],
            "contact_count": max(0, len(rows) - 1),
        }
        expected = {
            "columns": list(check["columns"]),
            "contact_count": int(check["contact_count"]),
        }
        return _result(
            observed["columns"] == expected["columns"]
            and observed["contact_count"] == expected["contact_count"],
            check,
            observed,
            expected,
        )
    if kind == "attachment_file":
        path = Path(check["path"]).expanduser()
        observed = {
            "path": str(path),
            "exists": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else None,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
            if path.is_file()
            else None,
        }
        expected = {
            "path": str(path),
            "size_bytes": int(check["size_bytes"]),
            "sha256": str(check["sha256"]),
        }
        return _result(
            observed["exists"]
            and observed["size_bytes"] == expected["size_bytes"]
            and observed["sha256"] == expected["sha256"],
            check,
            observed,
            expected,
        )
    if kind == "account_removed":
        data = json.loads((profile / "logins.json").read_text(encoding="utf-8"))
        hostnames = list(check.get("hostnames", []))
        if check.get("hostname"):
            hostnames.append(str(check["hostname"]))
        domains = {".".join(hostname.split(".")[-2:]) for hostname in hostnames}
        matching = [
            item
            for item in data.get("logins", [])
            if any(domain in str(item.get("hostname", "")) for domain in domains)
        ]
        prefs = read_preferences(profile / "prefs.js")
        account_values = [
            value
            for key, value in prefs.items()
            if key.endswith(".userName") or key.endswith(".useremail")
        ]
        observed = {"matching_logins": matching, "account_values": account_values}
        return _result(
            not matching and check["email"] not in account_values,
            check,
            observed,
            "account and credentials absent",
        )
    if kind == "accessibility":
        observed = accessibility_state(check["kind"], check["value"])
        return _result(observed["matched"], check, observed, True)
    return _result(False, check, None, None, "unsupported verifier")


def verify_specs(checks: list[dict[str, Any]]) -> dict[str, Any]:
    results = [verify_check(check) for check in checks]
    return {
        "passed": all(item["passed"] for item in results),
        "checks": results,
        "observed_state": [item["observed_state"] for item in results],
        "expected_state": [item["expected_state"] for item in results],
        "error_code": None
        if all(item["passed"] for item in results)
        else "VERIFICATION_FAILED",
        "details": "all checks passed"
        if all(item["passed"] for item in results)
        else "one or more checks failed",
    }
