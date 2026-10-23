from __future__ import annotations

import json

import pytest

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent import completion_recovery
from integrations.lite_agent.recovery_surface import (
    bounded_recovery_actions,
    decorate_recovery_tools,
    last_failure_summary,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools, search_actions
from integrations.lite_agent.generic_routing import recovery_search_routes
from integrations.lite_agent import source_execution_semantics


class NoAdapterExecutor:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("Adapter execution is not expected")


def make_agent(*, gui: bool = False) -> LiteAgent:
    return LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=gui),
        NoAdapterExecutor(),  # type: ignore[arg-type]
        gui_executor=(lambda _arguments: {"executed": True}) if gui else None,
    )


def repeated_path_failure_state() -> RuntimeState:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Find the exact report file in the home directory.",
    )
    arguments = {
        "roots": ["~/"],
        "name_patterns": ["report.txt"],
        "kind": "file",
        "recursive": True,
        "max_depth": 4,
        "include_hidden": False,
        "max_results": 50,
    }
    for step in (1, 2):
        state.events.append(
            ExecutionEvent(
                step=step,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__filesystem_find",
                    "action": "filesystem.find",
                    "arguments": arguments,
                },
                error={"type": "PATH_NOT_FOUND", "detail": "path unavailable"},
            )
        )
    LiteAgent._block_repeated_error(state)
    return state


def test_repeated_error_surface_keeps_replan_and_completion_controls() -> None:
    state = repeated_path_failure_state()
    agent = make_agent(gui=True)

    names = {tool["function"]["name"] for tool in agent.tools(state)}

    assert state.requires_replan()
    assert {"tools_search", "propose_done", "fail_task", "gui_action"}.issubset(names)
    assert len(names) <= agent.config.top_k_actions + 4
    # Recovery must offer at least one model-selectable public Adapter action;
    # a search-only surface would recreate the observed dead end.
    assert any(name.startswith("adapter__") for name in names)


def test_archive_command_search_recalls_generic_command_runner() -> None:
    matches = search_actions(
        "os",
        "decompress file with gunzip",
        strict_generic=True,
        instruction="Restore the local file and verify the result.",
    )
    assert matches
    assert matches[0]["action"] == "command.run"


def test_search_result_repeats_direct_action_usage_description() -> None:
    matches = search_actions(
        "os",
        "terminal size setting gsettings",
        instruction="set a desktop setting",
        strict_generic=True,
    )
    setting = next(item for item in matches if item["action"] == "desktop.set_setting")
    assert "list-relocatable-schemas" in setting["description"]
    assert "never guess" in setting["description"]


@pytest.mark.parametrize("domain", ["thunderbird", "multi_apps"])
@pytest.mark.parametrize("query", [
    "thunderbird draft email receiver field",
    "add a recipient to the open email",
    "change receiver addresses in the draft",
    "email compose recipients",
])
def test_recipient_search_finds_existing_compose_action(domain, query):
    matches = search_actions(domain, query, limit=5, strict_generic=True)
    actions = {
        item["downstream_action"] if domain == "multi_apps" else item["action"]
        for item in matches
        if domain != "multi_apps" or item.get("adapter") == "thunderbird"
    }
    assert "compose.set_recipients" in actions


@pytest.mark.parametrize("domain", ["thunderbird", "multi_apps"])
@pytest.mark.parametrize("query,action", [
    ("find an email by subject", "messages.query"),
    ("change email signature", "mail.configure"),
])
def test_recipient_search_keeps_other_mail_operations_discoverable(domain, query, action):
    matches = search_actions(domain, query, limit=5, strict_generic=True)
    actions = {
        item["downstream_action"] if domain == "multi_apps" else item["action"]
        for item in matches
        if domain != "multi_apps" or item.get("adapter") == "thunderbird"
    }
    assert action in actions


