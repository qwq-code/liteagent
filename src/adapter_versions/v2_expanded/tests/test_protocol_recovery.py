from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.episode_control import (
    begin_same_vm_soft_restart,
    mark_tool_result_for_audit,
)
from integrations.lite_agent.model_client import (
    StructuredToolModelClient,
    StructuredToolProtocolError,
)
from integrations.lite_agent.reasoning import extract_reasoning_effort_enum
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools
from scripts.run_lite_agent_pilot import (
    model_preflight_failure,
    protocol_recovery_after_error,
    write_invalid_configuration_result,
)


class NoAdapterExecutor:
    def execute(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Adapter execution is not expected")


class RecordingModelClient:
    client = object()

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def propose(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "id": "synthetic-call",
            "tool": "tools_search",
            "arguments_raw": '{"query":"inspect"}',
            "model_actual": "synthetic-model",
            "usage": None,
            "finish_reason": "tool_calls",
            "max_output_tokens_requested": kwargs["output_token_budget"],
            "response_message": {"tool_calls": []},
        }


class _FakeMessage:
    def __init__(
        self,
        tool_calls: list[Any],
        reasoning: str | None = "synthetic",
        content: str | None = None,
    ) -> None:
        self.tool_calls = tool_calls
        self.content = content
        self.reasoning = reasoning

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "content": self.content,
            "reasoning": self.reasoning,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in self.tool_calls
            ],
        }


class _FakeCompletionClient:
    def __init__(
        self,
        *,
        tool_calls: list[Any],
        finish_reason: str,
        effective_reasoning_mode: str | None = None,
        reasoning: str | None = "synthetic",
        content: str | None = None,
    ) -> None:
        self.timeout_values: list[float] = []
        self.requests: list[dict[str, Any]] = []
        message = _FakeMessage(tool_calls, reasoning=reasoning, content=content)
        choice = SimpleNamespace(message=message, finish_reason=finish_reason)
        response = SimpleNamespace(
            choices=[choice],
            model="qwen3.5-4b",
            usage=None,
            effective_reasoning_mode=effective_reasoning_mode,
        )
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create(response))
        )

    def _create(self, response: Any):
        def create(**kwargs: Any) -> Any:
            self.requests.append(kwargs)
            return response

        return create

    def with_options(self, *, timeout: float) -> "_FakeCompletionClient":
        self.timeout_values.append(timeout)
        return self


def _tool_call(arguments: str, name: str = "spreadsheet.write_range") -> Any:
    return SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _write_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "spreadsheet.write_range",
                "description": "Write a rectangular range.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sheet": {"type": "string"},
                        "range": {"type": "string"},
                        "values": {
                            "type": "array",
                            "items": {"type": "array"},
                        },
                    },
                    "required": ["sheet", "range", "values"],
                    "additionalProperties": False,
                },
            },
        }
    ]


def _schema_tools(name: str, schema: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": "Synthetic public-schema contract.",
                "parameters": schema,
            },
        }
    ]


def _model_client(
    tool_calls: list[Any], finish_reason: str
) -> StructuredToolModelClient:
    return StructuredToolModelClient(
        base_url="http://unused/v1",
        api_key="EMPTY",
        request_timeout_seconds=1,
        client=_FakeCompletionClient(
            tool_calls=tool_calls,
            finish_reason=finish_reason,
        ),
    )


def _large_state() -> RuntimeState:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="multi_apps",
        instruction="Inspect the current application and choose the next public action.",
    )
    for step in range(1, 18):
        state.events.append(
            ExecutionEvent(
                step=step,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__generic_observe",
                    "action": "generic.observe",
                    "arguments": {"path": f"/tmp/observed-{step}.dat"},
                },
                executed=True,
                result={
                    "context_hint": {
                        "path": f"/tmp/observed-{step}.dat",
                        "matches": [f"/tmp/item-{index}.dat" for index in range(20)],
                        "text": (
                            "Observed application state with ordinary fields. " * 160
                        ),
                        "guidance": "Use the exact observed target before selecting a mutation.",
                    }
                },
            )
        )
    return state


def _batch_recovery_state() -> RuntimeState:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="multi_apps",
        instruction="Read the observed PDF files and prepare the requested table.",
    )
    files = [
        {
            "path": f"/tmp/source-{index}.pdf",
            "status": "ok",
            "source_kind": "pdf",
            "returned_chars": 4_000,
            "extracted_chars": 4_000,
            "source_start_char": 0,
            "source_end_char": 4_000,
            "source_total_chars": 4_000,
            "source_truncated": False,
            "truncated": False,
            "text": (f"institution-{index} observed values 59 27 " * 120)[:4_000],
        }
        for index in range(9)
    ]
    state.events.append(
        ExecutionEvent(
            step=1,
            timestamp_utc="2026-08-30T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__pdf_extract_text_batch",
                "action": "pdf.extract_text_batch",
                "arguments": {"input_pattern": "*.pdf", "cwd_source": "explicit"},
            },
            executed=True,
            result={
                "context_hint": {
                    "input_directory": "/tmp",
                    "input_pattern": "*.pdf",
                    "matched_count": 9,
                    "files": files,
                }
            },
        )
    )
    for step, action in enumerate(
        (
            "spreadsheet.inspect_current",
            "spreadsheet.read_file",
            "spreadsheet.inspect_current",
        ),
        start=2,
    ):
        state.events.append(
            ExecutionEvent(
                step=step,
                timestamp_utc="2026-08-30T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": f"adapter__{action.replace('.', '_')}",
                    "action": action,
                    "arguments": {},
                },
                executed=True,
                result={"status": "ok"},
            )
        )
    state.events.append(
        ExecutionEvent(
            step=5,
            timestamp_utc="2026-08-30T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__spreadsheet_write_range",
                "action": "spreadsheet.write_range",
                "arguments": {"sheet": "Sheet1", "range": "B2:I10"},
            },
            executed=False,
            error={"type": "ValidationError", "detail": "values required"},
        )
    )
    return state


