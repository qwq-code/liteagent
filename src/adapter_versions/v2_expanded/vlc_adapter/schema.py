from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .errors import AdapterError


ADAPTER_NAME = "vlc"
MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 900_000
DEFAULT_TIMEOUT_MS = 60_000

ACTIONS = frozenset(
    {
        "config.update",
        "preferences.configure",
        "playback.open",
        "playback.find_local",
        "playback.status",
        "window.set_fullscreen",
        "media.extract_audio",
        "media.extract_subtitles",
        "media.transcode_clip",
        "media.flip_video",
        "media.extract_frame",
    }
)

VERIFY_TYPES = frozenset(
    {
        "config",
        "status",
        "playback",
        "window_fullscreen",
        "media",
        "subtitle",
        "wallpaper",
    }
)


@dataclass(frozen=True)
class ActionRequest:
    request_id: str
    adapter: str
    action: str
    timeout_ms: int
    params: dict[str, Any]
    verify: list[dict[str, Any]]

    def to_worker_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action,
            "timeout_ms": self.timeout_ms,
            "params": self.params,
            "verify": self.verify,
        }


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise AdapterError("INVALID_REQUEST", f"{field} must be an object")
    return dict(value)


def _string(data: Mapping[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(
            "INVALID_REQUEST", f"params.{field} must be a non-empty string"
        )
    return value


def _boolean(data: Mapping[str, Any], field: str) -> None:
    if not isinstance(data.get(field), bool):
        raise AdapterError("INVALID_REQUEST", f"params.{field} must be a boolean")


def _integer(data: Mapping[str, Any], field: str, minimum: int, maximum: int) -> int:
    value = data.get(field)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            f"params.{field} must be an integer from {minimum} to {maximum}",
        )
    return value


def _number(
    data: Mapping[str, Any],
    field: str,
    minimum: float,
    maximum: float,
    *,
    exclusive_minimum: bool = False,
) -> float:
    value = data.get(field)
    valid_type = isinstance(value, (int, float)) and not isinstance(value, bool)
    numeric = float(value) if valid_type else None
    valid_minimum = bool(
        numeric is not None
        and (numeric > minimum if exclusive_minimum else numeric >= minimum)
    )
    if numeric is None or not valid_minimum or numeric > maximum:
        comparison = "greater than" if exclusive_minimum else "at least"
        raise AdapterError(
            "INVALID_REQUEST",
            f"params.{field} must be a number {comparison} {minimum} and at most {maximum}",
        )
    return numeric


def _verification(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AdapterError("INVALID_REQUEST", "verify must be an array")
    checks = []
    for index, raw in enumerate(value):
        check = _mapping(raw, f"verify[{index}]")
        if check.get("type") not in VERIFY_TYPES:
            raise AdapterError(
                "INVALID_REQUEST",
                f"verify[{index}].type is unsupported",
                {"type": check.get("type")},
            )
        checks.append(check)
    return checks


def validate_action_params(action: str, params: Mapping[str, Any]) -> None:
    if action == "config.update":
        values = params.get("values")
        if not isinstance(values, Mapping) or not values:
            raise AdapterError(
                "INVALID_REQUEST", "params.values must be a non-empty object"
            )
        for key, value in values.items():
            if not isinstance(key, str) or not key.strip():
                raise AdapterError(
                    "INVALID_REQUEST", "params.values keys must be non-empty strings"
                )
            if not isinstance(value, (str, int, bool)):
                raise AdapterError(
                    "INVALID_REQUEST", f"params.values.{key} must be scalar"
                )
    elif action == "preferences.configure":
        allowed = {
            "global_play_pause_hotkey",
            "maximum_volume_percent",
            "volume_slider_color",
            "minimal_interface",
            "exit_after_playback",
            "allow_multiple_instances",
            "show_background_cone",
            "recording_directory",
            "recording_location",
        }
        unknown = sorted(set(params) - allowed)
        if unknown:
            raise AdapterError(
                "INVALID_REQUEST",
                "preferences.configure contains unsupported fields",
                {"unsupported_fields": unknown},
            )
        if not params:
            raise AdapterError(
                "INVALID_REQUEST", "preferences.configure requires at least one setting"
            )
        semantic_fields = {
            "global_play_pause_hotkey", "maximum_volume_percent", "volume_slider_color",
            "minimal_interface", "exit_after_playback", "allow_multiple_instances",
            "show_background_cone", "recording_directory", "recording_location",
        }
        if sum(field in params for field in semantic_fields) != 1:
            raise AdapterError(
                "INVALID_REQUEST", "preferences.configure accepts exactly one semantic setting per call",
                {"fields": sorted(field for field in semantic_fields if field in params),
                 "retry": "Call preferences.configure once for each independent setting"},
            )
        if "global_play_pause_hotkey" in params:
            _string(params, "global_play_pause_hotkey")
        if "maximum_volume_percent" in params:
            _integer(params, "maximum_volume_percent", 0, 300)
        if "volume_slider_color" in params:
            color = _string(params, "volume_slider_color")
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.volume_slider_color must be a #RRGGBB color",
                )
        if "minimal_interface" in params:
            _boolean(params, "minimal_interface")
        if "exit_after_playback" in params:
            _boolean(params, "exit_after_playback")
        if "allow_multiple_instances" in params:
            _boolean(params, "allow_multiple_instances")
        if "show_background_cone" in params:
            _boolean(params, "show_background_cone")
        if "recording_directory" in params:
            path = _string(params, "recording_directory")
            if not path.startswith("/"):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.recording_directory must be an absolute path",
                )
        if "recording_location" in params:
            location = _string(params, "recording_location")
            if location not in {"desktop", "downloads", "videos", "music", "home"}:
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.recording_location must name a standard user directory",
                )
        if "recording_directory" in params and "recording_location" in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "preferences.configure accepts either recording_directory or "
                "recording_location, not both",
            )
    elif action == "playback.find_local":
        roots = params.get("roots")
        if not isinstance(roots, list) or not roots or len(roots) > 8:
            raise AdapterError("INVALID_REQUEST", "params.roots must be a non-empty list of at most 8 paths")
        if any(not isinstance(root, str) or not root.strip() or not (root.startswith("/") or root.startswith("~/") or root == "~") for root in roots):
            raise AdapterError("INVALID_REQUEST", "params.roots must contain absolute or ~/ paths")
        patterns = params.get("name_patterns", ["*"])
        if not isinstance(patterns, list) or not patterns or len(patterns) > 16:
            raise AdapterError("INVALID_REQUEST", "params.name_patterns must be a non-empty list of at most 16 globs")
        if any(not isinstance(pattern, str) or not pattern.strip() or Path(pattern).name != pattern for pattern in patterns):
            raise AdapterError("INVALID_REQUEST", "params.name_patterns must contain basename globs")
        for field in ("recursive", "include_hidden"):
            if field in params:
                _boolean(params, field)
        for field, minimum, maximum in (("max_depth", 1, 8), ("max_results", 1, 200)):
            if field in params:
                _integer(params, field, minimum, maximum)
        if params.get("kind", "file") not in {"file", "directory", "any"}:
            raise AdapterError("INVALID_REQUEST", "params.kind must be file, directory, or any")
    elif action == "playback.open":
        allowed = {"source", "loop"}
        unknown = sorted(set(params) - allowed)
        if unknown:
            raise AdapterError(
                "INVALID_REQUEST",
                "playback.open contains unsupported fields",
                {"unsupported_fields": unknown, "allowed": sorted(allowed)},
            )
        _string(params, "source")
        if "loop" in params and not isinstance(params["loop"], bool):
            raise AdapterError("INVALID_REQUEST", "params.loop must be a boolean")
    elif action == "playback.status":
        if params:
            raise AdapterError("INVALID_REQUEST", "playback.status takes no parameters")
    elif action == "window.set_fullscreen":
        _boolean(params, "enabled")
    elif action == "media.extract_audio":
        _string(params, "input_path")
        _string(params, "output_path")
        unknown = sorted(set(params) - {"input_path", "output_path"})
        if unknown:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{action} contains unsupported fields",
                {"unsupported_fields": unknown},
            )
    elif action == "media.extract_subtitles":
        _string(params, "input_path")
        _string(params, "output_path")
        if "subtitle_stream_index" in params:
            _integer(params, "subtitle_stream_index", 0, 1024)
    elif action == "media.transcode_clip":
        _string(params, "input_path")
        _string(params, "output_path")
        _number(params, "start_time_seconds", 0, 86_400)
        _number(
            params,
            "duration_seconds",
            0,
            86_400,
            exclusive_minimum=True,
        )
        if "frame_rate" in params:
            _number(params, "frame_rate", 1, 60)
    elif action == "media.flip_video":
        allowed = {"input_path", "output_path", "axis"}
        unknown = sorted(set(params) - allowed)
        if unknown:
            raise AdapterError(
                "INVALID_REQUEST",
                "media.flip_video accepts one axis and one input/output video pair",
                {"conflicting_fields": unknown, "allowed": sorted(allowed)},
            )
        _string(params, "input_path")
        _string(params, "output_path")
        if params.get("axis") not in {"vertical", "horizontal"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.axis must be vertical (top/bottom) or horizontal (left/right)",
                {"axis": params.get("axis")},
            )
        if Path(params["input_path"]).expanduser().resolve() == Path(
            params["output_path"]
        ).expanduser().resolve():
            raise AdapterError(
                "INVALID_REQUEST",
                "media.flip_video requires a separate output_path; keep input_path unchanged",
            )
    elif action == "media.extract_frame":
        allowed = {"input_path", "output_path", "frame_index", "time_seconds"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "media.extract_frame received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        _string(params, "input_path")
        _string(params, "output_path")
        has_frame_index = "frame_index" in params
        has_time_seconds = "time_seconds" in params
        if has_frame_index == has_time_seconds:
            raise AdapterError(
                "INVALID_REQUEST",
                "params requires exactly one of frame_index or time_seconds",
            )
        if has_frame_index:
            _integer(params, "frame_index", 0, 10_000_000)
        else:
            _number(params, "time_seconds", 0, 86_400)


def parse_action_request(raw: Any) -> ActionRequest:
    data = _mapping(raw, "request")
    action = data.get("action")
    if action not in ACTIONS:
        raise AdapterError(
            "UNSUPPORTED_ACTION", "unsupported VLC action", {"action": action}
        )
    adapter = data.get("adapter", ADAPTER_NAME)
    if adapter != ADAPTER_NAME:
        raise AdapterError("INVALID_REQUEST", f"adapter must be {ADAPTER_NAME}")
    request_id = data.get("request_id") or str(uuid4())
    if not isinstance(request_id, str) or not request_id.strip():
        raise AdapterError("INVALID_REQUEST", "request_id must be a non-empty string")
    timeout_ms = data.get("timeout_ms", DEFAULT_TIMEOUT_MS)
    if (
        isinstance(timeout_ms, bool)
        or not isinstance(timeout_ms, int)
        or not MIN_TIMEOUT_MS <= timeout_ms <= MAX_TIMEOUT_MS
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            f"timeout_ms must be from {MIN_TIMEOUT_MS} to {MAX_TIMEOUT_MS}",
        )
    params = _mapping(data.get("params"), "params")
    validate_action_params(action, params)
    return ActionRequest(
        request_id=request_id,
        adapter=adapter,
        action=action,
        timeout_ms=timeout_ms,
        params=params,
        verify=_verification(data.get("verify")),
    )
