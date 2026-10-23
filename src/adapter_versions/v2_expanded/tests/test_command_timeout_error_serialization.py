from __future__ import annotations

import importlib
import io
import json
import subprocess

import pytest


@pytest.mark.parametrize("adapter", ["vscode_adapter", "vlc_adapter"])
def test_timeout_partial_output_reaches_worker_error_json(
    adapter, monkeypatch, capsys
) -> None:
    command = importlib.import_module(f"{adapter}.command")
    worker = importlib.import_module(f"{adapter}.worker")
    argv = ["synthetic-cli", "--inspect"]

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            argv, 0.1, output=b"partial output\n", stderr=b"native error: \xff\n"
        )

    monkeypatch.setattr(command.subprocess, "run", timeout)
    monkeypatch.setattr(
        worker, "execute", lambda _payload: command.CommandRunner().run(argv, timeout=0.1)
    )
    monkeypatch.setattr(worker.sys, "stdin", io.StringIO("{}"))

    with pytest.raises(SystemExit) as stopped:
        worker.main()

    assert stopped.value.code == 1
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["code"] == "OPERATION_TIMEOUT"
    assert error["message"] == "command exceeded 0.1 seconds"
    assert error["http_status"] == 504
    assert error["details"] == {
        "argv": argv,
        "stdout": "partial output\n",
        "stderr": "native error: \ufffd\n",
    }