def _agent(client: RecordingModelClient) -> LiteAgent:
    return LiteAgent(
        LiteAgentConfig(
            base_url="http://unused/v1",
            enable_thinking=True,
            max_output_tokens=4096,
        ),
        NoAdapterExecutor(),  # type: ignore[arg-type]
        model_client=client,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize("domain", ["libreoffice_writer", "multi_apps"])
def test_normal_next_action_uses_tool_results_and_screenshot(domain: str) -> None:
    agent = _agent(RecordingModelClient())
    state = _large_state()
    state.domain = domain

    messages = agent._messages(state, b"png")
    state_text = messages[2]["content"][0]["text"]
    _header, encoded = state_text.split("\n", 1)
    summary, end = json.JSONDecoder().raw_decode(encoded)

    assert encoded[end:] == (
        "\nChoose the single next action using the instruction, latest tool results, "
        "and current screenshot."
    )
    if domain == "multi_apps":
        assert len(json.dumps(summary, ensure_ascii=False)) <= 9_000
        assert summary[-1]["step"] == 17
    else:
        assert summary == state.context_summary(strict_generic=True)
    assert messages[1]["content"] == state.instruction
    assert messages[2]["content"][1]["image_url"]["url"] == agent._image_url(b"png")


def test_api_only_message_uses_string_content_for_local_model_compatibility() -> None:
    agent = LiteAgent(
        LiteAgentConfig(
            base_url="http://unused/v1",
            include_gui=False,
            enable_thinking=True,
            max_output_tokens=4096,
        ),
        NoAdapterExecutor(),  # type: ignore[arg-type]
        model_client=RecordingModelClient(),  # type: ignore[arg-type]
    )
    messages = agent._messages(_large_state(), b"png")
    assert len(messages) == 2
    assert isinstance(messages[1]["content"], str)
    assert "Current truthful execution state" in messages[1]["content"]


def test_protocol_recovery_message_is_bounded_and_structured() -> None:
    client = RecordingModelClient()
    agent = _agent(client)
    state = _large_state()

    messages = agent._messages(state, b"png", protocol_recovery=True)
    state_text = messages[2]["content"][0]["text"]

    assert "Protocol recovery is active" in messages[0]["content"]
    assert "Return exactly one tool call now." in state_text
    assert len(state_text) < 9_500
    assert "preview" not in state_text
    assert messages[2]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


def test_protocol_recovery_includes_bounded_schema_rules_without_model_values() -> None:
    client = RecordingModelClient()
    agent = _agent(client)
    state = _large_state()

    messages = agent._messages(
        state,
        b"png",
        protocol_recovery=True,
        protocol_error={
            "missing_fields": ["evidence"],
            "schema_hints": [
                "evidence: type must be 'array'",
                "evidence.*: type must be 'string' or 'object'",
            ],
        },
    )

    system = messages[0]["content"]
    assert "Public schema rules violated" in system
    assert "evidence: type must be 'array'" in system
    assert "evidence.*: type must be 'string' or 'object'" in system
    assert len(system) < 9_000


def test_protocol_recovery_explains_how_to_complete_a_missing_field() -> None:
    client = RecordingModelClient()
    agent = _agent(client)
    state = _large_state()

    system = agent._messages(
        state,
        b"png",
        protocol_recovery=True,
        protocol_error={
            "tool": "adapter__range_write",
            "missing_fields": ["values"],
            "schema_hints": ["<root>: required fields: values"],
            "recovery_attempt": 2,
        },
    )[0]["content"]

    assert "adapter__range_write call was incomplete" in system
    assert "every required top-level field present" in system
    assert "small valid source write" in system
    assert "after 2 rejected responses" in system


@pytest.mark.parametrize("schema_hints", [["payload: type must be 'object'"], []])
def test_repeated_protocol_recovery_changes_request_without_missing_fields(
    schema_hints: list[str],
) -> None:
    agent = _agent(RecordingModelClient())
    state = _large_state()
    error = {
        "tool": "adapter__adapter_call",
        "missing_fields": [],
        "schema_hints": schema_hints,
    }
    first = agent._messages(
        state, b"png", protocol_recovery=True,
        protocol_error={**error, "recovery_attempt": 1},
    )
    repeated = agent._messages(
        state, b"png", protocol_recovery=True,
        protocol_error={**error, "recovery_attempt": 2},
    )

    assert first[0] != repeated[0]
    assert first[1:] == repeated[1:]
    assert "after 2 rejected responses" in repeated[0]["content"]
    assert "None of those calls executed" in repeated[0]["content"]


def test_rejected_model_action_automatically_uses_bounded_recovery() -> None:
    """Execution rejection must compact the following turn even without a retry flag."""
    client = RecordingModelClient()
    agent = _agent(client)
    state = _large_state()
    state.events.append(
        ExecutionEvent(
            step=len(state.events) + 1,
            timestamp_utc="2026-08-30T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__spreadsheet_write_range",
                "action": "spreadsheet.write_range",
                "arguments": {"sheet": "Sheet1", "range": "A1:B2"},
            },
            executed=False,
            error={
                "type": "ValidationError",
                "detail": "missing required values",
            },
        )
    )

    messages = agent._messages(state, b"png")
    state_text = messages[2]["content"][0]["text"]

    assert "Compact truthful execution state" in state_text
    assert len(state_text) < 9_500
    assert "Bounded execution recovery is active" in messages[0]["content"]
    assert "missing required values" not in messages[0]["content"]


