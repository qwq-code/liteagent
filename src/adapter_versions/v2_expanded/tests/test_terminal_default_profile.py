from __future__ import annotations

from copy import deepcopy
import sys
from types import SimpleNamespace

import jsonschema
import pytest

from integrations.lite_agent.completion_policy import action_is_read_only
from integrations.lite_agent.tool_catalog import build_tools, search_actions
from os_adapter import terminal_profile, worker
from os_adapter.actions import OSActions
from os_adapter.errors import AdapterError
from os_adapter.schema import ACTIONS, validate_action_params


INSPECT = "terminal.default_profile.inspect"
SET = "terminal.default_profile.set_setting"


class Variant:
    def __init__(self, signature, value):
        self.signature = signature
        self.value = int(value) if signature == "i" else value

    def unpack(self):
        return self.value

    def get_type_string(self):
        return self.signature

    def print_(self, annotate):
        if isinstance(self.value, bool):
            return str(self.value).lower()
        return repr(self.value)


@pytest.fixture
def profile_backend(monkeypatch):
    values = {
        "default-size-columns": Variant("i", 80),
        "default-size-rows": Variant("i", 24),
        "scrollback-lines": Variant("i", 1000),
        "scrollback-unlimited": Variant("b", False),
        "font": Variant("s", "Monospace 11"),
    }
    writes, syncs = [], []

    def write(key, value):
        writes.append((key, value.unpack()))
        values[key] = value
        return True

    profile = SimpleNamespace(
        list_keys=lambda: list(values), get_value=values.__getitem__,
        get_range=lambda key: Variant("s", values[key].get_type_string()), set_value=write,
    )
    native_schema = "org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:sample-profile/"
    gio = SimpleNamespace(Settings=SimpleNamespace(sync=lambda: syncs.append(True)))
    monkeypatch.setattr(
        terminal_profile, "_default_profile",
        lambda: (gio, SimpleNamespace(Variant=Variant), profile, native_schema, "'sample-profile'"),
    )

    class Runner:
        def run(self, argv, **kwargs):
            assert argv[:2] == ["gsettings", "get"]
            observed = "'sample-profile'" if argv[2].endswith("ProfilesList") else values[argv[3]].print_(True)
            return {"stdout": observed, "returncode": 0}

    monkeypatch.setattr(worker, "OSActions", lambda: OSActions(runner=Runner()))
    return values, writes, syncs, profile


def exposed_schema(action):
    return build_tools("os", [action], include_gui=False, include_control_tools=False, strict_generic=True)[0]["function"]["parameters"]


@pytest.mark.parametrize("key", [None, "default-size-columns", "font"])
def test_inspect_is_read_only_and_uses_existing_verification(profile_backend, key):
    params = {} if key is None else {"key": key}
    jsonschema.validate(params, exposed_schema(INSPECT))
    validate_action_params(INSPECT, params)
    response = worker.execute({"action": INSPECT, "params": params})
    values, writes, syncs, _profile = profile_backend
    assert response["verification"]["passed"] is True
    assert action_is_read_only(INSPECT)
    assert not writes and not syncs
    if key:
        assert response["result"]["value"] == values[key].unpack()
    else:
        assert response["result"]["keys"] == sorted(values)


@pytest.mark.parametrize("key,value", [
    ("default-size-columns", 92), ("default-size-rows", 31),
    ("scrollback-lines", 4321), ("scrollback-unlimited", True), ("font", "Monospace 14"),
])
def test_single_preference_write_preserves_other_values(profile_backend, key, value):
    values, writes, syncs, _profile = profile_backend
    before = {key: native.unpack() for key, native in values.items()}
    params = {"key": key, "value": value}
    original = deepcopy(params)
    jsonschema.validate(params, exposed_schema(SET))
    validate_action_params(SET, params)
    response = worker.execute({"action": SET, "params": params})
    assert response["verification"]["passed"] is True
    assert response["result"]["value"] == value
    assert {key: native.unpack() for key, native in values.items()} == {**before, key: value}
    assert writes == [(key, value)] and syncs == [True]
    assert params == original
    assert not action_is_read_only(SET)


def test_native_type_error_does_not_mutate(profile_backend):
    with pytest.raises(AdapterError, match="does not match"):
        worker.execute({"action": SET, "params": {"key": "default-size-rows", "value": 2.5}})
    assert profile_backend[1] == []


def test_missing_key_returns_available_keys(profile_backend):
    with pytest.raises(AdapterError) as caught:
        worker.execute({"action": SET, "params": {"key": "missing-preference", "value": 3}})
    assert caught.value.details["key"] == "missing-preference"
    assert "scrollback-lines" in caught.value.details["available_keys"]
    assert profile_backend[1] == []


def test_existing_readback_rejects_a_setting_that_did_not_persist(profile_backend):
    profile_backend[3].set_value = lambda key, value: True
    with pytest.raises(AdapterError, match="operation verification failed"):
        worker.execute({"action": SET, "params": {"key": "default-size-rows", "value": 31}})


@pytest.mark.parametrize("identifier", ["profile-sun", "profile-moon"])
def test_native_profile_resolution_uses_current_registry_value(monkeypatch, identifier):
    registry = SimpleNamespace(get_value=lambda key: Variant("s", identifier))
    resolved = []
    profile = object()

    def resolve(schema, path):
        resolved.append((schema, path))
        return profile

    gio = SimpleNamespace(Settings=SimpleNamespace(new=lambda schema: registry, new_with_path=resolve))
    repository = SimpleNamespace(Gio=gio, GLib=SimpleNamespace())
    monkeypatch.setitem(sys.modules, "gi", SimpleNamespace(repository=repository))
    monkeypatch.setitem(sys.modules, "gi.repository", repository)

    result = terminal_profile._default_profile()

    assert result[2] is profile
    assert resolved == [("org.gnome.Terminal.Legacy.Profile", f"/org/gnome/terminal/legacy/profiles:/:{identifier}/")]
    assert result[4] == repr(identifier)


@pytest.mark.parametrize("query", ["terminal permanent default size", "GNOME terminal font preferences"])
def test_catalog_discovers_owning_atomic_actions(query):
    actions = {item["action"] for item in search_actions("os", query, limit=7, strict_generic=True)}
    assert {INSPECT, SET}.issubset(actions)
    assert {INSPECT, SET}.issubset(ACTIONS)
    assert "terminal.configure_size" not in ACTIONS


def test_setting_usage_distinguishes_persistence_from_new_window_behavior():
    tool = build_tools("os", [SET], include_gui=False, include_control_tools=False, strict_generic=True)[0]
    description = tool["function"]["description"]
    assert "Verify startup preferences in a new terminal" in description
    assert "terminal.launch" in description
    assert "does not inspect window behavior" in description
    assert "Do not supply a geometry override" in description
