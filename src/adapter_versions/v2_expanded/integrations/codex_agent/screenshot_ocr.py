"""Read visible text and pixel boxes from a supplied desktop screenshot."""

from __future__ import annotations

import csv
import io
import json
import math
import os
import subprocess
from typing import Any


def _lines(tsv: str) -> tuple[list[dict[str, Any]], bool]:
    lines: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        text = row.get("text", "").strip()
        if row.get("level") != "5" or not text:
            continue
        confidence = float(row["conf"])
        if not math.isfinite(confidence) or confidence < 0:
            continue
        key = tuple(
            row[field] for field in ("page_num", "block_num", "par_num", "line_num")
        )
        lines.setdefault(key, []).append(
            {
                "text": text,
                "box": [
                    int(row[field]) for field in ("left", "top", "width", "height")
                ],
                "confidence": confidence,
            }
        )

    items = []
    length = 2  # Opening and closing brackets of the compact JSON array.
    for words in lines.values():
        left = min(word["box"][0] for word in words)
        top = min(word["box"][1] for word in words)
        right = max(word["box"][0] + word["box"][2] for word in words)
        bottom = max(word["box"][1] + word["box"][3] for word in words)
        item = {
            "text": " ".join(word["text"] for word in words),
            "box": [left, top, right - left, bottom - top],
            "center": [(left + right) // 2, (top + bottom) // 2],
            "confidence": round(
                sum(word["confidence"] for word in words) / len(words), 1
            ),
        }
        encoded = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        next_length = length + len(encoded) + bool(items)
        if len(items) >= 100 or next_length > 6000:
            return items, True
        items.append(item)
        length = next_length
    return items, False


def read_screenshot(
    png: bytes, *, language: str = "eng", timeout: float = 5.0
) -> dict[str, Any]:
    """Return OCR observations; OCR errors never invalidate the source screenshot.

    Boxes and centers use the supplied image's unscaled pixel coordinates.
    Confidence is the mean Tesseract word confidence (0 to 100) for each line.
    """
    result = {"engine": "tesseract", "language": language}
    try:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("OCR timeout must be positive and finite")
        completed = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", language, "--psm", "11", "tsv"],
            input=png,
            capture_output=True,
            check=True,
            timeout=timeout,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
        )
        items, truncated = _lines(completed.stdout.decode("utf-8", errors="replace"))
        return {**result, "status": "ok", "items": items, "truncated": truncated}
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
        return {
            **result,
            "status": "error",
            "detail": f"Tesseract exited with code {exc.returncode}: {detail[:1000]}",
        }
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, csv.Error) as exc:
        return {**result, "status": "error", "detail": f"{type(exc).__name__}: {exc}"}