@pytest.mark.parametrize("query", ["save the document", "save presentation Ctrl+S", "presentation.save"])
def test_semantic_save_search_reaches_the_next_model_tool_surface(query):
    state = RuntimeState(
        task_id="synthetic-save-discovery",
        domain="libreoffice_impress",
        instruction="Underline all textboxes on slides 2 and 4.",
    )
    semantic = ["presentation.inspect", "shape.format_text", "slide.format_text_roles", "slides.format_text_roles"]
    matches = search_actions(
        state.domain, query, instruction=state.instruction,
        semantic_actions=semantic, strict_generic=True,
    )
    assert "presentation.save" in {item["action"] for item in matches}
    assert "presentation.save" not in semantic
    state.events.append(ExecutionEvent(
        step=1, timestamp_utc="2026-09-01T00:00:00Z",
        proposed={"kind": "catalog", "tool": "tools_search", "arguments": {"query": query}},
        executed=True, result={"status": "ok", "executed": True, "matches": matches},
    ))
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        NoAdapterExecutor(),
    )

    names = {tool["function"]["name"] for tool in agent.tools(state)}

    assert "adapter__presentation_save" in names
    assert not any(item["action"] in {"slide.delete", "shape.delete", "presentation.export"} for item in matches)


def test_failure_summary_keeps_nested_command_diagnostic() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="vs_code",
        instruction="Inspect the current editor state.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "action": "ui.open_view",
                    "arguments": {"window_id": "0x1", "view": "run_and_debug"},
                },
                error={
                    "type": "OPERATION_FAILED",
                    "error": {
                        "code": "OPERATION_FAILED",
                        "message": "command failed",
                        "details": {
                            "argv": ["wmctrl", "-ia", "0x1"],
                            "stderr": "X Error of failed request: BadWindow (invalid Window parameter)",
                        },
                    },
                },
            )
        ],
    )

    summary = last_failure_summary(state)

    assert summary is not None
    assert summary["error_type"] == "OPERATION_FAILED"
    assert "BadWindow" in summary["error_hint"]


def test_recovery_action_description_repeats_usage_and_safe_diagnostic() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Find a report file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "action": "filesystem.find",
                    "arguments": {"roots": ["~/"], "name_patterns": ["report.txt"]},
                },
                error={"type": "PATH_NOT_FOUND", "detail": "path unavailable"},
            )
        ],
    )
    tools = build_tools(
        "os",
        ["filesystem.find"],
        include_gui=False,
        include_control_tools=True,
        strict_generic=True,
    )

    decorated = decorate_recovery_tools(tools, state, mode="catalog_search")
    description = decorated[0]["function"]["description"]

    assert "read the parameter descriptions above" in description
    assert "freshly observed identifier/handle" in description
    assert "path unavailable" in description


def test_later_blocked_calls_keep_original_error_in_model_feedback() -> None:
    state = repeated_path_failure_state()
    original = state.events[-1].error["previous_error"]
    arguments = state.events[-1].proposed["arguments"]
    agent = make_agent()

    for _ in range(6):
        event = agent.execute_proposal(
            state,
            {
                "tool": "adapter__filesystem_find",
                "arguments_raw": json.dumps(arguments),
                "_model_visible_tools": agent.tools(state),
            },
        )
        assert event.executed is False
        assert event.error["type"] == "RepeatedActionBlocked"
        assert event.error["previous_error"] == original
        assert event.proposed["arguments"] == arguments
        assert last_failure_summary(state)["error_type"] == "PATH_NOT_FOUND"

    messages = agent._messages(state, b"screenshot", execution_recovery=True)
    assert "path unavailable" in json.dumps(messages)
    assert "previous_error" not in json.dumps(event.error["previous_error"])


def test_pending_terminal_surface_exposes_audit_controls_and_alternatives() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Find the exact report file in the home directory.",
        pending_terminal={
            "status": "done",
            "tool": "propose_done",
            "event_step": 1,
        },
    )
    agent = make_agent(gui=False)

    tools = agent.tools(state)
    names = {tool["function"]["name"] for tool in tools}
    control_descriptions = {
        tool["function"]["name"]: tool["function"]["description"]
        for tool in tools
        if tool.get("function", {}).get("name") in {"propose_done", "fail_task"}
    }

    assert {"propose_done", "fail_task", "tools_search"}.issubset(names)
    assert any(name.startswith("adapter__") for name in names)
    assert (
        "Audit the previous propose_done result" in control_descriptions["propose_done"]
    )


