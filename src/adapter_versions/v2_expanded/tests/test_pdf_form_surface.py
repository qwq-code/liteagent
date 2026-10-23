from __future__ import annotations

import json
from copy import deepcopy

import jsonschema
import pytest

from integrations.lite_agent.adapter_results import adapter_context_hint
from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.context_projection import compact_hint
from integrations.lite_agent.episode_control import mark_tool_result_for_audit
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools, search_actions
from multi_apps_adapter.actions import MultiAppsActions
from multi_apps_adapter.schema import parse_action_request as parse_multi_apps_request
from os_adapter.errors import AdapterError
from os_adapter.schema import parse_action_request as parse_os_request
from os_adapter.schema import validate_action_params


FORM_ACTIONS = ("pdf.form.inspect", "pdf.form.fill")


def _params(action: str) -> dict:
    params = {"input_path": "/tmp/synthetic blank form.pdf"}
    if action == "pdf.form.inspect":
        params.update(field_offset=7, max_fields=2)
    else:
        params.update(
            output_path="/tmp/synthetic filled form.pdf",
            fields=[
                {"field_name": "panel.item_07", "value": " 0042 "},
                {"field_name": "Résumé", "value": "临时 notes\n第二行"},
                {"field_name": "clear_field", "value": ""},
            ],
            overwrite=False,
        )
    return params


def _function(action: str, forwarded: bool) -> dict:
    if not forwarded:
        tools = build_tools(
            "os",
            [action],
            include_gui=False,
            include_control_tools=False,
            strict_generic=True,
        )
    else:
        tools = constrain_adapter_call_routes(
            build_tools(
                "multi_apps",
                ["adapter.call"],
                include_gui=False,
                include_control_tools=False,
                strict_generic=True,
            ),
            [("os", action)],
        )
    return tools[0]["function"]


@pytest.mark.parametrize("domain", ["os", "multi_apps"])
def test_pdf_form_inspection_and_fill_are_discoverable(domain: str) -> None:
    hits = search_actions(
        domain, "fill PDF form fields", strict_generic=True, limit=6
    )
    actions = {
        hit.get("downstream_action") if domain == "multi_apps" else hit["action"]
        for hit in hits
        if domain != "multi_apps" or hit.get("adapter") == "os"
    }
    assert set(FORM_ACTIONS).issubset(actions)


@pytest.mark.parametrize("action", FORM_ACTIONS)
def test_forwarded_pdf_form_schema_preserves_direct_contract(action: str) -> None:
    direct = _function(action, False)["parameters"]
    forwarded = _function(action, True)["parameters"]
    nested = forwarded["oneOf"][0]["properties"]["payload"]["properties"]["params"]
    assert nested["properties"] == direct["properties"]
    assert nested["required"] == direct["required"]
    assert nested["additionalProperties"] == direct["additionalProperties"]
    params = _params(action)
    jsonschema.validate(params, direct)
    jsonschema.validate(
        {"adapter": "os", "action": action, "payload": {"params": params}},
        forwarded,
    )
    if action == "pdf.form.fill":
        assert "pdf.form.inspect" in str(_function(action, False))
        assert "pdf.form.inspect" in str(_function(action, True))


@pytest.mark.parametrize("action", FORM_ACTIONS)
@pytest.mark.parametrize("forwarded", [False, True])
def test_pdf_form_request_parsing_preserves_model_selected_values(
    action: str, forwarded: bool
) -> None:
    params = _params(action)
    before = deepcopy(params)
    if forwarded:
        outer = parse_multi_apps_request(
            {
                "action": "adapter.call",
                "params": {
                    "adapter": "os",
                    "action": action,
                    "payload": {"params": params},
                },
            }
        )
        adapter, downstream_action, downstream_params, payload = (
            MultiAppsActions._effective_downstream_request(outer.params)
        )
        assert (adapter, downstream_action) == ("os", action)
        assert downstream_params == before
        parsed = parse_os_request(payload)
    else:
        parsed = parse_os_request({"action": action, "params": params})
    assert parsed.params == before
    assert parsed.to_worker_payload()["params"] == before
    assert params == before


