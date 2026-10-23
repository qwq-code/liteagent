from copy import deepcopy
import json

import pytest

from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from os_adapter.actions import OSActions
from os_adapter.errors import AdapterError, error_payload


@pytest.mark.parametrize("redirected", [False, True])
def test_command_timeout_keeps_native_error_and_explains_mode_in_model_request(
    tmp_path, monkeypatch, redirected
):
    params = {
        "argv": ["synthetic-viewer", "notes.txt"],
        "cwd_source": "explicit",
        "cwd_path": str(tmp_path),
        "provenance": "none",
    }
    if redirected:
        params["stdout_path"] = str(tmp_path / "capture.txt")
    original = deepcopy(params)
    calls = []
    native_details = None
    actions = OSActions()

    def timed_out(argv, **kwargs):
        nonlocal native_details
        calls.append((deepcopy(argv), kwargs))
        native_details = {
            "argv": list(argv), "stdout": "opened view\n", "stderr": "partial diagnostic\n"
        }
        raise AdapterError("OPERATION_TIMEOUT", "command exceeded 2.0 seconds", native_details, 504)

    monkeypatch.setattr(actions.runner, "run", timed_out)
    with pytest.raises(AdapterError) as caught:
        actions.run_command(params, 2)

    error = caught.value
    assert error.code == "OPERATION_TIMEOUT"
    assert error.http_status == 504
    assert error.message == "command exceeded 2.0 seconds"
    assert all(error.details[key] == value for key, value in native_details.items())
    assert error.details["requested_argv"] == original["argv"]
    assert error.details["cwd"] == str(tmp_path)
    assert error.details["terminal_launch"] is False
    assert error.details["waited_for_process_exit"] is True
    assert error.details["partial_effects_possible"] is True
    assert "inspect the current state before retrying" in error.details["guidance"]
    assert "terminal=true" in error.details["guidance"]
    assert params == original
    assert len(calls) == 1
    assert calls[0][0] == native_details["argv"]
    assert (calls[0][0] != original["argv"]) is redirected
    assert calls[0][1]["cwd"] == str(tmp_path)

    forwarded = {
        "status": "error", "error_code": "DOWNSTREAM_FAILED",
        "error": "downstream Adapter call failed",
        "details": {"adapter": "os", "response": {"status": "error", "error": error_payload(error)}},
    }
    event = ExecutionEvent(
        step=1, timestamp_utc="2026-09-13T00:00:00Z",
        proposed={"kind": "adapter", "action": "adapter.call", "arguments": {
            "adapter": "os", "action": "command.run", "payload": {"params": params}
        }},
        executed=False, error=forwarded,
    )
    state = RuntimeState(
        task_id="synthetic-command-timeout", domain="multi_apps",
        instruction="Open the notes in a viewer from a terminal.", events=[event],
    )
    messages = AgentProtocolMixin()._messages(state, b"png")
    summary = json.loads(messages[2]["content"][0]["text"].split("\n")[1])
    failure = next(item for item in summary if item.get("step") == 1)
    assert failure["error"] == forwarded
    assert failure["executed"] is False
