from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from multi_apps_adapter.route_utils import (
    contains_route,
    contains_route_in_prose,
    decode_text,
    has_unresolved_encoding,
    is_route,
    normalize_route,
)

from .tool_catalog import FORBIDDEN_DATASET_ACTIONS


UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
DATASET_REFERENCE_MARKERS = ("osworld_baby_justin_bieber",)
MODEL_HIDDEN_METADATA_KEYS = frozenset(
    {
        "answer",
        "answer_sheet",
        "cloud_file",
        "dataset",
        "evaluation_examples",
        "evaluator",
        "evaluator_config",
        "evaluator_url",
        "expected",
        "expected_getter",
        "expected_state",
        "expected_value",
        "golden",
        "golden_file",
        "golden_hash",
        "golden_url",
        "reference_state",
        "reference",
        "postconfig",
        "reference_artifact",
        "result_getter",
        "reasoning_effort_effective",
        "reasoning_effort_requested",
        "reasoning_mode_effective",
        "reasoning_mode_requested",
        "reasoning_observed",
        "model_actual",
        "dataset_id",
        "dataset_order",
        "reward",
        "task_id",
        "task_uuid",
        "task_prefix",
        "uuid",
    }
)
_MODEL_HIDDEN_METADATA_KEYS_NORMALIZED = frozenset(
    normalize_route(key) for key in MODEL_HIDDEN_METADATA_KEYS
)
_MODEL_HIDDEN_METADATA_PREFIXES = frozenset(
    normalize_route(key)
    for key in (
        "answer",
        "dataset",
        "evaluation",
        "evaluator",
        "expected",
        "golden",
        "reference",
        "result_getter",
        "task",
        "uuid",
    )
)
_MODEL_HIDDEN_METADATA_SUFFIXES = frozenset(
    {
        "artifact",
        "file",
        "getter",
        "hash",
        "id",
        "order",
        "path",
        "prefix",
        "profile",
        "secret",
        "state",
        "url",
        "value",
    }
)
_SENSITIVE_CONTEXT_KEYS = frozenset(
    {
        "error",
        "errorcode",
        "details",
        "cause",
        "previouserror",
        "exception",
        "failure",
    }
)
_SENSITIVE_IDENTIFIER_RE = re.compile(
    r"(?i)^(?:answer|expected|reference|dataset|golden|evaluator)"
    r"(?:[_:.\-/](?:artifact|file|getter|hash|id|order|path|prefix|"
    r"profile|secret|state|url|value))+$"
)
MODEL_HIDDEN_STRING_MARKERS = (
    "artifact.materialize",
    "assessment.grade_multiple_choice_documents",
    "assessment_grade_multiple_choice_documents",
    "task.execute",
    "task.inspect",
    "task_execute",
    "task_inspect",
    "evaluation_examples",
    "expected_state",
    "reference_state",
    "reference_profile",
    "dataset_id",
    "evaluator_url",
    "expected_getter",
    "golden_file",
    "golden_hash",
    "golden_url",
    "result_getter",
    "task_manifest.json",
    "ubuntu_osworld_file_cache",
    "xlang-ai/osworld",
    "xlangai/osworld",
    *DATASET_REFERENCE_MARKERS,
)
REDACTED_BENCHMARK_METADATA = "<internal-benchmark-metadata>"


def _is_hidden_metadata_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    normalized = normalize_route(key)
    if normalized in _MODEL_HIDDEN_METADATA_KEYS_NORMALIZED:
        return True
    if any(
        normalized.startswith(prefix)
        and normalized[len(prefix) :] in _MODEL_HIDDEN_METADATA_SUFFIXES
        for prefix in _MODEL_HIDDEN_METADATA_PREFIXES
    ):
        return True
    return bool(
        has_unresolved_encoding(key) or contains_route(key, FORBIDDEN_DATASET_ACTIONS)
    )


