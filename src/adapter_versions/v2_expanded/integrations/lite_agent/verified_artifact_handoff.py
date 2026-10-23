"""Bind verified local Adapter outputs to later typed path schemas.

The model still chooses the consumer action and every argument. This module
only narrows a consumer path schema to compatible files observed in a prior
successful Adapter result; it never executes an action or manufactures a path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable

from . import media_presentation_semantics
from .adapter_results import has_passed_verification


@dataclass(frozen=True)
class HandoffSpec:
    producer: str
    consumer: str
    consumer_field: str
    kind: str


_AUDIO = HandoffSpec(
    "media.extract_current_audio",
    "presentation.insert_audio",
    "path",
    "audio",
)
_FRAME = HandoffSpec(
    "media.extract_current_frame",
    "presentation.set_background_image",
    "image_path",
    "image",
)
_DOCUMENT_IMAGE = HandoffSpec(
    "document.extract_images",
    "desktop.set_wallpaper",
    "image_path",
    "image",
)

_SUFFIXES = {
    "audio": frozenset({".mp3", ".wav"}),
    "image": frozenset(
        {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
    ),
}
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


def _normalized(instruction: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-_]", " ", instruction.casefold())).strip()


def requests_document_image_wallpaper(instruction: str) -> bool:
    """Recognize a document-image to desktop-wallpaper transfer."""
    text = _normalized(instruction)
    document = re.search(r"\b(?:doc|docx|document|odt|word|writer)\b", text)
    image = re.search(r"\b(?:graphic|image|photo|picture)\b", text)
    extraction = re.search(r"\b(?:copy|export|extract|get|pull|save)\w*\b", text)
    wallpaper = re.search(
        r"\bwallpaper\b|\bdesktop\b.{0,40}\bbackground\b|"
        r"\bbackground\b.{0,40}\bdesktop\b",
        text,
    )
    apply = re.search(r"\b(?:apply|change|make|set|use)\w*\b", text)
    return bool(document and image and extraction and wallpaper and apply)


def required_actions(domain: str, instruction: str) -> list[str]:
    """Return the additional public chain not owned by media semantics."""
    if domain == "multi_apps" and requests_document_image_wallpaper(instruction):
        return [_DOCUMENT_IMAGE.producer, _DOCUMENT_IMAGE.consumer]
    return []


def active_handoff(domain: str, instruction: str) -> HandoffSpec | None:
    """Resolve one reusable handoff from public instruction semantics only."""
    if domain != "multi_apps":
        return None
    media_actions = media_presentation_semantics.required_actions(domain, instruction)
    if media_actions == [_AUDIO.producer, _AUDIO.consumer]:
        return _AUDIO
    if media_actions == [_FRAME.producer, _FRAME.consumer]:
        return _FRAME
    if requests_document_image_wallpaper(instruction):
        return _DOCUMENT_IMAGE
    return None


def _local_file(path: Any, kind: str) -> str | None:
    if not isinstance(path, str) or not path.startswith(("/", "~/")):
        return None
    value = path.strip()
    if not value or value.endswith("/"):
        return None
    suffix = PurePosixPath(value).suffix.casefold()
    return value if suffix in _SUFFIXES[kind] else None


def _adapter_result(event: Any, action: str) -> dict[str, Any] | None:
    value = getattr(event, "result", None)
    if not isinstance(value, dict):
        return None
    envelope = value.get("adapter_response")
    if (
        not isinstance(envelope, dict)
        or envelope.get("status") != "ok"
        or envelope.get("action") != action
        or not isinstance(envelope.get("result"), dict)
    ):
        return None
    result = envelope["result"]
    if result.get("status") not in {None, "ok"}:
        return None
    return result


def _media_payload(result: dict[str, Any], spec: HandoffSpec) -> dict[str, Any] | None:
    """Unwrap the generic facade while retaining only a concrete media result."""
    pending: list[Any] = [result]
    seen: set[int] = set()
    for _depth in range(8):
        next_pending: list[Any] = []
        for value in pending:
            if not isinstance(value, dict) or id(value) in seen:
                continue
            seen.add(id(value))
            path = _local_file(value.get("output_path"), spec.kind)
            probe = value.get("probe")
            if path is not None and isinstance(probe, dict):
                if spec is _AUDIO and isinstance(value.get("output_sha256"), str):
                    return value
                if spec is _FRAME and isinstance(value.get("frame_index"), int):
                    return value
            for key in ("response", "result", "adapter_response"):
                child = value.get(key)
                if isinstance(child, dict):
                    next_pending.append(child)
        pending = next_pending
    return None


def _verified_document_images(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Find the Adapter's verified image records without trusting the hint alone."""
    pending: list[Any] = [result]
    seen: set[int] = set()
    for _depth in range(8):
        next_pending: list[Any] = []
        for value in pending:
            if not isinstance(value, dict) or id(value) in seen:
                continue
            seen.add(id(value))
            images = value.get("images")
            verification = value.get("verification")
            if (
                isinstance(images, list)
                and isinstance(verification, dict)
                and verification.get("passed") is True
            ):
                return [item for item in images if isinstance(item, dict)]
            nested_result = value.get("result")
            if (
                isinstance(nested_result, dict)
                and isinstance(nested_result.get("images"), list)
                and isinstance(verification, dict)
                and verification.get("passed") is True
            ):
                return [
                    item for item in nested_result["images"] if isinstance(item, dict)
                ]
            for key in ("response", "result", "adapter_response"):
                child = value.get(key)
                if isinstance(child, dict):
                    next_pending.append(child)
        pending = next_pending
    return []


