import json
from pathlib import Path
import sys

import pytest

from os_adapter import desktop_dependencies as desktop
from os_adapter import package_install as installer
from os_adapter.errors import AdapterError


@pytest.fixture(autouse=True)
def no_host_package_state(monkeypatch):
    monkeypatch.setattr(desktop, "needs_package_recovery", lambda: False)


def response(argv, code=0, stderr="", timed_out=False):
    return {"argv": argv, "returncode": code, "stdout": "", "stderr": stderr, "timed_out": timed_out}


@pytest.mark.parametrize("mode", ["success", "lock", "interrupted", "dependency", "timeout"])
def test_install_recovers_only_known_states_and_preserves_errors(monkeypatch, mode):
    calls = []
    monkeypatch.setattr(Path, "glob", lambda *_: iter([]))
    monkeypatch.setattr(installer.time, "sleep", lambda _: None)

    def command(argv, timeout):
        calls.append(argv)
        if argv[0] == "systemctl":
            return response(argv, 5, "Unit packagekit.socket not loaded")
        assert timeout > 120
        installs = sum(c[:2] == ["dpkg", "-i"] for c in calls)
        if argv[:2] == ["dpkg", "-i"] and installs == 1:
            if mode == "lock":
                return response(argv, 2, "frontend lock was locked by process 123")
            if mode == "interrupted":
                return response(argv, 2, "dpkg was interrupted")
            if mode == "dependency":
                return response(argv, 1, "missing libexample dependency")
            if mode == "timeout":
                return response(argv, -15, "unpacking", timed_out=True)
        return response(argv)

    monkeypatch.setattr(installer, "_run_command", command)
    report = installer._install(["/tmp/verified.deb"], 600)
    assert report["ok"] == (mode not in {"dependency", "timeout"})
    assert len(report["warnings"]) == 2  # Missing optional service is not fatal.
    assert (["dpkg", "--configure", "--pending"] in calls) == (mode == "interrupted")
    assert sum(c[:2] == ["dpkg", "-i"] for c in calls) == (2 if mode in {"lock", "interrupted"} else 1)
    if mode == "dependency":
        assert report["attempts"][-1]["stderr"] == "missing libexample dependency"


def test_prior_interrupted_journal_is_configured_before_install(monkeypatch):
    monkeypatch.setattr(Path, "glob", lambda *_: iter([Path("0000")]))
    calls = []

    def command(argv, timeout):
        calls.append(argv)
        return response(argv)

    monkeypatch.setattr(installer, "_run_command", command)
    assert installer._install(["/tmp/verified.deb"], 600)["ok"]
    assert calls[-2:] == [["dpkg", "--configure", "--pending"], ["dpkg", "-i", "/tmp/verified.deb"]]


def test_timeout_cleans_up_descendant_process_and_retains_output(tmp_path):
    pidfile = tmp_path / "child.pid"
    program = (
        "import subprocess,sys,time; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        f"open({str(pidfile)!r},'w').write(str(p.pid)); "
        "print('unpacking evidence',flush=True); time.sleep(60)"
    )
    result = installer._run_command([sys.executable, "-c", program], 1)
    assert result["timed_out"]
    assert "unpacking evidence" in result["stdout"]
    pid = int(pidfile.read_text())
    stat = Path(f"/proc/{pid}/stat")
    assert not stat.exists() or stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"


def test_host_receives_dpkg_error_details(monkeypatch, capsys):
    report = {"ok": False, "attempts": [{"stderr": "exact dpkg error", "returncode": 2}]}

    class Runner:
        def sudo(self, argv, timeout):
            assert timeout == 615
            return {"stdout": json.dumps(report)}

    monkeypatch.setattr(installer, "CommandRunner", Runner)
    with pytest.raises(AdapterError) as failure:
        installer.install_offline_packages([Path("/tmp/verified.deb")])
    assert failure.value.details == report
    assert "exact dpkg error" in capsys.readouterr().out


def test_missing_dependencies_are_checked_then_installed_together(monkeypatch, tmp_path):
    clipboard = tmp_path / "clipboard" / desktop.PACKAGE
    clipboard.parent.mkdir()
    clipboard.write_bytes(b"clipboard")
    monkeypatch.setattr(desktop, "PACKAGE_SHA256", desktop.hashlib.sha256(b"clipboard").hexdigest())
    ocr = tmp_path / "ocr"
    ocr.mkdir()
    manifest = []
    for name in desktop.OCR_PACKAGES:
        (ocr / name).write_bytes(name.encode())
        manifest.append(f"{desktop.hashlib.sha256(name.encode()).hexdigest()}  {name}")
    (ocr / "SHA256SUMS.sha256").write_text("\n".join(manifest))
    installed = False

    def install(packages):
        nonlocal installed
        assert packages == [clipboard, *[ocr / name for name in desktop.OCR_PACKAGES]]
        installed = True

    monkeypatch.setattr(desktop, "install_offline_packages", install)
    monkeypatch.setattr(desktop.shutil, "which", lambda _: installed)
    monkeypatch.setattr(desktop, "ocr_ready", lambda: installed)
    desktop.ensure_desktop_dependencies(tmp_path)
    assert installed


def test_unconfigured_packages_are_not_accepted_just_because_binaries_work(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop.shutil, "which", lambda _: True)
    monkeypatch.setattr(desktop, "ocr_ready", lambda: True)
    monkeypatch.setattr(desktop, "needs_package_recovery", lambda: True)
    # A ready executable must not let a damaged package transaction bypass the
    # verified bundle requirement and be declared deployment success.
    with pytest.raises(FileNotFoundError):
        desktop.ensure_desktop_dependencies(tmp_path)


def test_ready_dependencies_need_no_package_files_or_privilege(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop.shutil, "which", lambda _: True)
    monkeypatch.setattr(desktop, "ocr_ready", lambda: True)
    monkeypatch.setattr(installer, "CommandRunner", lambda: pytest.fail("unnecessary privilege"))
    desktop.ensure_desktop_dependencies(tmp_path)


def test_bad_ocr_hash_prevents_any_install(monkeypatch, tmp_path):
    directory = tmp_path / "ocr"
    directory.mkdir()
    entries = []
    for name in desktop.OCR_PACKAGES:
        (directory / name).write_bytes(b"corrupt")
        entries.append("0" * 64 + "  " + name)
    (directory / "SHA256SUMS.sha256").write_text("\n".join(entries))
    monkeypatch.setattr(desktop.shutil, "which", lambda _: True)
    monkeypatch.setattr(desktop, "ocr_ready", lambda: False)
    monkeypatch.setattr(desktop, "install_offline_packages", lambda _: pytest.fail("checksum first"))
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        desktop.ensure_desktop_dependencies(tmp_path)
