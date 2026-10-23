from types import SimpleNamespace

import pytest

from vlc_adapter import worker
from vlc_adapter.actions import VlcActions
from vlc_adapter.errors import AdapterError
from vlc_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


@pytest.mark.parametrize("create_media", [False, True])
def test_find_local_reports_successful_discovery_with_or_without_matches(
    tmp_path, monkeypatch, create_media
) -> None:
    if create_media:
        (tmp_path / "sample.mp4").write_bytes(b"video")
    actions = SimpleNamespace(
        dispatch=lambda _action, params, timeout: VlcActions.playback_find_local(
            None, params, timeout
        ),
        runner=object(),
    )
    monkeypatch.setattr(worker, "VlcActions", lambda: actions)

    response = worker.execute(
        {
            "action": "playback.find_local",
            "params": {"roots": [str(tmp_path)], "name_patterns": ["*.mp4"]},
        }
    )

    assert response["verification"]["passed"] is True
    assert response["result"]["match_count"] == int(create_media)
    assert response["result"]["returned_count"] == int(create_media)
    if create_media:
        assert response["result"]["matches"][0]["path"] == str(
            tmp_path / "sample.mp4"
        )


def test_find_local_rejects_malformed_discovery_result(monkeypatch) -> None:
    actions = SimpleNamespace(
        dispatch=lambda *_args: {"matches": [{"path": "file.mp4"}], "match_count": 1},
        runner=object(),
    )
    monkeypatch.setattr(worker, "VlcActions", lambda: actions)

    with pytest.raises(AdapterError, match="operation verification failed"):
        worker.execute(
            {"action": "playback.find_local", "params": {"roots": ["~/Desktop"]}}
        )


def test_find_local_schema_guides_truncated_labels_to_broad_globs() -> None:
    description = STRICT_ACTION_PARAM_SCHEMAS["playback.find_local"]["properties"][
        "name_patterns"
    ]["description"]
    assert "*.mp4" in description
    assert "ellipsis" in description