def _media_candidates(event: Any, spec: HandoffSpec) -> list[str]:
    envelope_result = _adapter_result(event, spec.producer)
    value = getattr(event, "result", None)
    hint = value.get("context_hint") if isinstance(value, dict) else None
    result = (
        _media_payload(envelope_result, spec) if envelope_result is not None else None
    )
    if result is None or not isinstance(hint, dict):
        return []
    path = _local_file(result.get("output_path"), spec.kind)
    if path is None or hint.get("output_path") != path:
        return []
    if spec is _AUDIO:
        digest = result.get("output_sha256")
        probe = result.get("probe")
        streams = probe.get("streams") if isinstance(probe, dict) else None
        if (
            not isinstance(digest, str)
            or not _HEX_SHA256.fullmatch(digest)
            or hint.get("output_sha256") != digest
            or not isinstance(streams, list)
            or not any(
                isinstance(stream, dict) and stream.get("codec_type") == "audio"
                for stream in streams
            )
            or not isinstance(hint.get("audio_stream_count"), int)
            or hint["audio_stream_count"] < 1
        ):
            return []
    else:
        probe = result.get("probe")
        streams = probe.get("streams") if isinstance(probe, dict) else None
        output_format = probe.get("format") if isinstance(probe, dict) else None
        size = output_format.get("size") if isinstance(output_format, dict) else None
        if (
            not isinstance(streams, list)
            or not any(
                isinstance(stream, dict)
                and stream.get("codec_type") == "video"
                and isinstance(stream.get("width"), int)
                and stream["width"] > 0
                and isinstance(stream.get("height"), int)
                and stream["height"] > 0
                for stream in streams
            )
            or not str(size or "").isdigit()
            or int(size) < 1
            or not isinstance(result.get("frame_index"), int)
            or hint.get("frame_index") != result.get("frame_index")
        ):
            return []
    return [path]


def _document_image_candidates(event: Any) -> list[str]:
    value = getattr(event, "result", None)
    hint = value.get("context_hint") if isinstance(value, dict) else None
    if (
        not isinstance(hint, dict)
        or hint.get("downstream_action") != _DOCUMENT_IMAGE.producer
        or hint.get("downstream_status") != "ok"
        or hint.get("verification_passed") is not True
        or not has_passed_verification(value)
    ):
        return []
    result = _adapter_result(event, _DOCUMENT_IMAGE.producer)
    context = hint.get("downstream_context")
    images = context.get("images") if isinstance(context, dict) else None
    verified_images = _verified_document_images(result) if result else []
    if not isinstance(images, list) or not verified_images:
        return []
    verified_by_path = {
        item.get("output_path"): item
        for item in verified_images
        if isinstance(item.get("output_path"), str)
    }
    candidates: list[str] = []
    for image in images:
        if not isinstance(image, dict):
            continue
        path = _local_file(image.get("output_path"), "image")
        digest = image.get("sha256")
        size = image.get("size_bytes")
        media_type = image.get("media_type")
        adapter_image = verified_by_path.get(path)
        if (
            path is None
            or not isinstance(digest, str)
            or not _HEX_SHA256.fullmatch(digest)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 1
            or not isinstance(media_type, str)
            or not media_type.casefold().startswith("image/")
            or not isinstance(adapter_image, dict)
            or adapter_image.get("sha256") != digest
            or adapter_image.get("size_bytes") != size
            or adapter_image.get("media_type") != media_type
        ):
            continue
        candidates.append(path)
    return list(dict.fromkeys(candidates))