@pytest.mark.parametrize("repeated", [False, True])
def test_execution_recovery_preserves_wrapped_command_diagnostics(repeated) -> None:
    from integrations.lite_agent.context_projection import failure_summary
    from integrations.lite_agent.recovery_surface import last_failure_summary

    error = {
        "status": "error",
        "error_code": "DOWNSTREAM_FAILED",
        "error": "downstream Adapter call failed",
        "details": {
            "adapter": "os",
            "response": {
                "status": "error",
                "duration_ms": 120,
                "logs": ["diagnostic log " * 200],
                "error": {
                    "code": "COMMAND_FAILED",
                    "message": "command returned an unexpected status",
                    "details": {
                        "argv": ["diagnostic-tool", "--invalid"],
                        "cwd": "/tmp/project",
                        "returncode": 2,
                        "stderr": "Usage: diagnostic-tool [options]\n"
                        + "option help\n" * 200,
                        "stdout": "",
                    },
                },
            },
        },
    }
    if repeated:
        error = {"type": "RepeatedActionBlocked", "previous_error": error}
    original = json.dumps(error, sort_keys=True)
    state = RuntimeState(
        task_id="synthetic-command-recovery",
        domain="multi_apps",
        instruction="Inspect the command output.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-09-05T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__adapter_call",
                    "action": "adapter.call",
                    "arguments": {
                        "adapter": "os",
                        "action": "command.run",
                        "payload": {
                            "params": {"argv": ["diagnostic-tool", "--invalid"]}
                        },
                    },
                },
                executed=False,
                error=error,
            )
        ],
    )

    messages = _agent(RecordingModelClient())._messages(state, b"png")
    state_text = messages[2]["content"][0]["text"]
    projected = state.context_summary(strict_generic=True)[-1]["error"]

    assert "COMMAND_FAILED" in state_text
    assert "command returned an unexpected status" in state_text
    assert "Usage: diagnostic-tool [options]" in state_text
    assert '"returncode": 2' in state_text
    assert len(json.dumps(projected, ensure_ascii=False)) <= 1_200
    assert len(state_text) < 9_500
    assert failure_summary(state.events[-1])["error_type"] == "COMMAND_FAILED"
    assert last_failure_summary(state)["error_type"] == "COMMAND_FAILED"
    assert (
        last_failure_summary(state)["error_hint"]
        == "command returned an unexpected status"
    )
    assert json.dumps(error, sort_keys=True) == original


def test_soft_restart_marker_keeps_bounded_recovery_after_executed_followup() -> None:
    """Recovery remains compact when the latest event itself succeeded."""
    state = RuntimeState(
        task_id="synthetic-soft-restart",
        domain="libreoffice_impress",
        instruction="Inspect the current presentation and make the requested change.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-30T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__presentation_inspect",
                    "action": "presentation.inspect",
                    "arguments": {},
                },
                executed=True,
                result={"status": "ok"},
            )
        ],
    )
    begin_same_vm_soft_restart(
        state,
        "local_step_limit",
        max_retries=1,
        trigger_step=1,
        context_limit=4,
    )
    state.events.append(
        ExecutionEvent(
            step=2,
            timestamp_utc="2026-08-30T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__presentation_inspect",
                "action": "presentation.inspect",
                "arguments": {},
            },
            executed=True,
            result={"status": "ok"},
        )
    )
    assert state.events[-1].executed is True
    assert AgentProtocolMixin._execution_recovery_pending(state) is True

    agent = _agent(RecordingModelClient())
    messages = agent._messages(state, b"png")
    state_text = messages[2]["content"][0]["text"]
    assert "Compact truthful execution state" in state_text
    assert len(state_text) < 9_500
    assert "Bounded execution recovery is active" in messages[0]["content"]

    # Once both transient handoff markers are consumed, an ordinary turn uses
    # the normal truthful projection again.
    state.recovery_context = None
    state.pending_runner_replan = None
    assert AgentProtocolMixin._execution_recovery_pending(state) is False
    normal_messages = agent._messages(state, b"png")
    assert (
        "Current truthful execution state" in normal_messages[2]["content"][0]["text"]
    )


def test_soft_restart_projection_retains_ledger_for_bounded_followups() -> None:
    """The restart handoff survives three follow-up proposals, then expires."""
    state = RuntimeState(
        task_id="synthetic-retention",
        domain="libreoffice_impress",
        instruction="Inspect the presentation and apply the requested change.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-30T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__shape_format_text",
                    "action": "shape.format_text",
                    "arguments": {
                        "slide": 0,
                        "selector": {"path": [2]},
                        "underline": True,
                    },
                },
                executed=True,
                result={"status": "ok"},
            )
        ],
    )
    mark_tool_result_for_audit(state, state.events[-1])
    decision = begin_same_vm_soft_restart(
        state,
        "local_step_limit",
        max_retries=1,
        trigger_step=1,
        context_limit=4,
    )
    assert decision.accepted is True
    assert state.recovery_projection_turns_remaining == 3
    agent = _agent(RecordingModelClient())

    def assert_bounded_with_latest(step: int) -> None:
        messages = agent._messages(state, b"png")
        state_text = messages[2]["content"][0]["text"]
        assert "Compact truthful execution state" in state_text
        assert len(state_text) < 9_500
        payload = state_text.split("\n", 1)[1].rsplit(
            "\nReturn exactly one tool call now.", 1
        )[0]
        projection = json.loads(payload)
        ledgers = [
            item["recovery_mutation_ledger"]
            for item in projection
            if isinstance(item, dict) and "recovery_mutation_ledger" in item
        ]
        assert ledgers
        assert ledgers[-1][-1]["step"] == step

    # The initial handoff is bounded and audits the triggering event.
    assert_bounded_with_latest(1)
    assert state.record_model_audit({"tool": "adapter__presentation_inspect"})
    state.pending_runner_replan = None

    # Three valid follow-up proposals each retain the latest model-facing ledger.
    for step in range(2, 5):
        state.events.append(
            ExecutionEvent(
                step=step,
                timestamp_utc="2026-08-30T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__shape_format_text",
                    "action": "shape.format_text",
                    "arguments": {
                        "slide": step - 1,
                        "selector": {"path": [step]},
                        "underline": True,
                    },
                },
                executed=True,
                result={"status": "ok"},
            )
        )
        mark_tool_result_for_audit(state, state.events[-1])
        assert_bounded_with_latest(step)
        assert state.record_model_audit({"tool": "adapter__presentation_inspect"})
        if step < 4:
            assert state.recovery_context is not None
            assert state.recovery_projection_turns_remaining == 4 - step
        else:
            assert state.recovery_context is None
            assert state.recovery_projection_turns_remaining == 0

    # Expiry restores the ordinary truthful projection; no restart remains.
    normal = agent._messages(state, b"png")
    assert "Current truthful execution state" in normal[2]["content"][0]["text"]

    # An explicit marker clear also restores normal context even if a counter
    # was left by an older caller.
    begin_same_vm_soft_restart(
        state,
        "explicit_clear_probe",
        max_retries=2,
        trigger_step=4,
        context_limit=4,
    )
    state.recovery_context = None
    state.pending_runner_replan = None
    explicit_clear = agent._messages(state, b"png")
    assert "Current truthful execution state" in explicit_clear[2]["content"][0]["text"]