@pytest.mark.parametrize("recovery_action", ["tools_search", "filesystem.find"])
def test_repeated_gui_error_temporarily_removes_gui_from_replan_surface(
    recovery_action: str,
) -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Find the exact report file in the home directory.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "gui",
                    "tool": "gui_action",
                    "action": "click",
                    "arguments": {"action": "click", "x": 10, "y": 10},
                },
                executed=False,
                error={
                    "type": "RepeatedActionBlocked",
                    "blocked_action": "gui_action",
                    "argument_signature": "synthetic-signature",
                    "error_signature": "RepeatedGUIAction",
                    "block_scope": "episode",
                    "fallback_reason": "repeated_gui_pattern",
                },
            )
        ],
    )

    names = {tool["function"]["name"] for tool in make_agent(gui=True).tools(state)}

    assert "gui_action" not in names
    assert "tools_search" in names
    assert "propose_done" in names
    assert "fail_task" in names
    assert any(name.startswith("adapter__") for name in names)

    original_blocks = state.active_request_blocks()
    state.events.append(
        ExecutionEvent(
            step=2,
            timestamp_utc="2026-08-29T00:00:01Z",
            proposed={
                "kind": "catalog" if recovery_action == "tools_search" else "adapter",
                "tool": recovery_action,
                "action": recovery_action,
                "arguments": {},
            },
            executed=True,
            result={"status": "ok", "matches": []},
        )
    )
    restored_names = {
        tool["function"]["name"] for tool in make_agent(gui=True).tools(state)
    }

    assert "gui_action" in restored_names
    assert state.active_request_blocks() == original_blocks
    assert state.active_request_block(
        "gui_action", state.events[0].proposed["arguments"]
    ) is not None
    assert "gui_action" not in {
        tool["function"]["name"] for tool in make_agent(gui=False).tools(state)
    }


def test_multi_apps_initial_surface_requires_route_discovery() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="multi_apps",
        instruction="Work with a local file.",
    )

    names = {tool["function"]["name"] for tool in make_agent().tools(state)}

    assert "adapter__adapter_call" not in names
    assert "tools_search" in names

    state.events.append(
        ExecutionEvent(
            step=1,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__file_read_text",
                "action": "file.read_text",
                "arguments": {"path": "/tmp/observed.txt"},
            },
            executed=True,
            result={"status": "ok"},
        )
    )
    later_names = {tool["function"]["name"] for tool in make_agent().tools(state)}
    assert "adapter__adapter_call" not in later_names


def test_unproven_multi_apps_route_is_rejected_at_execution_boundary() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="multi_apps",
        instruction="Work with a local file.",
    )
    visible_tools = build_tools(
        "multi_apps",
        ["adapter.call"],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )

    event = make_agent().execute_proposal(
        state,
        {
            "tool": "adapter__adapter_call",
            "arguments_raw": json.dumps(
                {
                    "adapter": "os",
                    "action": "filesystem.find",
                    "payload": {"params": {"roots": ["~/"]}},
                }
            ),
            "_model_visible_tools": visible_tools,
        },
    )

    assert event.executed is False
    assert "requires a matching public tools_search result" in event.error["detail"]


def test_multi_apps_route_is_constrained_after_catalog_search() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="multi_apps",
        instruction="Find a local file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "catalog",
                    "tool": "tools_search",
                    "arguments": {"query": "filesystem.find"},
                },
                executed=True,
                result={
                    "status": "ok",
                    "matches": [
                        {
                            "action": "adapter.call",
                            "adapter": "os",
                            "downstream_action": "filesystem.find",
                        }
                    ],
                },
            )
        ],
    )

    route_tool = next(
        tool
        for tool in make_agent().tools(state)
        if tool["function"]["name"] == "adapter__adapter_call"
    )
    parameters = route_tool["function"]["parameters"]

    assert parameters["x-route"] == {"adapter": "os", "action": "filesystem.find"}
    assert parameters["properties"]["adapter"] == {"const": "os"}
    assert parameters["properties"]["action"] == {"const": "filesystem.find"}
    assert parameters["required"] == ["payload"]


