"""Holo visual grounding for the Qwen/LiteAgent hybrid path.

The native Holo runner owns a complete GUI episode loop for diagnostic
experiments.  This module is deliberately narrower: it accepts one Qwen
``gui_request`` plus one screenshot and returns exactly one validated GUI
function call.  It never executes a command and has no completion/failure
control surface.
"""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from uuid import uuid4

import httpx
import jsonschema
from openai import OpenAI

from integrations.lite_agent.gui_actions import GUI_REQUEST_SCHEMA
from integrations.lite_agent.model_client import _schema_validation_hints
from integrations.lite_agent.reasoning import (
    SUPPORTED_REASONING_MODES,
    observed_reasoning_mode,
)

from .tools import HOLO_GROUNDING_TOOLS, validate_grounding_action


GroundingRequestObserver = Callable[[dict[str, Any]], None]
GroundingEvidenceObserver = Callable[[dict[str, Any]], None]


class HoloGroundingError(RuntimeError):
    """A Holo response cannot be used as one concrete GUI action."""


@dataclass(frozen=True)
class HoloGroundingConfig:
    base_url: str
    model: str = "holo3.1-4b"
    api_key: str = "EMPTY"
    temperature: float = 0.8
    max_output_tokens: int = 1024
    request_timeout_seconds: float = 180.0
    # ``reasoning_effort`` is retained for historical Holo runs.  New hybrid
    # conditions should use the provider-native binary mode instead.
    reasoning_effort: str | None = "medium"
    reasoning_mode: str | None = None
    reasoning_profile: str | None = None
    expected_model_root: str | None = None
    accepted_actual_models: tuple[str, ...] | None = None


def grounding_system_prompt() -> str:
    """Return a task-independent prompt for one visual grounding call."""
    return (
        "You are a GUI visual-grounding model used by another computer-use agent. "
        "Inspect the supplied screenshot and ground the requested single visible "
        "operation. Return exactly one function call from the provided GUI tools. "
        "Coordinates must be normalized integers in [0, 1000] with the origin at "
        "the screenshot's top-left. Do not answer the task, declare completion, "
        "execute multiple actions, infer hidden state, or use a terminal, API, or "
        "evaluator. If the target is not visually groundable, return a conservative "
        "visible action only when one is unambiguous; otherwise the caller will "
        "record the grounding failure for the reasoning model."
    )


