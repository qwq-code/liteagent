from __future__ import annotations

from pathlib import Path

from writer_adapter import deploy_host


def test_writer_install_uses_offline_pymupdf_without_package_mirrors() -> None:
    script = (
        Path(__file__).parents[1] / "writer_adapter" / "deploy" / "install.sh"
    ).read_text(encoding="utf-8")
    assert "import flask, uno" in script
    assert "apt-get" not in script
    assert "import fitz, flask, uno" not in script
    assert "pymupdf-1.28.0-cp310-abi3-manylinux_2_28_x86_64.whl" in script
    assert "--no-index" in script
    assert "--no-deps" in script
    assert '--target "${install_dir}"' in script


def test_writer_deployment_includes_offline_pdf_dependency() -> None:
    root = Path(__file__).parents[1]
    wheel = (
        root / "writer_adapter/vendor"
        / "pymupdf-1.28.0-cp310-abi3-manylinux_2_28_x86_64.whl"
    )

    assert wheel in deploy_host.source_files(root)
    assert wheel.is_file()


def test_writer_health_accepts_missing_optional_pymupdf(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "status": "ok",
                "uno_module_available": True,
                "pymupdf_available": False,
                "listener_ready": True,
            }

    monkeypatch.setattr(deploy_host.requests, "get", lambda *args, **kwargs: Response())
    assert deploy_host.wait_health("http://writer.invalid", timeout=0.1)[
        "pymupdf_available"
    ] is False
