from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from vscode_adapter import deploy_host
from vscode_adapter import lifecycle as lifecycle_module
from vscode_adapter.deploy_host import source_files, wait_health
from vscode_adapter.errors import AdapterError
from vscode_adapter.lifecycle import FORBIDDEN_EXTENSION_ID, VscodeLifecycle


class ExtensionRunner:
    def __init__(
        self,
        *,
        installed: bool,
        uninstall_succeeds: bool = True,
        listing_fails: bool = False,
    ) -> None:
        self.installed = installed
        self.uninstall_succeeds = uninstall_succeeds
        self.listing_fails = listing_fails
        self.calls: list[list[str]] = []

    def run(self, argv: list[str], **_kwargs: Any) -> dict[str, Any]:
        self.calls.append(argv)
        if argv[:2] == ["code", "--uninstall-extension"]:
            if self.uninstall_succeeds:
                self.installed = False
            return {
                "argv": argv,
                "returncode": 0 if self.uninstall_succeeds else 1,
                "stdout": "",
                "stderr": "",
            }
        if argv[:2] == ["code", "--list-extensions"]:
            if self.listing_fails:
                raise AdapterError("VSCODE_NOT_READY", "listing unavailable")
            entries = (
                f"{FORBIDDEN_EXTENSION_ID}@0.0.1\nother.publisher@2.0.0\n"
                if self.installed
                else "other.publisher@2.0.0\n"
            )
            return {
                "argv": argv,
                "returncode": 0,
                "stdout": entries,
                "stderr": "",
            }
        raise AssertionError(f"unexpected command: {argv}")


class Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


def _ready_health(*, forbidden_installed: bool) -> dict[str, Any]:
    return {
        "status": "ok",
        "all_commands_available": True,
        "dbus_available": True,
        "config_writable": True,
        "flask_available": True,
        "pyatspi_available": True,
        "pyautogui_available": True,
        "forbidden_extension_absent": not forbidden_installed,
        "forbidden_extension": {
            "extension_id": FORBIDDEN_EXTENSION_ID,
            "installed": forbidden_installed,
        },
    }


def _make_prerequisites_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        lifecycle_module.shutil, "which", lambda name: f"/usr/bin/{name}"
    )
    monkeypatch.setattr(lifecycle_module.Path, "exists", lambda _path: True)
    monkeypatch.setattr(lifecycle_module.Path, "mkdir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(lifecycle_module.os, "access", lambda *_args: True)
    monkeypatch.setattr(
        lifecycle_module.importlib.util, "find_spec", lambda _name: object()
    )


def test_strict_payload_excludes_task_shaped_extension_tree(tmp_path: Path) -> None:
    package = tmp_path / "vscode_adapter"
    extension = package / "extension" / "extension"
    extension.mkdir(parents=True)
    (package / "service.py").write_text("STATUS = 'ok'\n", encoding="utf-8")
    (extension / "package.json").write_text(
        '{"publisher": "synthetic", "name": "counterfactual"}\n',
        encoding="utf-8",
    )
    (extension / "extension.js").write_text("module.exports = {};\n", encoding="utf-8")

    selected = source_files(tmp_path, strict_generic=True)
    relative = [path.relative_to(package).as_posix() for path in selected]

    assert relative == ["service.py"]


def test_installer_neither_builds_nor_installs_forbidden_extension() -> None:
    install_script = (
        Path(__file__).parents[1] / "vscode_adapter" / "deploy" / "install.sh"
    ).read_text(encoding="utf-8")

    assert "extension_build" not in install_script
    assert "--install-extension" not in install_script
    assert 'test ! -e "${payload_dir}/vscode_adapter/extension"' in install_script
    assert f"--uninstall-extension {FORBIDDEN_EXTENSION_ID}" in install_script

    healthcheck = (
        Path(__file__).parents[1] / "vscode_adapter" / "deploy" / "healthcheck.sh"
    ).read_text(encoding="utf-8")
    assert "helper_extension" not in healthcheck
    assert 'payload.get("forbidden_extension_absent") is not True' in healthcheck
    assert (
        'payload.get("forbidden_extension", {}).get("installed") is not False'
        in healthcheck
    )


def test_prepare_uninstalls_residual_forbidden_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_prerequisites_available(monkeypatch)
    runner = ExtensionRunner(installed=True)

    result = VscodeLifecycle(runner).prepare(timeout_seconds=7)

    assert result["ready"] is True
    assert result["health"]["forbidden_extension_absent"] is True
    assert runner.calls[0] == [
        "code",
        "--uninstall-extension",
        FORBIDDEN_EXTENSION_ID,
    ]
    assert runner.calls[1] == ["code", "--list-extensions", "--show-versions"]


@pytest.mark.parametrize(
    ("runner", "expected_installed"),
    [
        (ExtensionRunner(installed=True, uninstall_succeeds=False), True),
        (ExtensionRunner(installed=False, listing_fails=True), None),
    ],
)
def test_prepare_fails_closed_when_forbidden_extension_absence_is_unproven(
    monkeypatch: pytest.MonkeyPatch,
    runner: ExtensionRunner,
    expected_installed: bool | None,
) -> None:
    _make_prerequisites_available(monkeypatch)

    with pytest.raises(AdapterError, match="prerequisites are unavailable") as raised:
        VscodeLifecycle(runner).prepare()

    health = raised.value.details
    assert health["forbidden_extension_absent"] is False
    assert health["forbidden_extension"]["installed"] is expected_installed


def test_host_health_wait_rejects_residual_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = iter(
        [
            _ready_health(forbidden_installed=True),
            _ready_health(forbidden_installed=False),
        ]
    )
    calls = 0

    def get(_url: str, *, timeout: float) -> Response:
        nonlocal calls
        calls += 1
        assert timeout == 5
        return Response(next(payloads))

    monkeypatch.setattr(deploy_host.requests, "get", get)
    monkeypatch.setattr(deploy_host.time, "sleep", lambda _seconds: None)

    result = wait_health("http://adapter.invalid", timeout=1)

    assert calls == 2
    assert result["forbidden_extension_absent"] is True
