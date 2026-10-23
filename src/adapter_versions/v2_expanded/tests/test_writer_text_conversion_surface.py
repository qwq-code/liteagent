from copy import deepcopy
from types import SimpleNamespace

import jsonschema
import pytest

from integrations.lite_agent.adapter_results import adapter_context_hint
from integrations.lite_agent.agent import LiteAgent
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.state_model import RuntimeState
from integrations.lite_agent.tool_catalog import build_tools
from writer_adapter.errors import AdapterError
from writer_adapter.schema import validate_action_params


@pytest.mark.parametrize("forwarded", [False, True])
def test_conversion_exposes_explicit_range_and_preserves_arguments(forwarded):
    if forwarded:
        tool = constrain_adapter_call_routes(
            build_tools("multi_apps", ["adapter.call"], include_gui=False),
            [("libreoffice_writer", "table.convert_text")],
        )[0]
        schema = tool["function"]["parameters"]["oneOf"][0]["properties"]["payload"][
            "properties"
        ]["params"]
    else:
        schema = build_tools(
            "libreoffice_writer", ["table.convert_text"],
            include_control_tools=False, include_gui=False,
        )[0]["function"]["parameters"]
    args = {"start_index": 2, "end_index": 6, "delimiter": ";"}
    original = deepcopy(args)
    jsonschema.validate(args, schema)
    validate_action_params("table.convert_text", args)
    assert args == original
    assert set(schema["required"]) == set(args)

    invalid = args | {"rows": [["model-retyped content"]]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)
    with pytest.raises(AdapterError):
        validate_action_params("table.convert_text", invalid)


@pytest.mark.parametrize("delimiter", ["\x00", "\U0001f4a0"])
def test_native_single_code_unit_delimiter_limit_is_visible(delimiter):
    schema = build_tools(
        "libreoffice_writer", ["table.convert_text"],
        include_control_tools=False, include_gui=False,
    )[0]["function"]["parameters"]
    args = {"start_index": 1, "end_index": 2, "delimiter": delimiter}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(args, schema)
    with pytest.raises(AdapterError):
        validate_action_params("table.convert_text", args)


@pytest.mark.parametrize("instruction", [
    "Convert the comma separated text to a table.",
    "Turn these semicolon-delimited paragraphs into a table.",
    "Convert the tab separated text into a table without retyping it.",
])
def test_conversion_reaches_actual_initial_tool_surface(instruction):
    agent = object.__new__(LiteAgent)
    agent.config = SimpleNamespace(top_k_actions=7)
    state = RuntimeState(
        task_id="synthetic-conversion", domain="libreoffice_writer",
        instruction=instruction,
    )
    actions = agent.selected_actions(state)
    tools = build_tools("libreoffice_writer", actions, include_gui=True)
    names = {tool["function"]["name"] for tool in tools}
    assert "adapter__table_convert_text" in names
    assert "adapter__table_read" in names


def test_conversion_receipt_preserves_selected_scope_and_native_readback():
    result = {
        "name": "Observed table", "rows": 3, "columns": 2,
        "start_index": 2, "end_index": 4, "delimiter": "\t",
        "source_text_char_count": 57, "text_preserved": True, "saved": True,
    }
    body = {"result": result, "verification": {"passed": True}}
    original = deepcopy(body)
    hint = adapter_context_hint("libreoffice_writer", "table.convert_text", body)
    assert hint == result | {"verification_passed": True}
    assert body == original
