from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

import httpx
from jsonschema import Draft202012Validator
from openai import OpenAI

from .tool_catalog import tool_name
from .atomic_tool_surface import atomic_provider_surface, restore_adapter_arguments
from .reasoning import (
    SUPPORTED_REASONING_EFFORTS,
    SUPPORTED_REASONING_MODES,
    explicit_effective_reasoning_mode,
    observed_reasoning_mode,
)


_SCHEMA_HINT_MAX = 8
_SCHEMA_HINT_ITEM_MAX = 180
# The Runner owns bounded retries and recomputes the remaining episode
# deadline before each attempt.  OpenAI's implicit retries would otherwise
# keep an HTTP request alive after that deadline and hide the true attempt
# count in the episode ledger.
MODEL_SDK_MAX_RETRIES = 0


def _normalize_boolean_literals(value: Any, schema: Any) -> Any:
    """Decode explicit boolean words only where the public schema requires a boolean."""
    if not isinstance(schema, dict):
        return value
    if schema.get("type") == "boolean" and isinstance(value, str):
        literal = value.strip().lower()
        if literal in {"true", "false"}:
            return literal == "true"
    if isinstance(value, dict):
        branches = schema.get("oneOf") or schema.get("anyOf")
        if isinstance(branches, list):
            matching = [
                branch
                for branch in branches
                if isinstance(branch, dict)
                and set(branch.get("required", ())) <= set(value)
                and (
                    branch.get("additionalProperties") is not False
                    or set(value) <= set(branch.get("properties", ()))
                )
            ]
            if len(matching) == 1:
                value = _normalize_boolean_literals(value, matching[0])
        properties = schema.get("properties")
        if isinstance(properties, dict):
            return {
                key: _normalize_boolean_literals(item, properties.get(key))
                for key, item in value.items()
            }
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        return [_normalize_boolean_literals(item, schema["items"]) for item in value]
    return value


def _provider_array_uniqueness(schema: Any) -> Any:
    """Move unsupported generation constraints to text, retaining runtime validation.

    Visit schema positions only: properties named uniqueItems and literal JSON
    in defaults/enums must not be mistaken for schema keywords. The caller
    validates returned arguments against the untouched original tool schema.
    """
    if not isinstance(schema, dict):
        return copy.deepcopy(schema)
    result = copy.deepcopy(schema)
    if isinstance(result.get("uniqueItems"), bool):
        unique = result.pop("uniqueItems")
        if unique:
            hint = "Array items must be unique; duplicate items are rejected before execution."
            description = result.get("description", "")
            result["description"] = f"{description}\n{hint}" if description else hint
    for key in ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas"):
        mapping = result.get(key)
        if isinstance(mapping, dict):
            result[key] = {name: _provider_array_uniqueness(value) for name, value in mapping.items()}
    for key in ("items", "additionalItems", "additionalProperties", "contains",
                "propertyNames", "not", "if", "then", "else",
                "unevaluatedItems", "unevaluatedProperties"):
        child = result.get(key)
        if isinstance(child, dict):
            result[key] = _provider_array_uniqueness(child)
        elif key == "items" and isinstance(child, list):
            result[key] = [_provider_array_uniqueness(item) for item in child]
    for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
        children = result.get(key)
        if isinstance(children, list):
            result[key] = [_provider_array_uniqueness(item) for item in children]
    dependencies = result.get("dependencies")
    if isinstance(dependencies, dict):
        result["dependencies"] = {
            key: _provider_array_uniqueness(value) if isinstance(value, dict) else value
            for key, value in dependencies.items()
        }
    return result


