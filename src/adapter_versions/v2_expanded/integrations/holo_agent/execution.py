from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DesktopExecution:
    observation: Any
    result: dict[str, Any]
    transport: dict[str, Any]


def _model_error(returncode: Any) -> dict[str, Any]:
    error: dict[str, Any] = {
        "type": "DesktopActionError",
        "detail": "The desktop environment rejected the GUI input command.",
    }
    if isinstance(returncode, int):
        error["returncode"] = returncode
    return {"status": "error", "executed": False, "error": error}


def execute_desktop_action(
    env: Any,
    command: str,
    settle_seconds: float,
) -> DesktopExecution:
    """Execute through OSWorld while retaining its otherwise discarded reply."""
    if command == "WAIT":
        observation, _reward, _done, _info = env.step(command, settle_seconds)
        return DesktopExecution(
            observation=observation,
            result={
                "status": "ok",
                "executed": True,
                "environment_acknowledged": True,
            },
            transport={"kind": "wait"},
        )

    original = env.controller.execute_python_command
    calls: list[dict[str, Any]] = []

    def capture(actual_command: str) -> Any:
        response = original(actual_command)
        calls.append({"command": actual_command, "response": response})
        return response

    env.controller.execute_python_command = capture
    try:
        observation, _reward, _done, _info = env.step(command, settle_seconds)
    finally:
        env.controller.execute_python_command = original

    if len(calls) != 1:
        raise RuntimeError(
            f"desktop execution boundary expected one command, observed {len(calls)}"
        )
    transport = calls[0]
    if transport["command"] != command:
        raise RuntimeError("desktop execution boundary changed the GUI command")

    response = transport["response"]
    returncode = response.get("returncode") if isinstance(response, dict) else None
    succeeded = (
        isinstance(response, dict)
        and response.get("status") == "success"
        and returncode == 0
    )
    result = (
        {
            "status": "ok",
            "executed": True,
            "environment_acknowledged": True,
        }
        if succeeded
        else _model_error(returncode)
    )
    return DesktopExecution(
        observation=observation,
        result=result,
        transport=transport,
    )