@pytest.mark.parametrize("forwarded", [False, True])
def test_pdf_form_nested_value_remains_a_string_contract(forwarded: bool) -> None:
    action = "pdf.form.fill"
    params = _params(action)
    params["fields"][0]["value"] = 42
    arguments = (
        {"adapter": "os", "action": action, "payload": {"params": params}}
        if forwarded
        else params
    )
    validator = jsonschema.Draft202012Validator(_function(action, forwarded)["parameters"])
    assert not validator.is_valid(arguments)
    with pytest.raises(AdapterError):
        validate_action_params(action, params)


@pytest.mark.parametrize(
    "action,field,value",
    [("pdf.form.inspect", "max_fields", 257), ("pdf.form.fill", "fields", [])],
)
def test_pdf_form_bounded_request_contract_is_shared(
    action: str, field: str, value: object
) -> None:
    params = _params(action)
    params[field] = value
    validator = jsonschema.Draft202012Validator(_function(action, False)["parameters"])
    assert not validator.is_valid(params)
    with pytest.raises(AdapterError):
        validate_action_params(action, params)


def _observed_fields(count: int = 128, offset: int = 0) -> list[dict]:
    return [
        {
            "field_name": f"panel.section_{index // 16}.item_{index:03d}",
            "label": f"Entry {index}",
            "field_type": "/Tx",
            "value": None,
            "writable": True,
        }
        for index in range(offset, offset + count)
    ]


def _assert_field_semantics(observed: list[dict], source: list[dict]) -> None:
    assert [field["field_name"] for field in observed] == [
        field["field_name"] for field in source
    ]
    for projected, original in zip(observed, source, strict=True):
        assert projected.get("field_type", "/Tx") == original["field_type"]
        assert projected.get("writable", True) == original["writable"]
        assert projected.get("value") == original["value"]
        if original.get("label") not in ("", original["field_name"]):
            assert projected["label"] == original["label"]
        assert projected.get("max_length") == original.get("max_length")


@pytest.mark.parametrize("forwarded", [False, True])
def test_pdf_form_inspection_keeps_observed_field_names_in_model_messages(
    forwarded: bool,
) -> None:
    fields = _observed_fields()
    result = {
        "input_path": "/tmp/synthetic blank form.pdf",
        "page_count": 8,
        "total_fields": 130,
        "field_offset": 0,
        "next_offset": 128,
        "truncated": True,
        "fields": fields,
    }
    body = {"status": "ok", "result": result}
    domain, action = "os", "pdf.form.inspect"
    if forwarded:
        body = {
            "status": "ok",
            "result": {"adapter": domain, "action": action, "response": body},
        }
        domain, action = "multi_apps", "adapter.call"
    original = deepcopy(body)
    hint = adapter_context_hint(domain, action, body)
    assert isinstance(hint, dict)
    projected = compact_hint(hint, remaining_chars=24_000)
    observed = projected["downstream_context"] if forwarded else projected
    _assert_field_semantics(observed["fields"], fields)

    event = ExecutionEvent(
        step=1,
        timestamp_utc="2026-09-12T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": {}},
        executed=True,
        result={"context_hint": hint},
    )
    state = RuntimeState(
        task_id="synthetic-form-observation",
        domain=domain,
        instruction="Inspect the fields in this PDF form before choosing values.",
        events=[event],
    )
    mark_tool_result_for_audit(state, event)
    messages = AgentProtocolMixin()._messages(state, b"synthetic-screenshot")
    summary = json.loads(messages[2]["content"][0]["text"].split("\n")[1])
    entry = next(item for item in summary if item.get("step") == 1)
    model_hint = entry["result"]["context_hint"]
    observed = model_hint["downstream_context"] if forwarded else model_hint
    _assert_field_semantics(observed["fields"], fields)
    assert observed["total_fields"] == 130
    assert observed["next_offset"] == 128
    assert observed["truncated"] is True
    assert body == original


