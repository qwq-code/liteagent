from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.completion_policy import action_is_read_only
from integrations.lite_agent.generic_completion import strict_completion_phase
from integrations.lite_agent.instruction_semantics import strict_instruction_required_actions
from integrations.lite_agent.semantic_requirements import strict_semantic_action_equivalents
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import FORBIDDEN_DATASET_ACTIONS


INSTRUCTION = "Change the picture height to 4, 5, 6 cm on slides 1, 2, 3 respectively."
DOCUMENT_URL = "file:///tmp/synthetic-picture-heights.pptx"


def _picture(path: list[int], height: int) -> dict[str, Any]:
    return {
        "path": path,
        "name": "Synthetic picture",
        "kind": "com.sun.star.drawing.GraphicObjectShape",
        "x": 100,
        "y": 100,
        "width": 5000,
        "height": height,
        "fill_style": "bitmap",
        "is_text": False,
    }


def _slides(heights: list[int]) -> list[dict[str, Any]]:
    return [
        {
            "slide": index,
            "width": 10000,
            "height": 8000,
            "picture_containers": [_picture([index], height)],
            "graphic_shapes": [_picture([index], height)],
            "all_shapes": [_picture([index], height)],
            "text_shapes": [],
        }
        for index, height in enumerate(heights)
    ]


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


def _inspect(step: int, heights: list[int]) -> ExecutionEvent:
    return _event(
        step,
        "presentation.inspect",
        {},
        {
            "context_hint": {
                "identity": {"url": DOCUMENT_URL},
                "slide_count": len(heights),
                "slides": _slides(heights),
            }
        },
    )


def _resize(step: int, slide: int, height: int) -> ExecutionEvent:
    return _event(
        step,
        "shape.set_geometry",
        {
            "slide": slide,
            "selector": {"path": [slide]},
            "height": height,
        },
        {
            "context_hint": {
                "slide": slide,
                "display_slide_number": slide + 1,
                "resolved_selector": {"path": [slide]},
                "height": height,
                "resolved_geometry": {"height": height},
                "verification_passed": True,
            },
            "adapter_response": {
                "result": {
                    "slide": slide,
                    "display_slide_number": slide + 1,
                    "path": [slide],
                    "resolved_selector": {"path": [slide]},
                    "height": height,
                    "resolved_geometry": {"height": height},
                    "verification_passed": True,
                },
                "status": "ok",
            },
        },
    )


def _save(step: int) -> ExecutionEvent:
    return _event(
        step,
        "presentation.save",
        {"url": DOCUMENT_URL},
        {"status": "ok", "result": {"url": DOCUMENT_URL, "size": 100}},
    )


def _state(events: list[ExecutionEvent]) -> RuntimeState:
    return RuntimeState(
        task_id="synthetic-picture-heights",
        domain="libreoffice_impress",
        instruction=INSTRUCTION,
        events=events,
    )


def _completion() -> dict[str, Any]:
    return {
        "reason": "The requested picture heights were applied.",
        "evidence": ["verified"],
    }


