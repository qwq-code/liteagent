from pathlib import Path

import pytest

from integrations.lite_agent.source_execution_semantics import (
    CAPTURE_OUTPUT,
    DONE,
    READ_OUTPUT,
    READ_REFERENCE,
    protocol_guidance,
    workflow_state,
)
from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.standard_location_semantics import (
    argument_contract_errors as standard_location_argument_contract_errors,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from os_adapter.actions import OSActions
from os_adapter.errors import AdapterError
from os_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS as OS_SCHEMAS


def _capture_arguments(
    source_argument: str,
    stdout_path: str,
    cwd: Path,
    *,
    append: bool = False,
) -> dict:
    return {
        "argv": ["cat", source_argument],
        "cwd_source": "explicit",
        "cwd_path": str(cwd),
        "stdout_path": stdout_path,
        "append_stdout": append,
        "provenance": "none",
    }


def _verified_event(
    step: int,
    action: str,
    arguments: dict,
    **result_fields: object,
) -> ExecutionEvent:
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-08-31T00:00:00Z",
        proposed={
            "kind": "adapter",
            "tool": f"adapter__{action.replace('.', '_')}",
            "action": action,
            "arguments": arguments,
        },
        executed=True,
        result={"verification": {"passed": True}, **result_fields},
    )


def _source_workflow_state(stdout_path: str) -> RuntimeState:
    source_path = "/tmp/counterfactual/source.py"
    return RuntimeState(
        task_id="synthetic-source-output",
        domain="multi_apps",
        instruction="Complete source.py and save its output as result.txt.",
        events=[
            _verified_event(
                1, "file.read_text", {"path": source_path}, path=source_path
            ),
            _verified_event(
                2,
                "file.write_text",
                {"path": source_path, "text": "print('done')\n"},
                path=source_path,
            ),
            _verified_event(
                3,
                "command.capture_output",
                {
                    "argv": ["python3", source_path],
                    "cwd_source": "explicit",
                    "cwd_path": "/tmp/counterfactual",
                    "stdout_path": stdout_path,
                    "provenance": "none",
                },
                stdout_path=stdout_path,
            ),
            _verified_event(
                4, "file.read_text", {"path": stdout_path}, path=stdout_path
            ),
        ],
    )


@pytest.mark.parametrize("append", [False, True])
def test_capture_rejects_exact_input_output_path_before_truncation(
    tmp_path: Path, append: bool
) -> None:
    source = tmp_path / "source.py"
    source.write_text("print('preserved')\n", encoding="utf-8")

    with pytest.raises(AdapterError) as raised:
        OSActions().run_command(
            _capture_arguments(str(source), str(source), tmp_path, append=append),
            5,
        )

    assert raised.value.code == "OUTPUT_CONFLICT"
    assert raised.value.http_status == 409
    assert source.read_text(encoding="utf-8") == "print('preserved')\n"