def _provider_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Adapt schema spelling without deleting the executable parameter contract.

    In particular, arrays keep their element types, and route alternatives keep
    their own payload requirements. Runtime validation still uses the original
    schema. A provider limitation must not turn a constrained tool into an
    untyped object that asks the model to guess its arguments.
    """
    def normalize(value: Any) -> Any:
        if not isinstance(value, dict):
            return copy.deepcopy(value)
        # Only schema positions contain keywords. A property called "const"
        # or a literal JSON object in an enum/default is application data.
        result = copy.deepcopy(value)
        result.pop("x-route", None)
        for key in ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas"):
            mapping = result.get(key)
            if isinstance(mapping, dict):
                result[key] = {name: normalize(child) for name, child in mapping.items()}
        for key in ("items", "additionalItems", "additionalProperties", "contains",
                    "propertyNames", "not", "if", "then", "else",
                    "unevaluatedItems", "unevaluatedProperties"):
            child = result.get(key)
            if isinstance(child, dict):
                result[key] = normalize(child)
            elif key == "items" and isinstance(child, list):
                result[key] = [normalize(item) for item in child]
        for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
            children = result.get(key)
            if isinstance(children, list):
                result[key] = [normalize(child) for child in children]
        dependencies = result.get("dependencies")
        if isinstance(dependencies, dict):
            result["dependencies"] = {
                key: normalize(child) if isinstance(child, dict) else child
                for key, child in dependencies.items()
            }
        types = result.get("type")
        if isinstance(types, list) and all(isinstance(item, str) for item in types):
            result.pop("type")
            # JSON Schema type arrays are inclusive unions (integer is also a
            # number). oneOf would incorrectly reject integers in that case.
            union = {"anyOf": [{"type": item} for item in types]}
            if "anyOf" in result:
                result.setdefault("allOf", []).append(union)
            else:
                result.update(union)
        if "const" in result:
            constant = result.pop("const")
            if "enum" in result:
                result["enum"] = [x for x in result["enum"] if x == constant]
            else:
                result["enum"] = [constant]
        return result

    normalized = copy.deepcopy(tools)
    for tool in normalized:
        function = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(function, dict):
            continue
        parameters = function.get("parameters")
        if not isinstance(parameters, dict):
            continue
        if function.get("name") == "adapter__adapter_call":
            function["name"] = "adapter_call"
            route = parameters.get("x-route")
            if isinstance(route, dict):
                # Expose the route identity as literal arguments as well, so
                # the execution boundary need not invent action parameters.
                parameters["required"] = list(dict.fromkeys([
                    *parameters.get("required", []), "adapter", "action",
                ]))
            function["description"] = (
                "Call exactly one discovered adapter action. Supply adapter, "
                "action and payload; put action parameters inside payload.params. "
                "Follow the selected route's required fields and descriptions."
            )
        parameters = _provider_array_uniqueness(normalize(parameters))
        if function.get("name") == "propose_done":
            properties = parameters.get("properties", {})
            evidence = properties.get("evidence")
            if isinstance(evidence, dict) and evidence.get("type") != "string":
                properties["evidence"] = {
                    "type": "string", "minLength": 1,
                    "description": evidence.get("description", "Completion evidence."),
                }
        function["parameters"] = parameters
    return normalized


def _textual_tool_envelope(content: Any) -> tuple[str, dict[str, Any], str] | None:
    """Decode a provider's strict JSON tool envelope when native calls are absent.

    A few OpenAI-compatible local servers honor ``tool_choice=required`` but
    return the selected call in ``message.content`` instead of
    ``message.tool_calls``. Accept only the exact two-field envelope so
    ordinary assistant prose cannot become an executable action.
    """
    if not isinstance(content, str):
        return None
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if (
            len(lines) >= 3
            and lines[0].strip() in {"```", "```json"}
            and lines[-1].strip() == "```"
        ):
            text = "\n".join(lines[1:-1]).strip()
    if not text or not text.startswith("{") or not text.endswith("}"):
        return None
    try:
        envelope = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(envelope, dict):
        return None
    name = envelope.get("name")
    arguments = envelope.get("arguments")
    if (
        not isinstance(name, str)
        or not name
        or not isinstance(arguments, dict)
        or set(envelope) != {"name", "arguments"}
    ):
        return None
    return name, arguments, json.dumps(arguments, ensure_ascii=False)


def _direct_adapter_alias(
    tools: list[dict[str, Any]], tool: str, arguments: dict[str, Any]
) -> tuple[str, dict[str, Any], str] | None:
    """Normalize a small model's direct adapter name when that route is exposed.

    Some providers emit ``os.filesystem.find`` after seeing the catalog result
    even though the public surface exposes the generic adapter-call wrapper.
    Accept the alias only when the exact adapter/action pair is present in the
    current wrapper schema; this does not add an unexposed capability.
    """
    if "." not in tool:
        return None
    adapter, action = tool.split(".", 1)
    wrapper = tool_name("adapter.call")
    wrapper_schema = None
    for exposed in tools:
        function = exposed.get("function") if isinstance(exposed, dict) else None
        if isinstance(function, dict) and function.get("name") == wrapper:
            candidate = function.get("parameters")
            if isinstance(candidate, dict):
                wrapper_schema = candidate
            break
    if not isinstance(wrapper_schema, dict):
        return None
    for branch in wrapper_schema.get("oneOf", []):
        if not isinstance(branch, dict):
            continue
        properties = branch.get("properties")
        if not isinstance(properties, dict):
            continue
        adapter_enum = properties.get("adapter", {}).get("enum")
        action_enum = properties.get("action", {}).get("enum")
        if adapter_enum == [adapter] and action_enum == [action]:
            normalized = {
                "adapter": adapter,
                "action": action,
                "payload": {"params": arguments},
            }
            return wrapper, normalized, json.dumps(normalized, ensure_ascii=False)
    return None


def _safe_schema_path(path: Any) -> str:
    """Render validator paths without copying model-controlled values."""
    parts: list[str] = []
    for item in path:
        text = str(item)
        if (
            len(text) > 64
            or not text
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
                for character in text
            )
        ):
            text = "<field>"
        parts.append(text)
    return ".".join(parts) or "<root>"


def _safe_schema_value(value: Any) -> str:
    """Keep schema-authored expectations compact and free of actual arguments."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = repr(value)
    elif isinstance(value, list):
        scalar_values = [
            item for item in value if isinstance(item, (str, int, float, bool))
        ]
        text = "[" + ", ".join(repr(item) for item in scalar_values[:8]) + "]"
    else:
        text = type(value).__name__
    return text[:100]