@pytest.mark.parametrize("cleanup", [None, "shape.delete", "slide.delete"])
def test_ordered_image_deck_does_not_require_both_cleanup_strategies(cleanup):
    events = [_inspect(1, [8000])]
    if cleanup is None:
        # This starting page is already empty; no cleanup operation is needed.
        page = events[0].result["context_hint"]["slides"][0]
        for field in ("picture_containers", "graphic_shapes", "all_shapes"):
            page[field] = []
    if cleanup is not None:
        arguments = {"slide": 0}
        if cleanup == "shape.delete":
            arguments["selector"] = {"path": [0]}
        events.append(_event(len(events) + 1, cleanup, arguments, {"status": "ok"}))
    for index in range(0 if cleanup == "slide.delete" else 1, 3):
        events.append(_event(
            len(events) + 1, "slide.create", {"index": index, "layout": 20},
            {"status": "ok"},
        ))
    for index in range(3):
        events.append(_event(
            len(events) + 1, "shape.insert_image",
            {"slide": index, "path": f"/tmp/frame{index + 1}.png"},
            {"status": "ok"},
        ))
    state = RuntimeState(
        task_id="synthetic-ordered-image-deck",
        domain="libreoffice_impress",
        instruction=(
            "The Desktop has frame1.png to frame3.png. Create three blank slides "
            "with one image per slide in numerical order."
        ),
        events=events,
    )
    before_save = CompletionMixin._generic_completion_gate(state)
    assert not before_save["passed"]
    assert any("save" in item for item in before_save["missing"])
    assert not any("have not succeeded" in item for item in before_save["missing"])

    state.events.extend([_save(len(events) + 1), _inspect(len(events) + 2, [8000] * 3)])
    assert CompletionMixin._generic_completion_gate(state) == {"passed": True, "missing": []}


@pytest.mark.parametrize("action", ["shape.set_geometry", "shape.resize"])
def test_strict_gate_rejects_an_unfinished_multi_target_picture_request(action) -> None:
    state = _state(
        [
            _inspect(1, [8000, 8000, 8000]),
            _resize(2, 0, 4000),
            _save(3),
            _inspect(4, [4000, 8000, 8000]),
        ]
    )

    state.events[1].proposed["action"] = action
    gate = CompletionMixin._generic_completion_gate(state, _completion())

    assert gate["passed"] is False
    assert any("each requested picture" in item for item in gate["missing"])


@pytest.mark.parametrize("action", ["shape.set_geometry", "shape.resize"])
def test_strict_gate_accepts_all_observation_derived_picture_targets(action) -> None:
    state = _state(
        [
            _inspect(1, [8000, 8000, 8000]),
            _resize(2, 0, 4000),
            _resize(3, 1, 5000),
            _resize(4, 2, 6000),
            _save(5),
            _inspect(6, [4000, 5000, 6000]),
        ]
    )

    for event in state.events[1:4]:
        event.proposed["action"] = action
    assert CompletionMixin._generic_completion_gate(state, _completion()) == {
        "passed": True,
        "missing": [],
    }


@pytest.mark.parametrize("action,geometry", [
    ("shape.align_to_slide", {"edge": "bottom"}),
    ("shape.move", {"y": 6000}),
])
def test_atomic_positioning_requires_save_and_readback_then_allows_completion(action, geometry):
    def phase(state, gate):
        return strict_completion_phase(
            state, gate, instruction_actions=strict_instruction_required_actions,
            legacy_actions=FORBIDDEN_DATASET_ACTIONS, is_read_only_action=action_is_read_only,
            semantic_action_equivalents=strict_semantic_action_equivalents,
        )

    state = RuntimeState(
        task_id="synthetic-atomic-positioning", domain="libreoffice_impress",
        instruction="Move the table on Page 1 to the bottom of the slide.",
        events=[_inspect(1, [2000])],
    )
    assert not CompletionMixin._generic_completion_gate(state)["passed"]
    state.events.append(_event(2, action, {"slide": 0, "selector": {"path": [0]}, **geometry}, {
        "status": "ok", "result": {"slide": 0, "path": [0], "x": 100, "y": 6000,
                                    "width": 5000, "height": 2000, "verification_passed": True},
        "verification": {"passed": True},
    }))
    gate = CompletionMixin._generic_completion_gate(state)
    assert not gate["passed"]
    assert any("save" in item or "persist" in item for item in gate["missing"])
    assert not any("have not succeeded" in item for item in gate["missing"])
    assert phase(state, gate) == "persist_and_readback"
    state.events.append(_save(3))
    gate = CompletionMixin._generic_completion_gate(state)
    assert not gate["passed"]
    assert any("read" in item for item in gate["missing"])
    assert phase(state, gate) == "readback"
    readback = _inspect(4, [2000])
    for shapes in ("picture_containers", "graphic_shapes", "all_shapes"):
        readback.result["context_hint"]["slides"][0][shapes][0]["y"] = 6000
    state.events.append(readback)
    before = deepcopy(state.events)
    assert CompletionMixin._generic_completion_gate(state) == {"passed": True, "missing": []}
    assert state.events == before
    assert phase(state, CompletionMixin._generic_completion_gate(state)) == "done"
    state.events[1].executed = False
    gate = CompletionMixin._generic_completion_gate(state)
    assert not gate["passed"]
    assert any("shape.set_geometry" in item for item in gate["missing"])


