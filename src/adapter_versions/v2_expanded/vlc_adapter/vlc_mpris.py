"""Read fractional playback time from the matching native VLC player."""

from __future__ import annotations

import time
from typing import Any

from .errors import AdapterError


def read_playback_position(source_uri: str, timeout: float) -> dict[str, Any]:
    try:
        import dbus
    except ImportError as exc:
        raise AdapterError(
            "MEDIA_POSITION_UNAVAILABLE", "Python D-Bus support is unavailable"
        ) from exc

    deadline = time.monotonic() + timeout
    try:
        bus = dbus.SessionBus()
        names = [
            str(name)
            for name in bus.list_names()
            if str(name) == "org.mpris.MediaPlayer2.vlc"
            or str(name).startswith("org.mpris.MediaPlayer2.vlc.")
        ]
        matches = []
        for name in names:
            player = bus.get_object(name, "/org/mpris/MediaPlayer2", introspect=False)
            properties = dbus.Interface(player, "org.freedesktop.DBus.Properties")
            observed = properties.GetAll(
                "org.mpris.MediaPlayer2.Player",
                timeout=max(0.1, deadline - time.monotonic()),
            )
            if str(observed.get("Metadata", {}).get("xesam:url", "")) == source_uri:
                matches.append(observed)
    except dbus.DBusException as exc:
        raise AdapterError(
            "MEDIA_POSITION_UNAVAILABLE", "VLC MPRIS position read failed", str(exc)
        ) from exc

    if len(matches) != 1 or matches[0].get("PlaybackStatus") not in {
        "Playing",
        "Paused",
    }:
        raise AdapterError(
            "MEDIA_POSITION_UNAVAILABLE",
            "No unambiguous active MPRIS player matches the current media URI",
        )
    microseconds = matches[0].get("Position")
    if not isinstance(microseconds, int) or microseconds < 0:
        raise AdapterError(
            "MEDIA_POSITION_UNAVAILABLE", "VLC did not report a nonnegative position"
        )
    return {
        "time_seconds": int(microseconds) / 1_000_000,
        "position_microseconds": int(microseconds),
        "time_source": "mpris",
    }
