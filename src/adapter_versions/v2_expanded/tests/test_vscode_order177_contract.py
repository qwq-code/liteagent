import jsonschema
import pytest

from integrations.lite_agent.model_client import (
    _normalize_boolean_literals,
    _provider_tools,
)
from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS, build_tools
from vscode_adapter.errors import AdapterError
from vscode_adapter.schema import validate_action_params
from vscode_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


ACTION = "debugging.configure"
def test_order177_accepts_the_requested_single_debug_setting() -> None:
    params = {"focus_editor_on_break": False}
    for schema in (
        STRICT_ACTION_PARAM_SCHEMAS[ACTION],
        DIRECT_ACTION_SCHEMAS["vs_code"][ACTION],
    ):
        jsonschema.Draft202012Validator(schema).validate(params)
    validate_action_params(ACTION, params)


def test_order177_rejects_multiple_independent_debug_settings() -> None:
    params = {"focus_editor_on_break": False, "inline_values": "on"}
    for schema in (
        STRICT_ACTION_PARAM_SCHEMAS[ACTION],
        DIRECT_ACTION_SCHEMAS["vs_code"][ACTION],
    ):
        assert not jsonschema.Draft202012Validator(schema).is_valid(params)
    with pytest.raises(AdapterError, match="exactly one semantic setting"):
        validate_action_params(ACTION, params)


def test_order177_rejects_an_empty_debug_setting_request() -> None:
    with pytest.raises(AdapterError, match="exactly one documented debugging setting"):
        validate_action_params(ACTION, {})


def test_order177_provider_schema_keeps_single_setting_union() -> None:
    tool = next(
        tool
        for tool in build_tools(
            "vs_code",
            [ACTION],
            include_gui=False,
            include_control_tools=False,
            strict_generic=True,
        )
        if tool["function"]["name"] == "adapter__debugging_configure"
    )
    provider_schema = _provider_tools([tool])[0]["function"]["parameters"]
    assert len(provider_schema["oneOf"]) == 6
    setting_fields = {
        field for branch in provider_schema["oneOf"] for field in branch["required"]
    }
    assert setting_fields == {
        "focus_editor_on_break",
        "inline_values",
        "internal_console",
        "open_debug_view",
        "show_breakpoints_in_overview_ruler",
        "show_inline_breakpoint_candidates",
    }
    validator = jsonschema.Draft202012Validator(provider_schema)
    assert validator.is_valid({"focus_editor_on_break": False})
    assert not validator.is_valid({"focus_editor_on_break": False, "inline_values": "on"})


def test_order177_provider_schema_rejects_multiple_settings() -> None:
    tool = next(
        tool
        for tool in build_tools(
            "vs_code",
            [ACTION],
            include_gui=False,
            include_control_tools=False,
            strict_generic=True,
        )
        if tool["function"]["name"] == "adapter__debugging_configure"
    )
    provider_schema = _provider_tools([tool])[0]["function"]["parameters"]
    validator = jsonschema.Draft202012Validator(provider_schema)
    assert validator.is_valid({"focus_editor_on_break": False})
    assert validator.is_valid({"focus_editor_on_break": False, "path": "/tmp/settings.json"})
    assert not validator.is_valid(
        {"focus_editor_on_break": False, "inline_values": "on"}
    )


def test_boolean_literal_normalization_uses_schema_types() -> None:
    schema = {
        "type": "object",
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean"},
                    "path": {"type": "string"},
                },
                "required": ["enabled"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {"label": {"type": "string"}},
                "required": ["label"],
                "additionalProperties": False,
            },
        ],
    }
    assert _normalize_boolean_literals(
        {"enabled": "false", "path": "true"}, schema
    ) == {"enabled": False, "path": "true"}
    assert _normalize_boolean_literals({"label": "false"}, schema) == {
        "label": "false"
    }
    assert _normalize_boolean_literals({"enabled": "yes"}, schema) == {
        "enabled": "yes"
    }