def _safe_required_fields(schema: Any) -> tuple[str, ...]:
    if not isinstance(schema, dict):
        return ()
    required = schema.get("required")
    if not isinstance(required, list):
        return ()
    return tuple(
        field
        for field in required
        if isinstance(field, str)
        and field
        and len(field) <= 64
        and all(
            character
            in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
            for character in field
        )
    )


def _required_field_alternatives(
    schema: Any,
    *,
    depth: int = 0,
) -> tuple[tuple[str, ...], ...]:
    """Extract bounded positive field alternatives from a public schema union."""
    if not isinstance(schema, dict) or depth > 3:
        return ()
    base = _safe_required_fields(schema)
    for keyword in ("oneOf", "anyOf"):
        branches = schema.get(keyword)
        if not isinstance(branches, list):
            continue
        alternatives: list[tuple[str, ...]] = []
        for branch in branches[:8]:
            nested = _required_field_alternatives(branch, depth=depth + 1)
            if not nested:
                nested = ((),)
            for fields in nested:
                combined = tuple(dict.fromkeys((*base, *fields)))
                if combined and combined not in alternatives:
                    alternatives.append(combined)
        return tuple(alternatives[:8])
    return (base,) if base else ()


def _undiscriminated_union_alternatives(error: Any) -> tuple[tuple[str, ...], ...]:
    branches = getattr(error, "validator_value", None)
    if not isinstance(branches, list):
        return ()
    for branch in branches:
        if not isinstance(branch, dict):
            return ()
        properties = branch.get("properties")
        if isinstance(properties, dict) and any(
            isinstance(field_schema, dict)
            and ("const" in field_schema or "enum" in field_schema)
            for field_schema in properties.values()
        ):
            return ()
    return _required_field_alternatives({str(error.validator): branches})


def _selected_schema_branch_index(error: Any) -> int | None:
    """Select a union branch only when model arguments uniquely identify it."""
    if getattr(error, "validator", None) not in {"oneOf", "anyOf"}:
        return None
    branches = getattr(error, "validator_value", None)
    instance = getattr(error, "instance", None)
    if (
        not isinstance(branches, list)
        or not branches
        or any(not isinstance(branch, dict) for branch in branches)
    ):
        return None

    def accepts_instance_type(schema: dict[str, Any]) -> bool:
        if "type" in schema and not Draft202012Validator({"type": schema["type"]}).is_valid(instance):
            return False
        for keyword in ("oneOf", "anyOf"):
            alternatives = schema.get(keyword)
            if isinstance(alternatives, list) and not any(
                not isinstance(branch, dict) or accepts_instance_type(branch)
                for branch in alternatives
            ):
                return False
        conjunction = schema.get("allOf", [])
        return all(not isinstance(branch, dict) or accepts_instance_type(branch) for branch in conjunction)

    candidates = {
        index for index, branch in enumerate(branches)
        if accepts_instance_type(branch)
    }
    if len(candidates) == 1:
        return next(iter(candidates))
    if not candidates or not isinstance(instance, dict):
        return None

    discriminators_by_branch: dict[int, dict[str, Any]] = {}
    for index in sorted(candidates):
        branch = branches[index]
        properties = branch.get("properties")
        if not isinstance(properties, dict):
            return None
        discriminators_by_branch[index] = {
            field: {
                keyword: field_schema[keyword]
                for keyword in ("const", "enum")
                if keyword in field_schema
            }
            for field, field_schema in properties.items()
            if isinstance(field, str)
            and isinstance(field_schema, dict)
            and ("const" in field_schema or "enum" in field_schema)
        }

    shared_fields = set.intersection(
        *(set(fields) for fields in discriminators_by_branch.values())
    )
    present_fields = sorted(field for field in shared_fields if field in instance)
    if not present_fields:
        return None

    for field in present_fields:
        candidates.intersection_update(
            index
            for index, discriminators in discriminators_by_branch.items()
            if Draft202012Validator(discriminators[field]).is_valid(instance[field])
        )
    if len(candidates) != 1:
        return None
    return next(iter(candidates))