def _request_messages(
    screenshot: bytes, request: Mapping[str, Any]
) -> list[dict[str, Any]]:
    encoded = base64.b64encode(screenshot).decode("ascii")
    request_text = json.dumps(
        {"gui_request": dict(request)}, ensure_ascii=False, sort_keys=True
    )
    return [
        {"role": "system", "content": grounding_system_prompt()},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": request_text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{encoded}"},
                },
            ],
        },
    ]


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def project_grounding_request_for_evidence(
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Project an exact request artifact without retaining screenshot bytes."""
    snapshot = copy.deepcopy(dict(request))
    messages = snapshot.get("messages")
    if not isinstance(messages, list):
        return snapshot
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for chunk in content:
            if not isinstance(chunk, dict) or chunk.get("type") != "image_url":
                continue
            image_url = chunk.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else None
            if not isinstance(url, str):
                continue
            header, separator, encoded = url.partition(",")
            try:
                image_bytes = (
                    base64.b64decode(encoded, validate=True) if separator else b""
                )
            except (ValueError, binascii.Error):
                image_bytes = b""
            media_type = (
                header.removeprefix("data:").split(";", 1)[0]
                if header.startswith("data:")
                else None
            )
            chunk["image_url"] = {
                "artifact_type": "inline_image_digest",
                "media_type": media_type,
                "sha256": hashlib.sha256(image_bytes).hexdigest(),
                "bytes": len(image_bytes),
            }
    return snapshot


def _response_dump(
    response: Any,
    choice: Any | None,
    message: Any | None,
) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        try:
            dumped = response.model_dump(mode="json", exclude_none=False)
            if isinstance(dumped, dict):
                return dumped
        except (AttributeError, TypeError, ValueError):
            pass
    return {
        "model": getattr(response, "model", None),
        "finish_reason": getattr(choice, "finish_reason", None),
        "message": message.model_dump(mode="json", exclude_none=False)
        if hasattr(message, "model_dump")
        else None,
    }


class HoloGroundingAgent:
    """One-shot Holo caller that returns a single model-selected GUI action."""

    def __init__(
        self,
        config: HoloGroundingConfig,
        *,
        client: Any | None = None,
        request_observer: GroundingRequestObserver | None = None,
        evidence_observer: GroundingEvidenceObserver | None = None,
    ) -> None:
        self.config = config
        self.request_observer = request_observer
        self.evidence_observer = evidence_observer
        self._schema_error_feedback: tuple[str, str] | None = None
        self.client = (
            client
            if client is not None
            else OpenAI(
                base_url=config.base_url,
                api_key=config.api_key,
                http_client=httpx.Client(
                    timeout=config.request_timeout_seconds,
                    trust_env=False,
                ),
            )
        )

    def _emit_evidence(self, value: dict[str, Any]) -> None:
        if self.evidence_observer is not None:
            self.evidence_observer(copy.deepcopy(value))

    def ground(
        self,
        screenshot: bytes,
        gui_request: Mapping[str, Any],
    ) -> dict[str, Any]:
        previous_feedback = self._schema_error_feedback
        self._schema_error_feedback = None
        if not isinstance(screenshot, (bytes, bytearray, memoryview)) or not screenshot:
            raise HoloGroundingError(
                "Holo grounding requires non-empty screenshot bytes"
            )
        if not isinstance(gui_request, Mapping):
            raise HoloGroundingError("Qwen gui_request must be an object")
        try:
            jsonschema.validate(dict(gui_request), GUI_REQUEST_SCHEMA)
        except jsonschema.ValidationError as exc:
            raise HoloGroundingError(
                "Qwen gui_request does not satisfy the public grounding schema"
            ) from exc

        messages = _request_messages(bytes(screenshot), gui_request)
        request: dict[str, Any] = {
            "model": self.config.model,
            "messages": copy.deepcopy(messages),
            "tools": copy.deepcopy(HOLO_GROUNDING_TOOLS),
            "tool_choice": "required",
            "parallel_tool_calls": False,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
            "extra_body": {
                "chat_template_kwargs": {
                    "enable_thinking": (
                        self.config.reasoning_mode == "thinking"
                        if self.config.reasoning_mode is not None
                        else True
                    )
                }
            },
        }
        if self.config.reasoning_mode is not None:
            if self.config.reasoning_mode not in SUPPORTED_REASONING_MODES:
                raise HoloGroundingError(
                    f"unsupported Holo reasoning mode: {self.config.reasoning_mode!r}"
                )
        elif self.config.reasoning_effort:
            # vLLM's Qwen-compatible parser reads this provider option from
            # ``extra_body``; keeping it alongside the explicit observer field
            # makes the requested mode auditable without relying on a server
            # default.
            request["extra_body"]["reasoning_effort"] = self.config.reasoning_effort
        request_artifact = project_grounding_request_for_evidence(request)
        # Feedback contains only public schema rules, so a rephrased intent or
        # refreshed screenshot does not invalidate it. Never reuse old targets.
        input_key = _canonical_sha256(request["tools"])
        if previous_feedback is not None and previous_feedback[0] == input_key:
            # The parent chooses whether to call again; only Holo can correct
            # its arguments. A changed tool contract still clears this feedback.
            request["messages"][0]["content"] += (
                "\nYour previous GUI action did not execute because its arguments "
                f"failed validation: {previous_feedback[1]}. "
                "Use the current request and screenshot to choose one action with "
                "valid arguments. This feedback describes the tool schema only."
            )
            request_artifact = project_grounding_request_for_evidence(request)
        if self.request_observer is not None:
            self.request_observer(copy.deepcopy(request))

        request_id = str(uuid4())
        request_sha256 = _canonical_sha256(request_artifact)
        evidence_base = {
            "schema_version": 1,
            "request_id": request_id,
            "request_sha256": request_sha256,
            "model_requested": self.config.model,
            "reasoning_effort_requested": self.config.reasoning_effort,
            "reasoning_mode_requested": self.config.reasoning_mode,
            "reasoning_profile": self.config.reasoning_profile,
            "expected_model_root": self.config.expected_model_root,
            "accepted_actual_models": list(self.config.accepted_actual_models or ()),
            "enable_thinking_requested": request["extra_body"]["chat_template_kwargs"][
                "enable_thinking"
            ],
        }
        self._emit_evidence(
            {
                **evidence_base,
                "record_type": "request_attempt",
                "request": request_artifact,
            }
        )

        try:
            response = self.client.chat.completions.create(**request)
        except Exception as exc:
            self._emit_evidence(
                {
                    **evidence_base,
                    "record_type": "request_failure",
                    "error": {
                        "type": type(exc).__name__,
                        "detail": str(exc)[:1_000],
                    },
                }
            )
            raise HoloGroundingError(
                f"Holo grounding request failed: {type(exc).__name__}"
            ) from exc
        choices = getattr(response, "choices", None) or []
        choice = choices[0] if len(choices) == 1 else None
        message = getattr(choice, "message", None) if choice is not None else None
        response_dump = _response_dump(response, choice, message)
        response_sha256 = _canonical_sha256(response_dump)
        model_actual = getattr(response, "model", None)
        accepted_actual_models = tuple(self.config.accepted_actual_models or ())
        actual_model_accepted = (
            model_actual in accepted_actual_models if accepted_actual_models else None
        )
        observed_mode = (
            observed_reasoning_mode(response, message)
            if self.config.reasoning_mode is not None
            else None
        )
        response_evidence = {
            **evidence_base,
            "record_type": "response_received",
            "response_sha256": response_sha256,
            "response": response_dump,
            "model_actual": model_actual,
            "actual_model_accepted": actual_model_accepted,
            "reasoning_mode_effective": observed_mode,
        }
        self._emit_evidence(response_evidence)

        try:
            if len(choices) != 1:
                raise HoloGroundingError(
                    f"Holo grounding expected one choice, got {len(choices)}"
                )
            if accepted_actual_models and not actual_model_accepted:
                raise HoloGroundingError(
                    "Holo response model identity is outside the frozen accepted set"
                )
            if self.config.reasoning_mode is not None:
                if observed_mode is None:
                    raise HoloGroundingError(
                        "Holo did not attest the effective thinking mode"
                    )
                if observed_mode != self.config.reasoning_mode:
                    raise HoloGroundingError(
                        "Holo effective thinking mode does not match the requested mode"
                    )
            calls = getattr(message, "tool_calls", None) or []
            if len(calls) != 1:
                raise HoloGroundingError(
                    f"Holo grounding expected exactly one GUI action, got {len(calls)}"
                )
            call = calls[0]
            function = getattr(call, "function", None)
            name = str(getattr(function, "name", "") or "")
            raw_arguments = getattr(function, "arguments", "")
            try:
                arguments = json.loads(raw_arguments or "")
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise HoloGroundingError(
                    "Holo GUI action arguments are not valid JSON"
                ) from exc
            if not isinstance(arguments, dict):
                raise HoloGroundingError("Holo GUI action arguments must be an object")
            try:
                validate_grounding_action(name, arguments)
            except (ValueError, jsonschema.ValidationError) as exc:
                detail = (
                    "; ".join(_schema_validation_hints([exc]))
                    if isinstance(exc, jsonschema.ValidationError)
                    else "use one of the provided non-terminal GUI tools"
                )
                self._schema_error_feedback = (input_key, detail)
                raise HoloGroundingError(
                    f"Holo returned an invalid GUI action: {detail}"
                ) from exc
        except HoloGroundingError as exc:
            self._emit_evidence(
                {
                    **evidence_base,
                    "record_type": "grounding_failure",
                    "response_sha256": response_sha256,
                    "model_actual": model_actual,
                    "actual_model_accepted": actual_model_accepted,
                    "reasoning_mode_effective": observed_mode,
                    "error": {"type": type(exc).__name__, "detail": str(exc)},
                }
            )
            raise

        selected_tool_call = {
            "tool": "gui_action",
            "name": name,
            "arguments_raw": raw_arguments,
            "arguments": arguments,
            "call_id": getattr(call, "id", None),
        }
        result = {
            **selected_tool_call,
            "request_id": request_id,
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
            "model_requested": self.config.model,
            "model_actual": model_actual,
            "actual_model_accepted": actual_model_accepted,
            "reasoning_effort_requested": self.config.reasoning_effort,
            "reasoning_mode_requested": self.config.reasoning_mode,
            "reasoning_mode_effective": observed_mode,
            "reasoning_profile": self.config.reasoning_profile,
            "expected_model_root": self.config.expected_model_root,
            "accepted_actual_models": list(accepted_actual_models),
            "enable_thinking_requested": evidence_base["enable_thinking_requested"],
            "response": response_dump,
        }
        self._emit_evidence(
            {
                **evidence_base,
                "record_type": "grounding_selected",
                "response_sha256": response_sha256,
                "model_actual": model_actual,
                "actual_model_accepted": actual_model_accepted,
                "reasoning_mode_effective": observed_mode,
                "selected_tool_call": selected_tool_call,
            }
        )
        return result

    def __call__(
        self,
        screenshot: bytes,
        gui_request: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.ground(screenshot, gui_request)
