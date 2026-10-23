from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from .errors import AdapterError
from .lifecycle import GimpLifecycle


def scheme_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _selector_expression(params: dict[str, Any]) -> str:
    if "layer_index" in params:
        return f"(vector-ref (cadr (gimp-image-get-layers image)) {int(params['layer_index'])})"
    return f"(osw-find-layer image {scheme_string(str(params['layer_name']))})"


SCHEME_HELPERS = r"""
(define (osw-find-layer image wanted)
  (let* ((info (gimp-image-get-layers image))
         (count (car info))
         (layers (cadr info)))
    (let loop ((index 0))
      (if (>= index count)
          -1
          (let ((layer (vector-ref layers index)))
            (if (string=? (car (gimp-item-get-name layer)) wanted)
                layer
                (loop (+ index 1))))))))

(define (osw-write-meta path image layer)
  (let* ((offsets (gimp-drawable-offsets layer)))
    (call-with-output-file path
      (lambda (port)
        (display (car (gimp-image-width image)) port)
        (display "\t" port)
        (display (car (gimp-image-height image)) port)
        (display "\t" port)
        (display (car (gimp-item-get-name layer)) port)
        (display "\t" port)
        (display (car (gimp-drawable-width layer)) port)
        (display "\t" port)
        (display (car (gimp-drawable-height layer)) port)
        (display "\t" port)
        (display (car offsets) port)
        (display "\t" port)
        (display (cadr offsets) port)))))
"""


