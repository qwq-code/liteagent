import jsonschema
import pytest
from pathlib import Path

from integrations.lite_agent.instruction_semantics import instruction_required_actions
from integrations.lite_agent.model_client import _provider_tools
from integrations.lite_agent.tool_surface import ToolSurfaceMixin
from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS
from vlc_adapter.actions import semantic_preference_values
from vlc_adapter.errors import AdapterError
from vlc_adapter.schema import validate_action_params
from vlc_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


ACTION = "preferences.configure"


ORDER_167_STYLE_INSTRUCTION = (
    "A music video is already running in VLC. Change the setting so I can "
    "pause/start it using a keyboard shortcut while reading a PDF."
)


def test_existing_playback_does_not_force_media_discovery_for_preference_task() -> None:
    assert instruction_required_actions(
        "vlc", ORDER_167_STYLE_INSTRUCTION, strict_generic=True
    ) == [ACTION]


def test_preference_routing_selects_the_single_keyboard_setting_field() -> None:
    assert ToolSurfaceMixin._vlc_preference_field(ORDER_167_STYLE_INSTRUCTION) == (
        "global_play_pause_hotkey"
    )


def test_explicit_playback_request_keeps_discovery_and_open_actions() -> None:
    assert instruction_required_actions(
        "vlc", "Play the music file from the Desktop", strict_generic=True
    )[:2] == ["playback.find_local", "playback.open"]


def test_preference_schema_rejects_multiple_independent_settings() -> None:
    params = {
        "maximum_volume_percent": 200,
        "volume_slider_color": "#101010",
    }
    for schema in (
        STRICT_ACTION_PARAM_SCHEMAS[ACTION],
        DIRECT_ACTION_SCHEMAS["vlc"][ACTION],
    ):
        assert not jsonschema.Draft202012Validator(schema).is_valid(params)


def test_provider_surface_preserves_single_preference_constraint() -> None:
    tool = {
        "type": "function",
        "function": {
            "name": "configure",
            "parameters": STRICT_ACTION_PARAM_SCHEMAS[ACTION],
        },
    }
    provider_schema = _provider_tools([tool])[0]["function"]["parameters"]
    assert "oneOf" in provider_schema
    assert not jsonschema.Draft202012Validator(provider_schema).is_valid({"minimal_interface": True, "maximum_volume_percent": 200})
    assert set(provider_schema["properties"]) >= {"global_play_pause_hotkey", "minimal_interface"}


def test_preference_runtime_rejects_multiple_independent_settings() -> None:
    with pytest.raises(AdapterError, match="exactly one semantic setting"):
        validate_action_params(
            ACTION,
            {"global_play_pause_hotkey": "Media Play Pause", "maximum_volume_percent": 200},
        )


def test_recording_location_remains_model_selectable_and_resolves_in_adapter() -> None:
    instruction = "Store VLC recordings in a standard user folder."
    assert ToolSurfaceMixin._vlc_preference_field(instruction) is None
    params = {"recording_location": "videos"}
    for schema in (
        STRICT_ACTION_PARAM_SCHEMAS[ACTION],
        DIRECT_ACTION_SCHEMAS["vlc"][ACTION],
    ):
        assert jsonschema.Draft202012Validator(schema).is_valid(params)
        assert jsonschema.Draft202012Validator(schema).is_valid(
            {"recording_directory": "/srv/media/captures"}
        )
        assert not jsonschema.Draft202012Validator(schema).is_valid(
            {"recording_directory": "/srv/media/captures", **params}
        )
    validate_action_params(ACTION, params)
    assert semantic_preference_values(params, home=Path("/home/example")) == {
        "input-record-path": "/home/example/Videos"
    }


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"global_play_pause_hotkey": "Media Play Pause"}, {"global-key-play-pause": "Media Play Pause"}),
        ({"maximum_volume_percent": 200}, {"qt-max-volume": "200"}),
        ({"volume_slider_color": "#101010"}, {"qt-slider-colours": "16;16;16;16;16;16;16;16;16;16;16;16"}),
    ],
)
def test_each_assigned_preference_maps_to_one_vlc_key(params, expected) -> None:
    assert semantic_preference_values(params) == expected
