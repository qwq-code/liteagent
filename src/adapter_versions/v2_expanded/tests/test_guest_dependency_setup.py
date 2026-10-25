import contextlib
import io
import json
import shlex
import subprocess
from unittest.mock import mock_open, patch

import pytest

from scripts.run_lite_agent_pilot import prepare_guest_setup_dependencies


class Controller:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def run_bash_script(self, script, timeout):
        self.calls.append((script, timeout))
        return self.response


def test_dependency_command_uses_explicit_budget_and_safe_python_argument():
    controller = Controller({"returncode": 0, "output": '{"prepared": ["sar"]}'})
    assert prepare_guest_setup_dependencies(controller, {"instruction": "Use sar."}) == {
        "prepared": ["sar"]
    }
    script, timeout = controller.calls[0]
    argv = shlex.split(script)
    assert argv[:2] == ["python3", "-c"]
    assert len(argv) == 3
    assert timeout == 480

    # Exercise the exact guest payload without package installation. Already
    # installed tools must skip both package-manager and service mutations.
    output = io.StringIO()
    with patch("shutil.which", return_value="/usr/bin/sar"), patch(
        "subprocess.run", side_effect=AssertionError("unexpected mutation")
    ), contextlib.redirect_stdout(output):
        exec(argv[2], {})
    assert json.loads(output.getvalue()) == {
        "required": ["sar"], "prepared": ["sar"], "attempts": []
    }


@pytest.mark.parametrize("response", [None, [], {"returncode": -1, "output": "timeout"}])
def test_dependency_transport_failure_is_explicit_and_not_retried(response):
    controller = Controller(response)
    with pytest.raises(RuntimeError, match="guest dependency command failed"):
        prepare_guest_setup_dependencies(controller, {"instruction": "Use sar."})
    assert len(controller.calls) == 1


@pytest.mark.parametrize("output", ["null", "[]", "{}", '{"prepared": []}', "not json"])
def test_unverified_dependency_is_not_accepted(output):
    controller = Controller({"returncode": 0, "output": output})
    with pytest.raises(RuntimeError, match="failed to (prepare|parse)"):
        prepare_guest_setup_dependencies(controller, {"instruction": "Use sar."})


def test_no_dependency_leaves_guest_untouched():
    controller = Controller(None)
    assert prepare_guest_setup_dependencies(controller, {"instruction": "Write a report."}) == {
        "required": [], "prepared": []
    }
    assert controller.calls == []


def test_timed_out_installer_is_killed_before_endpoint_deadline():
    controller = Controller({"returncode": 0, "output": '{"prepared": ["sar"]}'})
    prepare_guest_setup_dependencies(controller, {"instruction": "Use sar."})
    code = shlex.split(controller.calls[0][0])[2]
    budgets = []

    def run(command, **kwargs):
        assert command[:5] == ["sudo", "-S", "timeout", "--signal=TERM", "--kill-after=5s"]
        budgets.append(int(command[5]) + 5)
        return subprocess.CompletedProcess(
            command, 124 if "install" in command else 0, "", ""
        )

    output = io.StringIO()
    with patch("shutil.which", return_value=None), patch(
        "builtins.open", mock_open()
    ), patch("fcntl.flock"), patch("subprocess.run", run), contextlib.redirect_stdout(output):
        exec(code, {})
    assert sum(budgets) == 440 < controller.calls[0][1]
    result = json.loads(output.getvalue())
    assert result["prepared"] == []
    assert result["attempts"][-1]["timed_out"] is True


def test_duplicate_dependency_setup_does_not_start_second_installer():
    controller = Controller({"returncode": 0, "output": '{"prepared": ["sar"]}'})
    prepare_guest_setup_dependencies(controller, {"instruction": "Use sar."})
    code = shlex.split(controller.calls[0][0])[2]
    output = io.StringIO()
    with patch("shutil.which", return_value=None), patch(
        "builtins.open", mock_open()
    ), patch("fcntl.flock", side_effect=BlockingIOError), patch(
        "subprocess.run", side_effect=AssertionError("duplicate installer")
    ), contextlib.redirect_stdout(output):
        exec(code, {})
    assert json.loads(output.getvalue())["attempts"] == [
        {"operation": "dependency setup", "error": "already running"}
    ]
