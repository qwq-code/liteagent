from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from openai.types.chat import ChatCompletion

from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.model_client import (
    StructuredToolModelClient,
    StructuredToolProtocolError,
    _actionable_validation_errors,
    _schema_validation_hints,
)
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.state_model import RuntimeState
from integrations.lite_agent.tool_catalog import build_tools


@pytest.mark.parametrize("as_matrix", [False, True])
def test_formatted_part_error_keeps_its_actual_field_path(as_matrix: bool) -> None:
    schema = build_tools(
        "libreoffice_calc", ["range.write"], include_gui=False, strict_generic=True
    )[0]["function"]["parameters"]
    cells = [
        {
            "kind": "formatted_text",
            "value": {
                "parts": [
                    {
                        "text": "private-synthetic-label",
                        "cell": "G4",
                        "decimal_places": 3,
                    }
                ]
            },
        }
    ]
    arguments = {
        "sheet": "Measures",
        "range": "H4",
        "values": [cells] if as_matrix else cells,
    }
    errors = list(Draft202012Validator(schema).iter_errors(arguments))
    assert errors
    hints = _schema_validation_hints(_actionable_validation_errors(errors))
    path = "values.0.0.value.parts.0" if as_matrix else "values.0.value.parts.0"
    assert hints == (f"{path}: provide one allowed field set: text OR cell",)
    assert "private-synthetic-label" not in " ".join(hints)


def test_uniqueness_error_explains_the_required_correction() -> None:
    schema = {
        "type": "object",
        "properties": {"cells": {"type": "array", "uniqueItems": True}},
    }
    errors = list(
        Draft202012Validator(schema).iter_errors(
            {"cells": ["private-synthetic-label", "private-synthetic-label"]}
        )
    )
    hints = _schema_validation_hints(errors)
    assert hints == ("cells: remove duplicate items; include each item only once",)
    assert "private-synthetic-label" not in " ".join(hints)


def test_excluded_argument_combination_explains_recovery_without_echoing_values():
    schema = {"not": {"properties": {"roots": {"const": ["private-synthetic-label"]}}, "required": ["roots"]}}
    errors = list(Draft202012Validator(schema).iter_errors({"roots": ["private-synthetic-label"]}))
    hints = _schema_validation_hints(errors)
    assert "combination is excluded" in hints[0]
    assert "change" in hints[0]
    assert "private-synthetic-label" not in " ".join(hints)


def test_ambiguous_enum_branches_do_not_invent_required_fields() -> None:
    schema = {
        "oneOf": [
            {
                "type": "object",
                "properties": {"operation": {"enum": ["package", "publish"]}},
                "required": ["left"],
            },
            {
                "type": "object",
                "properties": {"operation": {"enum": ["package", "extract"]}},
                "required": ["right"],
            },
        ]
    }
    errors = list(Draft202012Validator(schema).iter_errors({"operation": "package"}))
    hints = _schema_validation_hints(_actionable_validation_errors(errors))
    assert hints == ("<root>: must match one allowed schema branch",)


@pytest.mark.parametrize("case", ["empty_format", "extra_root_field"])
def test_forwarded_schema_feedback_reaches_retry_with_full_schema(case) -> None:
    tools = constrain_adapter_call_routes(
        build_tools(
            "multi_apps",
            ["adapter.call"],
            include_gui=False,
            strict_generic=True,
        ),
        [("libreoffice_writer", "text.find")],
    )
    original_tools = copy.deepcopy(tools)
    arguments = {
        "adapter": "libreoffice_writer",
        "action": "text.find",
        "payload": {
            "params": {
                "literal": "private-synthetic-label",
                "case_sensitive": False,
                "max_results": 3,
                "format": {},
            }
        },
    }
    corrected = copy.deepcopy(arguments)
    del corrected["payload"]["params"]["format"]
    hint = "payload.params.format: must contain at least 1 field(s)"
    if case == "extra_root_field":
        del arguments["payload"]["params"]["format"]
        arguments["timeout_ms"] = 5000
        hint = (
            "<root>: remove fields not declared at this level; declared fields: "
            "['adapter', 'action', 'payload']"
        )
    original_arguments = copy.deepcopy(arguments)
    raw_calls = [json.dumps(call) for call in (arguments, corrected)]
    responses = iter(
        [
            ChatCompletion.model_validate(
                {
                    "id": f"response-{index}",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "synthetic-model",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": f"call-{index}",
                                        "type": "function",
                                        "function": {
                                            "name": "adapter__adapter_call",
                                            "arguments": raw,
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                }
            )
            for index, raw in enumerate(raw_calls)
        ]
    )
    requests = []

    def complete(**request):
        requests.append(copy.deepcopy(request))
        return next(responses)

    client = StructuredToolModelClient(
        base_url="http://synthetic",
        api_key="unused",
        request_timeout_seconds=1,
        client=SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=complete),
            )
        ),
    )
    state = RuntimeState(
        task_id="synthetic-empty-format-feedback",
        domain="multi_apps",
        instruction="Find the supplied label in the Writer document.",
    )
    options = {
        "model": "synthetic-model",
        "tools": tools,
        "temperature": 0.0,
        "output_token_budget": 1024,
        "enable_thinking": False,
    }
    protocol = AgentProtocolMixin()
    protocol.config = SimpleNamespace(include_gui=False)
    with pytest.raises(StructuredToolProtocolError) as raised:
        client.propose(
            messages=protocol._messages(state, b"png"),
            **options,
        )
    error = raised.value
    assert error.schema_hints == (hint,)
    assert error.missing_fields == ()
    assert (
        error.response_snapshot["message"]["tool_calls"][0]["function"]["arguments"]
        == raw_calls[0]
    )
    retry_messages = protocol._messages(
        state,
        b"png",
        protocol_recovery=True,
        protocol_error=error.trace_record(),
    )
    proposal = client.propose(messages=retry_messages, **options)

    assert hint in requests[1]["messages"][0]["content"]
    assert "private-synthetic-label" not in requests[1]["messages"][0]["content"]
    assert requests[1]["messages"][1]["content"].endswith(state.instruction)
    from integrations.lite_agent.model_client import _provider_tools
    assert requests[0]["tools"] == requests[1]["tools"] == _provider_tools(original_tools)
    assert proposal["structured_call_validated"] is True
    assert proposal["arguments_raw"] == raw_calls[1]
    assert json.loads(proposal["arguments_raw"]) == corrected
    assert arguments == original_arguments
    assert tools == original_tools