def _contains_hidden_string_marker(
    value: Any, *, sensitive_context: bool = False
) -> bool:
    """Match sensitive markers after the same bounded decoding as route checks."""
    if not isinstance(value, (str, bytes, bytearray)):
        return False
    if has_unresolved_encoding(value):
        return True
    decoded = decode_text(value)
    folded = decoded.casefold()
    if _SENSITIVE_IDENTIFIER_RE.fullmatch(decoded.strip()):
        return True
    return bool(
        (
            any(marker.casefold() in folded for marker in MODEL_HIDDEN_STRING_MARKERS)
            or (
                sensitive_context
                and any(
                    re.search(
                        rf"(?<![A-Za-z0-9_]){re.escape(marker)}(?=$|[^A-Za-z0-9_])",
                        decoded,
                        re.IGNORECASE,
                    )
                    for marker in (
                        "answer",
                        "dataset",
                        "golden",
                        "evaluator",
                    )
                )
            )
        )
        or (
            contains_route(value, FORBIDDEN_DATASET_ACTIONS)
            if sensitive_context
            else contains_route_in_prose(value, FORBIDDEN_DATASET_ACTIONS)
        )
    )


def _contains_hidden_metadata_key(value: Any) -> bool:
    """Walk a model surface so assert and result sanitization share key rules."""
    if isinstance(value, dict):
        return any(
            _is_hidden_metadata_key(key) or _contains_hidden_metadata_key(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_hidden_metadata_key(item) for item in value)
    return False


def _iter_surface_strings(value: Any) -> Iterator[str | bytes | bytearray]:
    """Yield strings without joining tokens across structured boundaries."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_surface_strings(key)
            yield from _iter_surface_strings(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_surface_strings(item)
        return
    if isinstance(value, (str, bytes)):
        decoded = decode_text(value)
        try:
            nested = json.loads(decoded)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        else:
            if isinstance(nested, (dict, list)):
                yield from _iter_surface_strings(nested)
                return
        yield value
        return
    if isinstance(value, bytearray):
        yield value


def task_identity_tokens(task_id: str) -> tuple[str, ...]:
    if not task_id:
        return ()
    if UUID_RE.fullmatch(task_id):
        return (task_id, task_id[:8])
    return (task_id,)


def _task_identity_pattern(token: str) -> re.Pattern[str]:
    """Match an identity token without treating it as an arbitrary substring."""
    return re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])",
        flags=re.IGNORECASE,
    )


def _contains_task_identity(value: Any, task_id: str) -> bool:
    """Match raw and bounded-encoded task identity without exposing it."""
    if has_unresolved_encoding(value):
        return True
    decoded_value = decode_text(value).casefold()
    return any(
        _task_identity_pattern(token).search(decoded_value) is not None
        for token in task_identity_tokens(task_id)
    )


def sanitize_agent_visible_result(
    value: Any,
    benchmark_task_id: str,
    *,
    _sensitive_context: bool = False,
) -> Any:
    """Remove benchmark identity before Adapter results return to the model."""
    if isinstance(value, dict):
        return {
            key: sanitize_agent_visible_result(
                item,
                benchmark_task_id,
                _sensitive_context=(
                    _sensitive_context
                    or normalize_route(key) in _SENSITIVE_CONTEXT_KEYS
                ),
            )
            for key, item in value.items()
            if not _is_hidden_metadata_key(key)
        }
    if isinstance(value, list):
        return [
            sanitize_agent_visible_result(
                item,
                benchmark_task_id,
                _sensitive_context=_sensitive_context,
            )
            for item in value
        ]
    if isinstance(value, str):
        sanitized = value
        for token in task_identity_tokens(benchmark_task_id):
            sanitized = _task_identity_pattern(token).sub(
                "<internal-benchmark-task>", sanitized
            )
        if _contains_task_identity(sanitized, benchmark_task_id):
            return REDACTED_BENCHMARK_METADATA
        if _contains_hidden_string_marker(
            sanitized, sensitive_context=_sensitive_context
        ):
            return REDACTED_BENCHMARK_METADATA
        return sanitized
    if isinstance(value, (bytes, bytearray)):
        if _contains_task_identity(
            value, benchmark_task_id
        ) or _contains_hidden_string_marker(
            value, sensitive_context=_sensitive_context
        ):
            return REDACTED_BENCHMARK_METADATA
        return value
    return value


def sanitize_gui_result_for_model(value: Any) -> dict[str, Any]:
    """Keep only safe GUI acknowledgement and optional grounded-action evidence.

    Desktop transport details remain out of the model context.  A delegated
    Holo turn may additionally provide its validated action payload so the parent can
    audit what was actually sent to the gateway; arbitrary gateway metadata is
    intentionally discarded.
    """
    result: dict[str, Any] = {"environment_acknowledged": True}
    if not isinstance(value, dict):
        return result
    grounded = value.get("grounded_action")
    if not isinstance(grounded, dict):
        return result
    action = grounded.get("action")
    if not isinstance(action, str) or not action:
        return result
    safe: dict[str, Any] = {"action": action}
    for key in ("x", "y", "to_x", "to_y", "amount", "seconds"):
        item = grounded.get(key)
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            safe[key] = item
    for key in ("text", "key"):
        item = grounded.get(key)
        if isinstance(item, str):
            safe[key] = item
    keys = grounded.get("keys")
    if isinstance(keys, list) and all(isinstance(item, str) for item in keys):
        safe["keys"] = list(keys)
    modifiers = grounded.get("modifiers")
    if (
        action == "click"
        and isinstance(modifiers, list)
        and all(isinstance(item, str) for item in modifiers)
    ):
        safe["modifiers"] = list(modifiers)
    press_enter = grounded.get("press_enter")
    if isinstance(press_enter, bool):
        safe["press_enter"] = press_enter
    result["grounded_action"] = safe
    return result


def assert_agent_surface_safe(
    *,
    task_id: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> None:
    """Fail closed when benchmark identity or task routes reach the model."""
    encoded = json.dumps(
        {"messages": messages, "tools": tools},
        ensure_ascii=False,
        sort_keys=True,
    )
    decoded_encoded = decode_text(encoded)
    folded_encoded = decoded_encoded.casefold()
    dynamic_messages = [
        message for message in messages if message.get("role") != "system"
    ]
    complete_surface = {"messages": messages, "tools": tools}
    dynamic_surface = {"messages": dynamic_messages, "tools": tools}
    dynamic_strings = tuple(_iter_surface_strings(dynamic_surface))
    folded_dynamic_strings = tuple(
        decode_text(value).casefold() for value in dynamic_strings
    )
    if has_unresolved_encoding(encoded):
        raise RuntimeError(
            "unresolved encoded metadata leaked into the model-visible surface"
        )
    if _contains_hidden_metadata_key(messages) or _contains_hidden_metadata_key(tools):
        raise RuntimeError("hidden benchmark metadata keys leaked into strict mode")
    leaked_identity = [
        token
        for token in task_identity_tokens(task_id)
        if token.casefold() in folded_encoded
        or token.casefold() in decode_text(encoded).casefold()
    ]
    if leaked_identity:
        raise RuntimeError(
            "benchmark task identity leaked into the model-visible surface"
        )

    names = {tool["function"]["name"] for tool in tools}
    forbidden = {name for name in names if is_route(name, FORBIDDEN_DATASET_ACTIONS)}
    if forbidden:
        raise RuntimeError(
            f"legacy dataset tools leaked into strict mode: {sorted(forbidden)}"
        )

    leaked_markers = [
        marker
        for marker in MODEL_HIDDEN_STRING_MARKERS
        if any(marker.casefold() in value for value in folded_dynamic_strings)
    ]
    if any(
        contains_route_in_prose(value, FORBIDDEN_DATASET_ACTIONS)
        for value in _iter_surface_strings(complete_surface)
    ):
        raise RuntimeError("forbidden dataset routes leaked into strict mode")
    if leaked_markers or any(
        _contains_hidden_string_marker(value) for value in dynamic_strings
    ):
        raise RuntimeError(
            f"hidden benchmark metadata leaked into strict mode: {leaked_markers}"
        )
