from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image

from .errors import AdapterError
from .foreground import local_path


LOSSLESS_SUFFIXES = frozenset({".png", ".tif", ".tiff", ".webp"})
SAVE_FORMATS = {
    ".bmp": "BMP",
    ".jpeg": "JPEG",
    ".jpg": "JPEG",
    ".png": "PNG",
    ".tif": "TIFF",
    ".tiff": "TIFF",
    ".webp": "WEBP",
}


def _pixel_sha256(image: Image.Image) -> str:
    return hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _output_path(source: Path, value: str) -> Path:
    output = local_path(value)
    if output.is_absolute():
        return output
    if output.parent == Path(".") and output.name == value:
        return source.parent / output.name
    raise AdapterError(
        "INVALID_PATH",
        "output_path must be absolute, a local file URL, ~/..., or a basename",
        {"output_path": value},
    )


def _edge_pixels(value: float, dimension: int, unit: str) -> int:
    if unit == "percent":
        return int(math.floor(dimension * value / 100.0 + 0.5))
    return int(value)


def crop_image(params: dict[str, Any]) -> dict[str, Any]:
    source = local_path(params["input_path"])
    output = _output_path(source, params["output_path"])
    overwrite = bool(params.get("overwrite", False))
    if not source.is_file():
        raise AdapterError(
            "FILE_NOT_FOUND",
            "input image does not exist; locate it with filesystem.find",
            {"input_path": str(source)},
            404,
        )
    if output.exists() and not overwrite:
        raise AdapterError(
            "OUTPUT_EXISTS",
            "output image already exists; set overwrite=true to replace it",
            {"output_path": str(output)},
            409,
        )

    try:
        with Image.open(source) as opened:
            opened.load()
            image = opened.copy()
    except OSError as exc:
        raise AdapterError(
            "INVALID_IMAGE", f"failed to decode image: {source}", str(exc), 422
        ) from exc

    unit = params["unit"]
    requested = {
        edge: float(params.get(edge, 0)) for edge in ("top", "right", "bottom", "left")
    }
    removed = {
        "top": _edge_pixels(requested["top"], image.height, unit),
        "right": _edge_pixels(requested["right"], image.width, unit),
        "bottom": _edge_pixels(requested["bottom"], image.height, unit),
        "left": _edge_pixels(requested["left"], image.width, unit),
    }
    if not any(removed.values()):
        raise AdapterError(
            "NO_EFFECT",
            "the requested crop rounds to zero pixels on every edge",
            {"requested": requested, "unit": unit},
            422,
        )
    if removed["left"] + removed["right"] >= image.width:
        raise AdapterError(
            "INVALID_CROP",
            "left and right crop amounts would exhaust the image width",
            {"width": image.width, "removed_pixels": removed},
            422,
        )
    if removed["top"] + removed["bottom"] >= image.height:
        raise AdapterError(
            "INVALID_CROP",
            "top and bottom crop amounts would exhaust the image height",
            {"height": image.height, "removed_pixels": removed},
            422,
        )

    box = (
        removed["left"],
        removed["top"],
        image.width - removed["right"],
        image.height - removed["bottom"],
    )
    cropped = image.crop(box)
    intended_pixel_sha256 = _pixel_sha256(cropped)
    output.parent.mkdir(parents=True, exist_ok=True)
    suffix = output.suffix.casefold()
    temporary = output.with_name(f".{output.stem}.{uuid4().hex}.tmp{suffix}")
    image_to_save = cropped
    save_options: dict[str, Any] = {}
    if suffix in {".jpg", ".jpeg"} and cropped.mode not in {"L", "RGB", "CMYK"}:
        image_to_save = cropped.convert("RGB")
        save_options["quality"] = 95
    elif suffix == ".webp":
        save_options["lossless"] = True

    try:
        image_to_save.save(temporary, format=SAVE_FORMATS[suffix], **save_options)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        with Image.open(temporary) as saved:
            saved.load()
            saved_copy = saved.copy()
        if saved_copy.size != cropped.size:
            raise AdapterError(
                "IMAGE_EXPORT_FAILED",
                "saved crop dimensions differ from the requested crop",
                {
                    "expected": list(cropped.size),
                    "actual": list(saved_copy.size),
                },
                500,
            )
        saved_pixel_sha256 = _pixel_sha256(saved_copy)
        saved_pixels_match = saved_pixel_sha256 == intended_pixel_sha256
        if suffix in LOSSLESS_SUFFIXES and not saved_pixels_match:
            raise AdapterError(
                "PIXEL_PRESERVATION_FAILED",
                "lossless crop read-back differs from the selected source region",
                {"output_path": str(output)},
                500,
            )
        os.replace(temporary, output)
    except AdapterError:
        temporary.unlink(missing_ok=True)
        raise
    except (KeyError, OSError) as exc:
        temporary.unlink(missing_ok=True)
        raise AdapterError(
            "IMAGE_EXPORT_FAILED", f"failed to write image: {output}", str(exc), 422
        ) from exc

    return {
        "input_path": str(source),
        "output_path": str(output),
        "unit": unit,
        "requested_crop": requested,
        "removed_pixels": removed,
        "input_dimensions": {"width": image.width, "height": image.height},
        "output_dimensions": {"width": cropped.width, "height": cropped.height},
        "crop_box": {
            "left": box[0],
            "top": box[1],
            "right": box[2],
            "bottom": box[3],
        },
        "source_region_rgba_sha256": intended_pixel_sha256,
        "saved_rgba_sha256": saved_pixel_sha256,
        "saved_pixels_match": saved_pixels_match,
        "lossless_encoding": suffix in LOSSLESS_SUFFIXES,
        "sha256": _file_sha256(output),
        "size_bytes": output.stat().st_size,
    }
