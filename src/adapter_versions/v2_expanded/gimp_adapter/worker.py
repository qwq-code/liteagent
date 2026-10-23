from __future__ import annotations

import json
import sys
import time
from typing import Any

from .config_store import update_typed_config
from .crop import crop_image
from .errors import AdapterError, error_payload
from .lifecycle import GimpLifecycle
from .scriptfu import ScriptFuRunner
from .verifier import image_state, verify_specs


def _default_specs(
    action: str, params: dict[str, Any], result: dict[str, Any]
) -> list[dict[str, Any]]:
    if action == "image.export":
        return [{"type": "image"}]
    if action == "image.convert_indexed":
        return [{"type": "palette"}]
    if action == "image.adjust":
        if float(params.get("brightness", 0)) < 0:
            return [
                {"type": "brightness_decreased", "reference_path": params["input_path"]}
            ]
        if float(params.get("saturation", 0)) > 0:
            return [
                {"type": "saturation_increased", "reference_path": params["input_path"]}
            ]
        if float(params.get("contrast", 0)) > 0:
            return [
                {"type": "contrast_increased", "reference_path": params["input_path"]}
            ]
        return [{"type": "image"}]
    if action == "image.crop":
        return [
            {
                "type": "image",
                "width": result["output_dimensions"]["width"],
                "height": result["output_dimensions"]["height"],
            }
        ]
    if action == "image.flip" and params.get("direction", "horizontal") == "horizontal":
        return [{"type": "mirror", "reference_path": params["input_path"]}]
    if action == "image.apply_alpha_mask":
        return [{"type": "alpha"}]
    if action == "layer.add":
        return [{"type": "layer", "layer_name": params["name"]}]
    if action == "layer.fill":
        return [{"type": "image"}]
    if action == "layer.scale":
        expected = {"type": "layer"}
        if "width" in params:
            expected["layer_width"] = params["width"]
        if "height" in params:
            expected["layer_height"] = params["height"]
        return [expected]
    if action == "layer.translate":
        return [
            {
                "type": "layer",
                "offset_x": int(params["x"]),
                "offset_y": int(params["y"]),
            }
        ]
    if action == "config.set":
        return [
            {
                "type": "config",
                "file": params.get("file", "gimprc"),
                "key": params["key"],
                "value": params["value"],
            }
        ]
    return []


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload["action"]
    params = dict(payload.get("params") or {})
    timeout_seconds = max(0.1, int(payload.get("timeout_ms", 45_000)) / 1000 - 1)
    lifecycle = GimpLifecycle()
    scriptfu = ScriptFuRunner(lifecycle)
    started = time.monotonic()
    logs = [{"level": "info", "message": f"starting {action}"}]

    if action == "image.inspect":
        try:
            result = {"image": image_state(params["path"])}
        except AdapterError:
            result = scriptfu.inspect(params["path"], timeout_seconds)
        verification = {
            "passed": True,
            "checks": [{"type": "inspect", "passed": True, "observed": result}],
            "observed_state": result,
            "expected_state": [],
            "error_code": None,
            "details": None,
        }
    elif action == "image.export":
        result = scriptfu.export(
            params["input_path"],
            params["output_path"],
            loader=params.get("loader", "auto"),
            quality=float(params.get("quality", 0.98)),
            timeout_seconds=timeout_seconds,
        )
        verification = verify_specs(
            payload.get("verify") or _default_specs(action, params, result), result
        )
    elif action == "image.convert_indexed":
        result = scriptfu.convert_indexed(params, timeout_seconds)
        verification = verify_specs(
            payload.get("verify") or _default_specs(action, params, result), result
        )
    elif action == "image.adjust":
        result = scriptfu.adjust(params, timeout_seconds)
        verification = verify_specs(
            payload.get("verify") or _default_specs(action, params, result), result
        )
    elif action == "image.crop":
        result = crop_image(params)
        verification = verify_specs(
            payload.get("verify") or _default_specs(action, params, result), result
        )
    elif action == "image.flip":
        result = scriptfu.flip(params, timeout_seconds)
        verification = verify_specs(
            payload.get("verify") or _default_specs(action, params, result), result
        )
    elif action == "image.apply_alpha_mask":
        result = scriptfu.apply_alpha_mask(params, timeout_seconds)
        verification = verify_specs(
            payload.get("verify") or _default_specs(action, params, result), result
        )
    elif action == "layer.add":
        result = scriptfu.layer_add(params, timeout_seconds)
        verification = verify_specs(
            payload.get("verify") or _default_specs(action, params, result), result
        )
    elif action == "layer.fill":
        result = scriptfu.layer_fill(params, timeout_seconds)
        verification = verify_specs(
            payload.get("verify") or _default_specs(action, params, result), result
        )
    elif action == "layer.scale":
        result = scriptfu.layer_scale(params, timeout_seconds)
        verification = verify_specs(
            payload.get("verify") or _default_specs(action, params, result), result
        )
    elif action == "layer.translate":
        result = scriptfu.layer_translate(params, timeout_seconds)
        verification = verify_specs(
            payload.get("verify") or _default_specs(action, params, result), result
        )
    elif action == "config.set":
        lifecycle.shutdown(min(timeout_seconds, 10.0))
        result = update_typed_config(
            params.get("file", "gimprc"), params["key"], params["value"]
        )
        if params.get("restart", True):
            result["gui"] = lifecycle.prepare(min(timeout_seconds, 25.0))
        verification = verify_specs(
            payload.get("verify") or _default_specs(action, params, result), result
        )
    else:
        raise AdapterError(
            "UNSUPPORTED_ACTION", "action is not implemented", {"action": action}, 501
        )

    if not verification["passed"]:
        raise AdapterError(
            "VERIFICATION_FAILED", "operation verification failed", verification, 422
        )
    logs.append(
        {
            "level": "info",
            "message": f"completed {action} in {round((time.monotonic() - started) * 1000)} ms",
        }
    )
    return {"result": result, "verification": verification, "logs": logs}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        output = execute(payload)
        json.dump(output, sys.stdout, ensure_ascii=True)
    except AdapterError as error:
        json.dump(
            {
                "error": {
                    **error_payload(error),
                    "http_status": error.http_status,
                }
            },
            sys.stdout,
            ensure_ascii=True,
        )
        raise SystemExit(1)
    except Exception as exc:
        json.dump(
            {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "unexpected GIMP worker failure",
                    "details": str(exc),
                    "http_status": 500,
                }
            },
            sys.stdout,
            ensure_ascii=True,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
