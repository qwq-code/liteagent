from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.completion_policy import canonical_action_request
from integrations.lite_agent.episode_control import begin_same_vm_soft_restart
from integrations.lite_agent.generic_routing import filter_generic_actions
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.stall_policy import detect_no_progress_stall
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools, tool_name


class RecordingExecutor:
    def __init__(self):
        self.calls = []
        self.response = {
            "executed": True,
            "result": {"context_hint": {"name": "Inventory", "rows": 12}},
        }

    def execute(self, domain, action, arguments, _metadata):
        self.calls.append((domain, action, deepcopy(arguments)))
        return deepcopy(self.response)


def setup_call(
    action="table.read", params=None, *, forwarded=False,
    owning_domain="libreoffice_writer",
):
    params = {"name": "Inventory"} if params is None else params
    domain = "multi_apps" if forwarded else owning_domain
    public_action = "adapter.call" if forwarded else action
    arguments = (
        {
            "adapter": owning_domain,
            "action": action,
            "payload": {"params": params},
        }
        if forwarded
        else params
    )
    tools = build_tools(
        domain,
        [public_action],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )
    if forwarded:
        tools = constrain_adapter_call_routes(tools, [(owning_domain, action)])
    executor = RecordingExecutor()
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
        executor,
        model_client=SimpleNamespace(client=object()),
    )
    state = RuntimeState(
        task_id="synthetic-read-recovery",
        domain=domain,
        instruction="Inspect the active document table and its formatting.",
    )
    if forwarded:
        state.events.append(
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-09-05T00:00:00Z",
                executed=True,
                proposed={
                    "kind": "catalog",
                    "tool": "tools_search",
                    "arguments": {"query": "Writer table"},
                },
                result={
                    "matches": [
                        {
                            "action": "adapter.call",
                            "adapter": owning_domain,
                            "downstream_action": action,
                        }
                    ]
                },
            )
        )
    proposal = {
        "tool": tools[0]["function"]["name"],
        "arguments_raw": json.dumps(arguments),
        "_model_visible_tools": tools,
    }
    return agent, state, executor, proposal


@pytest.mark.parametrize("forwarded", [False, True])
@pytest.mark.parametrize(
    ("owning_domain", "action", "params"),
    [
        ("libreoffice_writer", "table.read", {"name": "Inventory"}),
        ("libreoffice_calc", "workbook.inspect", {}),
    ],
)
def test_model_selected_read_can_refresh_observation(
    forwarded, owning_domain, action, params,
):
    agent, state, executor, proposal = setup_call(
        action, params, forwarded=forwarded, owning_domain=owning_domain,
    )
    before = deepcopy(proposal)
    assert agent.execute_proposal(state, proposal).executed
    executor.response["result"]["context_hint"]["rows"] = 13

    event = agent.execute_proposal(state, proposal)

    assert event.executed, event.error
    assert event.error is None
    assert event.result["context_hint"]["rows"] == 13
    assert executor.calls[0] == executor.calls[1]
    assert event.proposed["arguments"] == json.loads(proposal["arguments_raw"])
    assert proposal == before


@pytest.mark.parametrize(
    ("owning_domain", "action"),
    [("libreoffice_calc", "workbook.inspect"), ("vlc", "playback.status")],
)
def test_successful_parameterless_read_remains_selectable(owning_domain, action):
    agent, state, _executor, proposal = setup_call(
        action, {}, owning_domain=owning_domain,
    )
    state.instruction = "Inspect the current application state."
    assert agent.execute_proposal(state, proposal).executed

    assert not state.stage_read_satisfied(action)
    assert filter_generic_actions(state, [action]) == [action]
    assert tool_name(action) in {tool["function"]["name"] for tool in agent.tools(state)}


@pytest.mark.parametrize(
    ("owning_domain", "action"),
    [("libreoffice_calc", "workbook.inspect"), ("vlc", "playback.status")],
)
def test_search_returns_successful_parameterless_read(owning_domain, action):
    agent, state, _executor, proposal = setup_call(
        action, {}, owning_domain=owning_domain,
    )
    state.instruction = "Inspect the current application state."
    assert agent.execute_proposal(state, proposal).executed

    search = agent.execute_proposal(
        state,
        {
            "tool": "tools_search",
            "arguments_raw": json.dumps({"query": action}),
            "_model_visible_tools": agent.tools(state),
        },
    )

    assert search.executed, search.error
    assert action in {item["action"] for item in search.result["matches"]}
    assert action not in search.result["recovery"]["excluded_actions"]
    assert tool_name(action) in {tool["function"]["name"] for tool in agent.tools(state)}


