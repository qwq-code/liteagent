from copy import deepcopy

import pytest

from os_adapter.actions import OSActions
from os_adapter.command import literal_argument_failure_guidance
from os_adapter.errors import AdapterError


@pytest.mark.parametrize("kind", ["attached_redirection", "wildcard"])
def test_native_command_failure_explains_literal_argument_without_rewriting(tmp_path, kind):
    argument = "> notes.txt" if kind == "attached_redirection" else "*.txt"
    params = {
        "argv": ["ls", "--", argument],
        "cwd_source": "explicit",
        "cwd_path": str(tmp_path),
        "provenance": "none",
    }
    original = deepcopy(params)

    with pytest.raises(AdapterError) as caught:
        OSActions().run_command(params, 5)

    error = caught.value
    assert error.code == "COMMAND_FAILED"
    assert error.details["returncode"] == 2
    assert argument in error.details["stderr"]
    assert "No such file or directory" in error.details["stderr"]
    assert error.details["stdout"] == ""
    assert error.details["argv"] == original["argv"]
    assert error.details["cwd"] == str(tmp_path)
    assert "literally" in error.details["guidance"]
    if kind == "attached_redirection":
        assert "stdout_path" in error.details["guidance"]
        assert "If the leading >" in error.details["guidance"]
    else:
        assert '["bash", "-c", <one model-authored script>]' in error.details["guidance"]
        assert "find -name" in error.details["guidance"]
    assert params == original
    assert list(tmp_path.iterdir()) == []


def test_native_pattern_unrelated_to_stderr_does_not_receive_shell_guidance():
    argv = ["find", ".", "-name", "*.txt", "-invalid-option"]
    original = list(argv)

    guidance = literal_argument_failure_guidance(
        argv, "find: unknown predicate '-invalid-option'\n"
    )

    assert guidance is None
    assert argv == original


def test_native_program_pattern_remains_executable_and_unchanged(tmp_path):
    source = tmp_path / "native note.txt"
    source.touch()
    params = {
        "argv": ["find", ".", "-name", "*.txt"],
        "cwd_source": "explicit",
        "cwd_path": str(tmp_path),
        "provenance": "none",
    }
    original = deepcopy(params)

    result = OSActions().run_command(params, 5)

    assert result["returncode"] == 0
    assert result["stdout"] == "./native note.txt\n"
    assert result["stderr"] == ""
    assert "guidance" not in result
    assert result["argv"] == original["argv"]
    assert params == original
