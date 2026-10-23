from __future__ import annotations

import struct
import time
from pathlib import Path
from typing import Any

from .command import CommandRunner
from .errors import AdapterError
from .lifecycle import OSLifecycle


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_dimensions(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) < 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise AdapterError(
            "SCREENSHOT_FAILED",
            "window capture is not a valid PNG image",
            {"output_path": str(path), "size": path.stat().st_size},
            422,
        )
    width, height = struct.unpack(">II", header[16:24])
    if width <= 0 or height <= 0:
        raise AdapterError(
            "SCREENSHOT_FAILED",
            "window capture has invalid dimensions",
            {"output_path": str(path), "width": width, "height": height},
            422,
        )
    return width, height


def capture_window(
    runner: CommandRunner,
    lifecycle: OSLifecycle,
    params: dict[str, Any],
    *,
    timeout: float,
) -> dict[str, Any]:
    """Capture one explicitly selected desktop window without performing other work."""
    title = str(params["title_contains"])
    destination = Path(str(params["output_path"])).expanduser()
    if not destination.parent.is_dir():
        raise AdapterError(
            "PATH_NOT_FOUND",
            f"output directory does not exist: {destination.parent}",
            http_status=404,
        )
    if destination.exists() and not params.get("overwrite", False):
        raise AdapterError(
            "DESTINATION_EXISTS",
            f"output_path already exists: {destination}",
            {"output_path": str(destination)},
            409,
        )

    deadline = time.monotonic() + max(0.1, timeout)
    matches: list[str] = []
    while time.monotonic() < deadline:
        matches = [
            line for line in lifecycle.windows() if title.casefold() in line.casefold()
        ]
        if matches:
            break
        time.sleep(0.1)
    if not matches:
        raise AdapterError(
            "WINDOW_NOT_FOUND",
            "no desktop window matched the model-selected title",
            {"title_contains": title},
            404,
        )
    if len(matches) != 1:
        raise AdapterError(
            "AMBIGUOUS_WINDOW",
            "multiple desktop windows matched the model-selected title",
            {"title_contains": title, "matches": matches},
            409,
        )

    destination.unlink(missing_ok=True)
    window_id = matches[0].split(maxsplit=1)[0]
    runner.run(["wmctrl", "-ia", window_id], timeout=min(10, timeout))
    time.sleep(0.3)
    capture = runner.run(
        ["gnome-screenshot", "-w", "-f", str(destination)],
        timeout=min(15, max(1, timeout)),
        error_code="SCREENSHOT_FAILED",
        error_message="failed to capture the selected desktop window",
    )
    if not destination.is_file() or destination.stat().st_size == 0:
        raise AdapterError(
            "SCREENSHOT_FAILED",
            "window capture file was not created",
            {"output_path": str(destination)},
            422,
        )
    width, height = _png_dimensions(destination)
    return {
        "title_contains": title,
        "window": matches[0],
        "window_id": window_id,
        "output_path": str(destination.resolve()),
        "screenshot_bytes": destination.stat().st_size,
        "screenshot_width": width,
        "screenshot_height": height,
        "capture_duration_ms": capture["duration_ms"],
        "verified": True,
    }


__all__ = ["capture_window"]