def test_normal_state_without_soft_restart_stays_unbounded() -> None:
    state = RuntimeState(
        task_id="synthetic-normal",
        domain="libreoffice_impress",
        instruction="Inspect the current presentation.",
    )
    agent = _agent(RecordingModelClient())
    messages = agent._messages(state, b"png")
    assert "Current truthful execution state" in messages[2]["content"][0]["text"]


def test_batch_recovery_uses_working_set_budget_without_expanding_plain_retries() -> (
    None
):
    agent = _agent(RecordingModelClient())
    state = _batch_recovery_state()

    messages = agent._messages(state, b"png")
    state_text = messages[2]["content"][0]["text"]
    payload = state_text.split("\n", 1)[1].rsplit(
        "\nReturn exactly one tool call now.", 1
    )[0]
    projected = json.loads(payload)

    assert len(state_text) <= 16_500
    batch_files = []
    for entry in projected:
        if not isinstance(entry, dict):
            continue
        for observation in entry.get("durable_observations", []):
            candidate = (
                observation.get("observation")
                if isinstance(observation, dict)
                else None
            )
            if (
                isinstance(candidate, dict)
                and candidate.get("observation_type") == "text_batch"
            ):
                batch_files.extend(candidate.get("files", []))
    assert len(batch_files) == 9
    assert (
        min(
            sum(
                len(chunk.get("text", ""))
                for chunk in file.get("chunks", [])
                if isinstance(chunk, dict)
            )
            for file in batch_files
        )
        >= 400
    )


def test_protocol_recovery_preserves_tools_and_reasoning_budget() -> None:
    client = RecordingModelClient()
    agent = _agent(client)
    state = _large_state()

    normal_tools = agent.tools(state)
    agent.propose(state, b"png", protocol_recovery=True)

    call = client.calls[0]
    assert call["tools"] == normal_tools
    assert call["enable_thinking"] is True
    assert call["output_token_budget"] == 4096
    assert "Protocol recovery is active" in call["messages"][0]["content"]


def test_truncated_protocol_recovery_gets_bounded_extra_output_budget() -> None:
    client = RecordingModelClient()
    agent = _agent(client)

    agent.propose(
        _large_state(),
        b"png",
        protocol_recovery=True,
        protocol_error={"finish_reason": "length"},
    )

    assert client.calls[0]["output_token_budget"] == 4096


@pytest.mark.parametrize("action", ["range.write", "cells.set_formulas"])
def test_direct_calc_matrix_writes_receive_bounded_json_output_budget(action: str) -> None:
    class _BudgetProbe(AgentProtocolMixin):
        config = SimpleNamespace(max_output_tokens=384)

        def tools(self, state: RuntimeState) -> list[dict[str, Any]]:
            return build_tools(
                state.domain,
                [action],
                include_gui=False,
                include_control_tools=False,
                strict_generic=True,
            )

    state = RuntimeState(
        task_id="synthetic-calc-token-budget",
        domain="libreoffice_calc",
        instruction="Write formulas into the spreadsheet cells.",
    )

    assert _BudgetProbe().output_token_budget(state) == 4096


def test_complete_tool_call_is_accepted_when_reasoning_finish_is_length() -> None:
    arguments = '{"sheet":"Sheet1","range":"A1:A1","values":[["ok"]]}'
    client = _model_client([_tool_call(arguments)], "length")

    proposal = client.propose(
        model="qwen3.5-4b",
        messages=[],
        tools=_write_tools(),
        temperature=0.0,
        output_token_budget=4096,
        enable_thinking=True,
    )

    assert proposal["structured_call_validated"] is True
    assert proposal["finish_reason"] == "length"
    assert proposal["arguments_raw"] == arguments


def test_same_tool_batch_requires_replanning_from_latest_state_and_tools() -> None:
    first = _tool_call('{"sheet":"Sheet1","range":"A1:A1","values":[["one"]]}')
    second = _tool_call('{"sheet":"Sheet1","range":"A2:A2","values":[["two"]]}')
    second.id = "call-2"
    transport = _FakeCompletionClient(tool_calls=[first, second], finish_reason="tool_calls")
    client = StructuredToolModelClient(
        base_url="http://unused/v1", api_key="EMPTY", request_timeout_seconds=1,
        client=transport,
    )
    arguments = dict(
        model="qwen3.5-4b", messages=[], tools=_write_tools(), temperature=0.0,
        output_token_budget=384, enable_thinking=True,
    )

    with pytest.raises(StructuredToolProtocolError, match="got 2"):
        client.propose(**arguments)
    # A changed surface can no longer accept the previously proposed writes.
    # Recovery must consult the provider again instead of replaying A2.
    fresh_call = _tool_call('{}', name='inspect_current')
    transport.chat.completions.create = transport._create(SimpleNamespace(
        choices=[SimpleNamespace(message=_FakeMessage([fresh_call]), finish_reason='tool_calls')],
        model='qwen3.5-4b', usage=None,
    ))
    arguments['messages'] = [{'role': 'user', 'content': 'No batch call executed; inspect the current target.'}]
    arguments['tools'] = _schema_tools('inspect_current', {'type': 'object', 'properties': {}, 'additionalProperties': False})
    proposal = client.propose(**arguments)
    assert len(transport.requests) == 2
    assert proposal['tool'] == 'inspect_current'
    assert proposal['arguments_raw'] == '{}'
    assert transport.requests[-1]['messages'][1:] == arguments['messages']
    assert transport.requests[-1]['messages'][0]['role'] == 'system'


def test_mixed_tool_batch_remains_rejected() -> None:
    first = _tool_call('{"sheet":"Sheet1","range":"A1:A1","values":[["one"]]}')
    second = _tool_call("{}", name="another.tool")
    client = _model_client([first, second], "tool_calls")

    with pytest.raises(StructuredToolProtocolError, match="got 2"):
        client.propose(
            model="qwen3.5-4b", messages=[], tools=_write_tools(), temperature=0.0,
            output_token_budget=384, enable_thinking=True,
        )


