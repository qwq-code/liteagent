from __future__ import annotations

from pathlib import Path

from os_adapter import deploy_host


def test_os_deploy_reuses_writer_pdf_wheel_in_own_payload(monkeypatch) -> None:
    root = Path(__file__).parents[1]
    wheel = (
        root / "writer_adapter/vendor"
        / "pymupdf-1.28.0-cp310-abi3-manylinux_2_28_x86_64.whl"
    )
    package_paths = deploy_host.source_files(root)
    uploads = []
    calls = []
    monkeypatch.setattr(
        deploy_host,
        "upload",
        lambda _url, source, destination: uploads.append((source, destination)),
    )
    monkeypatch.setattr(
        deploy_host,
        "execute",
        lambda _url, command: calls.append((command, len(uploads))) or {},
    )
    monkeypatch.setattr(
        deploy_host, "install_payload",
        lambda _url, command: calls.append((command, len(uploads))),
    )
    monkeypatch.setattr(deploy_host, "wait_health", lambda _url: {"status": "ok"})

    result = deploy_host.deploy("http://control.invalid", "http://os.invalid", root)

    assert wheel.is_file()
    assert not (root / "os_adapter/vendor" / wheel.name).exists()
    assert uploads == [
        (
            path,
            f"{deploy_host.REMOTE_PAYLOAD}/{path.relative_to(root).as_posix()}",
        )
        for path in package_paths
    ] + [(wheel, f"{deploy_host.REMOTE_PAYLOAD}/os_adapter/vendor/{wheel.name}")]
    assert result["uploaded_files"] == len(uploads) == len(package_paths) + 1
    install_command, uploads_before_install = calls[-1]
    assert install_command == [
        "bash",
        f"{deploy_host.REMOTE_PAYLOAD}/os_adapter/deploy/install.sh",
        deploy_host.REMOTE_PAYLOAD,
    ]
    assert uploads_before_install == len(uploads)


def test_os_installs_pdf_wheel_offline_into_own_import_root() -> None:
    script = (Path(__file__).parents[1] / "os_adapter/deploy/install.sh").read_text()
    assert (
        'pymupdf_wheel="${payload_dir}/os_adapter/vendor/'
        'pymupdf-1.28.0-cp310-abi3-manylinux_2_28_x86_64.whl"'
    ) in script
    pip_command = script.split("/usr/bin/python3 -m pip install", 1)[1].split(
        "install -m 0644", 1
    )[0]
    assert "--no-index" in pip_command
    assert "--no-deps" in pip_command
    assert "--upgrade" in pip_command
    assert '--target "${install_dir}"' in pip_command
    assert '"${pymupdf_wheel}"' in pip_command
