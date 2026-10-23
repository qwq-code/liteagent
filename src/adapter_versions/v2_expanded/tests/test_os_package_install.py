import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from os_adapter import command, deploy_host


ROOT = Path(__file__).parents[1]
OCR_DIR = ROOT / "os_adapter/vendor/ocr"


def installer_code():
    script = (ROOT / "os_adapter/deploy/install.sh").read_text()
    return script.split('/usr/bin/python3 - "${ocr_dir}" <<\'PY\'\n', 1)[1].split("\nPY", 1)[0]


def test_ocr_package_bundle_has_valid_hashes_and_is_deployed(monkeypatch):
    entries = [line.split() for line in (OCR_DIR / "SHA256SUMS.sha256").read_text().splitlines()]
    assert len(entries) == 5
    assert {name for _, name in entries} == {
        path.name for path in deploy_host.source_files(ROOT)
        if path.suffix == ".deb" and path.parent == OCR_DIR
    }
    assert OCR_DIR / "SHA256SUMS.sha256" in deploy_host.source_files(ROOT)
    for expected, name in entries:
        assert hashlib.sha256((OCR_DIR / name).read_bytes()).hexdigest() == expected

    calls = []
    monkeypatch.setattr(command, "CommandRunner", lambda: SimpleNamespace(
        sudo=lambda argv, *, timeout: calls.append((argv, timeout)) or {"stdout": "", "stderr": ""}
    ))
    monkeypatch.setattr(sys, "argv", ["install.sh:ocr", str(OCR_DIR)])
    exec(compile(installer_code(), "install.sh:ocr", "exec"), {})
    assert calls[-1][0][:4] == ["env", "DEBIAN_FRONTEND=noninteractive", "dpkg", "-i"]
    assert [Path(path).name for path in calls[-1][0][4:]] == [name for _, name in entries]
    assert not any("apt-get" in argv for argv, _ in calls)


def test_ocr_package_bundle_rejects_bad_checksum_before_install(monkeypatch, tmp_path):
    (tmp_path / "SHA256SUMS.sha256").write_bytes((OCR_DIR / "SHA256SUMS.sha256").read_bytes())
    (tmp_path / "liblept5_1.82.0-3build1_amd64.deb").write_bytes(b"tampered")
    monkeypatch.setattr(sys, "argv", ["install.sh:ocr", str(tmp_path)])
    monkeypatch.setattr(command, "CommandRunner", lambda: pytest.fail("checksum must fail before sudo"))
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        exec(compile(installer_code(), "install.sh:ocr", "exec"), {})
