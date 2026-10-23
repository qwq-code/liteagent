from __future__ import annotations

from copy import deepcopy
import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from calc_adapter.service import create_app as calc_app
from integrations.lite_agent.adapter_executor import AdapterExecutor
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools
from multi_apps_adapter.service import create_app as multi_apps_app
from multi_apps_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from os_adapter import worker
from os_adapter.errors import AdapterError
from os_adapter.service import create_app as os_app


@pytest.fixture
def bridge(monkeypatch):
    captured = {}

    def dispatch(action, params, timeout_seconds):
        captured["native"] = (action, deepcopy(params), timeout_seconds)
        if captured.get("native_error"):
            raise AdapterError(
                "OPERATION_TIMEOUT", "command timed out", {"stdout": "partial output"}, 504
            )
        return {"returncode": 0, "stdout": "finished"}

    monkeypatch.setattr(
        worker, "OSActions", lambda: SimpleNamespace(dispatch=dispatch, runner=None)
    )
    os_client = os_app(
        runner=SimpleNamespace(run=lambda parsed: worker.execute(parsed.to_worker_payload()))
    ).test_client()

    def run_calc(parsed):
        captured["calc_native"] = {
            **deepcopy(parsed.to_worker_payload()), "timeout_ms": parsed.timeout_ms,
        }
        return {"result": {"written": True}, "verification": {"passed": True}}

    calc_client = calc_app(
        lifecycle=SimpleNamespace(listener_ready=lambda: True),
        runner=SimpleNamespace(run=run_calc),
    ).test_client()

    def urlopen(request, *, timeout):
        payload = json.loads(request.data)
        captured["downstream"] = (deepcopy(payload), timeout)
        client = calc_client if payload["adapter"] == "libreoffice_calc" else os_client
        response = client.post("/v1/actions", json=payload)
        if response.status_code != 200:
            raise HTTPError(
                request.full_url, response.status_code, "native error", {},
                io.BytesIO(response.data),
            )
        return io.BytesIO(response.data)

    monkeypatch.setattr("multi_apps_adapter.actions.urlopen", urlopen)
    multi_client = multi_apps_app().test_client()

    def post(url, *, json, timeout):
        captured["outer"] = (deepcopy(json), timeout)
        client = multi_client if "/multi/" in url else os_client
        response = client.post("/v1/actions", json=json)
        return SimpleNamespace(
            ok=response.status_code == 200,
            status_code=response.status_code,
            json=response.get_json,
        )

    monkeypatch.setattr("integrations.lite_agent.adapter_executor.requests.post", post)
    return captured


def command_arguments(timeout_ms=None):
    payload = {
        "params": {
            "argv": ["example-converter", "input.bin"],
            "cwd_source": "home",
            "provenance": "none",
        }
    }
    if timeout_ms is not None:
        payload["timeout_ms"] = timeout_ms
    return {"adapter": "os", "action": "command.run", "payload": payload}


@pytest.mark.parametrize("selected_ms", [None, 5_000, 300_000, 900_000])
def test_nested_timeout_reaches_native_worker_without_changing_arguments(
    bridge, tmp_path, selected_ms
):
    arguments = command_arguments(selected_ms)
    original = deepcopy(arguments)
    trace_path = tmp_path / "calls.jsonl"
    executor = AdapterExecutor({"multi_apps": "http://synthetic/multi"}, trace_path)

    result = executor.execute("multi_apps", "adapter.call", arguments, {})

    assert result["executed"] is True, result
    outer_ms = max(120_000, selected_ms or 120_000)
    effective_ms = selected_ms or 120_000
    assert bridge["outer"][0]["timeout_ms"] == outer_ms
    assert bridge["outer"][1] == outer_ms / 1000 + 15
    assert bridge["downstream"][0]["timeout_ms"] == effective_ms
    assert bridge["downstream"][1] == outer_ms / 1000
    assert bridge["native"] == (
        "command.run", original["payload"]["params"], effective_ms / 1000 - 1
    )
    trace = json.loads(trace_path.read_text())
    assert trace["payload"]["params"] == original == arguments
    assert trace["timeout_budget"]["effective_ms"] == outer_ms


def test_explicit_timeout_respects_lower_calc_cap_through_native_validation(
    bridge, tmp_path,
):
    arguments = {
        "adapter": "libreoffice_calc",
        "action": "range.write",
        "payload": {
            "timeout_ms": 300_000,
            "document": {"title": "Synthetic workbook"},
            "params": {"sheet": "Data", "range": "B2:C2", "values": [[7, "sample"]]},
        },
    }
    original = deepcopy(arguments)
    trace_path = tmp_path / "calls.jsonl"
    executor = AdapterExecutor({"multi_apps": "http://synthetic/multi"}, trace_path)

    result = executor.execute("multi_apps", "adapter.call", arguments, {})

    assert result["executed"] is True, result
    assert bridge["outer"][0]["timeout_ms"] == 300_000
    assert bridge["downstream"][0]["timeout_ms"] == 120_000
    assert bridge["downstream"][1] == 300.0
    native = bridge["calc_native"]
    assert native["timeout_ms"] == 120_000
    assert native["action"] == original["action"]
    assert native["document"] == original["payload"]["document"]
    assert native["params"] == original["payload"]["params"]
    assert bridge["outer"][0]["params"] == original == arguments
    trace = json.loads(trace_path.read_text())
    assert trace["payload"]["params"] == original
    assert trace["timeout_budget"]["requested_ms"] == 300_000
    assert result["result"]["adapter_response"]["result"]["timeout_budget"] == {
        "requested_ms": 300_000, "effective_ms": 120_000,
    }


