from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFont

from integrations.codex_agent import screenshot_ocr


HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"


def test_words_merge_into_lines_in_original_pixel_coordinates(monkeypatch):
    def run(command, **kwargs):
        assert command == [
            "tesseract",
            "stdin",
            "stdout",
            "-l",
            "eng",
            "--psm",
            "11",
            "tsv",
        ]
        assert kwargs["input"] == b"provided-png"
        assert kwargs["timeout"] == 2.5
        assert kwargs["env"]["OMP_THREAD_LIMIT"] == "1"
        assert kwargs["check"] is True
        return SimpleNamespace(
            stdout=(
                HEADER
                + "5\t1\t1\t1\t1\t1\t10\t20\t40\t10\t95\tSave\n"
                + "5\t1\t1\t1\t1\t2\t60\t18\t60\t14\t85\tchanges\n"
                + "5\t1\t1\t1\t1\t3\t200\t20\t20\t10\t-1\tignored\n"
                + "5\t1\t1\t1\t1\t4\t200\t20\t20\t10\t80\t\n"
                + "5\t1\t2\t1\t1\t1\t150\t20\t60\t12\t92\tCancel\n"
            ).encode()
        )

    monkeypatch.setattr(screenshot_ocr.subprocess, "run", run)
    result = screenshot_ocr.read_screenshot(b"provided-png", timeout=2.5)
    assert result == {
        "engine": "tesseract",
        "language": "eng",
        "status": "ok",
        "items": [
            {
                "text": "Save changes",
                "box": [10, 18, 110, 14],
                "center": [65, 25],
                "confidence": 90.0,
            },
            {
                "text": "Cancel",
                "box": [150, 20, 60, 12],
                "center": [180, 26],
                "confidence": 92.0,
            },
        ],
        "truncated": False,
    }


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (FileNotFoundError("tesseract is unavailable"), "unavailable"),
        (subprocess.TimeoutExpired("tesseract", 0.2), "timed out"),
        (
            subprocess.CalledProcessError(
                1, "tesseract", stderr=b"Missing language data"
            ),
            "Missing language data",
        ),
    ],
)
def test_ocr_failures_return_observation_error(monkeypatch, failure, message):
    def run(*args, **kwargs):
        raise failure

    monkeypatch.setattr(screenshot_ocr.subprocess, "run", run)
    result = screenshot_ocr.read_screenshot(b"png")
    assert result["status"] == "error"
    assert message in result["detail"]
    assert result["engine"] == "tesseract"


def test_ocr_text_is_bounded_and_reports_truncation(monkeypatch):
    tsv = HEADER + "".join(
        f"5\t1\t1\t1\t{line}\t1\t10\t{line * 20}\t60\t12\t90\tMenu item {line}\n"
        for line in range(1, 151)
    )
    monkeypatch.setattr(
        screenshot_ocr.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=tsv.encode()),
    )
    result = screenshot_ocr.read_screenshot(b"png")
    assert result["status"] == "ok"
    assert result["truncated"] is True
    assert 0 < len(result["items"]) <= 100
    assert (
        len(json.dumps(result["items"], ensure_ascii=False, separators=(",", ":")))
        <= 6000
    )
    assert result["items"][0]["text"] == "Menu item 1"


def test_real_tesseract_reads_synthetic_screenshot():
    font = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if not shutil.which("tesseract") or not font.is_file():
        pytest.skip("Optional Tesseract and test font are not installed")
    image = Image.new("RGB", (640, 180), "white")
    ImageDraw.Draw(image).text(
        (40, 55), "Save changes", font=ImageFont.truetype(str(font), 32), fill="black"
    )
    png = io.BytesIO()
    image.save(png, format="PNG")

    result = screenshot_ocr.read_screenshot(png.getvalue())
    assert result["status"] == "ok"
    line = next(item for item in result["items"] if item["text"] == "Save changes")
    x, y, width, height = line["box"]
    assert 40 <= x < x + width < 300
    assert 55 <= y < y + height < 100
    assert line["center"] == [x + width // 2, y + height // 2]