def test_replan_description_does_not_echo_internal_blocked_action_names() -> None:
    state = repeated_path_failure_state()
    state.active_request_blocks = lambda: {  # type: ignore[method-assign]
        "internal": {
            "action": "task.execute",
            "argument_signature": "secret",
            "error_signature": "golden_url",
        }
    }
    state.blocked_actions = lambda: {"task.execute"}  # type: ignore[method-assign]

    search = next(
        tool
        for tool in make_agent().tools(state)
        if tool["function"]["name"] == "tools_search"
    )
    description = search["function"]["description"].casefold()

    assert "task.execute" not in description
    assert "golden_url" not in description
    assert "exact request variant" in description


def test_first_failure_gets_soft_recovery_guidance_without_argument_injection() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Find a report file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__filesystem_find",
                    "action": "filesystem.find",
                    "arguments": {"roots": ["~/bad"]},
                },
                error={"type": "PATH_NOT_FOUND"},
            )
        ],
    )

    message = make_agent()._system_message(state)

    assert "latest model-selected call failed or was rejected" in message
    assert "materially different" in message
    assert "~/bad" not in message


def test_recovery_description_redacts_sensitive_error_labels() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Find a report file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__filesystem_find",
                    "action": "filesystem.find",
                    "arguments": {"roots": ["~/"]},
                },
                error={"type": "EXPECTED_SECRET"},
            )
        ],
    )

    search = next(
        tool
        for tool in make_agent().tools(state)
        if tool["function"]["name"] == "tools_search"
    )
    description = search["function"]["description"].casefold()

    assert "expected_secret" not in description
    assert "expected" not in description
    assert last_failure_summary(state)["error_type"] == "unknown"


def test_recovery_summary_redacts_version_independent_uuid_and_prefix() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Find a report file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__filesystem.find",
                    "action": "filesystem.find",
                    "arguments": {"roots": ["~/"]},
                },
                error={
                    "type": "123e4567-e89b-72d3-a456-426614174000",
                    "detail": "session deadbeef",
                },
            )
        ],
    )

    summary = last_failure_summary(state)

    assert summary is not None
    assert summary["error_type"] == "unknown"
    assert "123e4567" not in str(summary)
    assert "deadbeef" not in str(summary)