def test_remaining_episode_time_bounds_outer_proxy_and_native_budget(
    bridge, monkeypatch, tmp_path
):
    monkeypatch.setattr("integrations.lite_agent.adapter_executor.time.monotonic", lambda: 100.0)
    arguments = command_arguments(300_000)
    original = deepcopy(arguments)
    trace_path = tmp_path / "calls.jsonl"
    executor = AdapterExecutor(
        {"multi_apps": "http://synthetic/multi"}, trace_path, deadline_monotonic=175.0
    )

    result = executor.execute("multi_apps", "adapter.call", arguments, {})

    assert result["executed"] is True, result
    assert bridge["outer"][0]["timeout_ms"] == 75_000
    assert bridge["outer"][1] == 75.0
    assert bridge["downstream"][0]["timeout_ms"] == 75_000
    assert bridge["downstream"][1] == 75.0
    assert bridge["native"][2] == 74.0
    assert bridge["outer"][0]["params"] == arguments == original
    trace = json.loads(trace_path.read_text())
    assert trace["timeout_budget"] == {
        "requested_ms": 300_000, "effective_ms": 75_000,
        "episode_remaining_seconds": 75.0, "http_wait_seconds": 75.0,
    }
    assert result["result"]["adapter_response"]["result"]["timeout_budget"] == {
        "requested_ms": 300_000, "effective_ms": 75_000,
    }


def test_expired_episode_does_not_start_a_guest_action(bridge, monkeypatch, tmp_path):
    monkeypatch.setattr("integrations.lite_agent.adapter_executor.time.monotonic", lambda: 100.0)
    trace_path = tmp_path / "calls.jsonl"
    executor = AdapterExecutor(
        {"multi_apps": "http://synthetic/multi"}, trace_path, deadline_monotonic=100.0
    )

    result = executor.execute("multi_apps", "adapter.call", command_arguments(300_000), {})

    assert result["executed"] is False
    assert result["error"]["type"] == "AgentDeadlineExceeded"
    assert bridge == {}
    assert json.loads(trace_path.read_text())["timeout_budget"]["effective_ms"] == 0


def test_unrelated_direct_action_keeps_default_timeout(bridge):
    arguments = command_arguments()["payload"]["params"]
    executor = AdapterExecutor({"os": "http://synthetic/os"})

    result = executor.execute("os", "command.run", arguments, {})

    assert result["executed"] is True, result
    assert bridge["outer"][0]["params"] == arguments
    assert bridge["outer"][0]["timeout_ms"] == 120_000
    assert bridge["outer"][1] == 135.0
    assert bridge["native"][2] == 119.0


def test_invalid_nested_timeout_keeps_existing_native_validation_feedback(bridge):
    arguments = command_arguments()
    arguments["payload"]["timeout_ms"] = None
    original = deepcopy(arguments)
    executor = AdapterExecutor({"multi_apps": "http://synthetic/multi"})

    result = executor.execute("multi_apps", "adapter.call", arguments, {})

    assert result["executed"] is False
    assert result["error"]["error_code"] == "INVALID_REQUEST"
    assert "params.payload.timeout_ms" in result["error"]["error"]
    assert bridge["outer"][0]["params"] == original == arguments
    assert "downstream" not in bridge


def test_native_timeout_error_and_partial_output_reach_model(bridge):
    bridge["native_error"] = True
    executor = AdapterExecutor({"multi_apps": "http://synthetic/multi"})

    result = executor.execute("multi_apps", "adapter.call", command_arguments(300_000), {})

    assert result["executed"] is False
    details = result["error"]["details"]
    assert details["response"]["error"]["code"] == "OPERATION_TIMEOUT"
    assert details["response"]["error"]["details"]["stdout"] == "partial output"
    assert details["timeout_budget"]["effective_ms"] == 300_000


def test_timeout_usage_flows_from_owner_to_correlated_route_schema():
    tools = build_tools(
        "multi_apps", ["adapter.call"], include_gui=False,
        include_control_tools=False, strict_generic=True,
    )
    tools = constrain_adapter_call_routes(tools, [("os", "command.run")])
    schema = tools[0]["function"]["parameters"]
    expected = STRICT_ACTION_PARAM_SCHEMAS["adapter.call"]["properties"]["payload"]["properties"]["timeout_ms"]

    assert "remaining episode time" in expected["description"]
    assert schema["properties"]["payload"]["properties"]["timeout_ms"] == expected
    assert len(schema["oneOf"]) == 1
    branch = schema["oneOf"][0]["properties"]
    assert branch["adapter"]["enum"] == ["os"]
    assert branch["action"]["enum"] == ["command.run"]
    assert branch["payload"]["properties"]["timeout_ms"] == expected
