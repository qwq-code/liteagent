import jsonschema

from desktop_env.evaluators.metrics.vlc import check_play_and_exit
from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS
from vlc_adapter.actions import semantic_preference_values
from vlc_adapter.schema import validate_action_params
from vlc_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


ACTION = "preferences.configure"
PARAMS = {"exit_after_playback": False}


def test_order171_exit_after_playback_is_one_model_visible_setting() -> None:
    for schema in (
        STRICT_ACTION_PARAM_SCHEMAS[ACTION],
        DIRECT_ACTION_SCHEMAS["vlc"][ACTION],
    ):
        jsonschema.Draft202012Validator(schema).validate(PARAMS)
    validate_action_params(ACTION, PARAMS)
    assert semantic_preference_values(PARAMS) == {"play-and-exit": "0"}


def test_order171_rejects_a_second_independent_preference() -> None:
    combined = {"exit_after_playback": False, "minimal_interface": True}
    for schema in (
        STRICT_ACTION_PARAM_SCHEMAS[ACTION],
        DIRECT_ACTION_SCHEMAS["vlc"][ACTION],
    ):
        assert not jsonschema.Draft202012Validator(schema).is_valid(combined)


def test_order171_evaluator_accepts_persistent_false_and_rejects_true(tmp_path) -> None:
    config = tmp_path / "vlcrc"
    config.write_text("play-and-exit=0\n", encoding="utf-8")
    rule = {"expected_play_and_exit": 0}
    assert check_play_and_exit(str(config), rule) == 1
    config.write_text("play-and-exit=1\n", encoding="utf-8")
    assert check_play_and_exit(str(config), rule) == 0