def _actionable_validation_errors(errors: list[Any]) -> list[Any]:
    """Descend only into a uniquely selected public-schema union branch."""
    actionable: list[Any] = []
    for error in errors:
        branch_index = _selected_schema_branch_index(error)
        if branch_index is None:
            actionable.append(error)
            continue
        branch_errors = [
            child
            for child in getattr(error, "context", ())
            if tuple(getattr(child, "relative_schema_path", ()))[:1] == (branch_index,)
        ]
        if not branch_errors:
            actionable.append(error)
            continue
        actionable.extend(_actionable_validation_errors(branch_errors))
    return actionable


def _safe_missing_fields(errors: list[Any]) -> tuple[str, ...]:
    fields: list[str] = []
    for error in errors:
        if getattr(error, "validator", None) != "required":
            continue
        required = getattr(error, "validator_value", None)
        local_instance = getattr(error, "instance", None)
        if not isinstance(required, list):
            continue
        for item in required:
            if (
                not isinstance(item, str)
                or not item
                or len(item) > 64
                or any(
                    character not in "abcdefghijklmnopqrstuvwxyz"
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
                    for character in item
                )
                or (isinstance(local_instance, dict) and item in local_instance)
                or item in fields
            ):
                continue
            fields.append(item)
            if len(fields) >= _SCHEMA_HINT_MAX:
                return tuple(fields)
    return tuple(fields)


def _schema_validation_hints(
    errors: list[Any], *, instance: dict[str, Any] | None = None
) -> tuple[str, ...]:
    """Create bounded recovery hints from public schema keywords only.

    The invalid value and jsonschema's full message are intentionally omitted:
    they may contain arbitrary model output or user data.  The next model turn
    only needs the path and the schema rule it must satisfy.
    """
    hints: list[str] = []
    for error in errors:
        path = _safe_schema_path(getattr(error, "absolute_path", ()))
        keyword = str(getattr(error, "validator", "schema"))
        value = getattr(error, "validator_value", None)
        if keyword == "required" and isinstance(value, list):
            local_instance = getattr(error, "instance", instance)
            fields = [
                str(item)
                for item in value
                if isinstance(item, str)
                and (not isinstance(local_instance, dict) or item not in local_instance)
                and item
                and len(item) <= 64
                and all(
                    character in "abcdefghijklmnopqrstuvwxyz"
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
                    for character in item
                )
            ]
            detail = "required fields: " + ", ".join(fields[:8])
        elif keyword == "enum":
            detail = "must be one of " + _safe_schema_value(value)
        elif keyword == "type":
            detail = "type must be " + _safe_schema_value(value)
            schema = getattr(error, "schema", None)
            items = schema.get("items") if isinstance(schema, dict) else None
            if (
                value == "array"
                and isinstance(items, dict)
                and items.get("type") == "string"
            ):
                detail += (
                    "; use native JSON array of concise strings; do not "
                    "JSON-encode inside string; do not copy full ledger"
                )
            elif value == "array" and isinstance(items, dict) and "oneOf" in items:
                detail += (
                    "; use a native JSON array; each item must be a concise string or "
                    "compact object copied from a successful tool result"
                )
            elif value == "object":
                detail += (
                    "; use a native JSON object, not a JSON-encoded string; "
                    "escape tabs/newlines inside string values as \\t/\\n"
                )
        elif keyword == "minimum":
            detail = "must be >= " + _safe_schema_value(value)
        elif keyword == "maximum":
            detail = "must be <= " + _safe_schema_value(value)
        elif keyword == "minProperties":
            detail = "must contain at least " + _safe_schema_value(value) + " field(s)"
        elif keyword == "uniqueItems":
            detail = "remove duplicate items; include each item only once"
        elif keyword == "not":
            detail = (
                "this argument combination is excluded; change the relevant fields "
                "or choose another discovered action. For a repeated empty search, "
                "use a different observed location or broader search criteria"
            )
        elif keyword == "additionalProperties" and value is False:
            detail = "remove fields not declared at this level"
            schema = getattr(error, "schema", None)
            properties = schema.get("properties") if isinstance(schema, dict) else None
            if isinstance(properties, dict):
                detail += "; declared fields: " + _safe_schema_value(list(properties))
        elif keyword in {
            "additionalProperties",
            "minItems",
            "maxItems",
            "minLength",
            "maxLength",
            "pattern",
            "const",
        }:
            detail = keyword
            if value is not None:
                detail += "=" + _safe_schema_value(value)
        elif keyword in {"oneOf", "anyOf"}:
            alternatives = _undiscriminated_union_alternatives(error)
            if alternatives:
                rendered = [" + ".join(fields) for fields in alternatives]
                detail = "provide one allowed field set: " + " OR ".join(rendered)
            elif keyword == "oneOf":
                detail = "must match one allowed schema branch"
            else:
                detail = "must match an allowed schema branch"
        else:
            detail = "schema rule " + keyword[:48]
        hint = f"{path}: {detail}"[:_SCHEMA_HINT_ITEM_MAX]
        if hint not in hints:
            hints.append(hint)
        if len(hints) >= _SCHEMA_HINT_MAX:
            break
    return tuple(hints)


