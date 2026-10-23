from __future__ import annotations

import copy
import json
import subprocess

import pytest

from calc_adapter.errors import AdapterError as CalcError
from calc_adapter.schema import validate_typed_matrix
from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.context_projection import sanitize
from integrations.lite_agent.episode_control import mark_tool_result_for_audit
from integrations.lite_agent.safety import (
    assert_agent_surface_safe,
    sanitize_agent_visible_result,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from os_adapter.errors import AdapterError as OsError
from os_adapter.command import CommandRunner, gsettings_failure_guidance
from os_adapter.local_paths import normalize_local_path
from vscode_adapter.errors import AdapterError as VscodeError
from vscode_adapter.jsonfiles import load_json
from vscode_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS as VSCODE_SCHEMAS
from writer_adapter import uno_worker
from writer_adapter.errors import AdapterError as WriterError


@pytest.mark.parametrize("case", ["cell_address", "file_uri", "json_type", "missing_document"])
@pytest.mark.parametrize("forwarded", [False, True])
def test_native_error_language_reaches_model(tmp_path, monkeypatch, case, forwarded) -> None:
    with pytest.raises((CalcError, OsError, VscodeError, WriterError)) as caught:
        if case == "cell_address":
            domain, action = "libreoffice_calc", "range.write"
            validate_typed_matrix(
                [[{"kind": "formatted_text", "value": {"parts": [{"cell": "C2:D4"}]}}]]
            )
        elif case == "file_uri":
            domain, action = "os", "filesystem.inspect"
            normalize_local_path("file://remote.invalid/tmp/notes.txt")
        elif case == "missing_document":
            domain, action = "libreoffice_writer", "document.read_file"
            path = tmp_path / "answer_sheet_blue.odt"
            monkeypatch.setattr(uno_worker, "_file_url", lambda value: value)
            uno_worker._read_file(None, {"path": path.as_uri()})
        else:
            domain, action = "vs_code", "workspace.inspect"
            path = tmp_path / "settings.json"
            path.write_text("[]", encoding="utf-8")
            load_json(path, dict, {})

    native = caught.value
    error = {
        "status": "error",
        "error": {
            "code": native.code,
            "message": native.message,
            "details": native.details,
        },
    }
    if forwarded:
        error = {
            "status": "error",
            "error_code": "DOWNSTREAM_FAILED",
            "error": "downstream Adapter call failed",
            "details": {"adapter": domain, "response": error},
        }
        domain, action = "multi_apps", "adapter.call"
    original = copy.deepcopy(error)
    task_id = "synthetic-error-language"

    sanitized = sanitize_agent_visible_result(error, task_id)
    assert sanitized == error
    assert sanitize(error) == error
    event = ExecutionEvent(
        step=1,
        timestamp_utc="2026-09-06T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": {}},
        executed=False,
        error=sanitized,
    )
    state = RuntimeState(
        task_id=task_id,
        domain=domain,
        instruction="Correct the reported application error.",
        events=[event],
    )
    mark_tool_result_for_audit(state, event)
    messages = AgentProtocolMixin()._messages(state, b"png")
    state_text = messages[2]["content"][0]["text"]
    summary = json.loads(state_text.split("\n")[1])
    failure = next(item for item in summary if item.get("step") == 1)

    assert failure["error"] == original
    assert failure["executed"] is False
    assert native.code in state_text
    assert native.message in state_text
    assert error == original
    assert_agent_surface_safe(task_id=task_id, messages=messages, tools=[])


def test_vscode_window_actions_explain_exact_handle_provenance() -> None:
    assert "never invent or normalize" in VSCODE_SCHEMAS["editor.open_file"]["description"]
    assert "successful editor.open_file" in VSCODE_SCHEMAS["ui.open_view"]["properties"]["window_id"]["description"]
    assert "fresh one with editor.open_file" in VSCODE_SCHEMAS["ui.expand_section"]["description"]
    assert "fresh one with editor.open_file" in VSCODE_SCHEMAS["debug.variables.read"]["description"]


@pytest.mark.parametrize("marker", ["expected_state", "reference_profile"])
def test_explicit_metadata_stays_hidden_in_application_errors(marker) -> None:
    body = {
        "error": {
            "message": f"Internal {marker} is unavailable",
            marker: "private-value",
        }
    }
    for sanitized in (sanitize(body), sanitize_agent_visible_result(body, "safe-task")):
        assert sanitized == {"error": {"message": "<internal-benchmark-metadata>"}}


@pytest.mark.parametrize("filename", ["answer_sheet.docx", "answer_sheet_blue.odt"])
def test_ordinary_answer_sheet_filename_reaches_model(filename) -> None:
    body = {"matches": [{"name": filename, "path": f"/tmp/course/{filename}"}]}

    sanitized = sanitize_agent_visible_result(body, "synthetic-case")

    assert sanitized == body
    assert sanitize(sanitized) == body
    assert_agent_surface_safe(
        task_id="synthetic-case",
        messages=[{"role": "user", "content": json.dumps(sanitized)}],
        tools=[],
    )


def test_answer_sheet_metadata_key_remains_hidden() -> None:
    body = {"result": {"answer_sheet": "private-content", "text": "visible-content"}}

    for sanitized in (sanitize(body), sanitize_agent_visible_result(body, "synthetic-case")):
        assert sanitized == {"result": {"text": "visible-content"}}
    with pytest.raises(RuntimeError, match="hidden benchmark metadata keys"):
        assert_agent_surface_safe(
            task_id="synthetic-case",
            messages=[],
            tools=[{"function": {"name": "example", "answer_sheet": "private-content"}}],
        )


def test_gsettings_failure_keeps_native_error_and_adds_recovery_guidance(monkeypatch) -> None:
    stderr = 'No such key “default-size-columns”\\n'
    monkeypatch.setattr(
        "os_adapter.command.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, stdout="", stderr=stderr
        ),
    )

    with pytest.raises(OsError) as caught:
        CommandRunner().run(
            ["gsettings", "set", "org.example.Profile", "default-size-columns", "132"]
        )

    details = caught.value.details
    assert details["stderr"] == stderr
    assert "list-relocatable-schemas" in details["guidance"]
    assert "Do not retry the unchanged" in details["guidance"]
    assert gsettings_failure_guidance(["printf", "x"], stderr) is None


def test_shell_syntax_error_explains_bash_c_recovery() -> None:
    from os_adapter.actions import _reject_shell_syntax

    with pytest.raises(OsError) as caught:
        _reject_shell_syntax(
            ["printf", "x", "|", "grep", "x"], redirection_recovery="unused"
        )

    assert "bash" in caught.value.details["recovery"]
    assert "separate argv items" in caught.value.details["recovery"]


def test_shell_syntax_error_explains_explicit_cwd_without_rewriting_argv() -> None:
    from os_adapter.actions import _reject_shell_syntax

    argv = ["cd", "/tmp/synthetic-notes", "&&", "wc", "-l", "notes.txt"]
    original_argv = list(argv)
    with pytest.raises(OsError) as caught:
        _reject_shell_syntax(argv, redirection_recovery="unused")

    error = caught.value
    assert error.code == "SHELL_SYNTAX_UNSUPPORTED"
    assert error.details["argv"] == original_argv
    assert argv == original_argv
    assert error.details["shell_tokens"] == ["&&"]
    assert error.details["shell_parsing"] is False
    recovery = error.details["recovery"]
    assert '["bash", "-c", <one complete model-authored script>]' in recovery
    assert '\\"' not in recovery
    assert 'cwd_source="explicit"' in recovery
    assert "cwd_path" in recovery
    assert "absolute" in recovery
    assert "relative" in recovery
