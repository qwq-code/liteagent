from __future__ import annotations

from typing import Any, Mapping

from .errors import AdapterError


LOCAL_PATH_PATTERN = r"^(?:/|~/)"

MEDIA_INSPECT_CURRENT_SCHEMA: dict[str, Any] = {
    "properties": {},
    "required": [],
}

MEDIA_EXTRACT_CURRENT_AUDIO_SCHEMA: dict[str, Any] = {
    "properties": {
        "output_path": {
            "type": "string",
            "minLength": 1,
            "pattern": r"^(?:/|~/).+\.(?:[mM][pP]3|[wW][aA][vV])$",
            "description": (
                "Exact absolute or ~/ destination ending in .mp3 or .wav. The source is "
                "the unique local media file currently playing in VLC; it is resolved from "
                "live application state rather than supplied as a path."
            ),
        },
    },
    "required": ["output_path"],
}

MEDIA_EXTRACT_CURRENT_FRAME_SCHEMA: dict[str, Any] = {
    "properties": {
        "timestamp": {
            "oneOf": [
                {"type": "number", "minimum": 0, "maximum": 86_400},
                {
                    "type": "string",
                    "minLength": 1,
                    "pattern": r"^\d+(?::[0-5]\d){0,2}(?:\.\d+)?$",
                },
            ],
            "description": (
                "Exact source-video time as seconds or MM:SS/HH:MM:SS, for example "
                "8 or 00:08. The source is the unique local video currently loaded in VLC."
            ),
        },
        "output_path": {
            "type": "string",
            "minLength": 1,
            "pattern": r"^(?:/|~/).+\.(?:[pP][nN][gG]|[jJ][pP][eE]?[gG])$",
            "description": "Exact absolute or ~/ destination ending in .png, .jpg, or .jpeg.",
        },
    },
    "required": ["timestamp", "output_path"],
}

MEDIA_EXTRACT_AUDIO_SCHEMA: dict[str, Any] = {
    "properties": {
        "input_path": {
            "type": "string",
            "minLength": 1,
            "pattern": LOCAL_PATH_PATTERN,
            "description": (
                "Exact absolute or ~/ path of the local media file selected by the model. "
                "Use media.inspect_current first when the source is the video currently open in VLC."
            ),
        },
        "output_path": {
            "type": "string",
            "minLength": 1,
            "pattern": r"^(?:/|~/).+\.(?:[mM][pP]3|[wW][aA][vV])$",
            "description": (
                "Exact absolute or ~/ destination ending in .mp3 or .wav. Parent directories "
                "are created and the extracted audio stream is verified."
            ),
        },
    },
    "required": ["input_path", "output_path"],
}

PRESENTATION_INSERT_AUDIO_SCHEMA: dict[str, Any] = {
    "properties": {
        "slide": {
            "type": "integer",
            "minimum": 0,
            "description": "Zero-based target slide index in the currently active presentation.",
        },
        "path": {
            "type": "string",
            "minLength": 1,
            "pattern": (
                r"^(?:/|~/).+\."
                r"(?:[aA][aA][cC]|[fF][lL][aA][cC]|[mM]4[aA]|[mM][pP]3|"
                r"[oO][gG][gG]|[oO][pP][uU][sS]|[wW][aA][vV])$"
            ),
            "description": (
                "Exact absolute or ~/ path of an existing local audio file selected by the "
                "model. Copy the complete filename including its supported audio extension; "
                "a directory such as ~/ is invalid."
            ),
        },
        "x": {
            "type": "integer",
            "minimum": 0,
            "description": "Optional horizontal position in LibreOffice hundredths of a millimeter.",
        },
        "y": {
            "type": "integer",
            "minimum": 0,
            "description": "Optional vertical position in LibreOffice hundredths of a millimeter.",
        },
        "width": {
            "type": "integer",
            "minimum": 1,
            "description": "Optional media-object width in LibreOffice hundredths of a millimeter.",
        },
        "height": {
            "type": "integer",
            "minimum": 1,
            "description": "Optional media-object height in LibreOffice hundredths of a millimeter.",
        },
    },
    "required": ["slide", "path"],
}

PRESENTATION_SET_BACKGROUND_IMAGE_SCHEMA: dict[str, Any] = {
    "properties": {
        "slide": {
            "type": "integer",
            "minimum": 0,
            "description": "Zero-based target slide index in the currently active presentation.",
        },
        "image_path": {
            "type": "string",
            "minLength": 1,
            "pattern": r"^(?:/|~/).+\.(?:[pP][nN][gG]|[jJ][pP][eE]?[gG])$",
            "description": "Exact absolute or ~/ path of the background PNG or JPEG selected by the model.",
        },
    },
    "required": ["slide", "image_path"],
}


def _nonempty_string(params: Mapping[str, Any], field: str) -> str:
    value = params.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(
            "INVALID_REQUEST", f"params.{field} must be a non-empty string"
        )
    return value


