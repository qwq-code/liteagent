from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    context_hint_for_model,
)
from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.episode_control import mark_tool_result_for_audit
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


def _text(length: int) -> str:
    return "".join(
        f"record {index:05d} Ω value 0042\n" for index in range(length // 20 + 1)
    )[:length]


def _source(text: str, *, start: int = 0, end: int | None = None) -> dict:
    end = len(text) if end is None else end
    return {
        "path": "/tmp/synthetic project/report.txt",
        "content": text[start:end],
        "total_chars": len(text),
        "total_lines": len(text.splitlines()),
        "returned_chars": end - start,
        "source_start_char": start,
        "source_end_char": end,
        "source_total_chars": len(text),
        "next_start_char": end if end < len(text) else None,
        "offset_basis": "unicode_characters",
        "source_truncated": end < len(text),
        "truncated": end < len(text),
        "sibling_file_paths": [
            "/tmp/synthetic project/notes.md",
            "/tmp/synthetic project/formatting.py",
        ],
        "sibling_file_count": 2,
        "sibling_files_truncated": False,
    }


def _model_observation(source: dict, *, forwarded: bool, recovery: bool = False):
    body = {"status": "ok", "result": source}
    domain, action = "vs_code", "file.read_text"
    arguments = {
        "path": source["path"],
        "start_char": source["source_start_char"],
        "max_chars": source["returned_chars"],
    }
    if forwarded:
        body = {
            "status": "ok",
            "result": {"adapter": domain, "action": action, "response": body},
        }
        arguments = {"adapter": domain, "action": action, "payload": {"params": arguments}}
        domain, action = "multi_apps", "adapter.call"
    hint = context_hint_for_model(
        domain, action, adapter_context_hint(domain, action, body), strict_generic=True,
    )
    event = ExecutionEvent(
        step=1,
        timestamp_utc="2026-09-12T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": arguments},
        executed=True,
        result={"context_hint": hint},
    )
    state = RuntimeState(
        task_id="synthetic-text-file-observation",
        domain=domain,
        instruction="Read the complete report before choosing any edits.",
        events=[event],
    )
    mark_tool_result_for_audit(state, event)
    agent = AgentProtocolMixin()
    agent.config = SimpleNamespace(include_gui=True)
    messages = agent._messages(
        state, b"synthetic-screenshot", execution_recovery=recovery,
    )
    summary = json.loads(messages[2]["content"][0]["text"].split("\n")[1])
    entry = next(item for item in summary if item.get("step") == 1)
    model_hint = entry["result"]["context_hint"]
    return messages, model_hint["downstream_context"] if forwarded else model_hint


def _assert_reader_and_edit_context(observed: dict, source: dict) -> None:
    assert observed["observation_type"] == "text_batch"
    assert observed["reader_action"] == "file.read_text"
    assert observed["sibling_file_paths"] == source["sibling_file_paths"]
    assert observed["sibling_file_count"] == 2
    guidance = observed["guidance"]
    assert "file.read_text" in guidance and "sibling_file_paths" in guidance
    assert "file.replace_literal replaces only old" in guidance
    assert "complete current block in old" in guidance
    assert "input_pattern" not in guidance and "max_chars_per_file" not in guidance
    assert "file.write_text" not in guidance


@pytest.mark.parametrize("forwarded", [False, True])
def test_complete_nine_thousand_character_file_reaches_normal_model_request(
    forwarded: bool,
) -> None:
    middle, tail = "SYNTHETIC-MIDDLE-CONTENT", "SYNTHETIC-TAIL-CONTENT"
    text = _text(9000)
    text = text[:4500] + middle + text[4500 + len(middle):]
    text = text[:-len(tail)] + tail
    source = _source(text)
    original = deepcopy(source)

    messages, observed = _model_observation(source, forwarded=forwarded)

    encoded = json.dumps(messages, ensure_ascii=False)
    assert middle in encoded and tail in encoded
    assert len(observed["files"]) == 1
    file = observed["files"][0]
    assert file["handle"]["path"] == source["path"]
    assert "".join(chunk["text"] for chunk in file["chunks"]) == text
    assert file["chunks"][0]["start_char"] == 0
    assert file["chunks"][-1]["end_char"] == len(text)
    assert file["source_has_more"] is False
    assert file["next_start_char"] is None
    assert not observed["context_truncated"]
    _assert_reader_and_edit_context(observed, source)
    assert source == original


@pytest.mark.parametrize("forwarded", [False, True])
@pytest.mark.parametrize("recovery", [False, True])
def test_bounded_file_observation_keeps_exact_slices_and_middle_continuation(
    forwarded: bool, recovery: bool,
) -> None:
    text = _text(60_000)
    source = _source(text, start=5000, end=45_000)
    original = deepcopy(source)

    _messages, observed = _model_observation(
        source, forwarded=forwarded, recovery=recovery,
    )

    assert observed["context_truncated"] is True
    assert len(json.dumps(observed, ensure_ascii=False)) <= 18_000
    file = observed["files"][0]
    assert file["handle"]["path"] == source["path"]
    assert file["source_start_char"] == 5000
    assert file["source_end_char"] == 45_000
    assert file["source_total_chars"] == len(text)
    assert file["next_start_char"] == 45_000
    assert file["source_has_more"] is True
    assert file["offset_basis"] == "unicode_characters"
    chunks = file["chunks"]
    assert len(chunks) == 2
    assert chunks[0]["start_char"] == 5000
    assert chunks[0]["end_char"] < chunks[1]["start_char"]
    assert chunks[-1]["end_char"] == 45_000
    for chunk in chunks:
        assert chunk["type"] == "text"
        assert chunk["text"] == text[chunk["start_char"]:chunk["end_char"]]
        assert chunk["context_has_more"] is True
    _assert_reader_and_edit_context(observed, source)
    guidance = observed["guidance"]
    assert "first chunk's end_char" in guidance
    assert "start_char" in guidance and "smaller max_chars" in guidance
    assert source == original
