from __future__ import annotations

import copy
import json

import pytest

from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.episode_control import mark_tool_result_for_audit
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from vscode_adapter.actions import VscodeActions
from vscode_adapter.errors import AdapterError, error_payload
from vscode_adapter.schema import validate_action_params


@pytest.mark.parametrize(
    ("content", "old", "new", "updated", "count"),
    [
        ("alpha\n\n\nbeta\n", "\n\n", "\n", "alpha\n\nbeta\n", 1),
        ("\talpha\n\tbeta\n", "\t", "    ", "    alpha\n    beta\n", 2),
        ("alpha  beta  gamma", "  ", " ", "alpha beta gamma", 2),
    ],
)
def test_nonempty_whitespace_literal_reaches_native_exact_replacement(
    tmp_path, content, old, new, updated, count
) -> None:
    path = tmp_path / "notes.txt"
    path.write_text(content, encoding="utf-8")
    params = {"path": str(path), "old": old, "new": new}
    original = copy.deepcopy(params)

    validate_action_params("file.replace_literal", params)
    result = VscodeActions().file_replace_literal(params, 1.0)

    assert result["replacement_count"] == count
    assert result["content"] == updated
    assert path.read_text(encoding="utf-8") == updated
    assert params == original


def test_empty_literal_is_still_rejected_before_replacement(tmp_path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("unchanged", encoding="utf-8")
    params = {"path": str(path), "old": "", "new": "replacement"}

    with pytest.raises(AdapterError, match="params.old must be a non-empty string"):
        validate_action_params("file.replace_literal", params)

    assert path.read_text(encoding="utf-8") == "unchanged"


@pytest.mark.parametrize("forwarded", [False, True])
def test_literal_miss_with_existing_new_text_reports_error_to_model(
    tmp_path, forwarded: bool
) -> None:
    path = tmp_path / "processor.py"
    content = "def scale(value):\n    return (value +\n            4)\n\ndef offset(value):\n    return value + 2\n"
    path.write_text(content, encoding="utf-8")
    params = {
        "path": str(path),
        "old": "return (value + 4)",
        "new": "return value + 2",
    }
    original_params = copy.deepcopy(params)

    with pytest.raises(AdapterError) as caught:
        VscodeActions().file_replace_literal(params, 1.0)

    assert caught.value.code == "TEXT_NOT_FOUND"
    assert caught.value.http_status == 404
    assert path.read_text(encoding="utf-8") == content
    assert params == original_params
    error = {"status": "error", "error": error_payload(caught.value)}
    domain, action, arguments = "vs_code", "file.replace_literal", params
    if forwarded:
        error = {
            "status": "error",
            "error_code": "DOWNSTREAM_FAILED",
            "error": "downstream Adapter call failed",
            "details": {"adapter": domain, "response": error},
        }
        arguments = {"adapter": domain, "action": action, "payload": {"params": params}}
        domain, action = "multi_apps", "adapter.call"
    original_error = copy.deepcopy(error)
    observation = ExecutionEvent(
        step=1,
        timestamp_utc="2026-09-06T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": arguments},
        executed=False,
        error=error,
    )
    state = RuntimeState(
        task_id="synthetic-literal-miss",
        domain=domain,
        instruction="Edit the observed source file.",
        events=[observation],
    )
    mark_tool_result_for_audit(state, observation)
    messages = AgentProtocolMixin()._messages(state, b"png")
    state_text = messages[2]["content"][0]["text"]
    summary = json.loads(state_text.split("\n")[1])
    feedback = next(item for item in summary if item.get("step") == 1)

    assert feedback["executed"] is False
    assert "TEXT_NOT_FOUND" in state_text
    assert "whitespace and newlines" in state_text
    assert "file.read_text" in state_text
    assert state.task_id not in state_text
    assert error == original_error


@pytest.mark.parametrize(
    ("content", "old", "new", "updated", "count"),
    [
        ("value = (1 +\n    2)\n", "(1 +\n    2)", "3", "value = 3\n", 1),
        ("red green red\n", "red", "blue", "blue green blue\n", 2),
        ("remove\nkeep\n", "remove\n", "", "keep\n", 1),
    ],
)
def test_exact_replacement_and_deletion_preserve_contract(
    tmp_path, content, old, new, updated, count
) -> None:
    path = tmp_path / "notes.txt"
    path.write_text(content, encoding="utf-8")
    params = {"path": str(path), "old": old, "new": new}
    original = copy.deepcopy(params)

    result = VscodeActions().file_replace_literal(params, 1.0)

    assert result["replacement_count"] == count
    assert result["content"] == updated
    assert result["already_applied"] is False
    assert path.read_text(encoding="utf-8") == updated
    assert params == original
    with pytest.raises(AdapterError, match="literal was not found"):
        VscodeActions().file_replace_literal(params, 1.0)
    assert path.read_text(encoding="utf-8") == updated


@pytest.mark.parametrize("include_body", [False, True])
def test_literal_scope_is_only_the_model_selected_text(tmp_path, include_body) -> None:
    declaration = "def convert(value):\n"
    body = "    return value * 3\n"
    prefix, suffix = "OFFSET = 7\n\n", "\nKEEP = True\n"
    path = tmp_path / "conversion.py"
    path.write_text(prefix + declaration + body + suffix, encoding="utf-8")
    replacement = declaration + "    return value - 2\n"
    params = {
        "path": str(path),
        "old": declaration + body if include_body else declaration,
        "new": replacement,
    }
    original = copy.deepcopy(params)

    result = VscodeActions().file_replace_literal(params, 1.0)

    updated = prefix + replacement + ("" if include_body else body) + suffix
    assert result["replacement_count"] == 1
    assert result["content"] == updated
    assert path.read_text(encoding="utf-8") == updated
    assert params == original
