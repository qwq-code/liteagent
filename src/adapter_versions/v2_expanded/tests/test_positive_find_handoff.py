from __future__ import annotations

from types import SimpleNamespace

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.positive_find_handoff import (
    age_organization_complete,
    constrain_age_organization_find_tools,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


INSTRUCTION = (
    'Compress files last modified 30 days ago under "/tmp/test_files" into '
    '"/tmp/test_files/old_files" and move all other files to '
    '"/tmp/test_files/new_files".'
)


def _tools():
    return [
        {"function": {"name": name}}
        for name in (
            "adapter__filesystem_find",
            "adapter__archive_compress_file",
            "adapter__filesystem_rename",
            "tools_search",
            "propose_done",
        )
    ]


def _find_event(*, truncated=False, matched=True):
    matches = [
        {
            "path": "/tmp/test_files/old_files/old.txt",
            "kind": "file",
            "modified_at": "2026-09-21T00:00:00+00:00",
        }
    ] if matched else []
    return ExecutionEvent(
        step=1,
        timestamp_utc="2026-10-21T00:00:00Z",
        proposed={
            "kind": "adapter",
            "action": "filesystem.find",
            "arguments": {"roots": ["/tmp/test_files"], "name_patterns": ["*"]},
        },
        executed=True,
        result={
            "context_hint": {
                "match_count": 1 if matched else 0,
                "returned_count": 1 if matched else 0,
                "truncated": truncated,
                "matches": matches,
            }
        },
    )


def _names(tools):
    return {tool["function"]["name"] for tool in tools}


def test_complete_age_inventory_exposes_mutations_without_repeating_find():
    state = RuntimeState(task_id="age", domain="os", instruction=INSTRUCTION)
    state.events.append(_find_event())
    names = _names(constrain_age_organization_find_tools(_tools(), state))
    assert names == {
        "adapter__archive_compress_file",
        "adapter__filesystem_rename",
        "propose_done",
    }


def test_agent_tool_surface_hands_off_to_age_mutations():
    state = RuntimeState(task_id="age", domain="os", instruction=INSTRUCTION)
    state.events.append(_find_event())
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused.invalid/v1"),
        adapter_executor=object(),
        model_client=SimpleNamespace(client=object()),
    )
    names = _names(agent.tools(state))
    assert "adapter__filesystem_find" not in names
    assert "adapter__archive_compress_file" in names
    assert "adapter__filesystem_rename" in names


def test_incomplete_or_empty_inventory_keeps_discovery_available():
    for event in (_find_event(truncated=True), _find_event(matched=False)):
        state = RuntimeState(task_id="age", domain="os", instruction=INSTRUCTION)
        state.events.append(event)
        assert _names(constrain_age_organization_find_tools(_tools(), state)) == _names(
            _tools()
        )


def test_non_age_workflow_keeps_find_available():
    state = RuntimeState(
        task_id="other", domain="os", instruction="Find /tmp/test_files/old.txt"
    )
    state.events.append(_find_event())
    assert _names(constrain_age_organization_find_tools(_tools(), state)) == _names(
        _tools()
    )


def test_mutation_after_inventory_preserves_readback_find():
    state = RuntimeState(task_id="age", domain="os", instruction=INSTRUCTION)
    state.events.append(_find_event())
    state.events.append(
        ExecutionEvent(
            step=2,
            timestamp_utc="2026-10-21T00:00:01Z",
            proposed={
                "kind": "adapter",
                "action": "archive.compress_file",
                "arguments": {"source": "/tmp/test_files/old_files/old.txt"},
            },
            executed=True,
            result={"status": "ok"},
        )
    )
    assert "adapter__filesystem_find" in _names(
        constrain_age_organization_find_tools(_tools(), state)
    )


def _aged_task_state(*, missing_compression=False, extra_readback=False):
    state = RuntimeState(task_id="age", domain="os", instruction=INSTRUCTION)
    paths = [
        "/tmp/test_files/old_files/old1.txt",
        "/tmp/test_files/old_files/old2.txt",
        "/tmp/test_files/new_files/new1.txt",
    ]

    def find_event(step, observed):
        return ExecutionEvent(
            step=step,
            timestamp_utc="2026-10-21T00:00:00Z",
            proposed={
                "kind": "adapter", "action": "filesystem.find",
                "arguments": {"roots": ["/tmp/test_files"], "name_patterns": ["*"]},
            },
            executed=True,
            result={"context_hint": {
                "match_count": len(observed), "returned_count": len(observed),
                "truncated": False,
                "matches": [
                    {"path": path, "kind": "file", "modified_at": "2026-09-21T00:00:00Z"}
                    for path in observed
                ],
            }},
        )

    state.events.append(find_event(1, paths))
    old = paths[:1] if missing_compression else paths[:2]
    for step, source in enumerate(old, start=2):
        state.events.append(ExecutionEvent(
            step=step,
            timestamp_utc="2026-10-21T00:00:00Z",
            proposed={"kind": "adapter", "action": "archive.compress_file", "arguments": {
                "source": source, "destination": source + ".gz", "remove_source": True,
            }},
            executed=True,
            result={"verification": {"passed": True}},
        ))
    readback = [source + ".gz" for source in old] + paths[len(old):]
    if extra_readback:
        readback.append("/tmp/test_files/new_files/duplicate.txt")
    state.events.append(find_event(len(old) + 2, readback))
    return state


def test_completed_age_organization_uses_terminal_tools_only():
    state = _aged_task_state()
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused.invalid/v1"),
        adapter_executor=object(),
        model_client=SimpleNamespace(client=object()),
    )
    assert age_organization_complete(state)
    assert agent._generic_completion_gate(state)["passed"]
    assert _names(agent.tools(state)) == {"propose_done", "fail_task"}


def test_age_organization_needs_every_source_and_exact_readback():
    assert not age_organization_complete(_aged_task_state(missing_compression=True))
    assert not age_organization_complete(_aged_task_state(extra_readback=True))