def test_model_request_carries_explicit_reasoning_effort_and_observation() -> None:
    arguments = '{"sheet":"Sheet1","range":"A1:A1","values":[["ok"]]}'
    transport = _FakeCompletionClient(
        tool_calls=[_tool_call(arguments)],
        finish_reason="tool_calls",
        effective_reasoning_mode="xhigh",
    )
    client = StructuredToolModelClient(
        base_url="http://unused/v1",
        api_key="EMPTY",
        request_timeout_seconds=1,
        client=transport,
    )

    proposal = client.propose(
        model="qwen3.5-4b",
        messages=[],
        tools=_write_tools(),
        temperature=0.0,
        output_token_budget=4096,
        enable_thinking=True,
        reasoning_effort="xhigh",
    )

    assert transport.requests[0]["reasoning_effort"] == "xhigh"
    assert proposal["reasoning_effort_requested"] == "xhigh"
    assert proposal["reasoning_observed"] is True


def test_qwen_binary_thinking_mode_uses_only_enable_thinking() -> None:
    arguments = '{"sheet":"Sheet1","range":"A1:A1","values":[["ok"]]}'
    transport = _FakeCompletionClient(
        tool_calls=[_tool_call(arguments)],
        finish_reason="tool_calls",
    )
    client = StructuredToolModelClient(
        base_url="http://unused/v1",
        api_key="EMPTY",
        request_timeout_seconds=1,
        client=transport,
    )

    proposal = client.propose(
        model="qwen3.5-4b",
        messages=[],
        tools=_write_tools(),
        temperature=0.0,
        output_token_budget=4096,
        enable_thinking=True,
        reasoning_mode="thinking",
    )

    request = transport.requests[0]
    assert "reasoning_effort" not in request
    assert request["extra_body"]["chat_template_kwargs"] == {"enable_thinking": True}
    assert proposal["reasoning_mode_requested"] == "thinking"
    assert proposal["reasoning_mode_effective"] == "thinking"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("presence_penalty", None),
        ("presence_penalty", 0.0),
        ("presence_penalty", 1.0),
        ("thinking_token_budget", None),
        ("thinking_token_budget", 1024),
        ("thinking_token_budget", 1536),
        ("tool_call_stop_sequence", None),
        ("tool_call_stop_sequence", "\n</function>\n</tool_call>"),
    ],
)
@pytest.mark.parametrize("recovery", [False, True])
def test_optional_generation_setting_reaches_captured_request_unchanged(
    field, value, recovery
) -> None:
    transport = _FakeCompletionClient(
        tool_calls=[_tool_call("{}", name="adapter__document_inspect")],
        finish_reason="tool_calls",
    )
    captured = []
    client = StructuredToolModelClient(
        base_url="http://unused/v1",
        api_key="EMPTY",
        request_timeout_seconds=1,
        client=transport,
        request_observer=captured.append,
    )
    agent = LiteAgent(
        LiteAgentConfig(
            base_url="http://unused/v1",
            enable_thinking=True,
            reasoning_mode="thinking",
            max_output_tokens=4096,
            **{field: value},
        ),
        NoAdapterExecutor(),
        model_client=client,
    )
    state = RuntimeState(
        task_id="synthetic-generation-setting",
        domain="libreoffice_writer",
        instruction="Read the current document paragraphs.",
    )

    proposal = agent.propose(state, b"png", protocol_recovery=recovery)

    request = transport.requests[0]
    assert captured == [request]
    body = request["extra_body"] if field == "thinking_token_budget" else request
    if field == "tool_call_stop_sequence":
        if value is None:
            assert "stop" not in request
            assert "include_stop_str_in_output" not in request["extra_body"]
        else:
            assert request["stop"] == [value]
            assert request["extra_body"]["include_stop_str_in_output"] is True
        assert field not in request
    elif value is None:
        assert field not in body
    else:
        assert body[field] == value
    assert request["tool_choice"] == "required"
    assert request["parallel_tool_calls"] is False
    assert request["temperature"] == 0
    assert request["max_tokens"] == 4096
    assert request["extra_body"]["chat_template_kwargs"] == {"enable_thinking": True}
    assert proposal["arguments_raw"] == "{}"


def test_qwen_binary_mode_rejects_missing_thinking_observation() -> None:
    arguments = '{"sheet":"Sheet1","range":"A1:A1","values":[["ok"]]}'
    transport = _FakeCompletionClient(
        tool_calls=[_tool_call(arguments)],
        finish_reason="tool_calls",
        reasoning=None,
    )
    client = StructuredToolModelClient(
        base_url="http://unused/v1",
        api_key="EMPTY",
        request_timeout_seconds=1,
        client=transport,
    )

    with pytest.raises(StructuredToolProtocolError, match="thinking mode") as raised:
        client.propose(
            model="qwen3.5-4b",
            messages=[],
            tools=_write_tools(),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
            reasoning_mode="thinking",
        )

    assert raised.value.configuration_failure is True


def test_qwen_binary_non_thinking_mode_sends_false_switch() -> None:
    arguments = '{"sheet":"Sheet1","range":"A1:A1","values":[["ok"]]}'
    transport = _FakeCompletionClient(
        tool_calls=[_tool_call(arguments)],
        finish_reason="tool_calls",
        reasoning=None,
    )
    client = StructuredToolModelClient(
        base_url="http://unused/v1",
        api_key="EMPTY",
        request_timeout_seconds=1,
        client=transport,
    )

    proposal = client.propose(
        model="qwen3.5-4b",
        messages=[],
        tools=_write_tools(),
        temperature=0.0,
        output_token_budget=4096,
        enable_thinking=False,
        reasoning_mode="non_thinking",
    )

    assert transport.requests[0]["extra_body"]["chat_template_kwargs"] == {
        "enable_thinking": False
    }
    assert proposal["reasoning_mode_effective"] == "non_thinking"


def test_configured_reasoning_effort_requires_provider_attestation() -> None:
    arguments = '{"sheet":"Sheet1","range":"A1:A1","values":[["ok"]]}'
    client = _model_client([_tool_call(arguments)], "tool_calls")

    with pytest.raises(StructuredToolProtocolError, match="did not attest") as raised:
        client.propose(
            model="qwen3.5-4b",
            messages=[],
            tools=_write_tools(),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
            reasoning_effort="xhigh",
        )

    assert raised.value.configuration_failure is True
    assert raised.value.trace_record()["configuration_failure"] is True