def test_capture_rejects_relative_alias_before_truncation(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("preserved\n", encoding="utf-8")

    with pytest.raises(AdapterError, match="stdout_path must differ"):
        OSActions().run_command(
            _capture_arguments("source.txt", "./source.txt", tmp_path),
            5,
        )

    assert source.read_text(encoding="utf-8") == "preserved\n"


@pytest.mark.parametrize("alias_kind", ["symlink", "hardlink"])
def test_capture_rejects_same_inode_alias(tmp_path: Path, alias_kind: str) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "alias.txt"
    source.write_text("preserved\n", encoding="utf-8")
    if alias_kind == "symlink":
        destination.symlink_to(source)
    else:
        destination.hardlink_to(source)

    with pytest.raises(AdapterError, match="stdout_path must differ"):
        OSActions().run_command(
            _capture_arguments(str(source), str(destination), tmp_path),
            5,
        )

    assert source.read_text(encoding="utf-8") == "preserved\n"


def test_capture_keeps_distinct_output_semantics(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "captured.txt"
    source.write_text("counterfactual output\n", encoding="utf-8")

    result = OSActions().run_command(
        _capture_arguments(str(source), str(destination), tmp_path),
        5,
    )

    assert result["returncode"] == 0
    assert result["stdout_path"] == str(destination)
    assert result["stdout_bytes"] == len("counterfactual output\n")
    assert destination.read_text(encoding="utf-8") == "counterfactual output\n"
    assert source.read_text(encoding="utf-8") == "counterfactual output\n"


def test_capture_resolves_relative_output_from_selected_command_cwd(tmp_path: Path) -> None:
    command_cwd = tmp_path / "command"
    command_cwd.mkdir()

    result = OSActions().run_command(
        {
            "argv": ["printf", "captured\\n"],
            "cwd_source": "explicit",
            "cwd_path": str(command_cwd),
            "stdout_path": "result.txt",
            "provenance": "none",
        },
        5,
    )

    destination = command_cwd / "result.txt"
    assert destination.read_text(encoding="utf-8") == "captured\n"
    assert result["stdout_path"] == str(destination.resolve())


def test_public_command_contract_explains_the_cross_field_constraint() -> None:
    os_description = OS_SCHEMAS["command.run"]["properties"]["stdout_path"][
        "description"
    ]

    assert "must be distinct" in os_description
    assert "truncate" in os_description


@pytest.mark.parametrize(
    "instruction",
    [
        "Fix analyzer.py and save its output to a text file.",
        "Complete the program and store the result in a file.",
    ],
)
def test_source_output_guidance_names_the_available_command(instruction: str) -> None:
    state = RuntimeState(
        task_id="synthetic-output-guidance",
        domain="multi_apps",
        instruction=instruction,
    )
    guidance = protocol_guidance(instruction)
    system = AgentProtocolMixin()._system_message(state)

    assert guidance is not None and guidance in system
    assert "use tools_search for command.run" in guidance
    assert "if that action is not exposed" in guidance
    assert "Omitting stdout_path" in guidance
    assert "does not save an output file" in guidance
    assert "command.capture_output" not in system
    assert "stdout_path" in OS_SCHEMAS["command.run"]["properties"]


def test_source_edit_without_output_request_adds_no_capture_guidance() -> None:
    assert protocol_guidance("Fix the formatting in analyzer.py.") is None


def test_command_run_stdout_path_preserves_requested_desktop() -> None:
    state = RuntimeState(
        task_id="synthetic-desktop-output",
        domain="multi_apps",
        instruction="Run the report and save the output on Desktop.",
    )

    errors = standard_location_argument_contract_errors(
        state,
        "command.run",
        {
            "argv": ["sar", "-u", "1", "1"],
            "cwd_source": "home",
            "stdout_path": "/home/Desktop/report.txt",
            "provenance": "shell_history",
        },
    )

    assert errors
    assert "~/Desktop/" in errors[0]


def test_completion_ledger_rejects_capture_overwriting_source() -> None:
    current = workflow_state(_source_workflow_state("/tmp/counterfactual/./source.py"))

    assert current.phase == CAPTURE_OUTPUT
    assert current.capture_step is None
    assert current.output_path is None


def test_completion_ledger_accepts_distinct_verified_capture_and_readback() -> None:
    current = workflow_state(_source_workflow_state("/tmp/counterfactual/result.txt"))

    assert current.phase == DONE
    assert current.capture_step == 3
    assert current.output_path == "/tmp/counterfactual/result.txt"
    assert current.readback_step == 4


def test_completion_requires_persisted_stdout_before_done() -> None:
    state = _source_workflow_state("/tmp/counterfactual/result.txt")
    capture = state.events[2]
    capture.proposed["arguments"].pop("stdout_path")
    capture.result.pop("stdout_path")

    gate = CompletionMixin._generic_completion_gate(state)

    assert gate["passed"] is False
    assert any("stdout_path" in item and "save" in item for item in gate["missing"])
    assert workflow_state(state).phase == CAPTURE_OUTPUT


def test_completion_requires_readback_after_persisted_stdout() -> None:
    state = _source_workflow_state("/tmp/counterfactual/result.txt")
    state.events.pop()

    gate = CompletionMixin._generic_completion_gate(state)

    assert gate["passed"] is False
    assert any("read back" in item and "stdout_path" in item for item in gate["missing"])
    assert workflow_state(state).phase == "read_output"


def test_non_persistent_command_instruction_has_no_source_output_requirement() -> None:
    state = RuntimeState(
        task_id="synthetic-command-only",
        domain="multi_apps",
        instruction="Run analyzer.py and report the result; do not save a file.",
    )

    assert workflow_state(state).active is False


def test_completion_accepts_persisted_stdout_and_readback() -> None:
    state = _source_workflow_state("/tmp/counterfactual/result.txt")

    gate = CompletionMixin._generic_completion_gate(state)

    assert gate == {"passed": True, "missing": []}


@pytest.mark.parametrize(
    "event_count,phase",
    [(1, READ_REFERENCE), (2, CAPTURE_OUTPUT), (3, READ_OUTPUT), (4, DONE)],
)
def test_named_reference_does_not_hide_remaining_output_state_after_edit(
    event_count: int, phase: str
) -> None:
    state = _source_workflow_state("/tmp/counterfactual/result.txt")
    state.instruction = (
        "Using guide.docx, complete source.py and save its output as result.txt."
    )
    state.events = state.events[:event_count]

    assert workflow_state(state).phase == phase
    gate = CompletionMixin._generic_completion_gate(state)
    assert gate["passed"] is (phase == DONE)
    missing = " ".join(gate["missing"])
    if phase == READ_REFERENCE:
        assert "document.read_file" in missing
    elif phase == CAPTURE_OUTPUT:
        assert "stdout_path" in missing and "save" in missing
    elif phase == READ_OUTPUT:
        assert "stdout_path" in missing and "read back" in missing
    else:
        assert gate["missing"] == []
