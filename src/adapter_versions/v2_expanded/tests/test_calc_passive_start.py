from __future__ import annotations

from unittest.mock import Mock

import pytest

from calc_adapter import lifecycle as lifecycle_module
from calc_adapter.errors import AdapterError
from calc_adapter.lifecycle import LibreOfficeLifecycle


@pytest.fixture
def office(tmp_path, monkeypatch):
    instance = LibreOfficeLifecycle()
    instance.log_path = tmp_path / "soffice.log"
    monkeypatch.setattr(instance, "_stop_stale_office", Mock(return_value=True))
    monkeypatch.setattr(instance, "_remove_profile_locks", Mock())
    monkeypatch.setattr(instance, "_live_office_processes", Mock(return_value=[]))
    monkeypatch.setattr(lifecycle_module.subprocess, "Popen", Mock())
    return instance


def test_ready_listener_is_a_noop(office, monkeypatch):
    monkeypatch.setattr(office, "listener_ready", Mock(return_value=True))
    result = office.prepare(restart_existing=False)
    assert result["ready"] is True
    assert result["already_running"] is True
    office._stop_stale_office.assert_not_called()
    office._remove_profile_locks.assert_not_called()
    office._live_office_processes.assert_not_called()
    lifecycle_module.subprocess.Popen.assert_not_called()


def test_passive_start_clears_stale_locks_when_no_live_office_exists(
    office, monkeypatch
):
    monkeypatch.setattr(office, "listener_ready", Mock(side_effect=[False, True]))
    result = office.prepare(restart_existing=False)
    assert result["ready"] is True
    assert result["already_running"] is False
    assert result["attached_to_running"] is False
    assert result["cleaned_stale_processes"] is False
    office._stop_stale_office.assert_not_called()
    office._live_office_processes.assert_called_once_with()
    office._remove_profile_locks.assert_called_once_with()
    args = lifecycle_module.subprocess.Popen.call_args.args[0]
    assert args == [
        "soffice",
        "--accept=socket,host=127.0.0.1,port=2002;urp;",
        "--norestore",
        "--nologo",
        "--nodefault",
        "--nofirststartwizard",
    ]


def test_live_office_receives_acceptor_without_stop_or_lock_removal(
    office, monkeypatch
):
    monkeypatch.setattr(
        office, "listener_ready", Mock(side_effect=[False, False, True])
    )
    monkeypatch.setattr(lifecycle_module.time, "sleep", Mock())
    office._live_office_processes.return_value = ["soffice.bin"]
    process = Mock(returncode=0)
    process.poll.return_value = 0
    lifecycle_module.subprocess.Popen.return_value = process
    unlink = Mock()
    monkeypatch.setattr(lifecycle_module.Path, "unlink", unlink)
    result = office.prepare(restart_existing=False)
    assert result["ready"] is True
    assert result["already_running"] is True
    assert result["attached_to_running"] is True
    assert result["cleaned_stale_processes"] is False
    process.poll.assert_called_once()
    office._stop_stale_office.assert_not_called()
    office._remove_profile_locks.assert_not_called()
    unlink.assert_not_called()
    lifecycle_module.subprocess.Popen.assert_called_once()
    assert (
        "--accept=socket,host=127.0.0.1,port=2002;urp;"
        in lifecycle_module.subprocess.Popen.call_args.args[0]
    )


def test_forwarder_exit_zero_is_not_listener_success(office, monkeypatch):
    monkeypatch.setattr(office, "listener_ready", Mock(return_value=False))
    office._live_office_processes.return_value = ["soffice.bin"]
    process = Mock(returncode=0)
    process.poll.return_value = 0
    lifecycle_module.subprocess.Popen.return_value = process
    with pytest.raises(AdapterError) as caught:
        office.prepare(timeout_seconds=0.01, restart_existing=False)
    assert caught.value.code == "LIBREOFFICE_NOT_READY"
    assert caught.value.details["last_exit_code"] == 0
    assert caught.value.details["live_processes"] == ["soffice.bin"]
    lifecycle_module.subprocess.Popen.assert_called_once()
    office._stop_stale_office.assert_not_called()
    office._remove_profile_locks.assert_not_called()


def test_passive_retry_rechecks_live_processes_before_starting(office, monkeypatch):
    monkeypatch.setattr(
        office, "listener_ready", Mock(side_effect=[False, False, False, True])
    )
    office._live_office_processes.side_effect = [[], ["soffice.bin"]]
    process = Mock(returncode=1)
    process.poll.return_value = 1
    lifecycle_module.subprocess.Popen.return_value = process
    result = office.prepare(restart_existing=False)
    assert result["ready"] is True
    assert result["attached_to_running"] is True
    assert office._live_office_processes.call_count == 2
    assert lifecycle_module.subprocess.Popen.call_count == 2
    office._remove_profile_locks.assert_called_once_with()
    office._stop_stale_office.assert_not_called()


def test_default_prepare_retains_setup_restart_behavior(office, monkeypatch):
    monkeypatch.setattr(office, "listener_ready", Mock(side_effect=[False, True]))
    result = office.prepare()
    assert result["ready"] is True
    assert result["cleaned_stale_processes"] is True
    office._stop_stale_office.assert_called_once()
    lifecycle_module.subprocess.Popen.assert_called_once()


def test_exited_spawn_reports_error_after_listener_clears_its_handle(
    office, monkeypatch
):
    monkeypatch.setattr(
        lifecycle_module.socket,
        "create_connection",
        Mock(side_effect=OSError("closed")),
    )
    process = Mock(returncode=1)
    process.poll.return_value = 1
    lifecycle_module.subprocess.Popen.return_value = process
    with pytest.raises(AdapterError) as caught:
        office.prepare(restart_existing=False)
    assert caught.value.code == "LIBREOFFICE_NOT_READY"
    assert caught.value.details["last_exit_code"] == 1
    assert lifecycle_module.subprocess.Popen.call_count == 2
    office._stop_stale_office.assert_not_called()
