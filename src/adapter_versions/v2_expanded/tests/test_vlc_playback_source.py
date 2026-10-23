from __future__ import annotations

from io import BytesIO
from urllib.error import URLError
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element, SubElement, tostring

import pytest

from integrations.lite_agent.adapter_results import compact_adapter_body
from integrations.lite_agent.context_projection import compact_execution_summary_for_model
from vlc_adapter.actions import VlcActions
from vlc_adapter import vlc_http
from vlc_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


def _status_xml(item_id="8", state="paused"):
    root = Element("root")
    for key, value in {"state": state, "time": "19", "currentplid": item_id}.items():
        SubElement(root, key).text = value
    category = SubElement(SubElement(root, "information"), "category", name="meta")
    SubElement(category, "info", name="filename").text = "display-name.mp4"
    return tostring(root)


def _playlist_xml(uri, item_id="8"):
    root = Element("node", name="Playlist")
    SubElement(root, "leaf", id="7", uri="file:///wrong/display-name.mp4")
    SubElement(root, "leaf", id=item_id, uri=uri, current="current")
    return tostring(root)


def _serve(monkeypatch, status, playlist):
    requested = []

    def urlopen(request, *, timeout):
        resource = urlsplit(request.full_url).path.rsplit("/", 1)[-1]
        requested.append(resource)
        assert timeout > 0
        assert request.has_header("Authorization")
        response = status if resource == "status.xml" else playlist
        if isinstance(response, Exception):
            raise response
        return BytesIO(response)

    monkeypatch.setattr(vlc_http.urllib.request, "urlopen", urlopen)
    return requested


def test_status_retains_native_current_playlist_id():
    assert vlc_http.parse_status(_status_xml())["currentplid"] == "8"


def test_status_contract_distinguishes_source_from_display_labels():
    contract = STRICT_ACTION_PARAM_SCHEMAS["playback.status"]
    assert contract["properties"] == {} and contract["required"] == []
    assert "display labels, not file paths" in contract["description"]
    assert "source_error" in contract["description"]


@pytest.mark.parametrize(
    ("uri", "source"),
    [
        ("file:///srv/clips/cut%20one.mp4", "/srv/clips/cut one.mp4"),
        ("https://media.example/clip%20one.mp4?edition=2", "https://media.example/clip%20one.mp4?edition=2"),
        ("file://media-host/share/clip.mp4", "file://media-host/share/clip.mp4"),
    ],
)
def test_playback_source_uses_observed_playlist_uri(monkeypatch, uri, source):
    requested = _serve(monkeypatch, _status_xml(), _playlist_xml(uri))

    result = VlcActions().playback_status({}, 2)

    assert result["source"] == source
    assert result["source_uri"] == uri
    assert result["currentplid"] == "8"
    assert result["metadata"]["filename"] == "display-name.mp4"
    assert result["state"] == "paused" and result["time"] == "19"
    assert requested == ["status.xml", "playlist.xml"]
    projected = compact_execution_summary_for_model(
        [{"step": 1, "action": "playback.status", "executed": True,
          "result": compact_adapter_body({"status": "ok", "result": result})}],
        max_chars=3200,
    )
    assert projected[0]["result"]["result"]["source"] == source
    assert projected[0]["result"]["result"]["source_uri"] == uri


def test_missing_playlist_item_does_not_guess_from_filename(monkeypatch):
    _serve(monkeypatch, _status_xml(), _playlist_xml("file:///wrong/other.mp4", "9"))

    result = VlcActions().playback_status({}, 2)

    assert result["source"] is None
    assert result["source_uri"] is None
    assert result["source_error"]["code"] == "MEDIA_SOURCE_UNAVAILABLE"
    assert result["source_error"]["details"]["currentplid"] == "8"


def test_playlist_failure_preserves_playback_status_and_error(monkeypatch):
    _serve(monkeypatch, _status_xml(), URLError("playlist unavailable"))

    result = VlcActions().playback_status({}, 2)

    assert result["state"] == "paused" and result["time"] == "19"
    assert result["source"] is None
    assert result["source_error"]["code"] == "VLC_NOT_READY"


def test_no_current_media_does_not_request_or_invent_a_source(monkeypatch):
    requested = _serve(monkeypatch, _status_xml("-1", "stopped"), None)

    result = VlcActions().playback_status({}, 2)

    assert result["state"] == "stopped"
    assert result["source"] is None and result["source_uri"] is None
    assert "source_error" not in result
    assert requested == ["status.xml"]