class StructuredToolProtocolError(RuntimeError):
    """A model response cannot be safely represented as one complete tool call.

    The raw response is retained on the exception for the immutable trace, but
    the exception text is deliberately bounded and does not contain arguments.
    This lets the Runner request a compact repair without exposing response
    contents as model-facing guidance or silently rewriting them.
    """

    def __init__(
        self,
        reason: str,
        *,
        response_snapshot: dict[str, Any],
        tool_name: str | None = None,
        missing_fields: tuple[str, ...] = (),
        schema_hints: tuple[str, ...] = (),
        configuration_failure: bool = False,
    ) -> None:
        self.reason = reason
        self.response_snapshot = response_snapshot
        self.tool_name = tool_name
        self.missing_fields = missing_fields
        self.schema_hints = schema_hints
        self.configuration_failure = configuration_failure
        super().__init__(f"structured tool call protocol error: {reason}")

    def trace_record(self) -> dict[str, Any]:
        """Return machine-readable diagnostics for the internal LLM trace."""
        record: dict[str, Any] = {
            "reason": self.reason,
            "tool_name": self.tool_name,
            "missing_fields": list(self.missing_fields),
            "schema_hints": list(self.schema_hints),
            "configuration_failure": self.configuration_failure,
            "response": self.response_snapshot,
        }
        return record


