from copy import deepcopy

import pytest

from integrations.lite_agent.execution_engine import ExecutionEngineMixin
from integrations.lite_agent.request_blocks import request_block_is_stale
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


def test_impress_image_export_expires_missing_artifact_block() -> None:
    events = [
        ExecutionEvent(
            step=1,
            timestamp_utc="now",
            proposed={
                "kind": "adapter",
                "domain": "gimp",
                "action": "image.adjust",
                "arguments": {"path": "/tmp/background.png"},
            },
            executed=False,
        ),
        ExecutionEvent(
            step=2,
            timestamp_utc="now",
            proposed={
                "kind": "adapter",
                "domain": "libreoffice_impress",
                "action": "shape.export_image",
                "arguments": {"output_path": "/tmp/background.png"},
            },
            executed=True,
        ),
    ]

    assert request_block_is_stale(events, blocked_at_step=1)


@pytest.mark.parametrize("between", ["file.replace_literal", "file.read_text", None])
def test_command_error_repetition_uses_current_application_state(between) -> None:
    command_arguments = {
        "adapter": "os",
        "action": "command.run",
        "payload": {
            "params": {
                "argv": ["python3", "/tmp/synthetic-source.py"],
                "cwd_source": "home",
                "stdout_path": "/tmp/synthetic-output.txt",
                "provenance": "none",
            }
        },
    }

    def failed_command(step, stderr):
        return ExecutionEvent(
            step=step,
            timestamp_utc="now",
            proposed={
                "kind": "adapter",
                "action": "adapter.call",
                "arguments": deepcopy(command_arguments),
            },
            executed=False,
            error={
                "error_code": "DOWNSTREAM_FAILED",
                "details": {
                    "response": {
                        "error": {
                            "code": "COMMAND_FAILED",
                            "message": "command returned an unexpected status",
                            "details": {"returncode": 1, "stderr": stderr},
                        }
                    }
                },
            },
        )

    first_error = "IndentationError: unindent does not match any outer indentation level"
    state = RuntimeState(
        task_id="synthetic-command-repair",
        domain="multi_apps",
        instruction="Edit the source and execute it again.",
        events=[failed_command(1, first_error)],
    )
    if between is not None:
        params = {"path": "/tmp/synthetic-source.py"}
        if between == "file.replace_literal":
            params.update(old="  value = 1", new="    value = 1")
        state.events.append(
            ExecutionEvent(
                step=2,
                timestamp_utc="now",
                proposed={
                    "kind": "adapter",
                    "action": "adapter.call",
                    "arguments": {
                        "adapter": "vs_code",
                        "action": between,
                        "payload": {"params": params},
                    },
                },
                executed=True,
            )
        )
    second_error = (
        "IndentationError: unexpected indent"
        if between == "file.replace_literal"
        else first_error
    )
    current = failed_command(3, second_error)
    original_error = deepcopy(current.error)
    state.events.append(current)

    ExecutionEngineMixin._block_repeated_error(state)

    assert current.proposed["arguments"] == command_arguments
    if between == "file.replace_literal":
        assert current.error == original_error
        assert state.active_request_blocks() == {}
        unchanged_retry = failed_command(4, second_error)
        state.events.append(unchanged_retry)
        ExecutionEngineMixin._block_repeated_error(state)
        assert unchanged_retry.error["type"] == "RepeatedActionBlocked"
        assert unchanged_retry.error["previous_step"] == 3
        assert unchanged_retry.error["previous_error"] == original_error
    else:
        assert current.error["type"] == "RepeatedActionBlocked"
        assert current.error["previous_step"] == 1
        assert current.error["previous_error"] == original_error
