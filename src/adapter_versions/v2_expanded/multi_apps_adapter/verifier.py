from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any
from urllib.request import urlopen


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_check(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    with path.open("rb") as stream:
        magic = stream.read(8)
    if suffix in {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".zip", ".epub"}:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            return {
                "type": "zip_container",
                "passed": bad is None,
                "member_count": len(archive.namelist()),
                "bad_member": bad,
            }
    if suffix == ".pdf":
        return {"type": "pdf_magic", "passed": magic.startswith(b"%PDF-")}
    signatures = {
        ".png": b"\x89PNG\r\n\x1a\n",
        ".jpg": b"\xff\xd8\xff",
        ".jpeg": b"\xff\xd8\xff",
        ".gif": b"GIF8",
    }
    if suffix in signatures:
        return {"type": "image_magic", "passed": magic.startswith(signatures[suffix])}
    return {"type": "nonempty", "passed": path.stat().st_size > 0}


def verify_file(path_value: str, expected_sha256: str | None = None) -> dict[str, Any]:
    path = Path(path_value)
    checks = [{"type": "exists", "passed": path.is_file()}]
    observed: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
    if path.is_file():
        observed.update({"size": path.stat().st_size, "sha256": sha256_file(path)})
        checks.append({"type": "nonempty", "passed": path.stat().st_size > 0})
        try:
            checks.append(_format_check(path))
        except Exception as exc:
            checks.append(
                {
                    "type": "format",
                    "passed": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        if expected_sha256:
            checks.append(
                {
                    "type": "sha256",
                    "passed": observed["sha256"] == expected_sha256,
                    "expected": expected_sha256,
                }
            )
    passed = all(check.get("passed") for check in checks)
    return {
        "passed": passed,
        "checks": checks,
        "observed_state": observed,
        "expected_state": {"path": str(path), "sha256": expected_sha256},
        "error_code": None if passed else "FILE_VERIFICATION_FAILED",
        "details": None if passed else "one or more file checks failed",
    }


def verify_adapter_health(url: str, timeout: float) -> dict[str, Any]:
    try:
        with urlopen(url.rstrip("/") + "/health", timeout=timeout) as response:
            payload = json.load(response)
        passed = payload.get("status") == "ok"
        return {"passed": passed, "url": url, "observed_state": payload}
    except Exception as exc:
        return {"passed": False, "url": url, "error": f"{type(exc).__name__}: {exc}"}


def verify_checks(checks: list[dict[str, Any]], timeout: float = 10) -> dict[str, Any]:
    rows = []
    for check in checks:
        check_type = check.get("type")
        if check_type == "file":
            rows.append(verify_file(check["path"], check.get("sha256")))
        elif check_type == "files":
            children = [verify_file(path) for path in check.get("paths", [])]
            rows.append(
                {
                    "passed": bool(children)
                    and all(item["passed"] for item in children),
                    "checks": children,
                }
            )
        elif check_type == "adapter_health":
            rows.append(verify_adapter_health(check["url"], timeout))
        else:
            rows.append(
                {"passed": False, "error": f"unsupported check type: {check_type}"}
            )
    passed = bool(rows) and all(row.get("passed") for row in rows)
    return {
        "passed": passed,
        "checks": rows,
        "observed_state": rows,
        "expected_state": checks,
        "error_code": None if passed else "STATE_VERIFICATION_FAILED",
        "details": None if passed else "one or more state checks failed",
    }
