from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace

import jsonschema
import pytest

from integrations.lite_agent.adapter_results import adapter_context_hint
from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.context_projection import compact_execution_summary_for_model
from integrations.lite_agent.episode_control import mark_tool_result_for_audit
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools, search_actions
from multi_apps_adapter.actions import MultiAppsActions
from multi_apps_adapter.schema import parse_action_request as parse_multi_apps_request
from os_adapter import worker
from os_adapter.errors import AdapterError
from os_adapter.schema import parse_action_request as parse_os_request


ACTION = "pdf.tables.inspect"


def _params() -> dict:
    return {
        "input_path": "/tmp/synthetic table Ω.pdf",
        "page": 2,
        "table_index": 1,
        "row_offset": 7,
        "max_rows": 4,
    }


def _function(forwarded: bool) -> dict:
    tools = build_tools(
        "multi_apps" if forwarded else "os",
        ["adapter.call" if forwarded else ACTION],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )
    if forwarded:
        tools = constrain_adapter_call_routes(tools, [("os", ACTION)])
    return tools[0]["function"]


@pytest.mark.parametrize("domain", ["os", "multi_apps"])
@pytest.mark.parametrize("query", ["read PDF table rows columns", "merged table headers"])
def test_pdf_table_inspection_is_discoverable(domain: str, query: str) -> None:
    hits = search_actions(domain, query, strict_generic=True, limit=6)
    assert any(
        hit.get("downstream_action") == ACTION and hit.get("adapter") == "os"
        if domain == "multi_apps"
        else hit["action"] == ACTION
        for hit in hits
    )


@pytest.mark.parametrize("forwarded", [False, True])
def test_pdf_table_contract_preserves_model_selected_parameters(forwarded: bool) -> None:
    params = _params()
    original = deepcopy(params)
    direct = _function(False)["parameters"]
    assert direct["required"] == ["input_path"]
    assert direct["properties"]["max_rows"]["maximum"] == 100
    jsonschema.validate(params, direct)
    if forwarded:
        schema = _function(True)["parameters"]
        nested = schema["oneOf"][0]["properties"]["payload"]["properties"]["params"]
        assert nested["properties"] == direct["properties"]
        assert nested["required"] == direct["required"]
        assert nested["additionalProperties"] == direct["additionalProperties"]
        arguments = {"adapter": "os", "action": ACTION, "payload": {"params": params}}
        jsonschema.validate(arguments, schema)
        outer = parse_multi_apps_request({"action": "adapter.call", "params": arguments})
        adapter, action, downstream_params, payload = (
            MultiAppsActions._effective_downstream_request(outer.params)
        )
        assert (adapter, action) == ("os", ACTION)
        assert downstream_params == original
        request = parse_os_request(payload)
    else:
        request = parse_os_request({"action": ACTION, "params": params})
    assert request.params == original
    assert request.to_worker_payload()["params"] == original
    assert params == original


def test_pdf_table_worker_default_verification_checks_actual_input_file(
    tmp_path, monkeypatch,
) -> None:
    source = _result()
    source["input_path"] = str(tmp_path / "missing.pdf")
    monkeypatch.setattr(
        worker,
        "OSActions",
        lambda: SimpleNamespace(dispatch=lambda *_args: deepcopy(source), runner=None),
    )
    request = parse_os_request(
        {"action": ACTION, "params": {"input_path": source["input_path"]}},
    )
    with pytest.raises(AdapterError) as caught:
        worker.execute(request.to_worker_payload())
    assert caught.value.code == "VERIFICATION_FAILED"
    verification = caught.value.details
    assert verification["passed"] is False
    assert len(verification["checks"]) == 1
    check = verification["checks"][0]
    assert check["type"] == "path" and check["passed"] is False
    assert check["observed"]["path"] == source["input_path"]
    assert check["observed"]["exists"] is False


