from __future__ import annotations

import pytest

from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import action_relevance_score


def _gate(instruction: str, action: str, *, executed: bool = True) -> dict:
    state = RuntimeState(
        task_id="synthetic-vlc-snapshot",
        domain="vlc",
        instruction=instruction,
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-09-07T00:00:00Z",
                proposed={"kind": "adapter", "action": action, "arguments": {}},
                executed=executed,
                result={"status": "ok", "verification": {"passed": True}}
                if executed
                else None,
                error=None if executed else {"code": "PATH_NOT_FOUND"},
            )
        ],
    )
    return CompletionMixin._generic_completion_gate(
        state,
        {
            "reason": "The requested change is complete.",
            "evidence": ["Verified result."],
        },
    )


@pytest.mark.parametrize(
    "instruction",
    [
        "Save a photo of the current video scene to Pictures.",
        "Capture a snapshot from the paused movie.",
        "Create a still image of the opening shot.",
        "Save a picture from the clip at 4 seconds.",
        "Extract a frame from the current video and save the picture.",
    ],
)
def test_verified_frame_extraction_counts_for_snapshot_requests(
    instruction: str,
) -> None:
    assert action_relevance_score("vlc", "media.extract_frame", instruction) >= 2
    assert _gate(instruction, "media.extract_frame") == {"passed": True, "missing": []}


@pytest.mark.parametrize(
    ("instruction", "action", "executed"),
    [
        ("Save a photo of the current video scene.", "media.extract_frame", False),
        ("Save a photo of the current video scene.", "playback.status", True),
        ("Set the volume to 25 percent.", "media.extract_frame", True),
        ("Use a minimal interface after restart.", "media.extract_frame", True),
    ],
)
def test_frame_vocabulary_does_not_replace_successful_relevant_mutation(
    instruction: str, action: str, executed: bool
) -> None:
    assert _gate(instruction, action, executed=executed)["passed"] is False
