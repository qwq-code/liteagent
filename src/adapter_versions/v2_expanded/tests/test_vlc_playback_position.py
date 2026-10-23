from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from integrations.lite_agent.adapter_results import compact_adapter_body
from integrations.lite_agent.context_projection import (
    compact_execution_summary_for_model,
)
from vlc_adapter import actions, vlc_mpris
from vlc_adapter.errors import AdapterError


def _native_bus(monkeypatch, players):
    class NativeError(Exception):
        pass

    class Bus:
        def list_names(self):
            return ["org.example.OtherPlayer", *players]

        def get_object(self, name, path, *, introspect):
            assert path == "/org/mpris/MediaPlayer2"
            assert introspect is False

            def get_all(interface, *, timeout):
                assert interface == "org.mpris.MediaPlayer2.Player" and timeout > 0
                if isinstance(players[name], Exception):
                    raise players[name]
                return players[name]

            return SimpleNamespace(GetAll=get_all)

    monkeypatch.setitem(
        sys.modules,
        "dbus",
        SimpleNamespace(
            SessionBus=Bus, DBusException=NativeError, Interface=lambda obj, _name: obj
        ),
    )
    return NativeError


def _player(uri="file:///srv/clips/sample.webm", position=12_345_678):
    return {
        "Metadata": {"xesam:url": uri},
        "Position": position,
        "PlaybackStatus": "Paused",
    }


def test_native_position_uses_matching_uri_and_preserves_microseconds(monkeypatch):
    _native_bus(
        monkeypatch,
        {
            "org.mpris.MediaPlayer2.vlc": _player("file:///srv/other.webm", 5_000_000),
            "org.mpris.MediaPlayer2.vlc.instance42": _player(),
        },
    )

    assert vlc_mpris.read_playback_position("file:///srv/clips/sample.webm", 2) == {
        "time_seconds": 12.345678,
        "position_microseconds": 12_345_678,
        "time_source": "mpris",
    }


@pytest.mark.parametrize(
    "players",
    [
        {"org.mpris.MediaPlayer2.vlc": _player("file:///other/sample.webm")},
        {
            "org.mpris.MediaPlayer2.vlc": _player(),
            "org.mpris.MediaPlayer2.vlc.instance42": _player(),
        },
    ],
)
def test_native_position_does_not_guess_missing_or_ambiguous_identity(
    monkeypatch, players
):
    _native_bus(monkeypatch, players)
    with pytest.raises(AdapterError, match="unambiguous"):
        vlc_mpris.read_playback_position("file:///srv/clips/sample.webm", 2)


@pytest.mark.parametrize("position", [0, 4_123_456])
def test_status_exposes_native_position_without_replacing_coarse_time(
    monkeypatch, position
):
    _native_bus(monkeypatch, {"org.mpris.MediaPlayer2.vlc": _player(position=position)})
    monkeypatch.setattr(
        actions,
        "wait_http",
        lambda *args, **kwargs: {"state": "paused", "currentplid": "4", "time": "4"},
    )
    monkeypatch.setattr(
        actions,
        "read_playlist_uri",
        lambda *args, **kwargs: "file:///srv/clips/sample.webm",
    )

    result = actions.VlcActions().playback_status({}, 2)

    assert result["time_seconds"] == position / 1_000_000
    assert result["time"] == "4"
    assert result["source"] == "/srv/clips/sample.webm"
    projected = compact_execution_summary_for_model(
        [
            {
                "step": 1,
                "action": "playback.status",
                "executed": True,
                "result": compact_adapter_body({"status": "ok", "result": result}),
            }
        ],
        max_chars=3200,
    )
    assert projected[0]["result"]["result"]["time_seconds"] == position / 1_000_000


def test_native_failure_preserves_source_and_reports_time_error(monkeypatch):
    players = {}
    error = _native_bus(monkeypatch, players)
    players["org.mpris.MediaPlayer2.vlc"] = error("connection unavailable")
    monkeypatch.setattr(
        actions,
        "wait_http",
        lambda *args, **kwargs: {"state": "paused", "currentplid": "4", "time": "4"},
    )
    monkeypatch.setattr(
        actions,
        "read_playlist_uri",
        lambda *args, **kwargs: "file:///srv/clips/sample.webm",
    )

    result = actions.VlcActions().playback_status({}, 2)

    assert result["source"] == "/srv/clips/sample.webm"
    assert result["time"] == "4" and "time_seconds" not in result
    assert result["time_error"]["code"] == "MEDIA_POSITION_UNAVAILABLE"