def test_failed_parameterless_read_keeps_its_error_and_search_block():
    action = "workbook.inspect"
    agent, state, executor, proposal = setup_call(
        action, {}, owning_domain="libreoffice_calc",
    )
    executor.response = {
        "executed": False,
        "error": {"type": "DOCUMENT_NOT_FOUND", "detail": "No open spreadsheet"},
    }
    first = agent.execute_proposal(state, proposal)
    second = agent.execute_proposal(state, proposal)

    assert first.error["type"] == "DOCUMENT_NOT_FOUND"
    assert second.error["type"] == "RepeatedActionBlocked"
    assert second.error["previous_error"] == first.error
    assert filter_generic_actions(state, [action]) == []

    search = agent.execute_proposal(
        state,
        {
            "tool": "tools_search",
            "arguments_raw": json.dumps({"query": action}),
            "_model_visible_tools": agent.tools(state),
        },
    )

    assert search.executed, search.error
    assert action not in {item["action"] for item in search.result["matches"]}
    assert action in search.result["recovery"]["excluded_actions"]
    assert len(executor.calls) == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["gsettings", "list-schemas"],
        ["gsettings", "range", "org.example.Settings", "sample-scale"],
    ],
)
def test_successful_read_only_command_can_refresh_observation(argv):
    """A repeated discovery command must not be mistaken for a duplicate write."""
    arguments = {
        "argv": argv,
        "cwd_source": "home",
        "provenance": "none",
    }
    tools = build_tools(
        "os",
        ["command.run"],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )
    executor = RecordingExecutor()
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
        executor,
        model_client=SimpleNamespace(client=object()),
    )
    state = RuntimeState(
        task_id="synthetic-command-read-recovery",
        domain="os",
        instruction="Inspect the current desktop setting metadata.",
    )
    proposal = {
        "tool": tools[0]["function"]["name"],
        "arguments_raw": json.dumps(arguments),
        "_model_visible_tools": tools,
    }

    first = agent.execute_proposal(state, proposal)
    second = agent.execute_proposal(state, proposal)

    assert first.executed and first.error is None
    assert second.executed and second.error is None
    assert len(executor.calls) == 2


def test_identical_reads_still_reach_existing_stall_detection():
    agent, state, executor, proposal = setup_call()
    for _ in range(9):
        event = agent.execute_proposal(state, proposal)
        assert event.executed, event.error

    assert len(executor.calls) == 9
    stall = detect_no_progress_stall(state.events, window=8)
    assert stall["reason"] == "repeated_equivalent_read_cycle"


@pytest.mark.parametrize("read_succeeds", [True, False])
def test_soft_restart_stall_window_uses_only_the_current_retry(read_succeeds):
    agent, state, executor, proposal = setup_call()
    if not read_succeeds:
        executor.response = {
            "executed": False,
            "error": {"type": "TABLE_NOT_FOUND", "detail": "Selected table is unavailable"},
        }
    for _ in range(9):
        agent.execute_proposal(state, proposal)
    original_events = deepcopy(state.events)
    original_proposal = deepcopy(proposal)
    initial_stall = detect_no_progress_stall(state.events, window=8)
    assert initial_stall is not None

    restart = begin_same_vm_soft_restart(state, initial_stall["reason"], max_retries=1)
    assert restart.accepted and restart.preserve_vm
    for local_step in range(1, 9):
        event = agent.execute_proposal(state, proposal)
        event.retry = state.retry
        event.local_step = local_step
        stall = detect_no_progress_stall(state.events, window=8)
        if local_step < 8:
            assert stall is None
        else:
            assert stall["reason"] == initial_stall["reason"]
            assert stall["event_steps"] == list(range(10, 18))

    assert state.events[:9] == original_events
    assert len(state.events) == 17
    assert proposal == original_proposal
    assert state.retry == 1
    assert state.soft_restart_count == 1
    assert not begin_same_vm_soft_restart(state, stall["reason"], max_retries=1).accepted


@pytest.mark.parametrize("forwarded", [False, True])
@pytest.mark.parametrize("changed_field", ["argv", "stdout_path", "terminal"])
def test_command_stall_identity_retains_forwarded_arguments(forwarded, changed_field):
    events = []
    for step in range(1, 9):
        params = {"argv": ["reporter", "--section", "summary"]}
        if changed_field == "argv":
            params["argv"][-1] = str(step)
        elif changed_field == "stdout_path":
            params["stdout_path"] = f"/tmp/output-{step}.txt"
        else:
            params["terminal"] = bool(step % 2)
        arguments = (
            {"adapter": "os", "action": "command.run", "payload": {"params": params}}
            if forwarded
            else params
        )
        events.append(
            ExecutionEvent(
                step=step,
                timestamp_utc="2026-09-06T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "action": "adapter.call" if forwarded else "command.run",
                    "arguments": arguments,
                },
                executed=True,
            )
        )
    original = deepcopy(events)

    stall = detect_no_progress_stall(events, window=8)

    if changed_field == "terminal":
        assert stall["reason"] == "repeated_successful_action_cycle"
    else:
        assert stall is None
    assert events == original


