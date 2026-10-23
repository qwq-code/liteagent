from __future__ import annotations

from typing import Any

import pytest

from integrations.lite_agent.impress_background import (
    background_argument_contract_errors,
    background_requirement_errors,
    parse_background_intent,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


DOCUMENT_URL = "file:///tmp/synthetic-background.pptx"
RED = 0xFF0000
BLUE = 0x0000FF


def _event(
    step: int,
    action: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> ExecutionEvent:
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-09-01T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": arguments},
        executed=True,
        result=result,
    )


def _slides(colors: list[int]) -> list[dict[str, Any]]:
    return [
        {
            "slide": index,
            "background": {"style": "solid", "color": color},
        }
        for index, color in enumerate(colors)
    ]


def _inspect(
    step: int, colors: list[int], *, reported_count: int | None = None
) -> ExecutionEvent:
    slides = _slides(colors)
    return _event(
        step,
        "presentation.inspect",
        {},
        {
            "context_hint": {
                "identity": {"url": DOCUMENT_URL},
                "slide_count": len(slides)
                if reported_count is None
                else reported_count,
                "slides": slides,
            }
        },
    )


def _save(step: int) -> ExecutionEvent:
    return _event(
        step,
        "presentation.save",
        {"url": DOCUMENT_URL},
        {"status": "ok", "result": {"url": DOCUMENT_URL, "size": 1}},
    )


def _background(step: int, *, all_slides: bool, color: str = "red") -> ExecutionEvent:
    arguments: dict[str, Any] = {"color": color}
    if all_slides:
        arguments["all_slides"] = True
    else:
        arguments["slide"] = 0
    return _event(step, "slide.set_background", arguments, {"status": "ok"})


def _state(instruction: str, events: list[ExecutionEvent]) -> RuntimeState:
    return RuntimeState(
        task_id="synthetic-background",
        domain="libreoffice_impress",
        instruction=instruction,
        events=events,
    )


def test_explicit_all_slides_scope_accepts_complete_readback() -> None:
    state = _state(
        "Change the background of all slides to red.",
        [
            _inspect(1, [BLUE, BLUE]),
            _background(2, all_slides=True),
            _save(3),
            _inspect(4, [RED, RED]),
        ],
    )

    assert background_requirement_errors(state) == []


def test_implicit_scope_accepts_model_selected_all_slides_after_full_readback() -> None:
    state = _state(
        "Change the slide's background to red.",
        [
            _inspect(1, [BLUE, BLUE]),
            _background(2, all_slides=True),
            _save(3),
            _inspect(4, [RED, RED]),
        ],
    )

    assert background_requirement_errors(state) == []


def test_implicit_all_slides_scope_rejects_incomplete_readback() -> None:
    state = _state(
        "Change the slide's background to red.",
        [
            _inspect(1, [BLUE, BLUE]),
            _background(2, all_slides=True),
            _save(3),
            _inspect(4, [RED, BLUE]),
        ],
    )

    errors = background_requirement_errors(state)
    assert errors
    assert "inspected final slide background" in errors[0]


@pytest.mark.parametrize("observed_color", [RED, BLUE])
def test_implicit_all_slides_scope_rejects_truncated_slide_inventory(observed_color) -> None:
    state = _state(
        "Change the slide's background to red.",
        [
            _inspect(1, [BLUE, BLUE]),
            _background(2, all_slides=True),
            _save(3),
            _inspect(4, [observed_color], reported_count=2),
        ],
    )

    errors = background_requirement_errors(state)
    assert errors
    if observed_color == RED:
        assert "incomplete" in errors[0]
        assert "presentation.inspect without slides" in errors[0]
        assert "new model-selected slide.set_background" not in errors[0]
    else:
        assert "does not match" in errors[0]
        assert "new model-selected slide.set_background" in errors[0]


def test_numbered_scope_still_rejects_overbroad_all_slides_mutation() -> None:
    state = _state(
        "Change the background of slide 1 to red.",
        [
            _inspect(1, [BLUE, BLUE]),
            _background(2, all_slides=True),
            _save(3),
            _inspect(4, [RED, RED]),
        ],
    )

    errors = background_requirement_errors(state)
    assert errors
    assert "outside the single requested target" in errors[0]


def test_numbered_scope_accepts_exact_single_slide_mutation() -> None:
    state = _state(
        "Change the background of slide 1 to red.",
        [
            _inspect(1, [BLUE, BLUE]),
            _background(2, all_slides=False),
            _save(3),
            _inspect(4, [RED, BLUE]),
        ],
    )

    assert background_requirement_errors(state) == []


@pytest.mark.parametrize(
    "instruction",
    [
        "Change the background of every page to red.",
        "Change the background of all pages to red.",
        "Change the background of each page to red.",
        "Change the background of every pages to red.",
        "Change the background throughout the presentation to red.",
        "Change the background throughout presentation to red.",
        "Change the background throughout the deck to red.",
        "Change the background throughout the entire deck to red.",
    ],
)
def test_generic_presentation_wide_language_selects_all_slides(
    instruction: str,
) -> None:
    intent = parse_background_intent(instruction)

    assert intent is not None
    assert intent.all_slides is True
    assert intent.slide is None


@pytest.mark.parametrize(
    "instruction",
    [
        "Change the background of a single slide to red.",
        "Change the background of slide 2 to red.",
        "Change the background of page 3 to red.",
        "Change the background on the first slide to red.",
    ],
)
def test_single_or_numbered_slide_language_does_not_select_all_slides(
    instruction: str,
) -> None:
    intent = parse_background_intent(instruction)

    assert intent is not None
    assert intent.all_slides is False


@pytest.mark.parametrize(
    "instruction",
    [
        "Change the background of every page to red.",
        "Change the background throughout the presentation to red.",
        "Change the background throughout the deck to red.",
    ],
)
def test_presentation_wide_contract_requires_model_all_slides_argument(
    instruction: str,
) -> None:
    state = _state(instruction, [])

    errors = background_argument_contract_errors(
        state,
        "slide.set_background",
        {"color": "red", "slide": 0},
    )

    assert errors
    assert "all_slides=true" in errors[0]