def test_configured_reasoning_effort_rejects_provider_downgrade() -> None:
    arguments = '{"sheet":"Sheet1","range":"A1:A1","values":[["ok"]]}'
    transport = _FakeCompletionClient(
        tool_calls=[_tool_call(arguments)],
        finish_reason="tool_calls",
        effective_reasoning_mode="high",
    )
    client = StructuredToolModelClient(
        base_url="http://unused/v1",
        api_key="EMPTY",
        request_timeout_seconds=1,
        client=transport,
    )

    with pytest.raises(StructuredToolProtocolError, match="does not match") as raised:
        client.propose(
            model="qwen3.5-4b",
            messages=[],
            tools=_write_tools(),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
            reasoning_effort="xhigh",
        )

    assert raised.value.configuration_failure is True


def test_model_response_identity_mismatch_is_rejected() -> None:
    arguments = '{"sheet":"Sheet1","range":"A1:A1","values":[["ok"]]}'
    wrong_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=_FakeMessage([_tool_call(arguments)]),
                finish_reason="tool_calls",
            )
        ],
        model="wrong-model",
        usage=None,
    )
    transport = _FakeCompletionClient(
        tool_calls=[_tool_call(arguments)],
        finish_reason="tool_calls",
    )
    transport.chat.completions.create = transport._create(wrong_response)
    client = StructuredToolModelClient(
        base_url="http://unused/v1",
        api_key="EMPTY",
        request_timeout_seconds=1,
        client=transport,
    )

    with pytest.raises(StructuredToolProtocolError, match="model identity") as raised:
        client.propose(
            model="expected-model",
            messages=[],
            tools=_write_tools(),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
            expected_model="expected-model",
        )

    assert raised.value.configuration_failure is True


def test_model_response_effective_reasoning_mode_is_recorded() -> None:
    arguments = '{"sheet":"Sheet1","range":"A1:A1","values":[["ok"]]}'
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=_FakeMessage([_tool_call(arguments)]),
                finish_reason="tool_calls",
            )
        ],
        model="qwen3.5-4b",
        usage=None,
        effective_reasoning_mode="xhigh",
    )
    transport = _FakeCompletionClient(
        tool_calls=[_tool_call(arguments)],
        finish_reason="tool_calls",
    )
    transport.chat.completions.create = transport._create(response)
    client = StructuredToolModelClient(
        base_url="http://unused/v1",
        api_key="EMPTY",
        request_timeout_seconds=1,
        client=transport,
    )

    proposal = client.propose(
        model="qwen3.5-4b",
        messages=[],
        tools=_write_tools(),
        temperature=0.0,
        output_token_budget=4096,
        enable_thinking=True,
        expected_model="qwen3.5-4b",
    )

    assert proposal["reasoning_effort_effective"] == "xhigh"


def test_reasoning_openapi_enum_is_taken_only_from_explicit_schema() -> None:
    document = {
        "components": {
            "schemas": {
                "ChatCompletionRequest": {
                    "properties": {
                        "reasoning_effort": {"enum": ["none", "xhigh", "unknown"]}
                    }
                }
            }
        }
    }
    assert extract_reasoning_effort_enum(document) == ("none", "xhigh")
    assert extract_reasoning_effort_enum({"description": "reasoning_effort=max"}) == ()


def test_reasoning_openapi_nullable_anyof_enum_is_supported() -> None:
    document = {
        "components": {
            "schemas": {
                "ChatCompletionRequest": {
                    "properties": {
                        "reasoning_effort": {
                            "anyOf": [
                                {
                                    "type": "string",
                                    "enum": ["none", "high", "max"],
                                },
                                {"type": "null"},
                            ]
                        }
                    }
                }
            }
        }
    }

    assert extract_reasoning_effort_enum(document) == ("none", "high", "max")


def test_incomplete_tool_call_is_recoverable_and_retains_raw_response() -> None:
    arguments = '{"sheet":"Sheet1","range":"A1:A1"}'
    client = _model_client([_tool_call(arguments)], "length")

    with pytest.raises(StructuredToolProtocolError) as raised:
        client.propose(
            model="qwen3.5-4b",
            messages=[],
            tools=_write_tools(),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
        )

    error = raised.value
    assert error.missing_fields == ("values",)
    assert error.schema_hints == ("<root>: required fields: values",)
    assert error.trace_record()["schema_hints"] == list(error.schema_hints)
    assert error.response_snapshot["finish_reason"] == "length"
    assert (
        error.response_snapshot["message"]["tool_calls"][0]["function"]["arguments"]
        == arguments
    )
    assert arguments not in str(error)


def test_schema_hints_describe_type_without_echoing_invalid_value() -> None:
    arguments = '{"sheet":"Sheet1","range":"A1:A1","values":"private-value"}'
    client = _model_client([_tool_call(arguments)], "tool_calls")

    with pytest.raises(StructuredToolProtocolError) as raised:
        client.propose(
            model="qwen3.5-4b",
            messages=[],
            tools=_write_tools(),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
        )

    error = raised.value
    assert any("values: type must be 'array'" in hint for hint in error.schema_hints)
    assert "native JSON array of concise strings" not in " ".join(error.schema_hints)
    assert "private-value" not in " ".join(error.schema_hints)


def test_schema_hints_render_numeric_bounds_as_direct_constraints() -> None:
    schema = {
        "type": "object",
        "properties": {"zoom": {"type": "integer", "minimum": 20, "maximum": 600}},
        "required": ["zoom"],
        "additionalProperties": False,
    }
    client = _model_client(
        [_tool_call('{"zoom":18}', "synthetic.zoom")],
        "tool_calls",
    )

    with pytest.raises(StructuredToolProtocolError) as raised:
        client.propose(
            model="qwen3.5-4b",
            messages=[],
            tools=_schema_tools("synthetic.zoom", schema),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
        )

    assert raised.value.schema_hints == ("zoom: must be >= 20",)


