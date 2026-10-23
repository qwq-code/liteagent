"""Provider reasoning controls used by requests and frozen conditions.

There are two deliberately separate concepts here:

* ``reasoning_effort`` is a tiered provider option (when a provider really
  implements one), and
* ``reasoning_mode`` is the binary thinking switch used by Qwen3.5.

Keeping the controls separate prevents a generic OpenAI-compatible enum from
being mistaken for a capability of a particular model template.
"""

from __future__ import annotations

SUPPORTED_REASONING_EFFORTS = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

SUPPORTED_REASONING_MODES = ("thinking", "non_thinking")


def normalize_reasoning_mode(value: object) -> str | None:
    """Return a canonical binary mode, or ``None`` for an unknown value."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold().replace("-", "_")
    aliases = {
        "think": "thinking",
        "thinking": "thinking",
        "on": "thinking",
        "enabled": "thinking",
        "nonthinking": "non_thinking",
        "non_thinking": "non_thinking",
        "no_thinking": "non_thinking",
        "off": "non_thinking",
        "disabled": "non_thinking",
    }
    return aliases.get(normalized)


def extract_reasoning_effort_enum(document: object) -> tuple[str, ...]:
    """Find the provider's declared reasoning-effort values in an OpenAPI document.

    OpenAI-compatible servers place the request schema at different paths, so
    this deliberately walks only dictionaries looking for a
    ``reasoning_effort`` property with an explicit enum.  It never treats a
    free-form description or a model-generated value as capability evidence.
    """
    pending: list[object] = [document]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            marker = id(current)
            if marker in seen:
                continue
            seen.add(marker)
            for key, value in current.items():
                if key == "reasoning_effort" and isinstance(value, dict):
                    values: list[str] = []
                    enum_nodes: list[object] = [value]
                    while enum_nodes:
                        enum_node = enum_nodes.pop()
                        if not isinstance(enum_node, dict):
                            continue
                        enum = enum_node.get("enum")
                        if isinstance(enum, list):
                            for item in enum:
                                if (
                                    isinstance(item, str)
                                    and item in SUPPORTED_REASONING_EFFORTS
                                    and item not in values
                                ):
                                    values.append(item)
                        for branch_key in ("anyOf", "oneOf", "allOf"):
                            branches = enum_node.get(branch_key)
                            if isinstance(branches, list):
                                enum_nodes.extend(branches)
                    if values:
                        return tuple(values)
                    continue
                pending.append(value)
        elif isinstance(current, list):
            pending.extend(current)
    return ()


def explicit_effective_reasoning_mode(payload: object) -> str | None:
    """Read an explicit provider effective-mode field, if one is supplied.

    The return value includes both the legacy tiered vocabulary and the new
    binary vocabulary.  Callers should compare it only with the control they
    requested.
    """
    if not isinstance(payload, dict):
        return None
    for key in (
        "effective_reasoning_effort",
        "effective_reasoning_mode",
        "reasoning_effort",
        "reasoning_mode",
    ):
        value = payload.get(key)
        if isinstance(value, str):
            if value in SUPPORTED_REASONING_EFFORTS:
                return value
            mode = normalize_reasoning_mode(value)
            if mode is not None:
                return mode
    for key in ("effective_thinking", "thinking_enabled", "enable_thinking"):
        value = payload.get(key)
        if isinstance(value, bool):
            return "thinking" if value else "non_thinking"
    return None


def _message_dump(message: object) -> dict[str, object] | None:
    if isinstance(message, dict):
        return message
    dump = getattr(message, "model_dump", None)
    if callable(dump):
        try:
            value = dump(mode="json", exclude_none=False)
        except (AttributeError, TypeError, ValueError):
            return None
        return value if isinstance(value, dict) else None
    # Lightweight test doubles and some OpenAI-compatible clients expose
    # response fields as attributes without implementing ``model_dump``.
    fields: dict[str, object] = {}
    for key in ("reasoning", "reasoning_content"):
        if hasattr(message, key):
            fields[key] = getattr(message, key)
    return fields or None


def observed_reasoning_mode(
    response: object, message: object | None = None
) -> str | None:
    """Determine the binary mode actually represented by a response.

    A structured effective field wins when the serving stack supplies one.
    Qwen3.5's public contract is the request-side boolean
    ``chat_template_kwargs.enable_thinking``; its parsed
    ``reasoning``/``reasoning_content`` field is recorded as an optional
    response observation, not as evidence of a numeric effort tier.  A
    non-empty field means thinking, an explicitly empty field means
    non-thinking, and a missing field remains ``None``.  Arbitrary prose is
    never used as a tiered effort claim.
    """
    candidates: list[object] = []
    if isinstance(response, dict):
        candidates.append(response)
    else:
        fields = {
            key: getattr(response, key, None)
            for key in (
                "effective_thinking",
                "thinking_enabled",
                "enable_thinking",
                "effective_reasoning_mode",
                "reasoning_mode",
            )
        }
        candidates.append(fields)
        for key in ("model_extra", "response_metadata", "metadata"):
            value = getattr(response, key, None)
            if isinstance(value, dict):
                candidates.append(value)
    for candidate in candidates:
        mode = explicit_effective_reasoning_mode(candidate)
        if mode in SUPPORTED_REASONING_MODES:
            return mode

    dumped = _message_dump(message)
    if dumped is None and not isinstance(response, dict):
        response_dump = getattr(response, "model_dump", None)
        if callable(response_dump):
            try:
                raw = response_dump(mode="json", exclude_none=False)
            except (AttributeError, TypeError, ValueError):
                raw = None
            if isinstance(raw, dict):
                # OpenAI responses keep the message below choices.  We only
                # inspect the first choice because the Runner requires one.
                choices = raw.get("choices")
                if isinstance(choices, list) and choices:
                    first = choices[0]
                    if isinstance(first, dict):
                        candidate_message = first.get("message")
                        if isinstance(candidate_message, dict):
                            dumped = candidate_message
    if dumped is None:
        return None
    for key in ("reasoning", "reasoning_content"):
        if key not in dumped:
            continue
        value = dumped.get(key)
        if isinstance(value, str):
            return "thinking" if value.strip() else "non_thinking"
        if value is None:
            return "non_thinking"
    return None