def test_repeated_error_precedes_source_phase_surface(monkeypatch) -> None:
    """A phase-specific workflow must still expose a recovery choice after a block."""
    state = repeated_path_failure_state()
    monkeypatch.setattr(
        source_execution_semantics,
        "build_phase_tools",
        lambda _state: [
            {
                "type": "function",
                "function": {
                    "name": "adapter__filesystem_find",
                    "description": "phase action",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )

    names = {tool["function"]["name"] for tool in make_agent(gui=True).tools(state)}

    assert {"tools_search", "propose_done", "fail_task", "gui_action"}.issubset(names)


def test_repeated_error_precedes_terminal_completion_surface(monkeypatch) -> None:
    """A completion heuristic must not hide an active recovery route."""
    state = repeated_path_failure_state()

    # This is the terminal-only surface that the completion heuristic would
    # otherwise return after it believed the mutation phase was complete.
    monkeypatch.setattr(
        completion_recovery,
        "strict_proactive_completion_tools",
        lambda *_args, **_kwargs: [
            {
                "type": "function",
                "function": {
                    "name": "adapter__workbook_inspect",
                    "description": "terminal inspection",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "propose_done",
                    "description": "done",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ],
    )

    names = {tool["function"]["name"] for tool in make_agent(gui=True).tools(state)}

    assert state.requires_replan()
    assert {"tools_search", "propose_done", "fail_task", "gui_action"}.issubset(names)
    assert "adapter__workbook_inspect" not in names


def test_active_block_survives_rejected_completion_and_keeps_recovery_surface(
    monkeypatch,
) -> None:
    state = repeated_path_failure_state()
    state.events.append(
        ExecutionEvent(
            step=3,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={"kind": "completion", "tool": "propose_done", "arguments": {}},
            error={
                "status": "rejected",
                "executed": False,
                "recovery": {"mode": "claim_only"},
            },
        )
    )
    assert not state.requires_replan()
    assert state.active_request_blocks()

    monkeypatch.setattr(
        completion_recovery,
        "strict_proactive_completion_tools",
        lambda *_args, **_kwargs: [
            {
                "type": "function",
                "function": {
                    "name": "propose_done",
                    "description": "done",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )
    names = {tool["function"]["name"] for tool in make_agent(gui=True).tools(state)}

    assert {"tools_search", "fail_task", "gui_action"}.issubset(names)


@pytest.mark.parametrize(
    "action,gate_passed,expected",
    [
        ("filesystem.find", True, False),
        ("filesystem.copy", False, False),
        ("filesystem.copy", True, True),
    ],
)
def test_completion_claim_only_retry_requires_verified_complete_mutation(
    monkeypatch, action, gate_passed, expected,
) -> None:
    agent = make_agent()
    state = RuntimeState(
        task_id="synthetic-completion-retry",
        domain="os",
        instruction="Copy the requested files.",
        completion_rejections=1,
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={"kind": "adapter", "action": action, "arguments": {}},
                executed=True,
                result={"verification": {"passed": True}},
            ),
            ExecutionEvent(
                step=2,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={"kind": "completion", "tool": "propose_done", "arguments": {}},
                error={"status": "rejected", "recovery": {"mode": "claim_only"}},
            ),
        ],
    )
    monkeypatch.setattr(agent, "_generic_completion_gate", lambda _state: {
        "passed": gate_passed,
        "missing": [] if gate_passed else ["another required action has not succeeded"],
    })

    assert agent._completion_claim_only_retry(state) is expected


def test_failed_required_action_is_not_marked_as_completed_attempt() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="libreoffice_calc",
        instruction="Complete the blank totals with spreadsheet formulas.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__cells_set_formulas",
                    "action": "cells.set_formulas",
                    "arguments": {"sheet": "Sheet 1", "writes": []},
                },
                error={"type": "INVALID_ARGUMENT", "detail": "empty writes"},
            )
        ],
    )

    names = {tool["function"]["name"] for tool in make_agent().tools(state)}

    assert "adapter__cells_set_formulas" in names


def test_recovery_action_candidates_are_bounded_and_do_not_choose_arguments() -> None:
    state = repeated_path_failure_state()
    actions = bounded_recovery_actions(
        state,
        required_actions=["filesystem.find"],
        searched_actions=[
            "filesystem.copy",
            "filesystem.find",
            "task.execute",
            "task-execute",
            "unknown.action",
        ],
        selected_actions=["filesystem.rename", "filesystem.copy"],
        limit=3,
    )

    assert set(actions) == {"filesystem.find", "filesystem.copy", "filesystem.rename"}
    assert actions[0] != "filesystem.find"
    assert "task.execute" not in actions


def test_fully_blocked_candidates_keep_one_unblocked_public_inspect() -> None:
    state = repeated_path_failure_state()
    # Simulate a parameterless inspection that has been fully blocked by the
    # repeated-request policy and no remaining semantic candidates.
    state.domain = "libreoffice_calc"
    state.blocked_actions = lambda: {"workbook.inspect"}  # type: ignore[method-assign]

    actions = bounded_recovery_actions(
        state,
        required_actions=[],
        searched_actions=[],
        selected_actions=[],
        limit=3,
    )

    assert actions == ["range.read"]


def test_failure_summary_is_coarse_and_filters_sensitive_fields() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Inspect a file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__task_execute",
                    "action": "task.execute",
                    "arguments": {
                        "task_id": "secret",
                        "evaluator": "secret",
                        "path": "/tmp/example.txt",
                    },
                },
                error={"type": "PATH_NOT_FOUND", "detail": "/tmp/example.txt"},
            )
        ],
    )

    summary = last_failure_summary(state)

    assert summary == {
        "action": "public_action",
        "error_type": "PATH_NOT_FOUND",
        "argument_fields": ["path"],
        "error_hint": "<path>",
    }