def test_schema_hints_explain_native_object_and_control_character_escaping() -> None:
    schema = {
        "type": "object",
        "properties": {"payload": {"type": "object"}},
        "required": ["payload"],
    }
    arguments = json.dumps({"payload": '{"text":"private-value\tnext\nrow"}'})
    client = _model_client([_tool_call(arguments, "synthetic.object")], "tool_calls")

    with pytest.raises(StructuredToolProtocolError) as raised:
        client.propose(
            model="qwen3.5-4b", messages=[],
            tools=_schema_tools("synthetic.object", schema), temperature=0.0,
            output_token_budget=4096, enable_thinking=True,
        )

    hints = " ".join(raised.value.schema_hints)
    assert "native JSON object" in hints
    assert "not a JSON-encoded string" in hints
    assert "escape tabs/newlines" in hints
    assert "\\t/\\n" in hints
    assert "private-value" not in hints
    assert all(len(hint) <= 180 for hint in raised.value.schema_hints)

    valid = json.dumps({"payload": {"text": "private-value\tnext\nrow"}})
    accepted = _model_client([_tool_call(valid, "synthetic.object")], "tool_calls").propose(
        model="qwen3.5-4b", messages=[],
        tools=_schema_tools("synthetic.object", schema), temperature=0.0,
        output_token_budget=4096, enable_thinking=True,
    )
    assert accepted["arguments_raw"] == valid


def test_schema_hints_explain_native_string_array_without_echoing_value() -> None:
    schema = {
        "type": "object",
        "properties": {
            "notes": {
                "type": "array",
                "items": {"type": "string"},
            }
        },
        "required": ["notes"],
        "additionalProperties": False,
    }
    arguments = '{"notes":"[\\"private-ledger-entry\\"]"}'
    client = _model_client([_tool_call(arguments, "synthetic.string_array")], "length")

    with pytest.raises(StructuredToolProtocolError) as raised:
        client.propose(
            model="qwen3.5-4b",
            messages=[],
            tools=_schema_tools("synthetic.string_array", schema),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
        )

    error = raised.value
    assert error.schema_hints == (
        "notes: type must be 'array'; use native JSON array of concise strings; "
        "do not JSON-encode inside string; do not copy full ledger",
    )
    assert "private-ledger-entry" not in " ".join(error.schema_hints)


def test_schema_hints_include_only_the_uniquely_selected_union_branch() -> None:
    schema = {
        "type": "object",
        "properties": {
            "operation": {"type": "string"},
            "target": {"type": "string"},
            "sources": {"type": "array"},
            "destination": {"type": "string"},
        },
        "required": ["operation", "target"],
        "oneOf": [
            {
                "properties": {"operation": {"const": "publish"}},
                "required": ["sources"],
            },
            {
                "properties": {"operation": {"const": "unpack"}},
                "required": ["destination"],
            },
        ],
        "additionalProperties": False,
    }
    arguments = '{"operation":"publish"}'
    client = _model_client([_tool_call(arguments, "synthetic.branch")], "tool_calls")

    with pytest.raises(StructuredToolProtocolError) as raised:
        client.propose(
            model="qwen3.5-4b",
            messages=[],
            tools=_schema_tools("synthetic.branch", schema),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
        )

    error = raised.value
    assert error.missing_fields == ("target", "sources")
    assert any("required fields: sources" in hint for hint in error.schema_hints)
    assert "destination" not in " ".join(error.schema_hints)
    assert arguments not in str(error)


@pytest.mark.parametrize(
    ("arguments", "expected_missing"),
    [
        ("{}", ("operation", "target")),
        ('{"operation":"unsupported"}', ("target",)),
    ],
)
def test_schema_hints_do_not_merge_unselected_union_branches(
    arguments: str, expected_missing: tuple[str, ...]
) -> None:
    schema = {
        "type": "object",
        "properties": {
            "operation": {"type": "string"},
            "target": {"type": "string"},
            "sources": {"type": "array"},
            "destination": {"type": "string"},
        },
        "required": ["operation", "target"],
        "oneOf": [
            {
                "properties": {"operation": {"const": "publish"}},
                "required": ["sources"],
            },
            {
                "properties": {"operation": {"const": "unpack"}},
                "required": ["destination"],
            },
        ],
        "additionalProperties": False,
    }
    client = _model_client([_tool_call(arguments, "synthetic.branch")], "tool_calls")

    with pytest.raises(StructuredToolProtocolError) as raised:
        client.propose(
            model="qwen3.5-4b",
            messages=[],
            tools=_schema_tools("synthetic.branch", schema),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
        )

    error = raised.value
    hints = " ".join(error.schema_hints)
    assert error.missing_fields == expected_missing
    assert "must match one allowed schema branch" in hints
    assert "sources" not in hints
    assert "destination" not in hints


def test_schema_hints_keep_ambiguous_const_branches_fail_closed() -> None:
    schema = {
        "type": "object",
        "properties": {
            "operation": {"type": "string"},
            "left": {"type": "string"},
            "right": {"type": "string"},
        },
        "required": ["operation"],
        "oneOf": [
            {
                "properties": {"operation": {"const": "publish"}},
                "required": ["left"],
            },
            {
                "properties": {"operation": {"const": "publish"}},
                "required": ["right"],
            },
        ],
        "additionalProperties": False,
    }
    client = _model_client(
        [_tool_call('{"operation":"publish"}', "synthetic.branch")],
        "tool_calls",
    )

    with pytest.raises(StructuredToolProtocolError) as raised:
        client.propose(
            model="qwen3.5-4b",
            messages=[],
            tools=_schema_tools("synthetic.branch", schema),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
        )

    error = raised.value
    assert error.missing_fields == ()
    assert error.schema_hints == ("<root>: must match one allowed schema branch",)


def test_schema_hints_list_fields_for_union_without_discriminator() -> None:
    schema = {
        "type": "object",
        "properties": {
            "edge": {"type": "string"},
            "x": {"type": "integer"},
            "y": {"type": "integer"},
        },
        "oneOf": [
            {"required": ["edge"]},
            {"anyOf": [{"required": ["x"]}, {"required": ["y"]}]},
        ],
        "additionalProperties": False,
    }
    client = _model_client([_tool_call("{}", "synthetic.geometry")], "tool_calls")

    with pytest.raises(StructuredToolProtocolError) as raised:
        client.propose(
            model="qwen3.5-4b",
            messages=[],
            tools=_schema_tools("synthetic.geometry", schema),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
        )

    assert raised.value.schema_hints == (
        "<root>: provide one allowed field set: edge OR x OR y",
    )


