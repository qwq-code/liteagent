from __future__ import annotations

from typing import Any

from integrations.holo_agent.execution import execute_desktop_action


class FakeController:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.commands: list[str] = []

    def execute_python_command(self, command: str) -> Any:
        self.commands.append(command)
        return self.response


class FakeEnv:
    def __init__(self, response: Any) -> None:
        self.controller = FakeController(response)

    def step(
        self, command: str, _pause: float
    ) -> tuple[dict[str, str], int, bool, dict]:
        if command != "WAIT":
            self.controller.execute_python_command(command)
        return {"screenshot": "frame"}, 0, False, {}


def test_execution_reports_success_only_for_zero_returncode() -> None:
    env = FakeEnv({"status": "success", "returncode": 0, "output": "", "error": ""})
    original = env.controller.execute_python_command

    execution = execute_desktop_action(env, "pyautogui.click(1, 2)", 0.0)

    assert execution.result == {
        "status": "ok",
        "executed": True,
        "environment_acknowledged": True,
    }
    assert execution.transport["command"] == "pyautogui.click(1, 2)"
    assert env.controller.commands == ["pyautogui.click(1, 2)"]
    assert env.controller.execute_python_command == original


def test_execution_sanitizes_nonzero_returncode_for_model() -> None:
    env = FakeEnv(
        {
            "status": "success",
            "returncode": 1,
            "output": "",
            "error": "private desktop traceback",
        }
    )

    execution = execute_desktop_action(env, "pyautogui.write('x')", 0.0)

    assert execution.result == {
        "status": "error",
        "executed": False,
        "error": {
            "type": "DesktopActionError",
            "detail": "The desktop environment rejected the GUI input command.",
            "returncode": 1,
        },
    }
    assert "private desktop traceback" not in str(execution.result)
    assert execution.transport["response"]["error"] == "private desktop traceback"


def test_wait_does_not_claim_a_python_command_reply() -> None:
    env = FakeEnv(None)

    execution = execute_desktop_action(env, "WAIT", 1.0)

    assert execution.result["executed"] is True
    assert execution.transport == {"kind": "wait"}
    assert env.controller.commands == []
