from __future__ import annotations

from typing import Any

from .errors import AdapterError


def _default_profile():
    from gi.repository import Gio, GLib

    registry = Gio.Settings.new("org.gnome.Terminal.ProfilesList")
    profile_id = registry.get_value("default")
    identifier = profile_id.unpack()
    if not identifier:
        raise AdapterError("SETTING_UNAVAILABLE", "GNOME Terminal has no default profile")
    path = f"/org/gnome/terminal/legacy/profiles:/:{identifier}/"
    schema = "org.gnome.Terminal.Legacy.Profile"
    profile = Gio.Settings.new_with_path(schema, path)
    return Gio, GLib, profile, f"{schema}:{path}", profile_id.print_(True)


def _require_key(profile: Any, key: str) -> None:
    if key not in profile.list_keys():
        raise AdapterError(
            "SETTING_UNAVAILABLE", "the default terminal profile has no such key",
            {"key": key, "available_keys": sorted(profile.list_keys())}, 422,
        )


def inspect_default_profile(params: dict[str, Any]) -> dict[str, Any]:
    _gio, _glib, profile, schema, profile_id = _default_profile()
    result = {"profile": "default", "schema": schema, "profile_id": profile_id}
    key = params.get("key")
    if key is None:
        return {**result, "keys": sorted(profile.list_keys())}
    _require_key(profile, key)
    value = profile.get_value(key)
    return {
        **result, "key": key, "value": value.unpack(),
        "observed": value.print_(True), "value_type": value.get_type_string(),
        "value_range": profile.get_range(key).print_(True),
    }


def set_default_profile_setting(params: dict[str, Any]) -> dict[str, Any]:
    gio, glib, profile, schema, _profile_id = _default_profile()
    key, requested = params["key"], params["value"]
    _require_key(profile, key)
    try:
        value = glib.Variant(profile.get_value(key).get_type_string(), requested)
        if value.unpack() != requested or isinstance(value.unpack(), bool) != isinstance(requested, bool):
            raise ValueError("the value would change under native type conversion")
    except (TypeError, ValueError, OverflowError) as exc:
        raise AdapterError(
            "INVALID_ARGUMENT", "value does not match the terminal preference type",
            {"key": key, "value": requested, "detail": str(exc)}, 422,
        ) from exc
    if not profile.set_value(key, value):
        raise AdapterError("SETTING_UNAVAILABLE", "terminal preference is not writable", {"key": key}, 422)
    gio.Settings.sync()
    observed = profile.get_value(key)
    return {
        "profile": "default", "schema": schema, "key": key,
        "expected": value.print_(True), "observed": observed.print_(True),
        "value": observed.unpack(),
    }