def test_schema_hints_use_nested_union_instance_for_required_fields() -> None:
    schema = {
        "type": "object",
        "properties": {
            "payload": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "path": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["kind"],
                "anyOf": [
                    {
                        "properties": {"kind": {"const": "read"}},
                        "required": ["path"],
                    },
                    {
                        "properties": {"kind": {"const": "write"}},
                        "required": ["value"],
                    },
                ],
                "additionalProperties": False,
            }
        },
        "required": ["payload"],
        "additionalProperties": False,
    }
    client = _model_client(
        [_tool_call('{"payload":{"kind":"read"}}', "synthetic.nested")],
        "tool_calls",
    )

    with pytest.raises(StructuredToolProtocolError) as raised:
        client.propose(
            model="qwen3.5-4b",
            messages=[],
            tools=_schema_tools("synthetic.nested", schema),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
        )

    error = raised.value
    assert error.missing_fields == ("path",)
    assert error.schema_hints == ("payload: required fields: path",)


def test_zero_call_response_is_recoverable_without_losing_finish_reason() -> None:
    client = _model_client([], "length")

    with pytest.raises(StructuredToolProtocolError) as raised:
        client.propose(
            model="qwen3.5-4b",
            messages=[],
            tools=_write_tools(),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
        )

    error = raised.value
    assert "got 0" in str(error)
    assert error.response_snapshot["finish_reason"] == "length"
    assert error.trace_record()["response"]["message"]["tool_calls"] == []


def test_strict_json_text_envelope_is_normalized_when_native_calls_are_missing() -> None:
    transport = _FakeCompletionClient(
        tool_calls=[],
        finish_reason="stop",
        content='{"name":"spreadsheet.write_range","arguments":{"sheet":"Sheet1","range":"A1:A1","values":[["ok"]]}}',
    )
    client = StructuredToolModelClient(
        base_url="http://unused/v1",
        api_key="EMPTY",
        request_timeout_seconds=1,
        client=transport,
    )

    proposal = client.propose(
        model="qwen3.5-4b",
        messages=[],
        tools=_write_tools(),
        temperature=0.0,
        output_token_budget=4096,
        enable_thinking=True,
    )

    assert proposal["id"] == "textual-tool-call-0"
    assert proposal["tool"] == "spreadsheet.write_range"
    assert json.loads(proposal["arguments_raw"]) == {
        "sheet": "Sheet1",
        "range": "A1:A1",
        "values": [["ok"]],
    }


def test_fenced_strict_json_text_envelope_is_normalized() -> None:
    transport = _FakeCompletionClient(
        tool_calls=[],
        finish_reason="stop",
        content='```json\n{"name":"spreadsheet.write_range","arguments":{"sheet":"Sheet1","range":"A1:A1","values":[["ok"]]}}\n```',
    )
    client = StructuredToolModelClient(
        base_url="http://unused/v1",
        api_key="EMPTY",
        request_timeout_seconds=1,
        client=transport,
    )

    proposal = client.propose(
        model="qwen3.5-4b",
        messages=[],
        tools=_write_tools(),
        temperature=0.0,
        output_token_budget=4096,
        enable_thinking=True,
    )

    assert proposal["tool"] == "spreadsheet.write_range"


def test_textual_prose_is_not_treated_as_a_tool_call() -> None:
    transport = _FakeCompletionClient(
        tool_calls=[], finish_reason="stop", content="I will call the tool now."
    )
    client = StructuredToolModelClient(
        base_url="http://unused/v1",
        api_key="EMPTY",
        request_timeout_seconds=1,
        client=transport,
    )

    with pytest.raises(StructuredToolProtocolError, match="got 0"):
        client.propose(
            model="qwen3.5-4b",
            messages=[],
            tools=_write_tools(),
            temperature=0.0,
            output_token_budget=4096,
            enable_thinking=True,
        )


def test_protocol_recovery_survives_a_following_transport_timeout() -> None:
    protocol_error = StructuredToolProtocolError(
        "expected exactly one complete structured tool call, got 0",
        response_snapshot={},
    )

    recovery = protocol_recovery_after_error(False, protocol_error)
    recovery = protocol_recovery_after_error(
        recovery, TimeoutError("transport timeout")
    )

    assert recovery is True


def test_model_request_can_use_runner_remaining_timeout() -> None:
    arguments = '{"sheet":"Sheet1","range":"A1:A1","values":[["ok"]]}'
    transport = _FakeCompletionClient(
        tool_calls=[_tool_call(arguments)],
        finish_reason="tool_calls",
    )
    client = StructuredToolModelClient(
        base_url="http://unused/v1",
        api_key="EMPTY",
        request_timeout_seconds=600,
        client=transport,
    )

    client.propose(
        model="qwen3.5-4b",
        messages=[],
        tools=_write_tools(),
        temperature=0.0,
        output_token_budget=4096,
        enable_thinking=True,
        request_timeout_seconds=7.5,
    )

    assert transport.timeout_values == [7.5]


def test_model_preflight_failure_is_persistable_non_scored_evidence(tmp_path) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text('{"tasks": []}\n', encoding="utf-8")
    snapshot, reason = model_preflight_failure(
        OSError("connection refused"),
        model="qwen3.5-4b",
        base_url="http://127.0.0.1:1/v1",
        reasoning_effort="xhigh",
    )

    result_dir = tmp_path / "result"
    write_invalid_configuration_result(
        result_dir,
        config_path=config_path,
        model="qwen3.5-4b",
        base_url="http://127.0.0.1:1/v1",
        reasoning_effort="xhigh",
        reason=reason,
        model_preflight_result=snapshot,
    )

    import json

    payload = json.loads((result_dir / "results.json").read_text(encoding="utf-8"))
    assert payload["metadata"]["status"] == "invalid_configuration"
    assert payload["metadata"]["model_preflight"]["status"] == "error"
    assert payload["metadata"]["model_preflight"]["reasoning_gate"]["verified"] is False
    assert payload["tasks"] == []