def _content_role_state(action: str) -> RuntimeState:
    arguments = {
        "slides" if action == "slides.format_text_roles" else "slide": [3]
        if action == "slides.format_text_roles"
        else 3,
        "roles": ["content"],
        "font_size": 18,
        "color": "blue",
    }
    return RuntimeState(
        task_id="synthetic-content-role-format",
        domain="libreoffice_impress",
        instruction=(
            "Change the font size of the content on slide 4 to 18, and change the "
            "font color to blue. Change the slide's background to yellow."
        ),
        events=[
            _event(
                1,
                action,
                arguments,
                {
                    "status": "ok",
                    "result": {
                        "slides": [
                            {
                                "slide": 3,
                                "rules": [
                                    {
                                        "normalized_roles": ["content"],
                                        "formatted": [
                                            {"path": [2], "font_size": 18, "color": 255}
                                        ],
                                    }
                                ],
                            }
                        ]
                    },
                },
            ),
            _event(
                2,
                "slide.set_background",
                {"slide": 3, "color": "yellow"},
                {"status": "ok"},
            ),
            _save(3),
            _event(
                4,
                "presentation.inspect",
                {},
                {
                    "context_hint": {
                        "identity": {"url": DOCUMENT_URL},
                        "slide_count": 4,
                        "slides": [
                            {
                                "slide": 3,
                                "background": {
                                    "style": "solid",
                                    "color": 0xFFFF00,
                                },
                            }
                        ],
                    }
                },
            ),
        ],
    )


@pytest.mark.parametrize(
    "action", ["slide.format_text_roles", "slides.format_text_roles"]
)
def test_content_role_completion_accepts_both_public_forms(action: str) -> None:
    state = _content_role_state(action)
    before = deepcopy(state.events)

    assert CompletionMixin._generic_completion_gate(state)["passed"] is True
    assert state.events == before

    state.events = state.events[:2]
    missing = CompletionMixin._generic_completion_gate(state)["missing"]
    assert missing
    assert any("save" in item or "persist" in item for item in missing)
    assert not any("format_text_roles" in item for item in missing)


@pytest.mark.parametrize("unexecuted", [True, False])
def test_content_role_completion_requires_successful_plural_role_evidence(
    unexecuted: bool,
) -> None:
    state = _content_role_state("slides.format_text_roles")
    event = state.events[0]
    if unexecuted:
        event.executed = False
        event.error = {"detail": "rejected", "previous_result": deepcopy(event.result)}
    else:
        event.result["result"]["slides"][0]["rules"][0]["normalized_roles"] = ["title"]

    gate = CompletionMixin._generic_completion_gate(state)
    assert gate["passed"] is False
    assert any("content-only" in item for item in gate["missing"])


def test_later_plural_format_cannot_be_hidden_by_earlier_singular_format() -> None:
    state = _content_role_state("slide.format_text_roles")
    later = _content_role_state("slides.format_text_roles").events[0]
    later.step = 2
    later.proposed["arguments"]["font_size"] = 23
    later.result["result"]["slides"][0]["rules"][0]["formatted"][0]["font_size"] = 23
    for event in state.events[1:]:
        event.step += 1
    state.events.insert(1, later)

    gate = CompletionMixin._generic_completion_gate(state)
    assert gate["passed"] is False
    assert any("content-only" in item for item in gate["missing"])