class StructuredToolModelClient:
    """OpenAI-compatible transport for one structured tool call per turn."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        request_timeout_seconds: float,
        client: Any | None = None,
        request_observer: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.client = (
            client
            if client is not None
            else OpenAI(
                base_url=base_url,
                api_key=api_key,
                max_retries=MODEL_SDK_MAX_RETRIES,
                http_client=httpx.Client(
                    timeout=request_timeout_seconds,
                    trust_env=False,
                ),
            )
        )
        self.request_observer = request_observer

    def propose(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float,
        output_token_budget: int,
        enable_thinking: bool,
        reasoning_effort: str | None = None,
        reasoning_mode: str | None = None,
        expected_model: str | None = None,
        request_timeout_seconds: float | None = None,
        presence_penalty: float | None = None,
        thinking_token_budget: int | None = None,
        tool_call_stop_sequence: str | None = None,
    ) -> dict[str, Any]:
        if (
            reasoning_effort is not None
            and reasoning_effort not in SUPPORTED_REASONING_EFFORTS
        ):
            raise ValueError(f"unsupported reasoning effort: {reasoning_effort!r}")
        if (
            reasoning_mode is not None
            and reasoning_mode not in SUPPORTED_REASONING_MODES
        ):
            raise ValueError(f"unsupported reasoning mode: {reasoning_mode!r}")
        if reasoning_effort is not None and reasoning_mode is not None:
            raise ValueError(
                "reasoning_effort and reasoning_mode are mutually exclusive"
            )
        if reasoning_mode is not None:
            expected_thinking = reasoning_mode == "thinking"
            if enable_thinking is not expected_thinking:
                raise ValueError(
                    "enable_thinking does not match the requested reasoning mode"
                )
        # Some local OpenAI-compatible models keep emitting a stale catalog
        # function after the surface has advanced to one executable Adapter
        # route. Pin only that unambiguous route at the provider boundary;
        # the model still supplies the route arguments and terminal controls
        # remain available on surfaces with more than one executable choice.
        provider_surface, atomic_bindings = atomic_provider_surface(tools)
        exposed_function_names = [
            tool.get("function", {}).get("name")
            for tool in provider_surface
            if isinstance(tool.get("function"), dict)
        ]
        adapter_function_names = [
            name
            for name in exposed_function_names
            if isinstance(name, str) and name.startswith(("adapter__", "atomic__"))
        ]
        force_single_adapter = (
            len(adapter_function_names) == 1
            and "tools_search" not in exposed_function_names
        )
        tool_choice: Any = "required"
        if force_single_adapter:
            tool_choice = {
                "type": "function",
                "function": {"name": "adapter_call" if adapter_function_names[0] == "adapter__adapter_call" else adapter_function_names[0]},
            }
        provider_messages = messages
        if atomic_bindings:
            guidance = (
                "For this turn, each atomic__ tool is one discovered adapter operation. "
                "Use its current schema: action parameters go at the top level, with optional "
                "request_options for document, target, verify or timeout_ms. Historical "
                "adapter.call/payload.params examples use the internal logging format. "
                "Choose one current tool and do not chain operations."
            )
            # Qwen's chat template permits system instructions only at the
            # beginning. Do not append a second system turn after observations.
            provider_messages = copy.deepcopy(messages)
            if provider_messages and provider_messages[0].get("role") == "system":
                content = provider_messages[0].get("content", "")
                if isinstance(content, list):
                    provider_messages[0]["content"] = [*content, {"type": "text", "text": guidance}]
                else:
                    provider_messages[0]["content"] = str(content) + "\n\n" + guidance
            else:
                provider_messages.insert(0, {"role": "system", "content": guidance})
        request = {
            "model": model,
            "messages": provider_messages,
            "tools": _provider_tools(provider_surface),
            "tool_choice": tool_choice,
            "parallel_tool_calls": False,
            "temperature": temperature,
            "max_tokens": output_token_budget,
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": enable_thinking}
            },
        }
        if reasoning_effort is not None:
            request["reasoning_effort"] = reasoning_effort
        if presence_penalty is not None:
            request["presence_penalty"] = presence_penalty
        if thinking_token_budget is not None:
            request["extra_body"]["thinking_token_budget"] = thinking_token_budget
        if tool_call_stop_sequence is not None:
            # Retain the complete native delimiter for the provider's tool parser.
            request["stop"] = [tool_call_stop_sequence]
            request["extra_body"]["include_stop_str_in_output"] = True
        if self.request_observer is not None:
            self.request_observer(request)
        request_client = self.client
        if request_timeout_seconds is not None:
            timeout = max(float(request_timeout_seconds), 0.1)
            with_options = getattr(self.client, "with_options", None)
            if callable(with_options):
                request_client = with_options(timeout=timeout)
        response = request_client.chat.completions.create(**request)
        if (
            expected_model is not None
            and getattr(response, "model", None) != expected_model
        ):
            raise StructuredToolProtocolError(
                "response model identity does not match the requested model",
                response_snapshot=self._response_snapshot(response, None, None),
                configuration_failure=True,
            )
        effective_reasoning_mode = self._effective_reasoning_mode(response)
        if reasoning_effort is not None:
            if effective_reasoning_mode is None:
                raise StructuredToolProtocolError(
                    "provider did not attest the effective reasoning effort",
                    response_snapshot=self._response_snapshot(response, None, None),
                    configuration_failure=True,
                )
            if effective_reasoning_mode != reasoning_effort:
                raise StructuredToolProtocolError(
                    "effective reasoning effort does not match the requested effort",
                    response_snapshot=self._response_snapshot(response, None, None),
                    configuration_failure=True,
                )
        if not response.choices:
            raise StructuredToolProtocolError(
                "response contained no choices",
                response_snapshot=self._response_snapshot(response, None, None),
            )
        choice = response.choices[0]
        message = choice.message
        observed_mode = observed_reasoning_mode(response, message)
        # The public Qwen3.5 llama.cpp gateway omits the optional reasoning
        # field for non-thinking responses. The request-side binary switch is
        # explicit, and the response already passed the Qwen3.5 identity
        # check in runner preflight, so treat that omission as non-thinking.
        # Keep strict attestation for thinking responses and other models.
        response_model = str(getattr(response, "model", "") or model).casefold()
        qwen35_response = (
            response_model.replace("-", "").replace("_", "").replace(".", "")
            .startswith("qwen35")
        )
        if (
            observed_mode is None
            and reasoning_mode == "non_thinking"
            and qwen35_response
        ):
            observed_mode = "non_thinking"
        if reasoning_mode is not None:
            if observed_mode is None:
                raise StructuredToolProtocolError(
                    "provider did not attest the effective thinking mode",
                    response_snapshot=self._response_snapshot(
                        response, choice, message
                    ),
                    configuration_failure=True,
                )
            if observed_mode != reasoning_mode:
                raise StructuredToolProtocolError(
                    "effective thinking mode does not match the requested mode",
                    response_snapshot=self._response_snapshot(
                        response, choice, message
                    ),
                    configuration_failure=True,
                )
        calls = message.tool_calls or []
        textual_call = None
        if not calls:
            textual_call = _textual_tool_envelope(getattr(message, "content", None))
        # Every next action must be chosen from the latest result and tool
        # surface. Queuing extra calls here skips that audit and can replay
        # stale writes after an earlier call fails or changes the target.
        if len(calls) != 1 and textual_call is None:
            raise StructuredToolProtocolError(
                f"expected exactly one structured tool call, got {len(calls)}",
                response_snapshot=self._response_snapshot(response, choice, message),
            )
        if textual_call is not None:
            tool, arguments, arguments_raw = textual_call
            call_id = "textual-tool-call-0"
        else:
            call = calls[0]
            tool = str(call.function.name or "")
            arguments_raw = call.function.arguments
            try:
                arguments = json.loads(arguments_raw or "")
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise StructuredToolProtocolError(
                    "tool arguments are not complete JSON",
                    response_snapshot=self._response_snapshot(response, choice, message),
                    tool_name=tool,
                ) from exc
            if not isinstance(arguments, dict):
                raise StructuredToolProtocolError(
                    "tool arguments must be a JSON object",
                    response_snapshot=self._response_snapshot(response, choice, message),
                    tool_name=tool,
                )
        provider_tool = tool
        provider_arguments_raw = arguments_raw
        if tool in atomic_bindings:
            binding = atomic_bindings[tool]
            atomic_schema = binding["schema"]
            arguments = _normalize_boolean_literals(arguments, atomic_schema)
            errors = list(Draft202012Validator(atomic_schema).iter_errors(arguments))
            if errors:
                actionable_errors = _actionable_validation_errors(errors)
                raise StructuredToolProtocolError(
                    "tool arguments do not satisfy the exposed schema",
                    response_snapshot=self._response_snapshot(response, choice, message),
                    tool_name=tool,
                    missing_fields=_safe_missing_fields(actionable_errors),
                    schema_hints=_schema_validation_hints(actionable_errors, instance=arguments),
                )
            arguments = restore_adapter_arguments(arguments, binding)
            arguments_raw = json.dumps(arguments, ensure_ascii=False)
            tool = "adapter__adapter_call"
        if tool == "adapter_call":
            tool = "adapter__adapter_call"

        # Some small providers serialize a primitive search query as a typed
        # wrapper. Normalize only that unambiguous public field before schema
        # validation so catalog routing can proceed normally.
        if (
            tool == "tools_search"
            and isinstance(arguments.get("query"), dict)
            and arguments["query"].get("type") == "string"
            and isinstance(arguments["query"].get("value"), str)
        ):
            arguments["query"] = arguments["query"]["value"]
            arguments_raw = json.dumps(arguments, ensure_ascii=False)
        # Do not reinterpret a requested file read as an inspection, or erase
        # supplied document/path arguments. Validate the exact exposed route;
        # recovery feedback can ask the model to choose a supported action.
        schema = self._tool_schema(tools, tool)
        if schema is None:
            alias = _direct_adapter_alias(tools, tool, arguments)
            if alias is not None:
                tool, arguments, arguments_raw = alias
                schema = self._tool_schema(tools, tool)
        if schema is None:
            raise StructuredToolProtocolError(
                "the returned tool is not present in the exposed tool surface",
                response_snapshot=self._response_snapshot(response, choice, message),
                tool_name=tool,
            )
        normalized_arguments = _normalize_boolean_literals(arguments, schema)
        if normalized_arguments != arguments:
            arguments = normalized_arguments
            arguments_raw = json.dumps(arguments, ensure_ascii=False)
        validator = Draft202012Validator(schema)
        validation_errors = sorted(
            validator.iter_errors(arguments),
            key=lambda error: (
                tuple(str(item) for item in error.absolute_path),
                error.message,
            ),
        )
        if validation_errors:
            actionable_errors = _actionable_validation_errors(validation_errors)
            raise StructuredToolProtocolError(
                "tool arguments do not satisfy the exposed schema",
                response_snapshot=self._response_snapshot(response, choice, message),
                tool_name=tool,
                missing_fields=_safe_missing_fields(actionable_errors),
                schema_hints=_schema_validation_hints(
                    actionable_errors,
                    instance=arguments,
                ),
            )
        finish_reason = choice.finish_reason
        if finish_reason == "stop":
            # Some OpenAI-compatible Qwen servers label a complete native
            # function call as ``stop``. Schema validation above already
            # proves the call is complete, so preserve it as a tool turn for
            # the completion and audit policies.
            finish_reason = "tool_calls"
        return {
            "id": call_id if textual_call is not None else call.id,
            "tool": tool,
            "arguments_raw": arguments_raw,
            "provider_tool": provider_tool,
            "provider_arguments_raw": provider_arguments_raw,
            "model_actual": response.model,
            "usage": response.usage.model_dump(mode="json") if response.usage else None,
            "finish_reason": finish_reason,
            "max_output_tokens_requested": output_token_budget,
            "request_timeout_seconds": request_timeout_seconds,
            "response_message": message.model_dump(mode="json", exclude_none=True),
            # ``length`` can still be valid when only the reasoning suffix was
            # truncated; completeness is established by JSON/schema validation.
            "structured_call_validated": True,
            "reasoning_effort_requested": reasoning_effort,
            "reasoning_effort_effective": self._response_snapshot(
                response, choice, message
            ).get("effective_reasoning_mode"),
            "reasoning_mode_requested": reasoning_mode,
            "reasoning_mode_effective": observed_mode,
            "reasoning_observed": self._reasoning_observed(message),
        }

    @staticmethod
    def _tool_schema(
        tools: list[dict[str, Any]], tool_name: str
    ) -> dict[str, Any] | None:
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            function = tool.get("function")
            if not isinstance(function, dict) or function.get("name") != tool_name:
                continue
            schema = function.get("parameters")
            return schema if isinstance(schema, dict) else None
        return None

    @staticmethod
    def _response_snapshot(
        response: Any, choice: Any | None, message: Any | None
    ) -> dict[str, Any]:
        usage = getattr(response, "usage", None)
        if usage is not None and hasattr(usage, "model_dump"):
            usage = usage.model_dump(mode="json")
        if message is not None and hasattr(message, "model_dump"):
            message_dump = message.model_dump(mode="json", exclude_none=True)
        else:
            message_dump = None
        snapshot = {
            "model": getattr(response, "model", None),
            "finish_reason": getattr(choice, "finish_reason", None),
            "usage": usage,
            "message": message_dump,
        }
        effective = StructuredToolModelClient._effective_reasoning_mode(response)
        if effective is not None:
            snapshot["effective_reasoning_mode"] = effective
        observed = observed_reasoning_mode(response, message)
        if observed is not None:
            snapshot["observed_reasoning_mode"] = observed
        return snapshot

    @staticmethod
    def _effective_reasoning_mode(response: Any) -> str | None:
        """Read an explicit provider attestation without inferring from text.

        OpenAI-compatible clients expose response extensions in a few shapes:
        as top-level fields, ``model_extra``/metadata dictionaries, or the
        serialized response object.  We inspect only those structured fields;
        a non-empty ``reasoning`` message is deliberately not evidence of the
        selected provider mode.
        """
        candidates: list[object] = []
        if isinstance(response, dict):
            candidates.append(response)
        else:
            candidates.append(
                {
                    key: getattr(response, key, None)
                    for key in (
                        "effective_reasoning_effort",
                        "effective_reasoning_mode",
                        "reasoning_effort",
                        "reasoning_mode",
                    )
                }
            )
            for key in ("model_extra", "response_metadata", "metadata"):
                value = getattr(response, key, None)
                if isinstance(value, dict):
                    candidates.append(value)
            model_dump = getattr(response, "model_dump", None)
            if callable(model_dump):
                try:
                    dumped = model_dump(mode="json", exclude_none=True)
                except (AttributeError, TypeError, ValueError):
                    dumped = None
                if isinstance(dumped, dict):
                    candidates.append(dumped)
        for candidate in candidates:
            effective = explicit_effective_reasoning_mode(candidate)
            if effective is not None:
                return effective
        return None

    @staticmethod
    def _reasoning_observed(message: Any) -> bool:
        """Record only whether the provider returned a non-empty reasoning field."""
        reasoning = getattr(message, "reasoning", None)
        if reasoning is None:
            reasoning = getattr(message, "reasoning_content", None)
        if reasoning is None and hasattr(message, "model_dump"):
            try:
                dumped = message.model_dump(mode="json")
                reasoning = dumped.get("reasoning")
                if reasoning is None:
                    reasoning = dumped.get("reasoning_content")
            except (AttributeError, TypeError, ValueError):
                reasoning = None
        return isinstance(reasoning, str) and bool(reasoning.strip())