def _local_path(params: Mapping[str, Any], field: str) -> str:
    value = _nonempty_string(params, field)
    if not value.startswith(("/", "~/")):
        raise AdapterError(
            "INVALID_REQUEST", f"params.{field} must be absolute or begin with ~/"
        )
    return value


def _reject_unexpected(
    params: Mapping[str, Any], allowed: set[str], action: str
) -> None:
    unexpected = sorted(set(params) - allowed)
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            f"{action} received unsupported parameters",
            {"unexpected": unexpected, "allowed": sorted(allowed)},
        )


def validate_media_inspect_current_params(params: Mapping[str, Any]) -> None:
    if params:
        raise AdapterError(
            "INVALID_REQUEST", "media.inspect_current does not accept parameters"
        )


def validate_media_extract_audio_params(params: Mapping[str, Any]) -> None:
    _reject_unexpected(params, {"input_path", "output_path"}, "media.extract_audio")
    _local_path(params, "input_path")
    output = _local_path(params, "output_path")
    if not output.casefold().endswith((".mp3", ".wav")):
        raise AdapterError(
            "INVALID_REQUEST", "params.output_path must end in .mp3 or .wav"
        )


def validate_media_extract_current_audio_params(params: Mapping[str, Any]) -> None:
    _reject_unexpected(params, {"output_path"}, "media.extract_current_audio")
    output = _local_path(params, "output_path")
    if not output.casefold().endswith((".mp3", ".wav")):
        raise AdapterError(
            "INVALID_REQUEST", "params.output_path must end in .mp3 or .wav"
        )


def parse_timestamp_seconds(value: Any) -> float:
    if isinstance(value, bool):
        raise AdapterError(
            "INVALID_REQUEST", "params.timestamp must be seconds or MM:SS/HH:MM:SS"
        )
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str) and value.strip():
        components = value.strip().split(":")
        if len(components) > 3:
            raise AdapterError(
                "INVALID_REQUEST", "params.timestamp must be seconds or MM:SS/HH:MM:SS"
            )
        try:
            numbers = [float(component) for component in components]
        except ValueError as exc:
            raise AdapterError(
                "INVALID_REQUEST", "params.timestamp must be seconds or MM:SS/HH:MM:SS"
            ) from exc
        if any(number < 0 for number in numbers) or any(
            number >= 60 for number in numbers[1:]
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.timestamp contains an invalid minute or second",
            )
        seconds = 0.0
        for number in numbers:
            seconds = seconds * 60 + number
    else:
        raise AdapterError(
            "INVALID_REQUEST", "params.timestamp must be seconds or MM:SS/HH:MM:SS"
        )
    if not 0 <= seconds <= 86_400:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.timestamp must resolve to 0 through 86400 seconds",
        )
    return seconds


def validate_media_extract_current_frame_params(params: Mapping[str, Any]) -> None:
    _reject_unexpected(
        params, {"timestamp", "output_path"}, "media.extract_current_frame"
    )
    parse_timestamp_seconds(params.get("timestamp"))
    output = _local_path(params, "output_path")
    if not output.casefold().endswith((".png", ".jpg", ".jpeg")):
        raise AdapterError(
            "INVALID_REQUEST", "params.output_path must end in .png, .jpg, or .jpeg"
        )


def validate_presentation_insert_audio_params(params: Mapping[str, Any]) -> None:
    allowed = {"slide", "path", "x", "y", "width", "height"}
    _reject_unexpected(params, allowed, "presentation.insert_audio")
    slide = params.get("slide")
    if isinstance(slide, bool) or not isinstance(slide, int) or slide < 0:
        raise AdapterError(
            "INVALID_REQUEST", "params.slide must be a non-negative integer"
        )
    path = _local_path(params, "path")
    if not path.casefold().endswith(
        (".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav")
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.path must end in a supported audio extension",
        )
    for field in ("x", "y"):
        if field in params:
            value = params[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must be a non-negative integer",
                )
    for field in ("width", "height"):
        if field in params:
            value = params[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AdapterError(
                    "INVALID_REQUEST", f"params.{field} must be a positive integer"
                )


def validate_presentation_set_background_image_params(
    params: Mapping[str, Any],
) -> None:
    _reject_unexpected(
        params, {"slide", "image_path"}, "presentation.set_background_image"
    )
    slide = params.get("slide")
    if isinstance(slide, bool) or not isinstance(slide, int) or slide < 0:
        raise AdapterError(
            "INVALID_REQUEST", "params.slide must be a non-negative integer"
        )
    image_path = _local_path(params, "image_path")
    if not image_path.casefold().endswith((".png", ".jpg", ".jpeg")):
        raise AdapterError(
            "INVALID_REQUEST", "params.image_path must end in .png, .jpg, or .jpeg"
        )
