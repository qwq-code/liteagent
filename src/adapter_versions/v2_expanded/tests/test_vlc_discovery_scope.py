"""A suggested finder is not an outstanding task obligation."""
from types import SimpleNamespace

import pytest

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.local_file_discovery import local_file_discovery_stage_active
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


def event(action, *, result=None, error=None, arguments=None):
    return ExecutionEvent(
        step=1, timestamp_utc="2026-10-23T00:00:00Z", executed=error is None,
        proposed={"kind": "adapter", "action": action, "arguments": arguments or {}},
        result=result, error=error,
    )


@pytest.mark.parametrize("instruction", [
    "Flip this video vertically and save it as corrected.mp4.",
    "Extract audio from the current video into a separate MP3 file.",
    "Open /tmp/example.mp4 in VLC.",
])
def test_suggested_finder_does_not_create_discovery_obligation(instruction):
    state = RuntimeState(task_id="synthetic-media", domain="vlc", instruction=instruction)
    assert not local_file_discovery_stage_active(state, ["playback.status", "playback.find_local"])


@pytest.mark.parametrize("search_state", ["absent", "empty", "failed", "positive"])
def test_explicit_local_playback_requires_successful_discovery(search_state):
    state = RuntimeState(task_id="synthetic-play", domain="vlc",
                         instruction="Play the music video saved on my desktop.")
    if search_state != "absent":
        state.events.append(event("playback.find_local", result={"context_hint": {
            "matches": [{"path": "/tmp/example.mp4"}] if search_state == "positive" else [],
        }}, error={"code": "FAILED"} if search_state == "failed" else None))
    assert local_file_discovery_stage_active(state, ["playback.find_local"]) == (search_state != "positive")


def test_verified_transform_retains_completion_and_further_edits():
    state = RuntimeState(task_id="synthetic-transform", domain="vlc",
                         instruction="Flip this video vertically and save it as corrected.mp4.")
    state.events.append(event("media.flip_video", arguments={
        "input_path": "/tmp/source.mp4", "output_path": "/tmp/corrected.mp4", "axis": "vertical",
    }, result={"status": "ok", "result": {
        "input_path": "/tmp/source.mp4", "output_path": "/tmp/corrected.mp4", "axis": "vertical",
        "probe": {"path": "/tmp/corrected.mp4", "streams": [{"codec_type": "video"}]},
    }, "verification": {"passed": True}}))
    agent = LiteAgent(LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
                      SimpleNamespace(), model_client=SimpleNamespace(client=object()))
    # Include the finder as a ranking candidate, as in the preserved failure.
    agent.selected_actions = lambda _state: ["playback.status", "media.flip_video", "playback.find_local"]
    assert agent._generic_completion_gate(state)["passed"]
    names = {tool["function"]["name"] for tool in agent.tools(state)}
    assert {"propose_done", "fail_task", "tools_search", "adapter__media_flip_video"} <= names
