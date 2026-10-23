"""Common execution gateway for Holo-grounded GUI actions."""

from __future__ import annotations

import copy
import io
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from PIL import Image

from .grounding import HoloGroundingError
from .tools import PreparedAction, prepare_action


Grounder = Callable[[bytes, Mapping[str, Any]], Mapping[str, Any]]
GatewayExecutor = Callable[[dict[str, Any]], dict[str, Any]]
GatewayExecutionObserver = Callable[[dict[str, Any]], None]


class HoloGuiGatewayError(RuntimeError):
    """A grounded action could not cross the GUI execution boundary."""


def screenshot_size(screenshot: bytes) -> tuple[int, int]:
    """Read the actual screenshot dimensions used for coordinate conversion."""
    try:
        with Image.open(io.BytesIO(screenshot)) as image:
            width, height = image.size
    except Exception as exc:
        raise HoloGuiGatewayError("cannot determine screenshot dimensions") from exc
    if width <= 0 or height <= 0:
        raise HoloGuiGatewayError("screenshot dimensions must be positive")
    return width, height


def _grounded_parts(grounded: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Accept the HoloGroundingAgent envelope without guessing arguments."""
    name = grounded.get("name")
    arguments = grounded.get("arguments")
    if isinstance(name, str) and isinstance(arguments, Mapping):
        return name, dict(arguments)
    # A small adapter is useful for model-free contract tests and gateways that
    # already return a canonical ``gui_action`` envelope.
    action = grounded.get("action")
    if isinstance(action, str):
        nested = grounded.get("arguments")
        if isinstance(nested, Mapping):
            return action, dict(nested)
        return action, {
            key: value
            for key, value in grounded.items()
            if key not in {"action", "tool", "name", "arguments"}
        }
    # Some lightweight adapters wrap the canonical action inside an
    # ``arguments`` object while retaining the outer ``tool=gui_action`` label.
    nested = grounded.get("arguments")
    if isinstance(nested, Mapping) and isinstance(nested.get("action"), str):
        action = str(nested["action"])
        return action, {key: value for key, value in nested.items() if key != "action"}
    raise HoloGuiGatewayError("Holo grounding result lacks one action and arguments")


def _audit_action(prepared: PreparedAction) -> dict[str, Any]:
    """Project a bounded, coordinate-bearing action for the parent's audit turn."""
    source = prepared.model_arguments
    if prepared.name == "write":
        action = "type"
        projected: dict[str, Any] = {
            "action": action,
            "text": source.get("content", ""),
        }
        if isinstance(source.get("press_enter"), bool):
            projected["press_enter"] = source["press_enter"]
        return projected
    projected = {"action": prepared.name}
    for key in (
        "x",
        "y",
        "to_x",
        "to_y",
        "amount",
        "seconds",
        "key",
        "keys",
    ):
        if key in source:
            projected[key] = source[key]
    if prepared.name == "click" and "modifiers" in source:
        projected["modifiers"] = list(source["modifiers"])
    return projected


def _grounding_link(grounded: Mapping[str, Any]) -> dict[str, Any]:
    """Copy only bounded provenance needed to join grounding and dispatch."""
    keys = (
        "request_id",
        "request_sha256",
        "response_sha256",
        "call_id",
        "model_requested",
        "model_actual",
        "actual_model_accepted",
        "reasoning_effort_requested",
        "reasoning_mode_requested",
        "reasoning_mode_effective",
        "reasoning_profile",
        "expected_model_root",
        "accepted_actual_models",
        "enable_thinking_requested",
    )
    return {key: copy.deepcopy(grounded[key]) for key in keys if key in grounded}


@dataclass(frozen=True)
class HoloGuiExecution:
    """Traceable result of grounding plus one gateway dispatch."""

    grounded: dict[str, Any]
    prepared: PreparedAction
    result: dict[str, Any]


class HoloGuiGateway:
    """Ground one request, validate it, and execute its exact command payload.

    ``executor`` is the existing common desktop gateway callback.  It receives
    the validated Holo arguments unchanged plus the generated internal command;
    no coordinate or text argument is inferred by this class.
    """

    def __init__(
        self,
        grounder: Grounder,
        executor: GatewayExecutor,
        *,
        default_settle_seconds: float = 2.0,
        execution_observer: GatewayExecutionObserver | None = None,
    ) -> None:
        self.grounder = grounder
        self.executor = executor
        self.default_settle_seconds = default_settle_seconds
        self.execution_observer = execution_observer

    def _emit_execution_evidence(self, value: dict[str, Any]) -> None:
        if self.execution_observer is not None:
            self.execution_observer(copy.deepcopy(value))

    def execute(
        self,
        gui_request: Mapping[str, Any],
        screenshot: bytes,
    ) -> dict[str, Any]:
        if not isinstance(screenshot, (bytes, bytearray, memoryview)) or not screenshot:
            raise HoloGuiGatewayError("GUI gateway requires non-empty screenshot bytes")
        if not isinstance(gui_request, Mapping):
            raise HoloGuiGatewayError("GUI gateway requires an object request")
        try:
            # Grounding is advisory; a buggy adapter must not mutate the
            # model-selected request retained in the execution ledger.
            grounded_raw = self.grounder(
                bytes(screenshot), copy.deepcopy(dict(gui_request))
            )
            if not isinstance(grounded_raw, Mapping):
                raise HoloGuiGatewayError("Holo grounder must return an object")
            name, arguments = _grounded_parts(grounded_raw)
            width, height = screenshot_size(bytes(screenshot))
            prepared = prepare_action(
                name,
                arguments,
                screenshot_width=width,
                screenshot_height=height,
                default_settle_seconds=self.default_settle_seconds,
            )
            if prepared.terminal is not None:
                raise HoloGuiGatewayError(
                    "Holo grounder returned a terminal control instead of a GUI action"
                )
            if prepared.command is None:  # pragma: no cover - terminal guard above
                raise HoloGuiGatewayError("prepared Holo action has no command")

            # ``model_arguments`` is the exact Holo payload.  ``command`` is an
            # internal representation conversion consumed by the desktop
            # gateway; it is never sent back as a model-selected argument.
            payload = {
                **prepared.model_arguments,
                "command": prepared.command,
            }
            selected_tool_call = {
                "tool": grounded_raw.get("tool", "gui_action"),
                "name": name,
                "arguments_raw": grounded_raw.get("arguments_raw"),
                "arguments": dict(arguments),
                "call_id": grounded_raw.get("call_id"),
            }
            prepared_evidence = {
                "name": prepared.name,
                "model_arguments": dict(prepared.model_arguments),
                "pixel_arguments": dict(prepared.pixel_arguments),
                "command": prepared.command,
                "settle_seconds": prepared.settle_seconds,
            }
            execution_link = _grounding_link(grounded_raw)
            self._emit_execution_evidence(
                {
                    "schema_version": 1,
                    "record_type": "gateway_dispatch",
                    **execution_link,
                    "selected_tool_call": selected_tool_call,
                    "prepared_action": prepared_evidence,
                    "executor_payload": copy.deepcopy(payload),
                }
            )
            try:
                execution = self.executor(payload)
            except Exception as exc:
                self._emit_execution_evidence(
                    {
                        "schema_version": 1,
                        "record_type": "gateway_result",
                        **execution_link,
                        "status": "exception",
                        "error": {
                            "type": type(exc).__name__,
                            "detail": str(exc)[:1_000],
                        },
                    }
                )
                raise
            if not isinstance(execution, dict):
                self._emit_execution_evidence(
                    {
                        "schema_version": 1,
                        "record_type": "gateway_result",
                        **execution_link,
                        "status": "invalid_result",
                        "result_type": type(execution).__name__,
                    }
                )
                raise HoloGuiGatewayError("GUI executor must return an object")
            executed = bool(execution.get("executed"))
            self._emit_execution_evidence(
                {
                    "schema_version": 1,
                    "record_type": "gateway_result",
                    **execution_link,
                    "status": "ok" if executed else "error",
                    "execution_result": copy.deepcopy(execution),
                }
            )
            result: dict[str, Any] = {
                "status": "ok" if executed else "error",
                "executed": executed,
                "result": {
                    "environment_acknowledged": executed,
                    "grounded_action": _audit_action(prepared),
                },
                "grounding": {
                    "tool": grounded_raw.get("tool", "gui_action"),
                    "name": name,
                    "arguments": dict(arguments),
                    "pixel_arguments": dict(prepared.pixel_arguments),
                },
                "prepared_action": prepared_evidence,
            }
            for key in (
                "request_id",
                "request_sha256",
                "response_sha256",
                "call_id",
                "arguments_raw",
                "model_requested",
                "model_actual",
                "actual_model_accepted",
                "reasoning_effort_requested",
                "reasoning_mode_requested",
                "reasoning_mode_effective",
                "reasoning_profile",
                "expected_model_root",
                "accepted_actual_models",
                "enable_thinking_requested",
            ):
                if key in grounded_raw:
                    result["grounding"][key] = grounded_raw[key]
            if not executed:
                result["error"] = execution.get(
                    "error",
                    {
                        "type": "DesktopActionError",
                        "detail": "the GUI executor rejected the grounded action",
                    },
                )
            return result
        except HoloGuiGatewayError:
            raise
        except HoloGroundingError as exc:
            raise HoloGuiGatewayError(
                f"Holo GUI gateway rejected grounded action: HoloGroundingError: {str(exc)[:1000]}"
            ) from exc
        except Exception as exc:
            raise HoloGuiGatewayError(
                f"Holo GUI gateway rejected grounded action: {type(exc).__name__}"
            ) from exc

    def __call__(
        self,
        gui_request: Mapping[str, Any],
        screenshot: bytes,
    ) -> dict[str, Any]:
        return self.execute(gui_request, screenshot)