def test_failure_summary_reads_nested_adapter_error_code_without_values() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Inspect a file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__filesystem.find",
                    "action": "filesystem.find",
                    "arguments": {"roots": ["~/"], "name_patterns": ["*.txt"]},
                },
                error={
                    "status": "error",
                    "error": {
                        "code": "INVALID_ARGUMENT",
                        "message": "bad path /home/user/private.txt",
                    },
                },
            )
        ],
    )

    summary = last_failure_summary(state)

    assert summary == {
        "action": "filesystem.find",
        "error_type": "INVALID_ARGUMENT",
        "argument_fields": ["name_patterns", "roots"],
        "error_hint": "bad path <path>",
    }
    assert "private" not in str(summary)


def test_failure_summary_prefers_specific_nested_code_over_transport_error() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Inspect a file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__filesystem.find",
                    "action": "filesystem.find",
                    "arguments": {"roots": ["~/"]},
                },
                error={
                    "status": "error",
                    "error": {"code": "INVALID_ARGUMENT", "message": "bad"},
                    "code": "ERROR",
                },
            )
        ],
    )

    assert last_failure_summary(state)["error_type"] == "INVALID_ARGUMENT"


def test_sensitive_outer_error_does_not_hide_specific_nested_code() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Inspect a file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__filesystem.find",
                    "action": "filesystem.find",
                    "arguments": {"roots": ["~/"]},
                },
                error={
                    "code": "ANSWER_SECRET",
                    "error": {"code": "PATH_NOT_FOUND"},
                },
            )
        ],
    )

    summary = last_failure_summary(state)

    assert summary is not None
    assert summary["error_type"] == "PATH_NOT_FOUND"


def test_catalog_recovery_keeps_gui_after_failed_required_mutation() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="libreoffice_calc",
        instruction="Fill the missing totals with formulas.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__cells_set_formulas",
                    "action": "cells.set_formulas",
                    "arguments": {"sheet": "Sheet1", "writes": []},
                },
                error={"type": "INVALID_ARGUMENT"},
            ),
            ExecutionEvent(
                step=2,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "catalog",
                    "tool": "tools_search",
                    "arguments": {"query": "spreadsheet formulas"},
                },
                executed=True,
                result={
                    "matches": [
                        {
                            "action": "cells.set_formulas",
                            "tool_name": "adapter__cells_set_formulas",
                        }
                    ]
                },
            ),
        ],
    )

    names = {tool["function"]["name"] for tool in make_agent(gui=True).tools(state)}

    assert "gui_action" in names


def test_catalog_recovery_moves_single_failed_action_after_alternatives() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Find then copy a report file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__filesystem_find",
                    "action": "filesystem.find",
                    "arguments": {"roots": ["~/bad"]},
                },
                error={"type": "PATH_NOT_FOUND"},
            ),
            ExecutionEvent(
                step=2,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "catalog",
                    "tool": "tools_search",
                    "arguments": {"query": "find or copy a file"},
                },
                executed=True,
                result={
                    "matches": [
                        {"action": "filesystem.find"},
                        {"action": "filesystem.copy"},
                    ]
                },
            ),
        ],
    )

    names = [
        tool["function"]["name"]
        for tool in make_agent().tools(state)
        if tool["function"]["name"].startswith("adapter__")
    ]

    assert names[0] == "adapter__filesystem_copy"
    assert "adapter__filesystem_find" in names


