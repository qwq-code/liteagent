from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from integrations.lite_agent.local_file_discovery import constrain_zero_match_find_tools
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools


QUERY = {"roots": ["~/Desktop"], "name_patterns": ["output.csv"], "kind": "file"}


def event(step, kind, action=None, arguments=None, *, executed=True, result=None, error=None):
    return ExecutionEvent(
        step=step,
        timestamp_utc="now",
        proposed={"kind": kind, "action": action, "arguments": arguments or {}},
        executed=executed,
        result=result,
        error=error,
    )


def empty_find(step, *, wrapped=False):
    action = "adapter.call" if wrapped else "filesystem.find"
    arguments = (
        {"adapter": "os", "action": "filesystem.find", "payload": {"params": deepcopy(QUERY)}}
        if wrapped else deepcopy(QUERY)
    )
    return event(step, "adapter", action, arguments, result={"matches": [], "match_count": 0})


def query_allowed(state):
    tools = build_tools(
        "os", ["filesystem.find"], include_gui=False,
        include_control_tools=False, strict_generic=True,
    )
    schema = constrain_zero_match_find_tools(tools, state)[0]["function"]["parameters"]
    return Draft202012Validator(schema).is_valid(QUERY)


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("change", [
    event(2, "gui", arguments={"action": "press", "key": "enter"}),
    event(2, "adapter", "file.write_text", {"path": "/tmp/new-file"}),
    event(2, "adapter", "document.save", {"path": "/tmp/new-file"}),
    event(2, "adapter", "adapter.call", {
        "adapter": "libreoffice_writer", "action": "document.export",
        "payload": {"params": {"path": "/tmp/new-file"}},
    }),
    event(2, "adapter", "adapter.call", {
        "adapter": "os", "action": "command.run",
        "payload": {"params": {"argv": ["touch", "/tmp/new-file"]}},
    }),
])
def test_state_change_allows_readback_then_new_empty_result_blocks_again(wrapped, change):
    state = RuntimeState(task_id="search-after-write", domain="os", instruction="Create a file")
    state.events.append(empty_find(1, wrapped=wrapped))
    assert not query_allowed(state)

    state.events.append(deepcopy(change))
    assert query_allowed(state)

    # Permission to recheck is not completion evidence, nor unlimited retries.
    state.events.append(empty_find(3, wrapped=wrapped))
    assert not query_allowed(state)


@pytest.mark.parametrize("intervening", [
    event(2, "gui", arguments={"action": "wait", "seconds": 1}),
    event(2, "gui", arguments={"action": "press", "key": "enter"}, executed=False),
    event(2, "adapter", "file.write_text", executed=False),
    event(2, "adapter", "command.run", error={"code": "COMMAND_FAILED"}),
    event(2, "adapter", "file.read_text"),
    event(2, "catalog", arguments={"query": "find files"}),
    event(2, "adapter", "playback.find_local", result={"matches": [], "match_count": 0}),
])
def test_observation_or_failed_action_keeps_empty_search_guard(intervening):
    state = RuntimeState(
        task_id="unchanged-empty-search", domain="os", instruction="Find a file",
        events=[empty_find(1), deepcopy(intervening)],
    )
    assert not query_allowed(state)
