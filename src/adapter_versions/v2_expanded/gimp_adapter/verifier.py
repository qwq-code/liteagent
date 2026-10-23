from __future__ import annotations

import math
import mimetypes
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat

from .config_store import CONFIG_DIR, encode_value, parse_tokens
from .errors import AdapterError


def image_state(path: str) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        raise AdapterError(
            "FILE_NOT_FOUND", f"image does not exist: {target}", http_status=404
        )
    try:
        with Image.open(target) as image:
            image.load()
            alpha_bbox = None
            if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                alpha_bbox = image.convert("RGBA").getchannel("A").getbbox()
            return {
                "path": str(target),
                "size_bytes": target.stat().st_size,
                "format": image.format,
                "mode": image.mode,
                "width": image.width,
                "height": image.height,
                "alpha_bbox": list(alpha_bbox) if alpha_bbox else None,
                "mime": Image.MIME.get(image.format)
                or mimetypes.guess_type(target.name)[0],
            }
    except OSError as exc:
        raise AdapterError(
            "INVALID_IMAGE", f"failed to decode image: {target}", str(exc), 422
        ) from exc


def _brightness(image: Image.Image) -> float:
    return float(ImageStat.Stat(image.convert("L")).mean[0])


def _saturation(image: Image.Image) -> float:
    return float(ImageStat.Stat(image.convert("HSV").getchannel("S")).mean[0])


def _contrast(image: Image.Image) -> float:
    stat = ImageStat.Stat(image.convert("RGB"))
    means = stat.mean
    squares = stat.sum2
    counts = [image.width * image.height] * 3
    variances = [max(0.0, squares[i] / counts[i] - means[i] ** 2) for i in range(3)]
    return math.sqrt(sum(variances) / 3)


def compare_metric(actual: str, reference: str, metric: str) -> dict[str, Any]:
    with Image.open(actual) as actual_image, Image.open(reference) as reference_image:
        if metric == "brightness_decreased":
            observed = _brightness(actual_image)
            baseline = _brightness(reference_image)
            passed = observed < baseline
        elif metric == "saturation_increased":
            observed = _saturation(actual_image)
            baseline = _saturation(reference_image)
            passed = observed > baseline
        elif metric == "contrast_increased":
            observed = _contrast(actual_image)
            baseline = _contrast(reference_image)
            passed = observed > baseline
        elif metric == "mirror":
            expected = reference_image.convert("RGB").transpose(
                Image.Transpose.FLIP_LEFT_RIGHT
            )
            candidate = actual_image.convert("RGB")
            if candidate.size != expected.size:
                passed = False
                observed = {"size": candidate.size}
                baseline = {"size": expected.size}
            else:
                difference = ImageChops.difference(candidate, expected)
                observed = float(sum(ImageStat.Stat(difference).mean) / 3)
                baseline = 0.0
                passed = observed < 1.0
        else:
            raise AdapterError(
                "INVALID_ARGUMENT", f"unsupported comparison metric: {metric}"
            )
    return {"passed": passed, "observed": observed, "reference": baseline}


def verify_specs(
    specs: list[dict[str, Any]], context: dict[str, Any]
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for spec in specs:
        check_type = spec["type"]
        output_path = str(context.get("output_path") or "")
        default_path = (
            context.get("preview_path")
            if output_path.lower().endswith(".xcf")
            else output_path or context.get("preview_path")
        )
        actual_path = str(spec.get("path") or default_path or "")
        if check_type in {"file", "image", "palette", "alpha"}:
            try:
                state = image_state(actual_path)
                passed = True
                if check_type == "palette":
                    passed = state["mode"] == "P"
                elif check_type == "alpha":
                    passed = (
                        state["mode"] in {"RGBA", "LA"}
                        and state["alpha_bbox"] is not None
                    )
                for field in ("format", "mode", "width", "height", "mime"):
                    if field in spec and state.get(field) != spec[field]:
                        passed = False
                checks.append(
                    {
                        "type": check_type,
                        "passed": passed,
                        "observed": state,
                        "expected": spec,
                    }
                )
            except AdapterError as exc:
                checks.append(
                    {
                        "type": check_type,
                        "passed": False,
                        "error": str(exc),
                        "expected": spec,
                    }
                )
        elif check_type in {
            "brightness_decreased",
            "saturation_increased",
            "contrast_increased",
            "mirror",
        }:
            reference = str(
                spec.get("reference_path") or context.get("input_path") or ""
            )
            outcome = compare_metric(actual_path, reference, check_type)
            checks.append({"type": check_type, **outcome, "expected": spec})
        elif check_type == "layer":
            observed = context.get("metadata", {})
            passed = all(
                observed.get(key) == value
                for key, value in spec.items()
                if key != "type"
            )
            checks.append(
                {
                    "type": check_type,
                    "passed": passed,
                    "observed": observed,
                    "expected": spec,
                }
            )
        elif check_type == "config":
            file_name = spec.get("file", "gimprc")
            observed = parse_tokens(CONFIG_DIR / file_name).get(spec.get("key"))
            expected = spec.get("token", encode_value(spec.get("value")))
            checks.append(
                {
                    "type": check_type,
                    "passed": observed == expected,
                    "observed": observed,
                    "expected": expected,
                }
            )
        elif check_type == "action_history":
            path = CONFIG_DIR / "action-history"
            content = path.read_text(encoding="utf-8") if path.exists() else ""
            token = str(spec.get("token", ""))
            excluded = [
                value
                for value in spec.get("exclude", [])
                if value.lower() in content.lower()
            ]
            checks.append(
                {
                    "type": check_type,
                    "passed": token in content and not excluded,
                    "observed": content[-2000:],
                    "expected": spec,
                }
            )
        elif check_type == "window":
            windows = context.get("windows", [])
            title = str(spec.get("title", ""))
            checks.append(
                {
                    "type": check_type,
                    "passed": any(title.lower() in item.lower() for item in windows),
                    "observed": windows,
                    "expected": spec,
                }
            )
        elif check_type == "background_color":
            expected = spec.get("color")
            tolerance = int(spec.get("tolerance", 8))
            try:
                with Image.open(actual_path) as image:
                    rgb = image.convert("RGB")
                    samples = [
                        list(rgb.getpixel((0, 0))),
                        list(rgb.getpixel((rgb.width - 1, 0))),
                        list(rgb.getpixel((0, rgb.height - 1))),
                        list(rgb.getpixel((rgb.width - 1, rgb.height - 1))),
                    ]
                passed = bool(
                    isinstance(expected, list)
                    and len(expected) == 3
                    and all(
                        all(
                            abs(actual - wanted) <= tolerance
                            for actual, wanted in zip(sample, expected, strict=True)
                        )
                        for sample in samples
                    )
                )
                checks.append(
                    {
                        "type": check_type,
                        "passed": passed,
                        "observed": {"corner_samples": samples},
                        "expected": spec,
                    }
                )
            except (AdapterError, OSError) as exc:
                checks.append(
                    {
                        "type": check_type,
                        "passed": False,
                        "error": str(exc),
                        "expected": spec,
                    }
                )
    passed = all(check.get("passed", False) for check in checks)
    return {
        "passed": passed,
        "checks": checks,
        "observed_state": context,
        "expected_state": specs,
        "error_code": None if passed else "VERIFICATION_FAILED",
        "details": None if passed else "one or more checks failed",
    }
