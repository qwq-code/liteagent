from __future__ import annotations

import pytest

from integrations.holo_agent.agent import (
    select_first_tool_call,
    system_prompt,
    trim_to_last_n_images,
)


def _observation(label: str) -> dict:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": "<observation>"},
            {"type": "image_url", "image_url": {"url": f"data:{label}"}},
            {"type": "text", "text": "</observation>"},
        ],
    }


def test_only_three_latest_screenshots_remain() -> None:
    messages = [{"role": "system", "content": "system"}]
    messages.extend(_observation(str(index)) for index in range(5))

    trim_to_last_n_images(messages, 3)

    images = [
        chunk
        for message in messages
        if isinstance(message.get("content"), list)
        for chunk in message["content"]
        if chunk.get("type") == "image_url"
    ]
    evicted = [
        chunk
        for message in messages
        if isinstance(message.get("content"), list)
        for chunk in message["content"]
        if chunk.get("text") == "[screenshot evicted]"
    ]
    assert len(images) == 3
    assert len(evicted) == 2


def test_system_prompt_contains_instruction_but_no_tool_format_example() -> None:
    prompt = system_prompt("Enable fullscreen mode.")

    assert "Enable fullscreen mode." in prompt
    assert "visible terminal, IDE" in prompt
    assert "hidden shell" in prompt
    assert "tool_calls" not in prompt
    assert '"name"' not in prompt


def test_native_loop_dispatches_only_first_returned_tool_call() -> None:
    first = object()
    selected, returned_count = select_first_tool_call([first, object(), object()])

    assert selected is first
    assert returned_count == 3


def test_native_loop_rejects_response_without_tool_call() -> None:
    with pytest.raises(ValueError, match="at least one"):
        select_first_tool_call([])