def _result() -> dict:
    return {
        "input_path": _params()["input_path"],
        "page_count": 3,
        "page": 2,
        "table_count": 2,
        "table_index": 1,
        "row_count": 18,
        "column_count": 4,
        "row_offset": 7,
        "next_row_offset": 11,
        "truncated": True,
        "rows": [
            ["Group Ω", None, " 03 ", ""],
            ["Item A", "12", "", "first\nsecond"],
            [None, "14", None, ""],
            ["Item B", "", "0", "note"],
        ],
        "merged_cells": [
            {"row": 7, "column": 0, "row_span": 1, "column_span": 2},
            {"row": 8, "column": 0, "row_span": 2, "column_span": 1},
        ],
    }


def _state(result: dict, forwarded: bool) -> RuntimeState:
    body = {"status": "ok", "result": result}
    domain, action = "os", ACTION
    arguments = _params()
    if forwarded:
        body = {
            "status": "ok",
            "result": {"adapter": domain, "action": action, "response": body},
        }
        arguments = {"adapter": domain, "action": action, "payload": {"params": arguments}}
        domain, action = "multi_apps", "adapter.call"
    event = ExecutionEvent(
        step=1,
        timestamp_utc="2026-09-12T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": arguments},
        executed=True,
        result={"context_hint": adapter_context_hint(domain, action, body)},
    )
    state = RuntimeState(
        task_id="synthetic-table-observation",
        domain=domain,
        instruction="Read the table, including its merged headers and empty cells.",
        events=[event],
    )
    mark_tool_result_for_audit(state, event)
    return state


def _assert_position_metadata(observed: dict, source: dict) -> None:
    for key in (
        "input_path", "page_count", "page", "table_count", "table_index",
        "row_count", "column_count", "row_offset", "next_row_offset", "truncated",
    ):
        assert observed[key] == source[key]
    assert observed["merged_cells"] == [[7, 0, 1, 2], [8, 0, 2, 1]]
    assert "row_span" in observed["guidance"]
    assert "column_span" in observed["guidance"]


@pytest.mark.parametrize("forwarded", [False, True])
@pytest.mark.parametrize("recovery", [False, True])
def test_pdf_table_positions_survive_actual_model_messages(
    forwarded: bool, recovery: bool,
) -> None:
    source = _result()
    original = deepcopy(source)
    state = _state(source, forwarded)
    messages = AgentProtocolMixin()._messages(
        state, b"synthetic-screenshot", execution_recovery=recovery,
    )
    summary = json.loads(messages[2]["content"][0]["text"].split("\n")[1])
    entry = next(item for item in summary if item.get("step") == 1)
    hint = entry["result"]["context_hint"]
    observed = hint["downstream_context"] if forwarded else hint
    assert observed["rows"] == source["rows"]
    _assert_position_metadata(observed, source)
    assert source == original


def test_bounded_pdf_table_window_keeps_complete_prefix_and_absolute_indices() -> None:
    source = _result()
    source["rows"].extend(
        [f"row {row}: " + "cell text " * 7, "", None, f"value {row}"]
        for row in range(11, 87)
    )
    source.update(row_count=100, next_row_offset=87)
    original = deepcopy(source)
    state = _state(source, forwarded=True)
    projected = compact_execution_summary_for_model(
        state.context_summary(strict_generic=True), max_chars=2400,
    )
    entry = next(item for item in projected if item.get("step") == 1)
    observed = entry["result"]["context_hint"]["downstream_context"]
    rows = observed["rows"]
    assert 0 < len(rows) < len(source["rows"])
    assert rows == source["rows"][:len(rows)]
    assert all(len(row) == source["column_count"] for row in rows)
    assert observed["context_truncated"] is True
    _assert_position_metadata(observed, source)
    assert "row_offset" in observed["guidance"] and "max_rows" in observed["guidance"]
    assert len(json.dumps(projected, ensure_ascii=False)) <= 2400
    assert source == original
