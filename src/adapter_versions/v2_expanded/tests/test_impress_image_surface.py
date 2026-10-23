from __future__ import annotations

from types import SimpleNamespace

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


INSTRUCTION = 'Add an image "none.png" on the Desktop to slide 2 with 1cm*1cm size.'


def _event(step: int, action: str, arguments: dict[str, object]) -> ExecutionEvent:
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-09-08T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": arguments},
        executed=True,
        result={"status": "ok"},
    )


def _agent() -> LiteAgent:
    return LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
        SimpleNamespace(execute=lambda *_args, **_kwargs: None),
    )


def test_initial_sized_image_surface_exposes_inspection_and_mutation_contract() -> None:
    state = RuntimeState(
        task_id="synthetic-image-surface",
        domain="libreoffice_impress",
        instruction=INSTRUCTION,
        events=[],
    )
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
        SimpleNamespace(execute=lambda *_args, **_kwargs: None),
    )
    try:
        tools = agent.tools(state)
        names = [tool["function"]["name"] for tool in tools]
        assert names == [
            "adapter__presentation_inspect",
            "adapter__shape_insert_image",
        ]

        image = tools[1]["function"]
        assert "Call presentation.inspect first" in image["description"]
        assert image["parameters"]["required"] == [
            "path",
            "width_measurement",
            "height_measurement",
        ]
        assert image["parameters"]["allOf"] == [
            {
                "anyOf": [
                    {"required": ["slide"]},
                    {"required": ["slide_number"]},
                ]
            }
        ]
    finally:
        agent.client.close()


def test_successful_image_insertion_surface_moves_to_save_then_readback() -> None:
    state = RuntimeState(
        task_id="synthetic-image-surface",
        domain="libreoffice_impress",
        instruction=INSTRUCTION,
        events=[
            _event(
                1,
                "shape.insert_image",
                {
                    "slide_number": 2,
                    "path": "~/Desktop/none.png",
                    "width_measurement": {"value": 1, "unit": "cm"},
                    "height_measurement": {"value": 1, "unit": "cm"},
                },
            )
        ],
    )
    agent = _agent()
    try:
        assert [tool["function"]["name"] for tool in agent.tools(state)] == [
            "adapter__presentation_save"
        ]

        state.events.append(_event(2, "presentation.save", {"url": "file:///deck.pptx"}))
        assert [tool["function"]["name"] for tool in agent.tools(state)] == [
            "adapter__presentation_inspect"
        ]
    finally:
        agent.client.close()
