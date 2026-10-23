import hashlib
from pathlib import Path

import pytest

from os_adapter import clipboard_dependency as dependency
from os_adapter import deploy_host, lifecycle
from os_adapter.errors import AdapterError


ROOT = Path(__file__).parents[1]
BUNDLE = ROOT / "os_adapter/vendor/clipboard"


def test_pinned_clipboard_package_is_valid_and_deployed():
    package = BUNDLE / dependency.PACKAGE
    assert package.stat().st_size == 20460
    assert hashlib.sha256(package.read_bytes()).hexdigest() == dependency.PACKAGE_SHA256
    assert package in deploy_host.source_files(ROOT)


@pytest.mark.parametrize("backend", ["xsel", "xclip"])
def test_existing_backend_needs_no_privilege_or_package(monkeypatch, tmp_path, backend):
    monkeypatch.setattr(dependency.shutil, "which", lambda name: name == backend)
    monkeypatch.setattr(dependency, "CommandRunner", lambda: pytest.fail("unnecessary installation"))
    assert dependency.ensure_clipboard_backend(tmp_path) == backend


def test_bad_package_is_rejected_before_privilege(monkeypatch, tmp_path):
    (tmp_path / dependency.PACKAGE).write_bytes(b"modified")
    monkeypatch.setattr(dependency.shutil, "which", lambda _: None)
    monkeypatch.setattr(dependency, "CommandRunner", lambda: pytest.fail("checksum first"))
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        dependency.ensure_clipboard_backend(tmp_path)


@pytest.mark.parametrize("failure", [None, "locked by process 123", "dependency problems"])
def test_offline_install_only_retries_package_lock(monkeypatch, failure):
    installed = False
    installs = []

    class Runner:
        def sudo(self, argv, *, timeout):
            nonlocal installed
            assert timeout <= 120
            if argv[0] == "systemctl":
                return {}
            installs.append(argv)
            if len(installs) == 1 and failure:
                raise AdapterError("OPERATION_FAILED", "dpkg failed", {"stderr": failure})
            installed = True
            return {"stdout": "", "stderr": ""}

    monkeypatch.setattr(dependency, "CommandRunner", Runner)
    monkeypatch.setattr(dependency.shutil, "which", lambda name: installed and name == "xsel")
    monkeypatch.setattr(dependency.time, "sleep", lambda _: None)
    if failure == "dependency problems":
        with pytest.raises(AdapterError):
            dependency.ensure_clipboard_backend(BUNDLE)
        assert len(installs) == 1
    else:
        assert dependency.ensure_clipboard_backend(BUNDLE) == "xsel"
        assert len(installs) == (2 if failure else 1)
    assert all(argv == ["env", "DEBIAN_FRONTEND=noninteractive", "dpkg", "-i",
                        str(BUNDLE / dependency.PACKAGE)] for argv in installs)


def test_install_must_leave_an_executable(monkeypatch):
    monkeypatch.setattr(dependency.shutil, "which", lambda _: None)

    class Runner:
        def sudo(self, *args, **kwargs):
            return {}

    monkeypatch.setattr(dependency, "CommandRunner", Runner)
    with pytest.raises(RuntimeError, match="without an xsel"):
        dependency.ensure_clipboard_backend(BUNDLE)


@pytest.mark.parametrize("backend", [None, "xsel", "xclip"])
def test_health_and_prepare_require_one_clipboard_backend(monkeypatch, backend):
    monkeypatch.setattr(lifecycle.shutil, "which", lambda name: (
        name == backend if name in {"xsel", "xclip"} else True
    ))
    monkeypatch.setattr(lifecycle.Path, "exists", lambda _: True)
    instance = lifecycle.OSLifecycle()
    monkeypatch.setattr(instance, "windows", lambda: [])
    assert instance.health()["clipboard_available"] is bool(backend)
    if backend:
        assert instance.prepare()["ready"]
    else:
        with pytest.raises(AdapterError, match="clipboard backend"):
            instance.prepare()
