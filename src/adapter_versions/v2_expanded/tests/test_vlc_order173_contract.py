import jsonschema

from integrations.lite_agent.instruction_semantics import instruction_required_actions
from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS
from vlc_adapter.actions import semantic_preference_values
from vlc_adapter.schema import validate_action_params
from vlc_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from vlc_adapter.verifier import verify_specs


ACTION = "preferences.configure"
PARAMS = {"show_background_cone": False}


def test_order173_routes_to_the_single_cone_preference() -> None:
    instruction = "Disable the cone icon in VLC's splash screen."
    assert instruction_required_actions("vlc", instruction, strict_generic=True) == [ACTION]
    for schema in (
        STRICT_ACTION_PARAM_SCHEMAS[ACTION],
        DIRECT_ACTION_SCHEMAS["vlc"][ACTION],
    ):
        jsonschema.Draft202012Validator(schema).validate(PARAMS)
    validate_action_params(ACTION, PARAMS)
    assert semantic_preference_values(PARAMS) == {"qt-bgcone": "0"}


def test_order173_rejects_a_compound_preference_request() -> None:
    params = {"show_background_cone": False, "minimal_interface": True}
    for schema in (
        STRICT_ACTION_PARAM_SCHEMAS[ACTION],
        DIRECT_ACTION_SCHEMAS["vlc"][ACTION],
    ):
        assert not jsonschema.Draft202012Validator(schema).is_valid(params)


def test_order173_verification_reads_the_original_evaluator_key(tmp_path) -> None:
    config = tmp_path / "vlcrc"
    config.write_text("qt-bgcone=0\n", encoding="utf-8")
    result = verify_specs(
        [{"type": "config", "path": str(config), "values": {"qt-bgcone": "0"}}],
        {},
    )
    assert result["passed"] is True