def test_first_error_soft_recovery_tail_places_failed_action_without_shrinking() -> (
    None
):
    instruction = "Find then copy a report file."
    clean_state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction=instruction,
    )
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction=instruction,
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__filesystem_find",
                    "action": "filesystem.find",
                    "arguments": {"roots": ["~/bad"]},
                },
                error={"type": "PATH_NOT_FOUND", "detail": "~/bad"},
            )
        ],
    )
    agent = make_agent(gui=True)
    clean_tools = agent.tools(clean_state)
    recovered_tools = agent.tools(state)
    clean_names = [tool["function"]["name"] for tool in clean_tools]
    recovered_names = [tool["function"]["name"] for tool in recovered_tools]

    # Soft recovery preserves the complete normal surface and only changes
    # Adapter ordering; the model can still retry with its own arguments.
    assert set(recovered_names) == set(clean_names)
    recovered_adapters = [
        name for name in recovered_names if name.startswith("adapter__")
    ]
    assert recovered_adapters[-1] == "adapter__filesystem_find"
    assert {"tools_search", "gui_action", "propose_done", "fail_task"}.issubset(
        recovered_names
    )
    clean_by_name = {
        tool["function"]["name"]: tool["function"]["parameters"] for tool in clean_tools
    }
    recovered_by_name = {
        tool["function"]["name"]: tool["function"]["parameters"]
        for tool in recovered_tools
    }
    # Reordering is the only recovery mutation; the failed values must never
    # become schema defaults, enums, or injected arguments.
    assert recovered_by_name == clean_by_name
    search = next(
        tool for tool in recovered_tools if tool["function"]["name"] == "tools_search"
    )
    assert "soft recovery" in search["function"]["description"]
    assert "~/bad" not in str(recovered_tools)


def test_soft_recovery_does_not_bypass_multi_apps_route_provenance() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="multi_apps",
        instruction="Find a local file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__adapter_call",
                    "action": "adapter.call",
                    "arguments": {"adapter": "os", "action": "filesystem.find"},
                },
                error={"type": "PATH_NOT_FOUND"},
            ),
            ExecutionEvent(
                step=2,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "catalog",
                    "tool": "tools_search",
                    "arguments": {"query": "filesystem.find"},
                },
                executed=True,
                result={
                    "matches": [
                        {
                            "action": "adapter.call",
                            "adapter": "os",
                            "downstream_action": "filesystem.find",
                        }
                    ]
                },
            ),
        ],
    )

    route_tool = next(
        tool
        for tool in make_agent().tools(state)
        if tool["function"]["name"] == "adapter__adapter_call"
    )
    parameters = route_tool["function"]["parameters"]
    assert parameters["x-route"] == {"adapter": "os", "action": "filesystem.find"}
    assert parameters["properties"]["adapter"] == {"const": "os"}
    assert parameters["properties"]["action"] == {"const": "filesystem.find"}


def test_first_error_soft_recovery_preserves_phase_surface(monkeypatch) -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Inspect and copy the observed file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__filesystem.find",
                    "action": "filesystem.find",
                    "arguments": {"roots": ["~/bad"]},
                },
                error={"type": "PATH_NOT_FOUND"},
            )
        ],
    )
    phase_tools = [
        {
            "type": "function",
            "function": {
                "name": "adapter__filesystem_find",
                "description": "find phase",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "adapter__filesystem_copy",
                "description": "copy phase",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]
    monkeypatch.setattr(
        source_execution_semantics,
        "build_phase_tools",
        lambda _state: phase_tools,
    )

    tools = make_agent(gui=True).tools(state)
    names = [tool["function"]["name"] for tool in tools]

    assert names == ["adapter__filesystem_copy", "adapter__filesystem_find"]
    # Phase tools intentionally omit GUI and completion controls; soft
    # recovery must not broaden that contract.
    assert "gui_action" not in names
    assert "propose_done" not in names
    assert "fail_task" not in names


def test_search_result_bridges_canonical_action_to_callable_without_values() -> None:
    matches = search_actions(
        "libreoffice_calc",
        "batch cells formulas totals",
        instruction="Complete blank totals with formulas.",
        limit=8,
        strict_generic=True,
    )
    match = next(item for item in matches if item["action"] == "cells.set_formulas")

    assert match["tool_name"] == "adapter__cells_set_formulas"
    assert match["parameter_summary"]["required"] == ["sheet", "writes"]
    assert match["parameter_summary"]["fields"] == {
        "sheet": {"type": "string"},
        "writes": {"type": "array"},
    }
    assert "task_id" not in match
    assert "golden" not in match
    assert "/" not in str(match["parameter_summary"])


def test_catalog_recovery_does_not_remove_controls() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Copy the observed file to a new directory.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "catalog",
                    "tool": "tools_search",
                    "arguments": {"query": "copy file"},
                },
                executed=True,
                result={
                    "status": "ok",
                    "executed": True,
                    "matches": [
                        {
                            "action": "filesystem.copy",
                            "tool_name": "adapter__filesystem_copy",
                        }
                    ],
                },
            )
        ],
    )
    names = {tool["function"]["name"] for tool in make_agent().tools(state)}

    assert {
        "adapter__filesystem_copy",
        "tools_search",
        "propose_done",
        "fail_task",
    }.issubset(names)