@pytest.mark.parametrize("forwarded", [False, True])
def test_positional_delete_can_remove_the_next_observed_shape(forwarded):
    params = {"slide": 2, "selector": {"path": [0]}}
    agent, state, _executor, proposal = setup_call(
        "shape.delete", params, forwarded=forwarded,
        owning_domain="libreoffice_impress",
    )
    state.instruction = "Remove the two text objects from the selected slide."

    class ShapeCollectionExecutor(RecordingExecutor):
        shapes = ["Heading", "Caption"]

        def execute(self, domain, action, arguments, _metadata):
            self.calls.append((domain, action, deepcopy(arguments)))
            _, _, selected = canonical_action_request(domain, action, arguments)
            try:
                removed = self.shapes.pop(selected["selector"]["path"][0])
            except IndexError:
                return {
                    "executed": False,
                    "error": {"type": "SHAPE_NOT_FOUND", "detail": "No shape at this path"},
                }
            return {
                "executed": True,
                "result": {"removed": removed, "count": len(self.shapes)},
            }

    executor = ShapeCollectionExecutor()
    agent.adapter_executor = executor
    original_proposal = deepcopy(proposal)
    first = agent.execute_proposal(state, proposal)
    assert first.executed and first.result["removed"] == "Heading"
    state.events.append(ExecutionEvent(
        step=first.step + 1,
        timestamp_utc="2026-09-13T00:00:00Z",
        proposed={"kind": "adapter", "action": "presentation.inspect", "arguments": {}},
        executed=True,
        result={"shapes": [{"name": "Caption", "selector": {"path": [0]}}]},
    ))

    second = agent.execute_proposal(state, proposal)
    assert second.executed, second.error
    assert second.result == {"removed": "Caption", "count": 0}
    assert executor.calls[0] == executor.calls[1]
    assert second.proposed["arguments"] == json.loads(proposal["arguments_raw"])
    assert proposal == original_proposal

    # Once the collection is empty, native errors and their repeat block remain.
    missing = agent.execute_proposal(state, proposal)
    assert missing.error["type"] == "SHAPE_NOT_FOUND"
    repeated = agent.execute_proposal(state, proposal)
    assert repeated.error["type"] == "RepeatedActionBlocked"
    assert repeated.error["previous_error"] == missing.error
    assert len(executor.calls) == 4


def test_duplicate_mutation_rule_is_unchanged():
    agent, state, executor, proposal = setup_call(
        "table.set_cell_text_color",
        {"name": "Inventory", "cells": ["B2"], "color": "#146C94"},
    )
    assert agent.execute_proposal(state, proposal).executed

    event = agent.execute_proposal(state, proposal)

    assert not event.executed
    assert "identical successful action" in event.error["detail"]
    assert len(executor.calls) == 1


def test_failed_reads_keep_original_error_and_existing_repeat_block():
    agent, state, executor, proposal = setup_call()
    executor.response = {
        "executed": False,
        "error": {"type": "TABLE_NOT_FOUND", "detail": "Selected table is unavailable"},
    }
    first = agent.execute_proposal(state, proposal)
    assert first.error["type"] == "TABLE_NOT_FOUND"
    second = agent.execute_proposal(state, proposal)

    assert not second.executed
    assert second.error["type"] == "RepeatedActionBlocked"
    assert second.error["previous_error"] == first.error
    assert len(executor.calls) == 2


def test_forwarded_command_blocks_only_repeated_downstream_error():
    agent, state, executor, proposal = setup_call(
        "command.run",
        {
            "argv": ["python3", "/tmp/project/app.py"],
            "cwd_source": "home",
            "provenance": "shell_history",
        },
        forwarded=True,
        owning_domain="os",
    )
    state.instruction = "Run the project script and fix its execution error."
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
                },
            },
        },
    }
    executor.response = {"executed": False, "error": error}
    first = agent.execute_proposal(state, proposal)
    assert first.error == error

    error["details"]["response"]["error"] = {
        "code": "OPERATION_TIMEOUT",
        "message": "command exceeded 2 seconds",
    }
    second = agent.execute_proposal(state, proposal)
    assert second.error == error
    assert len(executor.calls) == 2

    third = agent.execute_proposal(state, proposal)
    assert third.error["type"] == "RepeatedActionBlocked"
    assert third.error["previous_step"] == second.step
    assert third.error["previous_error"] == second.error
    assert len(executor.calls) == 3
