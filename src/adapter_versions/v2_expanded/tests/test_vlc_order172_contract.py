import jsonschema

from desktop_env.evaluators.metrics.vlc import check_one_instance_when_started_from_file
from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS
from vlc_adapter.actions import semantic_preference_values
from vlc_adapter.schema import validate_action_params
from vlc_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


ACTION = "preferences.configure"
PARAMS = {"allow_multiple_instances": True}


def test_order172_multiple_instances_is_one_model_visible_setting() -> None:
    for schema in (
        STRICT_ACTION_PARAM_SCHEMAS[ACTION],
        DIRECT_ACTION_SCHEMAS["vlc"][ACTION],
    ):
        jsonschema.Draft202012Validator(schema).validate(PARAMS)
    validate_action_params(ACTION, PARAMS)
    assert semantic_preference_values(PARAMS) == {
        "one-instance-when-started-from-file": "0"
    }


def test_order172_rejects_a_second_independent_preference() -> None:
    combined = {"allow_multiple_instances": True, "minimal_interface": True}
    for schema in (
        STRICT_ACTION_PARAM_SCHEMAS[ACTION],
        DIRECT_ACTION_SCHEMAS["vlc"][ACTION],
    ):
        assert not jsonschema.Draft202012Validator(schema).is_valid(combined)


def test_order172_evaluator_accepts_multiple_instances_and_rejects_single(tmp_path) -> None:
    config = tmp_path / "vlcrc"
    config.write_text("one-instance-when-started-from-file=0\n", encoding="utf-8")
    rule = {"expected_one_instance_when_started_from_file": 0}
    assert check_one_instance_when_started_from_file(str(config), rule) == 1
    config.write_text("one-instance-when-started-from-file=1\n", encoding="utf-8")
    assert check_one_instance_when_started_from_file(str(config), rule) == 0
