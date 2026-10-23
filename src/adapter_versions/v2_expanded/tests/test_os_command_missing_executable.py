import io
import json
import sys

import pytest

from os_adapter import worker
from os_adapter.command import CommandRunner
from os_adapter.errors import AdapterError


def test_complete_command_in_argv_zero_reports_exact_executable_without_running_shell(tmp_path):
    sentinel = tmp_path / "must-not-exist.txt"
    argv = [f"printf synthetic > {sentinel}"]
    original = list(argv)

    with pytest.raises(AdapterError) as caught:
        CommandRunner().run(argv, cwd=str(tmp_path), check=False)

    error = caught.value
    assert error.code == "EXECUTABLE_NOT_FOUND"
    assert error.http_status == 422
    assert error.details["argv"] == original
    assert error.details["executable"] == original[0]
    assert error.details["cwd"] == str(tmp_path)
    assert error.details["filename"] == original[0]
    assert error.details["errno"] == 2
    assert error.details["error"] == str(error.__cause__)
    assert error.details["shell_parsing"] is False
    assert "each argument in a separate string" in error.details["guidance"]
    assert '["bash", "-c", <one model-authored script>]' in error.details["guidance"]
    assert argv == original
    assert not sentinel.exists()


def test_missing_working_directory_is_not_misreported_as_missing_executable(tmp_path):
    cwd = str(tmp_path / "absent-directory")
    argv = [sys.executable, "-c", "print('should not run')"]

    with pytest.raises(AdapterError) as caught:
        CommandRunner().run(argv, cwd=cwd)

    error = caught.value
    assert error.code == "WORKING_DIRECTORY_NOT_FOUND"
    assert error.details["cwd"] == error.details["filename"] == cwd
    assert error.details["executable"] == sys.executable
    assert error.details["argv"] == argv
    assert error.details["error"] == str(error.__cause__)
    assert "select an existing cwd" in error.details["guidance"]


def test_missing_executable_details_reach_worker_json(tmp_path, monkeypatch, capsys):
    argv = [str(tmp_path / "unavailable-program"), "--inspect", "name with spaces"]
    monkeypatch.setattr(
        worker, "execute", lambda _payload: CommandRunner().run(argv, cwd=str(tmp_path))
    )
    monkeypatch.setattr(worker.sys, "stdin", io.StringIO("{}"))

    with pytest.raises(SystemExit) as stopped:
        worker.main()

    assert stopped.value.code == 1
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["code"] == "EXECUTABLE_NOT_FOUND"
    assert error["http_status"] == 422
    assert error["details"]["argv"] == argv
    assert error["details"]["cwd"] == str(tmp_path)
    assert error["details"]["filename"] == argv[0]
    assert "without a shell" in error["details"]["guidance"]


def test_separate_argv_keeps_literal_argument_characters(tmp_path):
    literal = "literal $HOME | > and repeated  spaces"
    argv = [sys.executable, "-c", "import sys; print(sys.argv[1])", literal]
    original = list(argv)

    result = CommandRunner().run(argv, cwd=str(tmp_path))

    assert result["returncode"] == 0
    assert result["stdout"] == literal + "\n"
    assert result["argv"] == original
    assert argv == original
