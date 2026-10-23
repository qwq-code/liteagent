from __future__ import annotations

from unittest.mock import Mock

import pytest

from impress_adapter import lifecycle as lifecycle_module
from impress_adapter.errors import AdapterError
from impress_adapter.lifecycle import LibreOfficeLifecycle


@pytest.fixture
def office(tmp_path, monkeypatch):
    instance = LibreOfficeLifecycle()
    instance.log_path = tmp_path / "soffice.log"
    monkeypatch.setattr(instance, "_stop_stale_office", Mock(return_value=True))
    monkeypatch.setattr(instance, "_remove_profile_locks", Mock())
    monkeypatch.setattr(instance, "_live_office_processes", Mock(return_value=[]))
    process = Mock(returncode=0)
    process.poll.return_value = 0
    monkeypatch.setattr(lifecycle_module.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(lifecycle_module.time, "sleep", Mock())
    return instance


@pytest.mark.parametrize("mode", ["ready", "live_office", "stopped", "host_prepare"])
def test_listener_start_preserves_live_office_and_existing_host_lifecycle(
    office, monkeypatch, mode,
):
    ready = [True] if mode == "ready" else [False, False, True]
    monkeypatch.setattr(office, "listener_ready", Mock(side_effect=ready))
    office._live_office_processes.return_value = (
        ["soffice.bin"] if mode == "live_office" else []
    )
    if mode == "host_prepare":
        monkeypatch.setattr(office, "listener_ready", Mock(side_effect=[False, True]))
        result = office.prepare()
    else:
        result = office.prepare(restart_existing=False)

    assert result["ready"] is True
    assert office._stop_stale_office.call_count == (mode == "host_prepare")
    assert office._remove_profile_locks.call_count == (mode == "stopped")
    assert lifecycle_module.subprocess.Popen.call_count == (mode != "ready")
    if mode == "live_office":
        assert result["attached_to_running"] is True
        assert result["cleaned_stale_processes"] is False
        assert lifecycle_module.subprocess.Popen.call_args.args[0] == [
            "soffice", "--accept=socket,host=127.0.0.1,port=2002;urp;",
            "--norestore", "--nologo", "--nodefault", "--nofirststartwizard",
        ]


def test_ipc_forwarder_exit_zero_requires_an_observed_listener(office, monkeypatch):
    monkeypatch.setattr(office, "listener_ready", Mock(return_value=False))
    office._live_office_processes.return_value = ["soffice.bin"]

    with pytest.raises(AdapterError) as failure:
        office.prepare(timeout_seconds=0.01, restart_existing=False)

    assert failure.value.code == "LIBREOFFICE_NOT_READY"
    assert failure.value.details["last_exit_code"] == 0
    assert failure.value.details["live_processes"] == ["soffice.bin"]
    office._stop_stale_office.assert_not_called()
    office._remove_profile_locks.assert_not_called()
    lifecycle_module.subprocess.Popen.assert_called_once()


def test_failed_spawn_keeps_its_exit_code_when_listener_check_clears_handle(
    office, monkeypatch,
):
    monkeypatch.setattr(
        lifecycle_module.socket, "create_connection", Mock(side_effect=OSError("closed"))
    )
    process = Mock(returncode=1)
    process.poll.return_value = 1
    lifecycle_module.subprocess.Popen.return_value = process

    with pytest.raises(AdapterError) as failure:
        office.prepare(restart_existing=False)

    assert failure.value.code == "LIBREOFFICE_NOT_READY"
    assert failure.value.details["last_exit_code"] == 1
    office._stop_stale_office.assert_not_called()
