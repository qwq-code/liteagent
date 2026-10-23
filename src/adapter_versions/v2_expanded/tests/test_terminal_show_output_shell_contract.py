from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from os_adapter import actions as actions_module
from os_adapter.actions import OSActions
from os_adapter.errors import AdapterError
from os_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from os_adapter.worker import _default_specs


SHELL_TOKENS = (">", ">>", "|", "||", "&&", ";")


def test_visible_terminal_specs_use_expanded_user_path_argv() -> None:
    params = {
        "argv": ["cat", "~/Desktop/System_Resources_Report.txt"],
        "expected_returncodes": [0],
    }
    result = {
        "argv": ["cat", "/home/user/Desktop/System_Resources_Report.txt"],
        "completion_marker": "[command exited with status 0]",
    }
    specs = _default_specs("terminal.show_output", params, result)
    assert specs[0]["argv"] == result["argv"]


class _MustNotBeCalled:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Any:
        def unexpected(*_args: object, **_kwargs: object) -> None:
            self.calls.append(name)
            raise AssertionError(f"unexpected call: {name}")

        return unexpected


@pytest.mark.parametrize("shell_token", SHELL_TOKENS)
def test_command_and_visible_terminal_reject_same_shell_tokens_before_execution(
    monkeypatch: pytest.MonkeyPatch,
    shell_token: str,
) -> None:
    runner = _MustNotBeCalled()
    lifecycle = _MustNotBeCalled()
    actions = OSActions(runner=runner, lifecycle=lifecycle)
    terminal_params = {
        "argv": ["printf", "counterfactual", shell_token, "wc", "-c"],
        "cwd_source": "active_context",
        "provenance": "none",
    }
    command_params = {
        "argv": list(terminal_params["argv"]),
        "cwd_source": "home",
        "provenance": "none",
    }
    original_terminal_params = deepcopy(terminal_params)
    original_command_params = deepcopy(command_params)
    cwd_resolution_calls = 0

    def unexpected_cwd_resolution(*_args: object, **_kwargs: object) -> Path:
        nonlocal cwd_resolution_calls
        cwd_resolution_calls += 1
        raise AssertionError("cwd resolution must follow shell-syntax validation")

    monkeypatch.setattr(
        actions_module,
        "resolve_active_desktop_directory",
        unexpected_cwd_resolution,
    )

    with pytest.raises(AdapterError) as terminal_raised:
        actions.dispatch("terminal.show_output", terminal_params, 5)
    with pytest.raises(AdapterError) as command_raised:
        actions.dispatch("command.run", command_params, 5)

    for error in (terminal_raised.value, command_raised.value):
        assert error.code == "SHELL_SYNTAX_UNSUPPORTED"
        assert error.http_status == 422
        assert error.details["shell_tokens"] == [shell_token]
        assert error.details["shell_parsing"] is False
        assert error.details["argv"] == terminal_params["argv"]
    assert terminal_raised.value.message == command_raised.value.message
    terminal_core = {
        key: terminal_raised.value.details[key]
        for key in ("shell_tokens", "shell_parsing", "argv")
    }
    command_core = {
        key: command_raised.value.details[key]
        for key in ("shell_tokens", "shell_parsing", "argv")
    }
    assert terminal_core == command_core
    if shell_token in {">", ">>"}:
        terminal_recovery = terminal_raised.value.details["recovery"]
        command_recovery = command_raised.value.details["recovery"]
        command_properties = STRICT_ACTION_PARAM_SCHEMAS["command.run"]["properties"]
        terminal_properties = STRICT_ACTION_PARAM_SCHEMAS["terminal.show_output"][
            "properties"
        ]

        assert terminal_recovery != command_recovery
        assert (
            "terminal.show_output leaves the command output visible"
            in terminal_recovery
        )
        assert "public command.run action" in terminal_recovery
        assert "command.run's stdout_path field" in terminal_recovery
        assert "destination as stdout_path" in command_recovery
        assert "append_stdout=true only for >> semantics" in command_recovery
        assert {"stdout_path", "append_stdout"}.issubset(command_properties)
        assert {"stdout_path", "append_stdout"}.isdisjoint(terminal_properties)
        assert {"stdout_path", "append_stdout"}.isdisjoint(terminal_params)
    else:
        assert terminal_raised.value.details == command_raised.value.details
    assert terminal_params == original_terminal_params
    assert command_params == original_command_params
    assert cwd_resolution_calls == 0
    assert runner.calls == []
    assert lifecycle.calls == []


