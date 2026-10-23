from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from vscode_adapter import deploy_host
from vscode_adapter.offline_extensions import (
    OFFLINE_EXTENSIONS,
    OfflineExtension,
    ensure_offline_extensions,
    offline_extension_path,
    verify_offline_extension,
)


def _vsix_bytes(*, publisher: str, name: str, version: str, engine: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "extension/package.json",
            json.dumps(
                {
                    "publisher": publisher,
                    "name": name,
                    "version": version,
                    "engines": {"vscode": engine},
                }
            ),
        )
    return output.getvalue()


class Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, *, chunk_size: int) -> list[bytes]:
        assert chunk_size == 1024 * 1024
        return [self.content]


class Session:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.calls: list[tuple[str, bool, tuple[int, int]]] = []

    def get(self, url: str, *, stream: bool, timeout: tuple[int, int]) -> Response:
        self.calls.append((url, stream, timeout))
        return Response(self.content)


def _synthetic_extension(content: bytes) -> OfflineExtension:
    return OfflineExtension(
        extension_id="example.tools",
        version="1.2.3",
        vscode_engine="^1.80.0",
        url="https://marketplace.visualstudio.com/example.vsix",
        sha256=hashlib.sha256(content).hexdigest(),
        filename="example.tools-1.2.3.vsix",
    )


def test_official_assets_are_pinned_to_marketplace_hashes() -> None:
    assert [item.extension_id for item in OFFLINE_EXTENSIONS] == [
        "ms-python.debugpy",
        "ms-python.python",
    ]
    assert len({item.sha256 for item in OFFLINE_EXTENSIONS}) == 2
    for item in OFFLINE_EXTENSIONS:
        assert item.url.startswith("https://marketplace.visualstudio.com/")
        assert len(item.sha256) == 64
        assert item.filename.endswith(".vsix")


def test_downloads_and_reuses_verified_cache(tmp_path: Path) -> None:
    content = _vsix_bytes(
        publisher="example",
        name="tools",
        version="1.2.3",
        engine="^1.80.0",
    )
    expected = _synthetic_extension(content)
    session = Session(content)

    first = ensure_offline_extensions(
        cache_directory=tmp_path,
        extensions=[expected],
        session=session,  # type: ignore[arg-type]
    )
    second = ensure_offline_extensions(
        cache_directory=tmp_path,
        extensions=[expected],
        session=session,  # type: ignore[arg-type]
    )

    assert len(session.calls) == 1
    assert first == second
    assert first[0]["extension_id"] == "example.tools"
    assert first[0]["sha256"] == expected.sha256


def test_replaces_invalid_cached_file(tmp_path: Path) -> None:
    content = _vsix_bytes(
        publisher="example",
        name="tools",
        version="1.2.3",
        engine="^1.80.0",
    )
    expected = _synthetic_extension(content)
    destination = tmp_path / expected.filename
    destination.write_bytes(b"not a vsix")

    result = ensure_offline_extensions(
        cache_directory=tmp_path,
        extensions=[expected],
        session=Session(content),  # type: ignore[arg-type]
    )

    assert result[0]["sha256"] == expected.sha256
    assert destination.read_bytes() == content


def test_rejects_manifest_mismatch(tmp_path: Path) -> None:
    content = _vsix_bytes(
        publisher="example",
        name="other",
        version="1.2.3",
        engine="^1.80.0",
    )
    expected = OfflineExtension(
        **{
            **_synthetic_extension(content).__dict__,
            "extension_id": "example.tools",
        }
    )
    path = tmp_path / expected.filename
    path.write_bytes(content)

    with pytest.raises(ValueError, match="manifest mismatch"):
        verify_offline_extension(path, expected)


def test_offline_extension_path_maps_only_known_deployed_assets(tmp_path: Path) -> None:
    expected = OFFLINE_EXTENSIONS[0]
    path = tmp_path / expected.filename
    path.write_bytes(b"verified-by-deployment")

    assert offline_extension_path(expected.extension_id, tmp_path) == path
    assert offline_extension_path("publisher.unknown", tmp_path) is None


def test_deploy_uploads_verified_assets_before_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "vscode_adapter"
    (package / "deploy").mkdir(parents=True)
    (package / "service.py").write_text("STATUS = 'ok'\n", encoding="utf-8")
    (package / "deploy" / "install.sh").write_text("exit 0\n", encoding="utf-8")
    asset = tmp_path / "example.tools-1.2.3.vsix"
    asset.write_bytes(b"verified")
    events: list[tuple[str, Any]] = []

    monkeypatch.setattr(
        deploy_host,
        "execute",
        lambda _url, command: events.append(("execute", command)) or {},
    )
    monkeypatch.setattr(
        deploy_host,
        "upload",
        lambda _url, source, destination: events.append(
            ("upload", (source, destination))
        ),
    )
    monkeypatch.setattr(
        deploy_host,
        "ensure_offline_extensions",
        lambda: [{"path": str(asset), "extension_id": "example.tools"}],
    )
    monkeypatch.setattr(deploy_host, "wait_health", lambda _url: {"status": "ok"})
    monkeypatch.setattr(
        deploy_host.requests,
        "post",
        lambda *_args, **_kwargs: Response(b""),
    )

    result = deploy_host.deploy("http://control", "http://adapter", tmp_path)

    install_index = next(
        index
        for index, event in enumerate(events)
        if event[0] == "execute" and event[1][0] == "bash"
    )
    asset_upload_index = next(
        index
        for index, event in enumerate(events)
        if event[0] == "upload" and str(event[1][0]).endswith(".vsix")
    )
    assert asset_upload_index < install_index
    assert events[asset_upload_index][1][1].endswith(asset.name)
    assert result["offline_extensions"][0]["extension_id"] == "example.tools"
