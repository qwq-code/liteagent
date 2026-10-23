import jsonschema

from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS
from vlc_adapter.actions import semantic_preference_values
from vlc_adapter.schema import validate_action_params
from vlc_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from vlc_adapter.verifier import verify_specs


ACTION = "preferences.configure"
PARAMS = {"minimal_interface": True}


def test_order170_minimal_interface_is_one_model_visible_setting() -> None:
    for schema in (
        STRICT_ACTION_PARAM_SCHEMAS[ACTION],
        DIRECT_ACTION_SCHEMAS["vlc"][ACTION],
    ):
        jsonschema.Draft202012Validator(schema).validate(PARAMS)
    validate_action_params(ACTION, PARAMS)
    assert semantic_preference_values(PARAMS) == {"qt-minimal-view": "1"}


def test_order170_rejects_a_second_independent_preference() -> None:
    combined = {"minimal_interface": True, "exit_after_playback": False}
    for schema in (
        STRICT_ACTION_PARAM_SCHEMAS[ACTION],
        DIRECT_ACTION_SCHEMAS["vlc"][ACTION],
    ):
        assert not jsonschema.Draft202012Validator(schema).is_valid(combined)


def test_order170_evaluator_rule_reads_persisted_minimal_view(tmp_path) -> None:
    config = tmp_path / "vlcrc"
    config.write_text("qt-minimal-view=1\n", encoding="utf-8")
    result = verify_specs(
        [{"type": "config", "path": str(config), "values": {"qt-minimal-view": "1"}}],
        {},
    )
    assert result["passed"] is True
