"""Latest-result visibility across model audit and Adapter forwarding."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.agent_protocol import (
    AgentProtocolMixin,
    MODEL_BATCH_RECOVERY_MAX_CHARS,
)
from integrations.lite_agent.adapter_executor import AdapterExecutor
from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_context_hint_for_model,
)
from integrations.lite_agent.episode_control import (
    begin_same_vm_soft_restart,
    mark_tool_result_for_audit,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools, tool_name


def _protocol() -> AgentProtocolMixin:
    protocol = AgentProtocolMixin()
    protocol.config = LiteAgentConfig(base_url="http://unused/v1")
    return protocol


def _state_with_recent_failure() -> RuntimeState:
    events = [
        ExecutionEvent(
            step=step,
            timestamp_utc="2026-09-05T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__file_read_text",
                "action": "file.read_text",
                "arguments": {"path": f"/tmp/observed-{step}.txt"},
            },
            executed=True,
            result={
                "context_hint": {
                    "path": f"/tmp/observed-{step}.txt",
                    "text": f"Observed content at step {step}",
                }
            },
        )
        for step in range(1, 14)
    ]
    events.append(
        ExecutionEvent(
            step=14,
            timestamp_utc="2026-09-05T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__file_read_text",
                "action": "file.read_text",
                "arguments": {"path": "/tmp/missing.txt"},
            },
            executed=False,
            error={"type": "PATH_NOT_FOUND", "detail": "Latest missing-file error"},
        )
    )
    state = RuntimeState(
        task_id="synthetic-context-tail-probe",
        domain="multi_apps",
        instruction="Read the observed files and report any unavailable input.",
        events=events,
    )
    mark_tool_result_for_audit(state, events[-1])
    return state


@pytest.mark.parametrize("limit", [1, 4, 12])
def test_pending_audit_keeps_latest_event_and_error(limit: int) -> None:
    state = _state_with_recent_failure()
    original = copy.deepcopy(state.events)

    projected = state.context_summary(limit=limit, strict_generic=True)
    live = [item for item in projected if "step" in item]

    assert live[-1]["step"] == 14
    assert live[-1]["executed"] is False
    assert live[-1]["error"]["detail"] == "Latest missing-file error"
    assert len(live) == limit
    assert any(
        item.get("model_audit_required", {}).get("event_step") == 14
        for item in projected
    )
    assert state.events == original


@pytest.mark.parametrize("recovery", [False, True])
def test_serialized_request_keeps_recent_observation_and_failure(
    recovery: bool,
) -> None:
    state = _state_with_recent_failure()
    messages = _protocol()._messages(
        state, b"png", execution_recovery=recovery
    )
    state_text = messages[2]["content"][0]["text"]
    projected = json.loads(state_text.split("\n")[1])
    live = [item for item in projected if "step" in item]

    assert [item["step"] for item in live[-2:]] == [13, 14]
    assert "Observed content at step 13" in state_text
    assert "Latest missing-file error" in state_text
    assert state.task_id not in state_text
    if recovery:
        assert len(state_text) < 9_500


@pytest.mark.parametrize(
    ("recovery", "wrapped"), [(False, False), (True, False), (True, True)]
)
def test_serialized_request_keeps_forwarded_command_failure_cause(
    recovery: bool, wrapped: bool,
) -> None:
    argv = ["python3", "-c", "import sample_math\n" + "print('sample')\n" * 20]
    stderr = "ModuleNotFoundError: No module named 'sample_math'\n"
    error = {
        "status": "error",
        "error_code": "DOWNSTREAM_FAILED",
        "error": "downstream Adapter call failed",
        "details": {
            "adapter": "os",
            "response": {
                "status": "error",
                "error": {
                    "code": "COMMAND_FAILED",
                    "message": "command returned an unexpected status",
                    "details": {
                        "argv": argv,
                        "cwd": "/tmp/observed-input",
                        "cwd_source": "explicit",
                        "duration_ms": 17,
                        "expected_returncodes": [0],
                        "returncode": 1,
                        "stderr": stderr,
                        "stdout": "",
                        "task_id": "synthetic-hidden-command-metadata",
                    },
                },
                "logs": [{"message": "captured command output" * 80}],
            },
        },
    }
    if wrapped:
        error = {"type": "RepeatedActionBlocked", "previous_error": error}
    event = ExecutionEvent(
        step=4,
        timestamp_utc="2026-09-13T00:00:00Z",
        proposed={
            "kind": "adapter",
            "tool": "adapter__adapter_call",
            "action": "adapter.call",
            "arguments": {
                "adapter": "os", "action": "command.run",
                "payload": {"params": {"argv": argv}},
            },
        },
        executed=False,
        error=error,
    )
    # Prior observations compete with the latest command error in the
    # existing recovery budget, just as they do in the serialized request.
    observations = [
        ExecutionEvent(
            step=step,
            timestamp_utc="2026-09-13T00:00:00Z",
            proposed={"kind": "adapter", "action": "file.read_text", "arguments": {}},
            executed=True,
            result={"context_hint": {"path": f"/tmp/input-{step}.txt", "text": "Observed input"}},
        )
        for step in range(1, 4)
    ]
    observations[-1].result = {
        "context_hint": {
            "observation_type": "text_batch",
            "context_char_budget": 18_000,
            "files": [
                {"path": f"/tmp/source-{index}.txt", "text": "sample source " * 44}
                for index in range(9)
            ],
        },
    }
    state = RuntimeState(
        task_id="synthetic-forwarded-command-feedback", domain="multi_apps",
        instruction="Inspect the inputs and correct the failed command.",
        events=[*observations, event],
    )
    mark_tool_result_for_audit(state, event)
    original = copy.deepcopy(state.events)

    messages = _protocol()._messages(
        state, b"png", execution_recovery=recovery,
    )
    state_text = messages[2]["content"][0]["text"]
    projected = json.loads(state_text.split("\n")[1])
    failure = next(item for item in projected if item.get("step") == 4)["error"]
    if wrapped:
        failure = failure["previous_error"]
    native = failure["details"]["response"]["error"]

    assert native["code"] == "COMMAND_FAILED"
    assert native["details"]["returncode"] == 1
    assert native["details"]["stderr"] == stderr
    assert "synthetic-hidden-command-metadata" not in state_text
    assert state.task_id not in state_text
    assert state.events == original
    if recovery:
        assert len(json.dumps(projected, ensure_ascii=False)) <= MODEL_BATCH_RECOVERY_MAX_CHARS


@pytest.mark.parametrize("recovery", [False, True], ids=["normal", "recovery"])
@pytest.mark.parametrize(
    ("domain", "native_action", "diagnostic_stream"),
    [("os", "command.run", "stderr"),
     ("multi_apps", "terminal.show_output", "stdout")],
    ids=["direct-command", "forwarded-visible-terminal"],
)
def test_large_http_failure_keeps_cause_through_execution_and_model_request(
    monkeypatch, tmp_path, recovery: bool, domain: str,
    native_action: str, diagnostic_stream: str,
) -> None:
    script = "sample = 1; " * 400 + "if sample: print(sample)"
    argv = ["python3", "-c", script]
    diagnostic = f'  File "<string>", line 1\n    {script}\n    ^^\nSyntaxError: invalid syntax\n'
    details = {
        "argv": argv,
        "returncode": 1,
        "stdout": diagnostic if diagnostic_stream == "stdout" else "",
        "stderr": diagnostic if diagnostic_stream == "stderr" else "",
        "task_id": "synthetic-hidden-http-metadata",
    }
    if diagnostic_stream == "stdout":
        # Visible terminal commands combine the process streams into stdout;
        # stderr alone cannot explain this real failure mode.
        details.update(combined_output=diagnostic, displayed_command=script)
    body = {
        "status": "error",
        "error": {
            "code": "COMMAND_FAILED",
            "message": "command returned an unexpected status",
            "details": details,
        },
    }
    if domain == "multi_apps":
        body = {
            "status": "error",
            "error_code": "DOWNSTREAM_FAILED",
            "error": "downstream Adapter call failed",
            "details": {"adapter": "os", "response": body},
        }
    original_body = copy.deepcopy(body)
    assert len(json.dumps(body)) > 6000
    captured = []

    def post(_url, *, json, timeout):
        captured.append(copy.deepcopy(json))
        return SimpleNamespace(ok=False, status_code=422, json=lambda: body)

    monkeypatch.setattr("integrations.lite_agent.adapter_executor.requests.post", post)
    trace_path = tmp_path / "adapter-trace.jsonl"
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        AdapterExecutor({domain: "http://synthetic"}, trace_path),
        model_client=SimpleNamespace(client=None),
    )
    params = {"argv": copy.deepcopy(argv), "cwd_source": "home", "provenance": "none"}
    action = native_action
    arguments = params
    state = RuntimeState(
        task_id="synthetic-large-http-failure", domain=domain,
        instruction="Inspect the inputs and correct the failed command.",
    )
    if domain == "multi_apps":
        action = "adapter.call"
        arguments = {"adapter": "os", "action": native_action, "payload": {"params": params}}
        state.events.append(ExecutionEvent(
            step=1, timestamp_utc="2026-09-14T00:00:00Z",
            proposed={"kind": "catalog", "tool": "tools_search", "arguments": {}},
            executed=True,
            result={"matches": [{
                "action": action, "adapter": "os", "downstream_action": native_action,
            }]},
        ))
    original_arguments = copy.deepcopy(arguments)
    arguments_raw = json.dumps(arguments)
    event = agent.execute_proposal(state, {
        "tool": tool_name(action),
        "arguments_raw": arguments_raw,
        "_model_visible_tools": build_tools(
            domain, [action], include_gui=False, strict_generic=True,
        ),
    })

    assert event.parsed and event.validated
    assert event.executed is False
    assert event.result is None
    assert len(captured) == 1
    assert captured[0]["params"] == original_arguments
    assert event.proposed["arguments"] == original_arguments
    assert event.proposed["arguments_raw"] == arguments_raw
    trace = json.loads(trace_path.read_text())
    assert trace["error"] == original_body
    assert trace["http_status"] == 422
    mark_tool_result_for_audit(state, event)
    original_events = copy.deepcopy(state.events)

    messages = agent._messages(state, b"png", execution_recovery=recovery)
    state_text = messages[2]["content"][0]["text"]
    projected = json.loads(state_text.split("\n")[1])
    failure = next(item for item in projected if item.get("step") == event.step)
    error = failure["error"]
    native = error["details"]["response"]["error"] if domain == "multi_apps" else error["error"]

    assert failure["executed"] is False
    assert failure["result"] is None
    assert native["code"] == "COMMAND_FAILED"
    assert native["details"]["returncode"] == 1
    assert "SyntaxError: invalid syntax" in native["details"][diagnostic_stream]
    assert "synthetic-hidden-http-metadata" not in json.dumps(messages)
    assert state.task_id not in json.dumps(messages)
    assert len(json.dumps(error, ensure_ascii=False)) <= 1200
    if recovery:
        assert len(json.dumps(projected, ensure_ascii=False)) <= MODEL_BATCH_RECOVERY_MAX_CHARS
    assert body == original_body
    assert arguments == original_arguments
    assert state.events == original_events


def test_soft_restart_markers_do_not_hide_latest_failure() -> None:
    state = _state_with_recent_failure()
    decision = begin_same_vm_soft_restart(
        state, "local_step_limit", trigger_step=14, context_limit=4
    )
    assert decision.accepted

    messages = _protocol()._messages(state, b"png")
    state_text = messages[2]["content"][0]["text"]
    projected = json.loads(state_text.split("\n")[1])

    assert any(
        item.get("step") == 14 and item.get("executed") is False for item in projected
    )
    assert "Latest missing-file error" in state_text
    assert "recovery_context" in state_text
    assert "model_audit_required" in state_text
    assert len(state_text) < 9_500


@pytest.mark.parametrize(
    ("adapter", "action", "observed"),
    [
        (
            "libreoffice_impress",
            "shape.export_image",
            {
                "output_path": "/tmp/exported-picture.png",
                "slide": 3,
                "selector": {"path": [4]},
                "format": "png",
                "size": 2048,
            },
        ),
        (
            "gimp",
            "image.inspect",
            {"path": "/tmp/observed-picture.png", "width": 640, "height": 480},
        ),
    ],
)
def test_forwarded_api_without_specific_hint_keeps_observed_result(
    adapter: str, action: str, observed: dict
) -> None:
    downstream_result = {**observed, "task_id": "synthetic-hidden-metadata"}
    body = {
        "status": "ok",
        "result": {
            "adapter": adapter,
            "action": action,
            "response": {
                "status": "ok",
                "result": downstream_result,
                "verification": {"passed": True},
            },
        },
    }
    original = copy.deepcopy(body)

    hint = adapter_context_hint("multi_apps", "adapter.call", body)
    projected = compact_context_hint_for_model(hint, remaining_chars=5000)

    assert projected["downstream_context"] == observed
    assert projected["verification_passed"] is True
    assert "synthetic-hidden-metadata" not in json.dumps(projected)
    assert body == original


def _workbook_with_observed_charts() -> dict:
    return {
        "status": "ok",
        "result": {
            "title": "Inventory.xlsx",
            "url": "file:///tmp/Inventory.xlsx",
            "active_sheet": "Overview",
            "modified": False,
            "sheets": [
                {
                    "name": "Overview",
                    "used_range": {
                        "start_column": 0,
                        "start_row": 0,
                        "end_column": 0,
                        "end_row": 0,
                    },
                    "charts": [
                        {
                            "name": "QuarterlyPlot",
                            "title": "Units shipped",
                            "type": "column",
                            "source_sheet": "Inventory",
                            "source_ranges": ["D6:D10", "G6:G10"],
                            "column_headers": False,
                            "row_headers": True,
                            "data_series_count": 1,
                            "data_series": [
                                {
                                    "coordinate_system": 0,
                                    "labels": ["Units"],
                                    "source_ranges": ["$Inventory.$G$6:$G$10"],
                                }
                            ],
                            "category_axes": [
                                {
                                    "coordinate_system": 0,
                                    "source_range": "$Inventory.$D$6:$D$10",
                                    "labels": ["North", "South", "East", "West", "Central"],
                                    "count": 5,
                                }
                            ],
                        },
                        {"name": "OlderPlot", "inspect_error": "Chart is unavailable"},
                    ],
                }
            ],
        },
    }


@pytest.mark.parametrize("forwarded", [False, True])
def test_workbook_chart_settings_reach_serialized_model_request(
    forwarded: bool,
) -> None:
    body = _workbook_with_observed_charts()
    original = copy.deepcopy(body)
    domain, action = "libreoffice_calc", "workbook.inspect"
    if forwarded:
        body = {
            "status": "ok",
            "result": {"adapter": domain, "action": action, "response": body},
        }
        domain, action = "multi_apps", "adapter.call"
    hint = adapter_context_hint(domain, action, body)
    state = RuntimeState(
        task_id="synthetic-chart-feedback",
        domain=domain,
        instruction="Inspect the existing workbook charts.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-09-06T00:00:00Z",
                proposed={"kind": "adapter", "action": action, "arguments": {}},
                executed=True,
                result={"context_hint": hint},
            )
        ],
    )
    messages = _protocol()._messages(state, b"png")
    state_text = messages[2]["content"][0]["text"]
    summary = json.loads(state_text.split("\n")[1])
    projected = next(item for item in summary if item.get("step") == 1)["result"][
        "context_hint"
    ]
    if forwarded:
        projected = projected["downstream_context"]
        body = body["result"]["response"]
    sheet = projected["sheets"][0]

    assert sheet["charts"] == original["result"]["sheets"][0]["charts"]
    assert sheet["chart_count"] == 2
    assert sheet["charts_omitted_from_context"] == 0
    assert sheet["used_range_a1"] == "A1:A1"
    assert "embedded objects" in projected["guidance"]
    assert state.task_id not in state_text
    assert body == original


def test_workbook_chart_projection_preserves_sheet_when_chart_details_overflow() -> None:
    body = _workbook_with_observed_charts()
    charts = body["result"]["sheets"][0]["charts"]
    chart = {**charts[0], "title": "Stock availability and shipment volume " * 6}
    charts[:] = [{**chart, "name": f"Plot-{index}"} for index in range(40)]
    original = copy.deepcopy(body)

    hint = adapter_context_hint("libreoffice_calc", "workbook.inspect", body)
    projected = compact_context_hint_for_model(hint, remaining_chars=5000)
    sheet = projected["sheets"][0]

    assert len(json.dumps(hint, ensure_ascii=False)) <= 4200
    assert sheet["name"] == "Overview"
    assert sheet["chart_count"] == len(charts)
    assert 0 < len(sheet["charts"]) < 12
    assert sheet["charts_omitted_from_context"] == len(charts) - len(sheet["charts"])
    assert sheet["charts"] == charts[: len(sheet["charts"])]
    assert body == original


def test_chart_category_preview_keeps_native_count_and_marks_omissions() -> None:
    body = _workbook_with_observed_charts()
    axis = body["result"]["sheets"][0]["charts"][0]["category_axes"][0]
    axis.update(labels=[f"Region {index}" for index in range(30)], count=30)
    original = copy.deepcopy(body)

    hint = adapter_context_hint("libreoffice_calc", "workbook.inspect", body)

    chart = hint["sheets"][0]["charts"][0]
    preview = chart["category_axes"][0]
    assert chart["data_series_count"] == 1
    assert preview["count"] == 30
    assert preview["labels"] == axis["labels"][:12]
    assert preview["labels_omitted_from_context"] == 18
    assert body == original


def test_large_debug_variables_response_keeps_structured_model_feedback(monkeypatch):
    variables = {
        "window_id": "0x2a00002", "window_title": "sample.py - Visual Studio Code",
        "session": {"phase": "paused", "active": True, "paused": True},
        "item_count": 4, "truncated": False,
        "item_names": [
            "Scope Locals", "samples, value array([" + "0.25, " * 260 + "])",
            "enabled, value True", "matrix_lib, value <module 'matrix_lib'>",
        ],
    }
    body = {
        "status": "ok", "result": {"variables": variables},
        "verification": {"passed": True, "checks": [
            {"observed": variables, "expected": variables} for _ in range(4)
        ]},
    }
    original = copy.deepcopy(body)
    assert len(json.dumps(body)) > 6000
    monkeypatch.setattr(
        "integrations.lite_agent.adapter_executor.requests.post",
        lambda *_args, **_kwargs: SimpleNamespace(
            ok=True, status_code=200, json=lambda: body,
        ),
    )
    action = "debug.variables.read"
    params = {"window_id": "0x2a00002", "max_items": 12}
    result = AdapterExecutor({"vs_code": "http://synthetic"}).execute(
        "vs_code", action, params, {},
    )
    assert result["executed"] is True
    assert result["result"]["adapter_response"]["truncated"] is True
    assert result["result"]["context_hint"]["item_names"] == variables["item_names"]
    event = ExecutionEvent(
        step=1, timestamp_utc="2026-09-11T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": params},
        executed=True, result=result["result"],
    )
    state = RuntimeState(
        task_id="synthetic-debug-variables", domain="vs_code",
        instruction="Inspect the program variables.", events=[event],
    )
    mark_tool_result_for_audit(state, event)
    messages = _protocol()._messages(state, b"png")
    summary = json.loads(messages[2]["content"][0]["text"].split("\n")[1])
    projected = next(item for item in summary if item.get("step") == 1)["result"][
        "context_hint"
    ]
    assert projected["window_id"] == variables["window_id"]
    assert projected["session"]["phase"] == "paused"
    assert projected["item_count"] == 4
    assert projected["truncated"] is False
    assert len(projected["item_names"]) == 4
    assert projected["item_names"][-2:] == variables["item_names"][-2:]
    assert "raising max_items does not" in projected["guidance"]
    assert "before its line executes" in projected["guidance"]
    assert body == original
