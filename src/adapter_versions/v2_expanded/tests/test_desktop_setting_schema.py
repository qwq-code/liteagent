from __future__ import annotations

import jsonschema
import pytest

from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS, build_tools
from os_adapter.actions import OSActions
from os_adapter.errors import AdapterError
from os_adapter.schema import validate_action_params
from os_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from os_adapter.verifier import verify_specs
from os_adapter.worker import _default_specs


ACTION = "desktop.set_setting"
BASE_ARGUMENTS = {"schema": "org.example.Settings", "key": "sample"}


def _exposed_schema() -> dict:
    tools = build_tools(
        "os",
        [ACTION],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )
    return tools[0]["function"]["parameters"]


def test_desktop_setting_contract_is_owned_by_os_manifest() -> None:
    manifest = STRICT_ACTION_PARAM_SCHEMAS[ACTION]
    direct = DIRECT_ACTION_SCHEMAS["os"][ACTION]

    # The LiteAgent catalog must consume the Adapter-owned contract verbatim.
    assert direct == manifest
    value_schema = manifest["properties"]["value"]
    assert "oneOf" not in value_schema
    assert value_schema["anyOf"] == [
        {"type": "string"},
        {"type": "boolean"},
        {"type": "number"},
    ]

    exposed = _exposed_schema()
    jsonschema.Draft202012Validator.check_schema(exposed)
    assert exposed["properties"]["value"] == value_schema


@pytest.mark.parametrize("value", [132, 132.0, 1.25, "true", True])
def test_desktop_setting_accepts_scalar_values_without_numeric_overlap(value) -> None:
    arguments = {**BASE_ARGUMENTS, "value": value}

    # Both the model-visible boundary and the Adapter's runtime contract agree.
    assert not list(
        jsonschema.Draft202012Validator(_exposed_schema()).iter_errors(arguments)
    )
    validate_action_params(ACTION, arguments)


@pytest.mark.parametrize("value", [None, [], {}, ["a", "b"]])
def test_desktop_setting_rejects_non_scalar_values(value) -> None:
    arguments = {**BASE_ARGUMENTS, "value": value}
    errors = list(
        jsonschema.Draft202012Validator(_exposed_schema()).iter_errors(arguments)
    )
    assert errors
    with pytest.raises(AdapterError, match="value must be a scalar"):
        validate_action_params(ACTION, arguments)


@pytest.mark.parametrize(
    "params",
    [{"magnifier_factor": 1.25}, {"text_factor": 1.2, "magnifier_factor": 1.25}],
)
def test_desktop_accessibility_scale_rejects_composite_magnifier(params) -> None:
    with pytest.raises(AdapterError, match="magnifier_factor is unsupported.*desktop.set_setting"):
        validate_action_params("desktop.set_accessibility_scale", params)

    with pytest.raises(jsonschema.exceptions.ValidationError):
        jsonschema.Draft202012Validator(
            STRICT_ACTION_PARAM_SCHEMAS["desktop.set_accessibility_scale"]
        ).validate(params)


def test_desktop_accessibility_scale_writes_only_text_factor() -> None:
    class Runner:
        def __init__(self):
            self.calls = []
            self.observed = "1.6000000000000001\n"

        def run(self, argv, **kwargs):
            self.calls.append(argv)
            return {"stdout": self.observed if argv[1] == "get" else "", "returncode": 0}

    params = {"text_factor": 1.6}
    validate_action_params("desktop.set_accessibility_scale", params)
    jsonschema.validate(params, STRICT_ACTION_PARAM_SCHEMAS["desktop.set_accessibility_scale"])
    runner = Runner()
    result = OSActions(runner=runner).set_accessibility_scale(params, 5)
    assert runner.calls == [
        ["gsettings", "set", "org.gnome.desktop.interface", "text-scaling-factor", "1.6"],
        ["gsettings", "get", "org.gnome.desktop.interface", "text-scaling-factor"],
    ]
    specs = _default_specs("desktop.set_accessibility_scale", params, result)
    assert verify_specs(specs, result, runner)["passed"] is True
    runner.observed = "1.7\n"
    assert verify_specs(specs, result, runner)["passed"] is False


def test_desktop_dim_inactive_requires_exactly_one_setting() -> None:
    params = {"idle_delay": 30, "idle_dim": False}
    with pytest.raises(
        AdapterError, match="exactly one of idle_delay or idle_dim"
    ):
        validate_action_params("desktop.set_dim_inactive", params)

    with pytest.raises(jsonschema.exceptions.ValidationError):
        jsonschema.Draft202012Validator(
            STRICT_ACTION_PARAM_SCHEMAS["desktop.set_dim_inactive"]
        ).validate(params)


def test_desktop_dim_inactive_schema_builds_for_liteagent() -> None:
    tools = build_tools(
        "os",
        ["desktop.set_dim_inactive"],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )
    exposed = tools[0]["function"]["parameters"]

    assert exposed["required"] == []
    jsonschema.Draft202012Validator.check_schema(exposed)
    assert exposed["oneOf"] == STRICT_ACTION_PARAM_SCHEMAS[
        "desktop.set_dim_inactive"
    ]["oneOf"]


def test_desktop_dim_inactive_updates_only_selected_setting() -> None:
    class Runner:
        def __init__(self):
            self.calls = []

        def run(self, argv, **kwargs):
            self.calls.append(argv)
            if argv[1] == "get":
                return {"stdout": "false\n", "returncode": 0}
            return {"stdout": "", "returncode": 0}

    runner = Runner()
    result = OSActions(runner=runner).set_dim_inactive({"idle_dim": False}, 5)

    assert runner.calls == [
        [
            "gsettings",
            "set",
            "org.gnome.settings-daemon.plugins.power",
            "idle-dim",
            "false",
        ],
        [
            "gsettings",
            "get",
            "org.gnome.settings-daemon.plugins.power",
            "idle-dim",
        ],
    ]
    assert result == {
        "settings": [
            {
                "schema": "org.gnome.settings-daemon.plugins.power",
                "key": "idle-dim",
                "expected": "false",
                "observed": "false",
            }
        ]
    }


def test_desktop_setting_explains_instance_paths_and_key_discovery() -> None:
    exposed = _exposed_schema()["properties"]

    assert "SCHEMA:/instance/path/" in exposed["schema"]["description"]
    assert "not a filesystem path" in exposed["schema"]["description"]
    assert "gsettings list-keys SCHEMA[:PATH]" in exposed["key"]["description"]
    assert "different schema" in exposed["key"]["description"]


@pytest.mark.parametrize(
    "schema",
    ["org.example.Settings", "org.example.Profile:/org/example/profiles/observed/"],
)
def test_desktop_setting_preserves_selected_schema_and_instance_path(schema) -> None:
    class Runner:
        def __init__(self):
            self.calls = []

        def run(self, argv, **kwargs):
            self.calls.append(argv)
            return {"stdout": "1.25\n", "returncode": 0}

    arguments = {"schema": schema, "key": "sample-scale", "value": 1.25}
    jsonschema.validate(arguments, _exposed_schema())
    validate_action_params(ACTION, arguments)
    runner = Runner()

    result = OSActions(runner=runner).set_setting(arguments, 5)

    assert runner.calls == [
        ["gsettings", "set", schema, "sample-scale", "1.25"],
        ["gsettings", "get", schema, "sample-scale"],
    ]
    assert result == {
        "schema": schema,
        "key": "sample-scale",
        "expected": "1.25",
        "observed": "1.25",
    }