@pytest.mark.parametrize(
    "argv",
    [
        [
            "find",
            ".",
            "-name",
            "*.php",
            "-type",
            "f",
            "-exec",
            "wc",
            "-l",
            "{}",
            "+",
        ],
        ["find", ".", "-name", "*.txt", "-exec", "wc", "-l", "{}", ";"],
        ["find", ".", "-exec", "printf", "%s", "+", "{}", ";"],
        ["python3", "-c", "print('|')"],
    ],
)
def test_visible_terminal_preserves_valid_argv_and_params(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
) -> None:
    runner = _MustNotBeCalled()
    lifecycle = _MustNotBeCalled()
    actions = OSActions(runner=runner, lifecycle=lifecycle)
    params = {
        "argv": argv,
        "cwd_source": "home",
        "provenance": "shell_history",
    }
    original_params = deepcopy(params)
    captured: dict[str, Any] = {}

    def capture_visible_command(
        received_runner: object,
        received_lifecycle: object,
        received_params: dict[str, Any],
        *,
        cwd: Path,
        timeout: float,
    ) -> dict[str, Any]:
        captured.update(
            {
                "runner": received_runner,
                "lifecycle": received_lifecycle,
                "params": deepcopy(received_params),
                "params_identity": received_params is params,
                "cwd": cwd,
                "timeout": timeout,
            }
        )
        return {"argv": list(received_params["argv"]), "verified": True}

    monkeypatch.setattr(
        actions_module,
        "run_visible_terminal_command",
        capture_visible_command,
    )

    result = actions.show_terminal_output(params, 7)

    assert result == {"argv": argv, "verified": True}
    assert captured == {
        "runner": runner,
        "lifecycle": lifecycle,
        "params": original_params,
        "params_identity": True,
        "cwd": Path.home().resolve(),
        "timeout": 7,
    }
    assert params == original_params
    assert runner.calls == []
    assert lifecycle.calls == []


def test_visible_terminal_schema_distinguishes_find_terminator_from_shell() -> None:
    description = STRICT_ACTION_PARAM_SCHEMAS["terminal.show_output"]["properties"][
        "argv"
    ]["description"]

    assert (
        "Do not include >, >>, |, ||, &&, or ; as shell operators; they are "
        "rejected."
    ) in description
    assert "terminating find's -exec" in description


@pytest.mark.parametrize("action", ["command.run", "terminal.show_output"])
def test_command_schema_explains_literal_globs(action: str) -> None:
    description = STRICT_ACTION_PARAM_SCHEMAS[action]["properties"]["argv"]["description"]
    assert "Wildcards such as *.txt stay literal" in description
    assert "select bash -c for shell expansion" in description
    assert "find -name" in description


@pytest.mark.parametrize("find,execute", [("find", "-exec"), ("/usr/bin/find", "-execdir")])
def test_command_executes_native_find_terminator_unchanged(
    tmp_path: Path, find: str, execute: str,
) -> None:
    source = tmp_path / "sample note.txt"
    source.write_text("native find execution\n", encoding="utf-8")
    params = {
        "argv": [find, ".", "-name", "*.txt", execute, "cat", "{}", ";"],
        "cwd_source": "explicit",
        "cwd_path": str(tmp_path),
        "provenance": "none",
    }
    original = deepcopy(params)

    result = OSActions().dispatch("command.run", params, 5)

    assert result["returncode"] == 0
    assert result["stdout"] == "native find execution\n"
    assert result["stderr"] == ""
    assert result["argv"] == original["argv"]
    assert params == original


def test_find_terminator_does_not_exempt_a_following_shell_operator() -> None:
    argv = ["find", ".", "-exec", "wc", "-l", "{}", ";", ";", "pwd"]
    with pytest.raises(AdapterError) as raised:
        actions_module._reject_shell_syntax(argv, redirection_recovery="unused")
    assert raised.value.details["shell_tokens"] == [";"]


def test_find_native_error_is_returned_after_terminator_is_accepted(tmp_path: Path) -> None:
    params = {
        "argv": ["find", "missing-input", "-exec", "cat", "{}", ";"],
        "cwd_source": "explicit",
        "cwd_path": str(tmp_path),
        "provenance": "none",
    }
    with pytest.raises(AdapterError) as raised:
        OSActions().dispatch("command.run", params, 5)
    assert raised.value.code == "COMMAND_FAILED"
    assert raised.value.details["argv"] == params["argv"]
    assert "missing-input" in raised.value.details["stderr"]


def test_command_run_schema_explains_bash_c_for_intended_shell_syntax() -> None:
    description = STRICT_ACTION_PARAM_SCHEMAS["command.run"]["description"]
    assert 'argv=["bash", "-c", <one complete model-authored script>]' in description
    assert "do not place standalone shell operators" in description


def test_terminal_show_output_schema_explains_bash_c_for_intended_shell_syntax() -> None:
    description = STRICT_ACTION_PARAM_SCHEMAS["terminal.show_output"]["description"]
    assert 'argv=["bash", "-c", <one complete model-authored script>]' in description
    assert "do not place standalone shell operators" in description
