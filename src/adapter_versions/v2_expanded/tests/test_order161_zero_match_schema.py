from __future__ import annotations

from jsonschema import Draft202012Validator

from integrations.lite_agent.local_file_discovery import constrain_zero_match_find_tools
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools


def test_zero_match_query_can_expand_search_with_optional_dimension() -> None:
    state = RuntimeState(task_id="media-find", domain="vlc", instruction="Play the video on my desktop")
    original = {
        "roots": ["~/Desktop"],
        "name_patterns": ["Rick Astley - Never Gonna Gi..."],
        "kind": "file",
        "max_results": 1,
    }
    state.events.append(
        ExecutionEvent(
            step=1,
            timestamp_utc="2026-10-21T00:00:00Z",
            proposed={"kind": "adapter", "action": "playback.find_local", "arguments": original},
            executed=True,
            result={"matches": [], "match_count": 0, "returned_count": 0},
        )
    )
    tools = build_tools(
        "vlc", ["playback.find_local"], include_gui=False,
        include_control_tools=False, strict_generic=True,
    )
    constrained = constrain_zero_match_find_tools(tools, state)
    schema = constrained[0]["function"]["parameters"]
    validator = Draft202012Validator(schema)

    assert not validator.is_valid(original)
    assert not validator.is_valid({**original, "recursive": True})
    assert validator.is_valid({**original, "name_patterns": ["*.mp4"]})
    assert validator.is_valid({"roots": ["~/Desktop"], "kind": "file"})
    assert schema["properties"]["name_patterns"]["items"]["enum"] == [
        "*", "*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov",
        "*.mp3", "*.wav", "*.flac", "*.ogg",
    ]


def test_zero_match_query_tracks_each_attempt_without_blocking_new_dimensions() -> None:
    state = RuntimeState(task_id="media-find", domain="vlc", instruction="Play the video on my desktop")
    for step, recursive in enumerate((None, True), 1):
        arguments = {"roots": ["~/Desktop"], "name_patterns": ["video..."], "kind": "file"}
        if recursive is not None:
            arguments["recursive"] = recursive
        state.events.append(
            ExecutionEvent(
                step=step,
                timestamp_utc="2026-10-21T00:00:00Z",
                proposed={"kind": "adapter", "action": "playback.find_local", "arguments": arguments},
                executed=True,
                result={"matches": [], "match_count": 0, "returned_count": 0},
            )
        )
    tools = build_tools(
        "vlc", ["playback.find_local"], include_gui=False,
        include_control_tools=False, strict_generic=True,
    )
    schema = constrain_zero_match_find_tools(tools, state)[0]["function"]["parameters"]
    validator = Draft202012Validator(schema)

    assert not validator.is_valid({"roots": ["~/Desktop"], "name_patterns": ["video..."], "kind": "file"})
    assert not validator.is_valid({"roots": ["~/Desktop"], "name_patterns": ["video..."], "kind": "file", "recursive": True})
    assert validator.is_valid({"roots": ["~/Desktop"], "name_patterns": ["*.mp4"], "kind": "file", "recursive": True})


def test_non_truncated_zero_match_keeps_normal_search_patterns() -> None:
    state = RuntimeState(task_id="media-find", domain="vlc", instruction="Play a video")
    state.events.append(
        ExecutionEvent(
            step=1,
            timestamp_utc="2026-10-21T00:00:00Z",
            proposed={
                "kind": "adapter", "action": "playback.find_local",
                "arguments": {"roots": ["~/Desktop"], "name_patterns": ["*.mp4"]},
            },
            executed=True,
            result={"matches": [], "match_count": 0, "returned_count": 0},
        )
    )
    tools = build_tools(
        "vlc", ["playback.find_local"], include_gui=False,
        include_control_tools=False, strict_generic=True,
    )
    schema = constrain_zero_match_find_tools(tools, state)[0]["function"]["parameters"]

    assert "enum" not in schema["properties"]["name_patterns"]["items"]