@pytest.mark.parametrize("forwarded", [False, True])
def test_pdf_form_compact_fields_keep_semantics_with_five_observations(
    forwarded: bool,
) -> None:
    fields = _observed_fields()
    fields[0]["label"] = fields[0]["field_name"]
    fields[1]["label"] = ""
    fields[2]["writable"] = False
    fields[3]["value"] = ""
    fields[4].update(value=" 010\nΩ ", max_length=64)
    fields[5].update(field_type="/Sig", writable=False)
    fields[6]["max_length"] = 0
    body = {
        "status": "ok",
        "result": {
            "input_path": "/tmp/synthetic blank form.pdf",
            "page_count": 8,
            "total_fields": 128,
            "field_offset": 0,
            "next_offset": None,
            "truncated": False,
            "fields": fields,
        },
    }
    domain, action = "os", "pdf.form.inspect"
    if forwarded:
        body = {
            "status": "ok",
            "result": {"adapter": domain, "action": action, "response": body},
        }
        domain, action = "multi_apps", "adapter.call"
    original = deepcopy(body)
    state = RuntimeState(
        task_id="synthetic-form-five-observations",
        domain=domain,
        instruction="Inspect this form before choosing its field values.",
        events=[
            ExecutionEvent(
                step=index + 1,
                timestamp_utc="2026-09-12T00:00:00Z",
                proposed={"kind": "adapter", "action": "filesystem.find"},
                executed=True,
                result={
                    "context_hint": {
                        "matches": [{"path": f"/tmp/synthetic-source-{index}.pdf"}]
                    }
                },
            )
            for index in range(4)
        ],
    )
    event = ExecutionEvent(
        step=5,
        timestamp_utc="2026-09-12T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": {}},
        executed=True,
        result={"context_hint": adapter_context_hint(domain, action, body)},
    )
    state.events.append(event)
    mark_tool_result_for_audit(state, event)
    messages = AgentProtocolMixin()._messages(state, b"synthetic-screenshot")
    summary = json.loads(messages[2]["content"][0]["text"].split("\n")[1])
    entry = next(item for item in summary if item.get("step") == 5)
    hint = entry["result"]["context_hint"]
    observed = hint["downstream_context"] if forwarded else hint

    _assert_field_semantics(observed["fields"], fields)
    assert "label" not in observed["fields"][0]
    assert "label" not in observed["fields"][1]
    assert observed["fields"][3]["value"] == ""
    assert observed["fields"][6]["max_length"] == 0
    assert "omitted field_type means /Tx" in observed["guidance"]
    assert "omitted writable means true" in observed["guidance"]
    assert "omitted value means null" in observed["guidance"]
    assert not observed.get("context_truncated", False)
    assert body == original


def test_crowded_pdf_form_history_keeps_same_offset_recovery_and_smaller_page() -> None:
    state = RuntimeState(
        task_id="synthetic-crowded-form-observation",
        domain="os",
        instruction="Inspect the fields in this PDF form before choosing values.",
        events=[
            ExecutionEvent(
                step=index + 1,
                timestamp_utc="2026-09-12T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "action": "filesystem.find",
                    "arguments": {},
                },
                executed=True,
                result={
                    "context_hint": {
                        "matches": [{"path": f"/tmp/synthetic-source-{index}.pdf"}]
                    }
                },
            )
            for index in range(10)
        ],
    )
    field_offset = 7

    def observe(count: int) -> dict:
        result = {
            "input_path": "/tmp/synthetic blank form.pdf",
            "page_count": 8,
            "total_fields": 137,
            "field_offset": field_offset,
            "next_offset": field_offset + count,
            "truncated": True,
            "fields": _observed_fields(count, field_offset),
        }
        event = ExecutionEvent(
            step=len(state.events) + 1,
            timestamp_utc="2026-09-12T00:00:00Z",
            proposed={
                "kind": "adapter",
                "action": "pdf.form.inspect",
                "arguments": {
                    "input_path": result["input_path"],
                    "field_offset": field_offset,
                    "max_fields": count,
                },
            },
            executed=True,
            result={
                "context_hint": adapter_context_hint(
                    "os", "pdf.form.inspect", {"status": "ok", "result": result}
                )
            },
        )
        state.events.append(event)
        mark_tool_result_for_audit(state, event)
        messages = AgentProtocolMixin()._messages(state, b"synthetic-screenshot")
        summary = json.loads(messages[2]["content"][0]["text"].split("\n")[1])
        entry = next(item for item in summary if item.get("step") == event.step)
        return entry["result"]["context_hint"]

    crowded = observe(128)
    assert crowded["context_truncated"] is True
    assert len(crowded["fields"]) < 128
    assert crowded["field_offset"] == field_offset
    assert "repeat the current field_offset" in crowded["guidance"]
    assert "max_fields (for example 8)" in crowded["guidance"]
    assert "do not jump to next_offset yet" in crowded["guidance"]

    reread = observe(8)
    _assert_field_semantics(reread["fields"], _observed_fields(8, field_offset))
    assert reread["field_offset"] == field_offset
    assert reread["next_offset"] == field_offset + 8
    assert not reread.get("context_truncated", False)