def _event_candidates(event: Any, spec: HandoffSpec) -> list[str]:
    if not getattr(event, "executed", False) or getattr(event, "error", None):
        return []
    proposed = getattr(event, "proposed", None)
    if not isinstance(proposed, dict) or proposed.get("action") != spec.producer:
        return []
    if spec is _DOCUMENT_IMAGE:
        return _document_image_candidates(event)
    return _media_candidates(event, spec)


def observed_candidates(
    state: Any, spec: HandoffSpec | None = None, *, before_step: int | None = None
) -> list[str]:
    """Return the latest verified compatible producer outputs."""
    resolved = spec or active_handoff(
        str(getattr(state, "domain", "")), str(getattr(state, "instruction", ""))
    )
    if resolved is None:
        return []
    events = list(getattr(state, "events", ()))
    for event in reversed(events):
        if before_step is not None and getattr(event, "step", 0) >= before_step:
            continue
        candidates = _event_candidates(event, resolved)
        if candidates:
            return candidates
    return []


def stage_actions(state: Any, actions: Iterable[str]) -> list[str]:
    """Focus a consumer only after a compatible producer artifact exists."""
    selected = list(actions)
    spec = active_handoff(str(state.domain), str(state.instruction))
    if (
        spec is None
        or state.successful_action_events(spec.consumer)
        or not observed_candidates(state, spec)
    ):
        return selected
    focused = [action for action in selected if action == spec.consumer]
    return focused or selected


def constrain_tool_schema(function: dict[str, Any], state: Any) -> None:
    """Constrain one consumer path to verified observed artifacts."""
    spec = active_handoff(str(state.domain), str(state.instruction))
    candidates = observed_candidates(state, spec)
    if (
        spec is None
        or not candidates
        or function.get("name")
        != "adapter__" + re.sub(r"[^a-zA-Z0-9_]", "_", spec.consumer)
    ):
        return
    parameters = function.get("parameters")
    properties = parameters.get("properties") if isinstance(parameters, dict) else None
    field_schema = (
        properties.get(spec.consumer_field) if isinstance(properties, dict) else None
    )
    if not isinstance(field_schema, dict):
        return
    field_schema["enum"] = candidates
    field_schema["description"] = (
        str(field_schema.get("description", "")).rstrip()
        + " Select one exact compatible local artifact observed from the preceding verified "
        "Adapter result. The model must submit the choice; the Runner does not inject or "
        "rewrite this argument."
    ).strip()


def argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    """Reject a consumer path outside the observed set without repairing it."""
    spec = active_handoff(str(state.domain), str(state.instruction))
    candidates = observed_candidates(state, spec)
    if spec is None or action != spec.consumer or not candidates:
        return []
    value = arguments.get(spec.consumer_field)
    if value in candidates:
        return []
    return [
        f"{spec.consumer}.{spec.consumer_field} must be one exact compatible path from "
        f"the preceding verified Adapter result; model-selected value {value!r} is not "
        f"in the observed candidate set {candidates!r}"
    ]


def completion_errors(state: Any) -> list[str]:
    """Require a successful producer-to-consumer relation for transfer intent."""
    spec = active_handoff(str(state.domain), str(state.instruction))
    if spec is None:
        return []
    producer_events = state.successful_action_events(spec.producer)
    if not producer_events or not observed_candidates(state, spec):
        return [
            f"the requested transfer lacks a verified compatible {spec.producer} artifact"
        ]
    for event in state.successful_action_events(spec.consumer):
        arguments = event.proposed.get("arguments")
        candidates = observed_candidates(state, spec, before_step=event.step)
        if (
            isinstance(arguments, dict)
            and arguments.get(spec.consumer_field) in candidates
        ):
            return []
    return [
        f"the requested transfer lacks a successful {spec.consumer} call using a "
        f"model-selected path from the preceding verified {spec.producer} result"
    ]


__all__ = [
    "HandoffSpec",
    "active_handoff",
    "argument_contract_errors",
    "completion_errors",
    "constrain_tool_schema",
    "observed_candidates",
    "requests_document_image_wallpaper",
    "required_actions",
    "stage_actions",
]