def test_catalog_recovery_rejects_non_public_downstream_routes() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="multi_apps",
        instruction="Use a public file operation.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "catalog",
                    "tool": "tools_search",
                    "arguments": {"query": "file operation"},
                },
                executed=True,
                result={
                    "matches": [
                        {
                            "action": "adapter.call",
                            "adapter": "golden",
                            "downstream_action": "task.execute",
                        },
                        {
                            "action": "adapter.call",
                            "adapter": "os",
                            "downstream_action": "task.inspect",
                        },
                    ]
                },
            )
        ],
    )

    assert recovery_search_routes(state) == []


def test_search_records_only_coarse_failure_context() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Find a local report file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__filesystem_find",
                    "action": "filesystem.find",
                    "arguments": {
                        "roots": ["~/"],
                        "name_patterns": ["report.txt"],
                        "task_id": "should-not-return",
                    },
                },
                error={
                    "type": "PATH_NOT_FOUND",
                    "detail": "/home/user/secret/report.txt",
                },
            )
        ],
    )
    agent = make_agent()

    event = agent.execute_proposal(
        state,
        {
            "tool": "tools_search",
            "arguments_raw": '{"query":"find a report file"}',
        },
    )

    summary = event.result["recovery"]["last_failure"]
    assert summary == {
        "action": "filesystem.find",
        "error_type": "PATH_NOT_FOUND",
        "argument_fields": ["name_patterns", "roots"],
        "error_hint": "<path>",
    }
    assert "secret" not in str(event.result)
    assert "should-not-return" not in str(event.result)


def test_search_does_not_expose_internal_block_signatures() -> None:
    state = repeated_path_failure_state()
    agent = make_agent()

    event = agent.execute_proposal(
        state,
        {
            "tool": "tools_search",
            "arguments_raw": '{"query":"find a local report file"}',
        },
    )

    recovery = event.result["recovery"]
    encoded = str(recovery)
    assert recovery["blocks"]
    assert all(
        set(block).issubset(
            {
                "action",
                "block_scope",
                "fallback_reason",
                "blocked_at_step",
                "blocked_until_step",
            }
        )
        for block in recovery["blocks"]
    )
    assert "argument_signature" not in encoded
    assert "error_signature" not in encoded


@pytest.mark.parametrize(
    "route",
    [
        "task%2eexecute",
        r"task\u002eexecute",
        "ｔａｓｋ．ｅｘｅｃｕｔｅ",
        "assessment/grade/multiple_choice_documents",
        "artifact-materialize",
    ],
)
def test_recovery_summary_redacts_encoded_forbidden_error_routes(route: str) -> None:
    """Recovery descriptions must share the strict model-surface route policy."""
    state = RuntimeState(
        task_id="synthetic-task",
        domain="os",
        instruction="Find a local report file.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-30T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__filesystem_find",
                    "action": "filesystem.find",
                    "arguments": {"roots": ["~/"]},
                },
                executed=False,
                error={"code": route},
            )
        ],
    )

    summary = last_failure_summary(state)
    assert summary is not None
    assert summary["error_type"] == "unknown"
    assert route not in json.dumps(summary, ensure_ascii=False)

    tools = build_tools(
        "os",
        ["tools_search"],
        include_gui=False,
        include_control_tools=True,
        strict_generic=True,
    )
    encoded = json.dumps(
        decorate_recovery_tools(tools, state, mode="structured_error"),
        ensure_ascii=False,
    )
    assert route not in encoded
