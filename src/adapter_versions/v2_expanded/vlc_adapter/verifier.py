from __future__ import annotations

from pathlib import Path
from typing import Any

from .actions import (
    inspect_subtitle,
    probe_media,
    status_flag,
    status_matches_source,
    window_state,
)
from .command import CommandRunner
from .config import VLC_CONFIG_PATH, read_config
from .errors import AdapterError
from .vlc_http import read_status


def _check(
    spec: dict[str, Any], context: dict[str, Any], runner: CommandRunner
) -> dict[str, Any]:
    check_type = spec["type"]
    if check_type == "config":
        path = Path(spec.get("path", VLC_CONFIG_PATH))
        observed = read_config(path)
        expected = {str(key): str(value) for key, value in dict(spec["values"]).items()}
        passed = all(observed.get(key) == value for key, value in expected.items())
    elif check_type == "local_discovery":
        observed = context
        expected = {"matches": "list of discovered paths"}
        matches = observed.get("matches")
        returned_count = observed.get("returned_count")
        match_count = observed.get("match_count")
        passed = (
            isinstance(matches, list)
            and isinstance(returned_count, int)
            and not isinstance(returned_count, bool)
            and isinstance(match_count, int)
            and not isinstance(match_count, bool)
            and returned_count == len(matches)
            and match_count >= returned_count
            and all(
                isinstance(item, dict)
                and isinstance(item.get("path"), str)
                and bool(item["path"])
                for item in matches
            )
        )
    elif check_type == "status":
        observed = read_status()
        expected = {"state": "valid VLC state"}
        passed = observed.get("state") in {"stopped", "playing", "paused"}
    elif check_type == "playback":
        observed = read_status()
        expected = {
            "source": spec["source"],
            "state": "playing",
            "loop": bool(spec.get("loop", False)),
        }
        passed = observed.get("state") == "playing" and status_matches_source(
            observed, spec["source"]
        )
        passed = passed and status_flag(observed.get("loop")) == expected["loop"]
    elif check_type == "window_fullscreen":
        observed = window_state(runner)
        expected = {"enabled": bool(spec["enabled"])}
        passed = False
        if observed["screen"] and observed["windows"]:
            window = observed["windows"][0]
            fullscreen = (
                window["width"] == observed["screen"]["width"]
                and window["height"] == observed["screen"]["height"]
            )
            passed = fullscreen == expected["enabled"]
    elif check_type == "media":
        path = Path(spec.get("path") or context.get("output_path", ""))
        observed = probe_media(runner, path)
        expected = {"path": str(path), "stream_type": spec["stream_type"]}
        passed = path.is_file() and path.stat().st_size > 0
        passed = passed and any(
            stream.get("codec_type") == spec["stream_type"]
            for stream in observed.get("streams", [])
        )
    elif check_type == "subtitle":
        path = Path(spec.get("path") or context.get("output_path", ""))
        observed = inspect_subtitle(path)
        expected = {
            "path": str(path),
            "sha256": spec.get("sha256"),
            "cue_count": spec.get("cue_count"),
        }
        passed = (
            observed["sha256"] == expected["sha256"]
            and observed["cue_count"] == expected["cue_count"]
        )
    elif check_type == "wallpaper":
        expected_path = Path(
            spec.get("path") or context.get("output_path", "")
        ).resolve()
        result = runner.run(
            ["gsettings", "get", "org.gnome.desktop.background", "picture-uri"],
            check=False,
            timeout=10,
        )
        raw = result["stdout"].strip().strip("'")
        observed_path = Path(raw.removeprefix("file://")).resolve() if raw else None
        observed = {"uri": raw, "path": str(observed_path) if observed_path else None}
        expected = {"path": str(expected_path)}
        passed = observed_path == expected_path and expected_path.is_file()
    else:
        raise AdapterError(
            "INVALID_REQUEST", f"unsupported verifier type: {check_type}"
        )
    return {
        "type": check_type,
        "passed": passed,
        "observed": observed,
        "expected": expected,
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
        except (AdapterError, OSError, ValueError, KeyError) as exc:
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
