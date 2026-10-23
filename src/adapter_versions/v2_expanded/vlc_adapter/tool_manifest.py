from __future__ import annotations

from typing import Any


STRICT_ACTION_PARAM_SCHEMAS: dict[str, dict[str, Any]] = {
    "playback.status": {
        "description": (
            "Read playback state, time, position and the current media source. source is "
            "an absolute local path or a stream URI observed in VLC's playlist; source_uri "
            "retains the original URI. A null source is unknown, with source_error when "
            "lookup failed. metadata.filename and title are display labels, not file paths. "
            "time_seconds is the matching player's fractional playback position from "
            "native position_microseconds; preserve its precision when selecting a media "
            "time. time is only whole seconds. If precise time is unavailable, time_error "
            "explains why; do not treat whole seconds as an exact video frame."
        ),
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
    "preferences.configure": {
        "properties": {
            "global_play_pause_hotkey": {
                "type": "string",
                "minLength": 1,
                "description": "VLC global Play/Pause key name, for example Media Play Pause.",
            },
            "maximum_volume_percent": {
                "type": "integer",
                "minimum": 0,
                "maximum": 300,
                "description": "Maximum volume shown by the VLC Qt interface, as a percentage.",
            },
            "volume_slider_color": {
                "type": "string",
                "pattern": "^#[0-9A-Fa-f]{6}$",
                "description": "One #RRGGBB color applied to all VLC volume-slider states.",
            },
            "minimal_interface": {
                "type": "boolean",
                "description": "True hides the normal playback controls in window mode.",
            },
            "exit_after_playback": {
                "type": "boolean",
                "description": "Whether VLC exits automatically when playback ends.",
            },
            "allow_multiple_instances": {
                "type": "boolean",
                "description": "Whether desktop-opened files may start independent VLC instances.",
            },
            "show_background_cone": {
                "type": "boolean",
                "description": "Whether the VLC cone is shown in the empty-player background.",
            },
            "recording_directory": {
                "type": "string",
                "minLength": 1,
                "pattern": "^/.*",
                "description": (
                    "Explicit absolute directory where VLC stores recordings, for example "
                    "/srv/media/captures. Use recording_location instead when the request "
                    "names a standard user directory without an absolute path."
                ),
            },
            "recording_location": {
                "type": "string",
                "enum": ["desktop", "downloads", "videos", "music", "home"],
                "description": (
                    "Standard directory under the active user's home. Select this when the "
                    "request says Desktop, Downloads, Videos, Music, or the home directory "
                    "without giving an absolute path."
                ),
            },
        },
        "required": [],
        "oneOf": [
            {"required": ["global_play_pause_hotkey"]},
            {"required": ["maximum_volume_percent"]},
            {"required": ["volume_slider_color"]},
            {"required": ["minimal_interface"]},
            {"required": ["exit_after_playback"]},
            {"required": ["allow_multiple_instances"]},
            {"required": ["show_background_cone"]},
            {"required": ["recording_directory"]},
            {"required": ["recording_location"]},
        ],
        "additionalProperties": False,
    },
    "playback.find_local": {
        "description": (
            "Find existing local media files or directories under model-selected roots. "
            "Use this read-only discovery step before playback.open when the exact source path "
            "is unknown; it never chooses a file or starts playback."
        ),
        "properties": {
            "roots": {
                "type": "array", "minItems": 1, "maxItems": 8,
                "items": {"type": "string", "minLength": 1, "pattern": "^(?:/.*|~/.*|~$)"},
                "description": "Linux directories selected by the model, such as ~/Desktop; do not use Windows C:\\ paths or placeholders.",
            },
            "name_patterns": {
                "type": "array", "minItems": 1, "maxItems": 16,
                "items": {"type": "string", "minLength": 1},
                "description": (
                    "Optional basename globs; omit this field to search all names "
                    "with the default * pattern. When a desktop label is truncated "
                    "with ..., search by extension (for example *.mp4) or omit "
                    "this field; do not use the ellipsis as a literal filename."
                ),
            },
            "kind": {"type": "string", "enum": ["file", "directory", "any"]},
            "recursive": {"type": "boolean"},
            "include_hidden": {"type": "boolean"},
            "max_depth": {"type": "integer", "minimum": 1, "maximum": 8},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 200},
        },
        "required": ["roots"],
        "additionalProperties": False,
    },
    "playback.open": {
        "description": (
            "Open exactly one model-selected local media path or HTTP(S) stream. Use the "
            "generic filesystem.find tool first when a local path is not known; this action "
            "does not search directories or choose among candidate files."
        ),
        "properties": {
            "source": {
                "type": "string",
                "minLength": 1,
                "description": "Exact local media path returned by observation, or an explicit HTTP(S) URL.",
            },
            "loop": {
                "type": "boolean",
                "description": "Whether VLC should loop this media; defaults to false.",
            },
        },
        "required": ["source"],
        "additionalProperties": False,
    },
    "media.flip_video": {
        "description": (
            "Flip one complete local video and save a new MP4. Choose vertical to reverse "
            "top and bottom for an upside-down flipped picture; choose horizontal only "
            "for a left/right mirror image. This does not trim or select a clip."
        ),
        "properties": {
            "input_path": {
                "type": "string", "minLength": 1,
                "description": "Absolute path of the existing source video.",
            },
            "output_path": {
                "type": "string", "minLength": 1, "pattern": r"^/.*\.[mM][pP]4$",
                "description": "Distinct absolute .mp4 output path selected from the request.",
            },
            "axis": {
                "type": "string", "enum": ["vertical", "horizontal"],
                "description": (
                    "vertical reverses top/bottom; horizontal mirrors left/right. "
                    "Select exactly one axis."
                ),
            },
        },
        "required": ["input_path", "output_path", "axis"],
        "additionalProperties": False,
    },
}