class ScriptFuRunner:
    def __init__(self, lifecycle: GimpLifecycle | None = None) -> None:
        self.lifecycle = lifecycle or GimpLifecycle()

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["DISPLAY"] = os.environ.get("DISPLAY", ":0")
        env.setdefault(
            "DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/bus"
        )
        return env

    def run_scheme(self, body: str, timeout_seconds: float = 60.0) -> dict[str, Any]:
        self.lifecycle.shutdown(min(10.0, max(1.0, timeout_seconds / 3)))
        scheme = f"(begin\n{SCHEME_HELPERS}\n{body}\n(gimp-quit 0))"
        started = time.monotonic()
        process = subprocess.Popen(
            ["gimp-console", "-i", "-b", scheme],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self._env(),
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, 15)
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, 9)
                stdout, stderr = process.communicate()
            raise AdapterError(
                "GIMP_TIMEOUT",
                "GIMP Script-Fu operation timed out",
                {"stdout": stdout[-4000:], "stderr": stderr[-4000:]},
                504,
            ) from exc
        combined = stdout + "\n" + stderr
        error_markers = (
            "batch command experienced an execution error",
            "Error: eval:",
            "execution error",
        )
        if process.returncode != 0 or any(
            marker.lower() in combined.lower() for marker in error_markers
        ):
            raise AdapterError(
                "GIMP_OPERATION_FAILED",
                "GIMP Script-Fu operation failed",
                {
                    "returncode": process.returncode,
                    "stdout": stdout[-6000:],
                    "stderr": stderr[-6000:],
                },
                422,
            )
        return {
            "returncode": process.returncode,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "stdout": stdout[-2000:],
            "stderr": stderr[-2000:],
        }

    @staticmethod
    def _paths(
        output_path: str, open_in_gui: bool
    ) -> tuple[Path | None, Path | None, Path]:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        if open_in_gui or output.suffix.lower() == ".xcf":
            xcf = output
            export = None
            preview = Path(str(output) + ".preview.png")
        else:
            xcf = None
            export = output
            preview = (
                output
                if output.suffix.lower() == ".png"
                else Path(str(output) + ".preview.png")
            )
        return xcf, export, preview

    @staticmethod
    def _save_expression(
        image: str,
        drawable: str,
        xcf_path: Path | None,
        export_path: Path | None,
        preview_path: Path,
        quality: float = 0.98,
    ) -> str:
        pieces: list[str] = []
        if xcf_path:
            path = scheme_string(str(xcf_path))
            pieces.append(f"(gimp-xcf-save 1 {image} {drawable} {path} {path})")
        pieces.append(
            f"(let ((merged (car (gimp-image-merge-visible-layers {image} 1))))"
        )
        if export_path:
            destination = scheme_string(str(export_path))
            if export_path.suffix.lower() in {".jpg", ".jpeg"}:
                pieces.append(
                    f"  (file-jpeg-save 1 {image} merged {destination} {destination} "
                    f'{quality:.4f} 0 1 0 "" 2 1 0 0)'
                )
            else:
                pieces.append(
                    f"  (file-png-save2 1 {image} merged {destination} {destination} 0 9 0 0 0 0 0 0 1)"
                )
        preview = scheme_string(str(preview_path))
        if not export_path or preview_path != export_path:
            pieces.append(
                f"  (file-png-save2 1 {image} merged {preview} {preview} 0 9 0 0 0 0 0 0 1)"
            )
        pieces.append(")")
        return "\n".join(pieces)

    def _run_image_operation(
        self,
        input_path: str,
        output_path: str,
        operation: str,
        *,
        loader: str = "auto",
        open_in_gui: bool = False,
        metadata_layer: str = "drawable",
        quality: float = 0.98,
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        source = Path(input_path)
        if not source.is_file():
            raise AdapterError(
                "FILE_NOT_FOUND",
                f"input file does not exist: {source}",
                http_status=404,
            )
        xcf, export, preview = self._paths(output_path, open_in_gui)
        meta = Path(str(output_path) + ".meta.tsv")
        artifacts = (xcf, export, preview, meta)
        source_path = source.resolve()
        # GIMP must load the input, and later verification may compare against it.
        if any(path and path.resolve() == source_path for path in artifacts):
            raise AdapterError(
                "INVALID_REQUEST",
                "output artifacts overlap input_path; choose a different output_path "
                "so the source image is preserved for loading and verification",
            )
        for path in artifacts:
            if path and path.exists():
                path.unlink()
        load_proc = "file-jpeg-load" if loader == "jpeg" else "gimp-file-load"
        source_string = scheme_string(str(source))
        save = self._save_expression(
            "image", metadata_layer, xcf, export, preview, quality
        )
        body = f"""
(let* ((image (car ({load_proc} 1 {source_string} {source_string})))
       (drawable (car (gimp-image-get-active-layer image))))
  {operation}
  (osw-write-meta {scheme_string(str(meta))} image {metadata_layer})
  {save}
  (gimp-image-delete image))
"""
        execution = self.run_scheme(body, timeout_seconds)
        required = [path for path in (xcf or export, preview, meta) if path]
        missing = [
            str(path)
            for path in required
            if not path.is_file() or path.stat().st_size == 0
        ]
        if missing:
            raise AdapterError(
                "PARTIAL_COMPLETION",
                "GIMP did not produce all expected artifacts",
                {"missing": missing, "execution": execution},
                422,
            )
        result = {
            "input_path": str(source),
            "output_path": str(xcf or export),
            "preview_path": str(preview),
            "metadata_path": str(meta),
            "metadata": parse_metadata(meta),
            "execution": execution,
        }
        if open_in_gui and xcf:
            # Large indexed/alpha XCFs can take more than 25 seconds to become
            # visible after a previous large GIMP process has exited. The
            # outer request timeout remains the hard limit.
            result["gui"] = self.lifecycle.reopen(str(xcf), min(60.0, timeout_seconds))
        return result

    def inspect(self, path: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
        source = Path(path)
        if not source.is_file():
            raise AdapterError(
                "FILE_NOT_FOUND", f"image does not exist: {source}", http_status=404
            )
        meta = Path("/tmp/osworld-gimp-adapter-inspect.tsv")
        source_string = scheme_string(str(source))
        body = f"""
(let* ((image (car (gimp-file-load 1 {source_string} {source_string})))
       (drawable (car (gimp-image-get-active-layer image))))
  (osw-write-meta {scheme_string(str(meta))} image drawable)
  (gimp-image-delete image))
"""
        execution = self.run_scheme(body, timeout_seconds)
        if not meta.is_file():
            raise AdapterError(
                "PARTIAL_COMPLETION",
                "GIMP inspection metadata is missing",
                http_status=422,
            )
        return {
            "path": str(source),
            "metadata": parse_metadata(meta),
            "execution": execution,
        }

    def export(
        self,
        input_path: str,
        output_path: str,
        *,
        loader: str = "auto",
        quality: float = 0.98,
        timeout_seconds: float = 60.0,
    ) -> dict[str, Any]:
        return self._run_image_operation(
            input_path,
            output_path,
            "",
            loader=loader,
            quality=quality,
            timeout_seconds=timeout_seconds,
        )

    def convert_indexed(
        self, params: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        colors = int(params.get("colors", 256))
        operation = f'(gimp-image-convert-indexed image 0 0 {colors} 0 1 "")'
        return self._run_image_operation(
            params["input_path"],
            params["output_path"],
            operation,
            open_in_gui=bool(params.get("open_in_gui", False)),
            timeout_seconds=timeout_seconds,
        )

    def adjust(self, params: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        commands: list[str] = []
        brightness = int(params.get("brightness", 0))
        contrast = int(params.get("contrast", 0))
        if brightness or contrast:
            commands.append(
                f"(gimp-brightness-contrast drawable {brightness} {contrast})"
            )
        saturation = float(params.get("saturation", 0))
        if saturation:
            commands.append(f"(gimp-hue-saturation drawable 0 0 0 {saturation})")
        return self._run_image_operation(
            params["input_path"],
            params["output_path"],
            "\n  ".join(commands),
            open_in_gui=bool(params.get("open_in_gui", False)),
            timeout_seconds=timeout_seconds,
        )

    def flip(self, params: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        orientation = 0 if params.get("direction", "horizontal") == "horizontal" else 1
        operation = f"(gimp-item-transform-flip-simple drawable {orientation} 1 0)"
        return self._run_image_operation(
            params["input_path"],
            params["output_path"],
            operation,
            open_in_gui=bool(params.get("open_in_gui", False)),
            timeout_seconds=timeout_seconds,
        )

    def apply_alpha_mask(
        self, params: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        mask = Path(params["mask_path"])
        if not mask.is_file():
            raise AdapterError(
                "FILE_NOT_FOUND", f"mask file does not exist: {mask}", http_status=404
            )
        mask_string = scheme_string(str(mask))
        operation = f"""
(let ((mask-layer (car (gimp-file-load-layer 1 image {mask_string}))))
  (gimp-image-insert-layer image mask-layer 0 0)
  (gimp-image-select-item image 2 mask-layer)
  (gimp-image-remove-layer image mask-layer)
  (gimp-selection-invert image)
  (gimp-layer-add-alpha drawable)
  (gimp-edit-clear drawable)
  (gimp-selection-none image))
"""
        return self._run_image_operation(
            params["input_path"],
            params["output_path"],
            operation,
            open_in_gui=bool(params.get("open_in_gui", False)),
            timeout_seconds=timeout_seconds,
        )

    def layer_add(
        self, params: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        width = int(params.get("width", 0))
        height = int(params.get("height", 0))
        width_expr = str(width) if width else "(car (gimp-image-width image))"
        height_expr = str(height) if height else "(car (gimp-image-height image))"
        name = scheme_string(params["name"])
        operation = f"""
(let ((new-layer (car (gimp-layer-new image {width_expr} {height_expr} 1 {name} 100 28))))
  (gimp-image-insert-layer image new-layer 0 0)
  (gimp-drawable-fill new-layer 3)
  (set! drawable new-layer))
"""
        return self._run_image_operation(
            params["input_path"],
            params["output_path"],
            operation,
            open_in_gui=bool(params.get("open_in_gui", False)),
            metadata_layer="drawable",
            timeout_seconds=timeout_seconds,
        )

    def layer_fill(
        self, params: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        selector = _selector_expression(params)
        color = params["color"][:3]
        operation = f"""
(let ((selected-layer {selector}))
  (if (< selected-layer 0) (error \"layer not found\"))
  (gimp-context-set-foreground '({color[0]} {color[1]} {color[2]}))
  (gimp-drawable-fill selected-layer 0)
  (set! drawable selected-layer))
"""
        return self._run_image_operation(
            params["input_path"],
            params["output_path"],
            operation,
            open_in_gui=bool(params.get("open_in_gui", False)),
            timeout_seconds=timeout_seconds,
        )

    def layer_scale(
        self, params: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        selector = _selector_expression(params)
        width = params.get("width")
        height = params.get("height")
        if width is None:
            width_expr = f"(quotient (+ (* old-width {int(height)}) (quotient old-height 2)) old-height)"
        else:
            width_expr = str(int(width))
        if height is None:
            height_expr = f"(quotient (+ (* old-height {int(width)}) (quotient old-width 2)) old-width)"
        else:
            height_expr = str(int(height))
        operation = f"""
(let* ((selected-layer {selector})
       (old-width (car (gimp-drawable-width selected-layer)))
       (old-height (car (gimp-drawable-height selected-layer)))
       (new-width {width_expr})
       (new-height {height_expr}))
  (if (< selected-layer 0) (error \"layer not found\"))
  (gimp-layer-scale selected-layer new-width new-height 1)
  (set! drawable selected-layer))
"""
        return self._run_image_operation(
            params["input_path"],
            params["output_path"],
            operation,
            open_in_gui=bool(params.get("open_in_gui", False)),
            timeout_seconds=timeout_seconds,
        )

    def layer_translate(
        self, params: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        selector = _selector_expression(params)
        x = float(params["x"])
        y = float(params["y"])
        operation = f"""
(let* ((selected-layer {selector})
       (offsets (gimp-drawable-offsets selected-layer)))
  (if (< selected-layer 0) (error \"layer not found\"))
  (gimp-item-transform-translate selected-layer (- {x} (car offsets)) (- {y} (cadr offsets)))
  (set! drawable selected-layer))
"""
        return self._run_image_operation(
            params["input_path"],
            params["output_path"],
            operation,
            open_in_gui=bool(params.get("open_in_gui", False)),
            timeout_seconds=timeout_seconds,
        )


def parse_metadata(path: Path) -> dict[str, Any]:
    values = path.read_text(encoding="utf-8").split("\t")
    if len(values) != 7:
        raise AdapterError(
            "INVALID_IMAGE",
            "GIMP metadata has an unexpected shape",
            {"path": str(path), "content": path.read_text(encoding="utf-8")},
            422,
        )
    return {
        "image_width": int(values[0]),
        "image_height": int(values[1]),
        "layer_name": values[2],
        "layer_width": int(values[3]),
        "layer_height": int(values[4]),
        "offset_x": int(values[5]),
        "offset_y": int(values[6]),
    }
