from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import unquote, urlparse
from uuid import uuid4

from .errors import AdapterError


DIRECT_IMAGE_SUFFIXES = frozenset(
    {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
)
LAYERED_IMAGE_SUFFIXES = frozenset({".ora", ".psd", ".svg", ".xcf"})
SUPPORTED_IMAGE_SUFFIXES = DIRECT_IMAGE_SUFFIXES | LAYERED_IMAGE_SUFFIXES
TEMP_ROOT = Path("/tmp/osworld-multi-apps-image-document")


class AdapterCaller(Protocol):
    def call_adapter(
        self, params: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]: ...

    @staticmethod
    def _downstream_result(call: dict[str, Any]) -> dict[str, Any]: ...


def _local_path(value: str) -> Path:
    if value.startswith(("/", "~/")):
        return Path(value).expanduser().resolve()
    parsed = urlparse(value)
    if parsed.scheme == "file" and parsed.netloc in {"", "localhost"}:
        return Path(unquote(parsed.path)).expanduser().resolve()
    raise AdapterError(
        "INVALID_PATH",
        "source_path must be an absolute, ~/, or local file URL path",
        {"source_path": value},
    )


def create_document_from_image(
    caller: AdapterCaller,
    params: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    """Render an image when needed, then create and verify a Writer DOCX."""
    source_path = _local_path(params["source_path"])
    if not source_path.is_file() or source_path.stat().st_size == 0:
        raise AdapterError(
            "FILE_NOT_FOUND",
            "the source image is missing or empty",
            {"source_path": str(source_path)},
            404,
        )
    suffix = source_path.suffix.casefold()
    if suffix not in SUPPORTED_IMAGE_SUFFIXES:
        raise AdapterError(
            "UNSUPPORTED_IMAGE_FORMAT",
            "the source image format is not supported",
            {
                "source_path": str(source_path),
                "supported_suffixes": sorted(SUPPORTED_IMAGE_SUFFIXES),
            },
            422,
        )

    started = time.monotonic()

    def remaining_seconds() -> float:
        remaining = timeout_seconds - (time.monotonic() - started)
        if remaining <= 0.1:
            raise AdapterError(
                "OPERATION_TIMEOUT",
                "image-to-document conversion exceeded its timeout",
                http_status=504,
            )
        return remaining

    rendered_path: Path | None = None
    render_result: dict[str, Any] | None = None
    writer_result: dict[str, Any] | None = None
    writer_verification: dict[str, Any] | None = None
    try:
        writer_source = source_path
        if suffix in LAYERED_IMAGE_SUFFIXES:
            TEMP_ROOT.mkdir(parents=True, exist_ok=True)
            rendered_path = TEMP_ROOT / f"{uuid4().hex}.png"
            render_call = caller.call_adapter(
                {
                    "adapter": "gimp",
                    "action": "image.export",
                    "payload": {
                        "params": {
                            "input_path": str(source_path),
                            "output_path": str(rendered_path),
                        }
                    },
                },
                remaining_seconds(),
            )
            render_result = caller._downstream_result(render_call)
            if not rendered_path.is_file() or rendered_path.stat().st_size == 0:
                raise AdapterError(
                    "RENDER_FAILED",
                    "GIMP reported success without producing a nonempty PNG render",
                    {"source_path": str(source_path)},
                    502,
                )
            writer_source = rendered_path

        writer_call = caller.call_adapter(
            {
                "adapter": "libreoffice_writer",
                "action": "document.create_from_image",
                "payload": {
                    "params": {
                        "source_path": str(writer_source),
                        "output_path": params["output_path"],
                        "overwrite": bool(params.get("overwrite", True)),
                    }
                },
            },
            remaining_seconds(),
        )
        writer_result = caller._downstream_result(writer_call)
        raw_response = writer_call.get("response")
        if isinstance(raw_response, dict) and isinstance(
            raw_response.get("verification"), dict
        ):
            writer_verification = raw_response["verification"]
        if not writer_verification or writer_verification.get("passed") is not True:
            raise AdapterError(
                "VERIFICATION_FAILED",
                "Writer did not verify the generated image document",
                {"verification": writer_verification},
                422,
            )
    finally:
        if rendered_path is not None:
            rendered_path.unlink(missing_ok=True)
            try:
                TEMP_ROOT.rmdir()
            except OSError:
                pass

    assert writer_result is not None
    assert writer_verification is not None
    return {
        "source_path": str(source_path),
        "source_format": suffix.removeprefix("."),
        "source_rendered": render_result is not None,
        "render_adapter": "gimp" if render_result is not None else None,
        "output_path": writer_result.get("output_path", params["output_path"]),
        "output_bytes": writer_result.get("output_bytes"),
        "embedded_image_count": writer_result.get("embedded_image_count"),
        "reopened": writer_result.get("reopened"),
        "verified": writer_result.get("verified"),
        "temporary_render_removed": rendered_path is None or not rendered_path.exists(),
        "verification": writer_verification,
    }
