from __future__ import annotations

import hashlib
from collections import deque
from datetime import datetime, timezone
from fnmatch import fnmatchcase
import json
import os
import re
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any

from .command import CommandRunner
from .config import VLC_CONFIG_PATH, update_config
from .errors import AdapterError, error_payload
from .vlc_http import read_playlist_uri, read_status, status_request, wait_http
from .vlc_mpris import read_playback_position


SEMANTIC_MEDIA_DIRECTORIES = {
    "desktop": "Desktop",
    "downloads": "Downloads",
    "videos": "Videos",
    "music": "Music",
    "home": "",
}
CLIP_OUTPUT_EXTENSIONS = frozenset(
    {".avi", ".gif", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}
)
SUBTITLE_OUTPUT_CODECS = {".srt": "srt", ".vtt": "webvtt"}
SUBTITLE_TIMING_RE = re.compile(
    r"(?m)^\s*(?:\d{2}:)?\d{2}:\d{2}[,.]\d{3}\s+-->\s+"
    r"(?:\d{2}:)?\d{2}:\d{2}[,.]\d{3}(?:\s+.*)?$"
)
VLC_SEMANTIC_PREFERENCE_FIELDS = frozenset(
    {
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
)


def semantic_preference_values(
    params: dict[str, Any], *, home: Path | None = None
) -> dict[str, str]:
    values: dict[str, str] = {}
    if "global_play_pause_hotkey" in params:
        values["global-key-play-pause"] = str(params["global_play_pause_hotkey"])
    if "maximum_volume_percent" in params:
        values["qt-max-volume"] = str(params["maximum_volume_percent"])
    if "volume_slider_color" in params:
        color = str(params["volume_slider_color"])
        channels = [str(int(color[index : index + 2], 16)) for index in (1, 3, 5)]
        values["qt-slider-colours"] = ";".join(channels * 4)
    if "minimal_interface" in params:
        values["qt-minimal-view"] = "1" if params["minimal_interface"] else "0"
    if "exit_after_playback" in params:
        values["play-and-exit"] = "1" if params["exit_after_playback"] else "0"
    if "allow_multiple_instances" in params:
        values["one-instance-when-started-from-file"] = (
            "0" if params["allow_multiple_instances"] else "1"
        )
    if "show_background_cone" in params:
        values["qt-bgcone"] = "1" if params["show_background_cone"] else "0"
    if "recording_directory" in params:
        values["input-record-path"] = str(params["recording_directory"])
    if "recording_location" in params:
        root = home if home is not None else Path.home()
        relative = SEMANTIC_MEDIA_DIRECTORIES[str(params["recording_location"])]
        values["input-record-path"] = str(root / relative if relative else root)
    return values


def _file(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_file():
        raise AdapterError(
            "PATH_NOT_FOUND", f"media file does not exist: {path}", http_status=404
        )
    return path.resolve()


def _temporary_output(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=path.suffix,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
    temporary.unlink()
    return temporary


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_subtitle(path: Path) -> dict[str, Any]:
    extension = path.suffix.casefold()
    if extension not in SUBTITLE_OUTPUT_CODECS:
        raise AdapterError(
            "UNSUPPORTED_FORMAT",
            "subtitle output must use the .srt or .vtt extension",
            {
                "extension": extension,
                "supported_extensions": sorted(SUBTITLE_OUTPUT_CODECS),
            },
            422,
        )
    if not path.is_file() or path.stat().st_size == 0:
        raise AdapterError(
            "SUBTITLE_EXTRACTION_FAILED",
            "subtitle extraction produced no output",
            {"path": str(path)},
            422,
        )
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AdapterError(
            "SUBTITLE_INVALID",
            "subtitle output is not valid UTF-8 text",
            {"path": str(path)},
            422,
        ) from exc
    cue_count = len(SUBTITLE_TIMING_RE.findall(text))
    if cue_count == 0:
        raise AdapterError(
            "SUBTITLE_INVALID",
            "subtitle output contains no timed cues",
            {"path": str(path), "format": extension.removeprefix(".")},
            422,
        )
    if extension == ".vtt" and not text.lstrip().startswith("WEBVTT"):
        raise AdapterError(
            "SUBTITLE_INVALID",
            "WebVTT output is missing its WEBVTT header",
            {"path": str(path)},
            422,
        )
    return {
        "path": str(path),
        "format": extension.removeprefix("."),
        "size_bytes": path.stat().st_size,
        "cue_count": cue_count,
        "sha256": _sha256(path),
    }


def probe_media(
    runner: CommandRunner, path: Path, timeout: float = 30
) -> dict[str, Any]:
    result = runner.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate:stream=index,codec_name,codec_type,width,height,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        timeout=timeout,
        error_code="TRANSCODE_FAILED",
        error_message="ffprobe could not inspect media output",
    )
    try:
        payload = json.loads(result["stdout"])
    except json.JSONDecodeError as exc:
        raise AdapterError(
            "TRANSCODE_FAILED", "ffprobe returned invalid JSON", result, 422
        ) from exc
    payload["path"] = str(path)
    return payload


def _status_source(status: dict[str, Any]) -> str | None:
    metadata = status.get("metadata", {})
    for key in ("filename", "title", "uri", "URI", "location", "url", "name"):
        if metadata.get(key):
            return str(metadata[key])
    return None


def status_matches_source(status: dict[str, Any], source: str) -> bool:
    observed = _status_source(status)
    if not observed:
        return False
    if source.startswith(("http://", "https://")):
        expected_name = Path(urllib.parse.urlparse(source).path).name
        return source in observed or observed in source or observed == expected_name
    expected_name = Path(source).name
    return observed == expected_name or observed.endswith("/" + expected_name)


def status_flag(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def window_state(runner: CommandRunner) -> dict[str, Any]:
    windows_result = runner.run(["wmctrl", "-lxG"], check=False, timeout=10)
    windows = [
        line
        for line in windows_result["stdout"].splitlines()
        if "vlc.vlc" in line.lower()
    ]
    screen_result = runner.run(["xrandr", "--current"], check=False, timeout=10)
    match = re.search(r"current\s+(\d+)\s+x\s+(\d+)", screen_result["stdout"])
    screen = (
        {"width": int(match.group(1)), "height": int(match.group(2))} if match else None
    )
    parsed = []
    for line in windows:
        fields = line.split(None, 8)
        if len(fields) >= 8:
            parsed.append(
                {
                    "id": fields[0],
                    "x": int(fields[2]),
                    "y": int(fields[3]),
                    "width": int(fields[4]),
                    "height": int(fields[5]),
                    "class": fields[6],
                    "line": line,
                }
            )
    return {"screen": screen, "windows": parsed, "raw_windows": windows}


class VlcActions:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def config_update(self, params: dict[str, Any], _timeout: float) -> dict[str, Any]:
        values = {
            str(key): "1" if value is True else "0" if value is False else str(value)
            for key, value in dict(params["values"]).items()
        }
        return update_config(values, Path(params.get("path", VLC_CONFIG_PATH)))

    def preferences_configure(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        values = semantic_preference_values(params)
        result = update_config(values, VLC_CONFIG_PATH)
        return {
            **result,
            "semantic_preferences": {
                key: params[key]
                for key in VLC_SEMANTIC_PREFERENCE_FIELDS
                if key in params
            },
        }

    def playback_status(
        self, _params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        observed = {
            **wait_http(min(timeout, 45), launch=False),
            "source": None,
            "source_uri": None,
        }
        item_id = observed.get("currentplid")
        if item_id in (None, "", "-1"):
            return observed
        try:
            # Match the status snapshot's item, not a display name or another track.
            uri = read_playlist_uri(
                str(item_id), timeout=max(0.1, min(10, deadline - time.monotonic()))
            )
            if uri is None:
                raise AdapterError(
                    "MEDIA_SOURCE_UNAVAILABLE",
                    "VLC has no playlist URI for the current item; its display name is not a file path.",
                    {"currentplid": item_id},
                )
            parsed = urllib.parse.urlsplit(uri)
            source = (
                urllib.parse.unquote(parsed.path)
                if parsed.scheme == "file"
                and parsed.netloc in ("", "localhost")
                and parsed.path.startswith("/")
                else uri
            )
            observed.update(source=source, source_uri=uri)
        except AdapterError as exc:
            observed["source_error"] = error_payload(exc)
        if observed["source_uri"] and observed.get("state") in {"playing", "paused"}:
            try:
                observed.update(
                    read_playback_position(
                        observed["source_uri"],
                        timeout=max(0.1, min(5, deadline - time.monotonic())),
                    )
                )
            except AdapterError as exc:
                observed["time_error"] = error_payload(exc)
        return observed

    def _restart_vlc(self, timeout: float) -> dict[str, Any]:
        self.runner.run(["pkill", "-TERM", "-x", "vlc"], check=False, timeout=5)
        deadline = time.monotonic() + max(1, min(timeout, 15))
        while time.monotonic() < deadline:
            running = self.runner.run(["pgrep", "-x", "vlc"], check=False, timeout=5)
            if not running["stdout"].strip():
                break
            time.sleep(0.1)
        else:
            self.runner.run(["pkill", "-KILL", "-x", "vlc"], check=False, timeout=5)
        return wait_http(min(timeout, 20), launch=True)

    def playback_find_local(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        """Discover model-selected local candidates without choosing one."""
        roots = [Path(value).expanduser().resolve() for value in params["roots"]]
        patterns = params.get("name_patterns", ["*"])
        kind = params.get("kind", "file")
        recursive = bool(params.get("recursive", True))
        include_hidden = bool(params.get("include_hidden", False))
        max_depth = int(params.get("max_depth", 4))
        max_results = int(params.get("max_results", 50))
        matches: dict[Path, dict[str, Any]] = {}
        scanned_entries = 0
        for root in dict.fromkeys(roots):
            queue = deque([(root, 0)])
            while queue and len(matches) < max_results:
                directory, depth = queue.popleft()
                try:
                    entries = sorted(directory.iterdir(), key=lambda path: path.name.casefold())
                except (FileNotFoundError, OSError, PermissionError):
                    continue
                for entry in entries:
                    if len(matches) >= max_results:
                        break
                    if not include_hidden and entry.name.startswith("."):
                        continue
                    scanned_entries += 1
                    try:
                        is_directory = entry.is_dir()
                        is_file = entry.is_file()
                        is_symlink = entry.is_symlink()
                    except (FileNotFoundError, OSError, PermissionError):
                        continue
                    if any(fnmatchcase(entry.name, pattern) for pattern in patterns):
                        if kind == "any" or (kind == "file" and is_file) or (kind == "directory" and is_directory):
                            try:
                                resolved = entry.resolve()
                                stat_result = entry.stat()
                            except (FileNotFoundError, OSError, PermissionError):
                                continue
                            matches[resolved] = {
                                "path": str(resolved),
                                "name": entry.name,
                                "kind": "directory" if is_directory else "file",
                                "size_bytes": stat_result.st_size,
                                "modified_at": datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).isoformat(),
                            }
                    if recursive and is_directory and not is_symlink and depth < max_depth:
                        queue.append((entry, depth + 1))
        ordered = sorted(matches.values(), key=lambda item: str(item["path"]).casefold())
        return {
            "matches": ordered[:max_results],
            "match_count": len(ordered),
            "returned_count": min(len(ordered), max_results),
            "truncated": len(ordered) > max_results,
            "scanned_entries": scanned_entries,
            "kind": kind,
        }

    def playback_open(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        source = str(params["source"])
        if source.startswith(("http://", "https://")):
            input_uri = source
        else:
            path = _file(source)
            source = str(path)
            input_uri = path.as_uri()
        initial = self._restart_vlc(timeout)
        loop_requested = bool(params.get("loop", False))
        if status_flag(initial.get("loop")) != loop_requested:
            status_request("pl_loop", timeout=min(timeout, 15))
        status_request("in_play", {"input": input_uri}, timeout=min(timeout, 15))
        deadline = time.monotonic() + max(1, timeout - 1)
        observed = read_status(timeout=min(timeout, 10))
        while time.monotonic() < deadline:
            if observed.get("state") == "playing" and status_matches_source(
                observed, source
            ):
                break
            time.sleep(0.25)
            observed = read_status(timeout=min(10, max(1, deadline - time.monotonic())))
        else:
            raise AdapterError(
                "PLAYBACK_FAILED",
                "VLC did not start the requested media",
                {"source": source, "observed": observed},
                422,
            )
        return {
            "source": source,
            "input_uri": input_uri,
            "loop_requested": loop_requested,
            "loop_enabled": status_flag(observed.get("loop")),
            "status": observed,
            "observed_source": _status_source(observed),
        }

    def window_set_fullscreen(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        enabled = bool(params["enabled"])
        deadline = time.monotonic() + max(1, timeout)
        observed = window_state(self.runner)
        while not observed["windows"] and time.monotonic() < deadline:
            time.sleep(0.25)
            observed = window_state(self.runner)
        if not observed["windows"]:
            raise AdapterError(
                "WINDOW_NOT_FOUND", "no VLC window was available", observed, 422
            )
        window_id = observed["windows"][0]["id"]
        operation = "add,fullscreen" if enabled else "remove,fullscreen"
        self.runner.run(["wmctrl", "-ir", window_id, "-b", operation], timeout=10)
        while time.monotonic() < deadline:
            observed = window_state(self.runner)
            if observed["screen"] and observed["windows"]:
                window = observed["windows"][0]
                is_fullscreen = (
                    window["width"] == observed["screen"]["width"]
                    and window["height"] == observed["screen"]["height"]
                )
                if is_fullscreen == enabled:
                    return {
                        "enabled": enabled,
                        "window_id": window_id,
                        "window": window,
                        "screen": observed["screen"],
                    }
            time.sleep(0.25)
        raise AdapterError(
            "WINDOW_NOT_FOUND",
            "VLC window did not reach the requested fullscreen state",
            observed,
            422,
        )

    def media_extract_audio(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        if "profile" in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "media.extract_audio does not accept reference profiles",
                {"unsupported_fields": ["profile"]},
            )
        source = _file(params["input_path"])
        output = Path(params["output_path"]).expanduser()
        temporary = _temporary_output(output)
        try:
            extension = output.suffix.casefold()
            if extension == ".mp3":
                audio_args = [
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    "128k",
                    "-ar",
                    "44100",
                    "-ac",
                    "2",
                    "-write_xing",
                    "0",
                    "-id3v2_version",
                    "0",
                ]
                strategy = "ffmpeg_libmp3lame"
            elif extension == ".wav":
                audio_args = [
                    "-codec:a",
                    "pcm_s16le",
                    "-ar",
                    "44100",
                    "-ac",
                    "2",
                ]
                strategy = "ffmpeg_pcm_s16le"
            else:
                raise AdapterError(
                    "UNSUPPORTED_FORMAT",
                    "output_path must use the .mp3 or .wav extension",
                    {
                        "extension": extension,
                        "supported_extensions": [".mp3", ".wav"],
                    },
                    422,
                )
            self.runner.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-map",
                    "0:a:0",
                    "-vn",
                    *audio_args,
                    "-map_metadata",
                    "-1",
                    str(temporary),
                ],
                timeout=timeout,
                error_code="TRANSCODE_FAILED",
                error_message="audio extraction failed",
            )
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise AdapterError(
                    "TRANSCODE_FAILED",
                    "audio extraction produced no output",
                    {"output_path": str(output)},
                    422,
                )
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "input_path": str(source),
            "output_path": str(output),
            "strategy": strategy,
            "input_sha256": _sha256(source),
            "output_sha256": _sha256(output),
            "probe": probe_media(self.runner, output),
        }

    def media_extract_subtitles(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        source = _file(params["input_path"])
        output = Path(params["output_path"]).expanduser()
        extension = output.suffix.casefold()
        codec = SUBTITLE_OUTPUT_CODECS.get(extension)
        if codec is None:
            raise AdapterError(
                "UNSUPPORTED_FORMAT",
                "output_path must use the .srt or .vtt subtitle extension",
                {
                    "extension": extension,
                    "supported_extensions": sorted(SUBTITLE_OUTPUT_CODECS),
                },
                422,
            )
        if output.resolve() == source:
            raise AdapterError(
                "INVALID_REQUEST",
                "output_path must differ from input_path",
                {"input_path": str(source), "output_path": str(output)},
                422,
            )

        source_probe = probe_media(self.runner, source, timeout=min(timeout, 30))
        subtitle_streams = [
            stream
            for stream in source_probe.get("streams", [])
            if stream.get("codec_type") == "subtitle"
        ]
        if not subtitle_streams:
            raise AdapterError(
                "NO_SUBTITLE_STREAM",
                "source media contains no embedded subtitle stream",
                {"input_path": str(source)},
                422,
            )
        stream_index = int(params.get("subtitle_stream_index", 0))
        if stream_index >= len(subtitle_streams):
            raise AdapterError(
                "SUBTITLE_STREAM_NOT_FOUND",
                "subtitle_stream_index is outside the available embedded subtitle streams",
                {
                    "subtitle_stream_index": stream_index,
                    "available_stream_count": len(subtitle_streams),
                    "available_streams": subtitle_streams,
                },
                422,
            )

        temporary = _temporary_output(output)
        try:
            command = self.runner.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-map",
                    f"0:s:{stream_index}",
                    "-c:s",
                    codec,
                    "-map_metadata",
                    "-1",
                    str(temporary),
                ],
                timeout=timeout,
                error_code="SUBTITLE_EXTRACTION_FAILED",
                error_message="embedded subtitle extraction failed",
            )
            try:
                output_evidence = inspect_subtitle(temporary)
            except AdapterError as exc:
                if exc.details is None:
                    exc.details = command
                raise
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        output_evidence = inspect_subtitle(output)
        return {
            "input_path": str(source),
            "output_path": str(output),
            "subtitle_stream_index": stream_index,
            "selected_stream": subtitle_streams[stream_index],
            "available_stream_count": len(subtitle_streams),
            "strategy": f"ffmpeg_{codec}",
            **output_evidence,
        }

    def media_transcode_clip(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        source = _file(params["input_path"])
        output = Path(params["output_path"]).expanduser()
        extension = output.suffix.casefold()
        if extension not in CLIP_OUTPUT_EXTENSIONS:
            raise AdapterError(
                "UNSUPPORTED_FORMAT",
                "output_path must use a supported video or animated GIF extension",
                {
                    "extension": extension,
                    "supported_extensions": sorted(CLIP_OUTPUT_EXTENSIONS),
                },
                422,
            )

        start_time = float(params["start_time_seconds"])
        duration = float(params["duration_seconds"])
        frame_rate = float(params.get("frame_rate", 15))
        temporary = _temporary_output(output)
        common = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{start_time:g}",
            "-i",
            str(source),
            "-t",
            f"{duration:g}",
        ]
        if extension == ".gif":
            filter_graph = (
                f"fps={frame_rate:g},split[clip_a][clip_b];"
                "[clip_a]palettegen=max_colors=256[palette];"
                "[clip_b][palette]paletteuse=dither=sierra2_4a"
            )
            output_args = ["-filter_complex", filter_graph, "-loop", "0"]
            strategy = "ffmpeg_animated_gif_palette"
        elif extension == ".webm":
            output_args = [
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libvpx-vp9",
                "-crf",
                "30",
                "-b:v",
                "0",
                "-c:a",
                "libopus",
            ]
            strategy = "ffmpeg_vp9_opus"
        elif extension in {".m4v", ".mov", ".mp4"}:
            output_args = [
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
            ]
            strategy = "ffmpeg_h264_aac"
        elif extension == ".mkv":
            output_args = [
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
            ]
            strategy = "ffmpeg_matroska_h264_aac"
        else:
            output_args = [
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "mpeg4",
                "-q:v",
                "2",
                "-c:a",
                "libmp3lame",
            ]
            strategy = "ffmpeg_avi_mpeg4_mp3"

        try:
            command = self.runner.run(
                [*common, *output_args, str(temporary)],
                timeout=timeout,
                error_code="TRANSCODE_FAILED",
                error_message="media clip transcoding failed",
            )
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise AdapterError(
                    "TRANSCODE_FAILED",
                    "media clip transcoding produced no output",
                    command,
                    422,
                )
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "input_path": str(source),
            "output_path": str(output),
            "start_time_seconds": start_time,
            "duration_seconds": duration,
            "frame_rate": frame_rate if extension == ".gif" else None,
            "strategy": strategy,
            "probe": probe_media(self.runner, output),
        }

    def media_flip_video(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        source = _file(params["input_path"])
        output = Path(params["output_path"]).expanduser()
        if output.suffix.casefold() != ".mp4":
            raise AdapterError(
                "UNSUPPORTED_FORMAT", "media.flip_video output_path must end in .mp4",
                {"output_path": str(output)}, 422,
            )
        if source == output.resolve():
            raise AdapterError(
                "INVALID_REQUEST",
                "media.flip_video requires a separate output_path; keep input_path unchanged",
            )
        axis = params["axis"]
        filter_name = {"vertical": "vflip", "horizontal": "hflip"}[axis]
        temporary = _temporary_output(output)
        try:
            command = self.runner.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(source), "-map", "0:v:0", "-map", "0:a?",
                    "-vf", filter_name, "-c:v", "libx264", "-preset", "medium",
                    "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-movflags", "+faststart", str(temporary),
                ],
                timeout=timeout,
                error_code="TRANSCODE_FAILED",
                error_message="video flipping failed",
            )
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise AdapterError(
                    "TRANSCODE_FAILED", "video flipping produced no output", command, 422
                )
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "input_path": str(source),
            "output_path": str(output),
            "axis": axis,
            "strategy": f"ffmpeg_{filter_name}_h264_aac",
            "probe": probe_media(self.runner, output),
        }

    def media_extract_frame(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        source = _file(params["input_path"])
        output = Path(params["output_path"]).expanduser()
        frame_index = params.get("frame_index")
        time_seconds = params.get("time_seconds")
        selector = (
            ["--frame-index", str(int(frame_index))]
            if frame_index is not None
            else ["--time-seconds", str(float(time_seconds))]
        )
        temporary = _temporary_output(output)
        try:
            command = self.runner.run(
                [
                    "python3",
                    "-m",
                    "vlc_adapter.frame_extract",
                    "--input",
                    str(source),
                    "--output",
                    str(temporary),
                    *selector,
                ],
                timeout=timeout,
                error_code="TRANSCODE_FAILED",
                error_message="video frame extraction failed",
            )
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise AdapterError(
                    "TRANSCODE_FAILED",
                    "frame extraction produced no image",
                    command,
                    422,
                )
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        try:
            extraction = json.loads(command["stdout"].strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            extraction = {}
        result = {
            "input_path": str(source),
            "output_path": str(output),
            "frame_index": extraction.get("frame_index", frame_index),
            "probe": probe_media(self.runner, output),
        }
        if time_seconds is not None:
            result["time_seconds"] = float(time_seconds)
            result["fps"] = extraction.get("fps")
        return result

    def dispatch(
        self, action: str, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        method = getattr(self, action.replace(".", "_"), None)
        if method is None:
            raise AdapterError(
                "UNSUPPORTED_ACTION", f"unsupported VLC action: {action}"
            )
        return method(params, timeout)
