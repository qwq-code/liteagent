from __future__ import annotations

import jsonschema
import pytest

from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS, build_tools
from os_adapter.errors import AdapterError
from os_adapter.schema import ACTIONS, validate_action_params
from os_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


ACTION = "audio.set_volume"


def _exposed_schema() -> dict:
    tools = build_tools(
        "os",
        [ACTION],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )
    return tools[0]["function"]["parameters"]


def test_audio_volume_contract_is_owned_and_exposed_directly() -> None:
    assert ACTION in ACTIONS
    manifest = STRICT_ACTION_PARAM_SCHEMAS[ACTION]
    direct = DIRECT_ACTION_SCHEMAS["os"][ACTION]

    # The LiteAgent catalog must consume the Adapter-owned contract verbatim.
    assert direct == manifest
    assert manifest["required"] == ["percent"]
    assert set(manifest["properties"]) == {"percent", "sink"}

    exposed = _exposed_schema()
    jsonschema.Draft202012Validator.check_schema(exposed)
    assert set(exposed["properties"]) == {"percent", "sink"}
    assert "params" not in exposed["properties"]
    assert exposed["additionalProperties"] is False
    assert exposed["properties"] == manifest["properties"]


def test_audio_volume_explains_normal_volume_and_optional_amplification() -> None:
    percent = _exposed_schema()["properties"]["percent"]
    assert "100% is full normal volume (0 dB)" in percent["description"]
    assert "over-amplification" in percent["description"]
    assert "explicitly requested" in percent["description"]
    assert percent["maximum"] == 150
    assert "default" not in percent


@pytest.mark.parametrize(
    "arguments",
    [
        {"percent": 0},
        {"percent": 100},
        {"percent": 125},
        {"percent": 150},
        {"percent": 37.5, "sink": "@DEFAULT_SINK@"},
    ],
)
def test_audio_volume_accepts_runtime_scalars_and_boundaries(arguments: dict) -> None:
    assert not list(
        jsonschema.Draft202012Validator(_exposed_schema()).iter_errors(arguments)
    )
    validate_action_params(ACTION, arguments)


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"percent": -0.1},
        {"percent": 150.1},
        {"percent": True},
        {"percent": "100"},
        {"percent": 100, "sink": ""},
        {"percent": 100, "sink": 7},
        {"percent": 100, "unexpected": "do-not-accept"},
    ],
)
def test_audio_volume_rejects_invalid_or_unknown_arguments(arguments: dict) -> None:
    errors = list(
        jsonschema.Draft202012Validator(_exposed_schema()).iter_errors(arguments)
    )
    assert errors
    with pytest.raises(AdapterError):
        validate_action_params(ACTION, arguments)
