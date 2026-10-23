from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from integrations.lite_agent import impress_semantics
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


INSTRUCTION = "Move the picture on page 2 to the top edge."
DOCUMENT_URL = "file:///tmp/synthetic-picture-edge.pptx"
SOURCE_GEOMETRY = {"x": 1800, "y": 2200, "width": 4200, "height": 1800}
TARGET_GEOMETRY = {**SOURCE_GEOMETRY, "y": 0}


def _picture(path: list[int], geometry: dict[str, int]) -> dict[str, Any]:
    return {
        "path": path,
        "name": "Synthetic picture",
        "kind": "com.sun.star.drawing.GraphicObjectShape",
        "is_text": False,
        **geometry,
        "fill_style": "bitmap",
        "graphic_count": 1,
    }


def _slides(geometry: dict[str, int]) -> list[dict[str, Any]]:
    picture = _picture([4], geometry)
    return [
        {
            "slide": 0,
            "width": 10000,
            "height": 8000,
            "picture_containers": [],
            "graphic_shapes": [],
            "all_shapes": [],
            "text_shapes": [],
        },
        {
            "slide": 1,
            "width": 10000,
            "height": 8000,
            "picture_containers": [picture],
            "graphic_shapes": [deepcopy(picture)],
            "all_shapes": [deepcopy(picture)],
            "text_shapes": [],
        },
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


def _inspect(step: int, geometry: dict[str, int]) -> ExecutionEvent:
    return _event(
        step,
        "presentation.inspect",
        {},
        {
            "context_hint": {
                "identity": {"url": DOCUMENT_URL},
                "slide_count": 2,
                "slides": _slides(geometry),
            }
        },
    )


def _edge_arguments(*, selector: list[int] | None = None) -> dict[str, Any]:
    return {
        "slide": 1,
        "slide_number": 2,
        "selector": {"path": selector if selector is not None else [4]},
        "edge": "top",
    }


def _edge_result(
    *,
    geometry: dict[str, int] | None = None,
    edge: str = "top",
    verified: bool = True,
    include_inner_verification: bool = True,
) -> dict[str, Any]:
    resolved = TARGET_GEOMETRY if geometry is None else geometry
    inner = {
        "slide": 1,
        "display_slide_number": 2,
        "edge": edge,
        "path": [-1],
        **resolved,
    }
    if include_inner_verification:
        inner["verification_passed"] = verified
    return {
        "status": "ok",
        "verification": {"passed": verified},
        "adapter_response": {"result": inner},
    }


def _save(step: int) -> ExecutionEvent:
    return _event(
        step,
        "presentation.save",
        {"url": DOCUMENT_URL},
        {"status": "ok", "result": {"url": DOCUMENT_URL, "size": 1}},
    )


def _state(events: list[ExecutionEvent]) -> RuntimeState:
    return RuntimeState(
        task_id="synthetic-picture-edge",
        domain="libreoffice_impress",
        instruction=INSTRUCTION,
        events=events,
    )


def test_verified_edge_form_matches_numeric_observation_plan() -> None:
    arguments = _edge_arguments()
    original_arguments = deepcopy(arguments)
    edge_event = _event(2, "shape.set_geometry", arguments, _edge_result())
    state = _state(
        [
            _inspect(1, SOURCE_GEOMETRY),
            edge_event,
            _save(3),
            _inspect(4, TARGET_GEOMETRY),
        ]
    )

    plan = impress_semantics.picture_edge_plan(state)
    assert plan is not None
    assert plan["step"]["arguments"] == {
        "slide": 1,
        "selector": {"path": [4]},
        **TARGET_GEOMETRY,
    }
    assert impress_semantics._matching_step_events(
        state, plan["step"], expected_edge=plan["edge"]
    ) == [edge_event]
    assert impress_semantics.picture_edge_readback_satisfied(state)
    assert impress_semantics.next_picture_edge_action(state) is None
    assert edge_event.proposed["arguments"] == original_arguments


def test_model_selected_edge_form_is_accepted_before_execution() -> None:
    state = _state([_inspect(1, SOURCE_GEOMETRY)])
    arguments = _edge_arguments()
    original = deepcopy(arguments)

    assert (
        impress_semantics.validate_arguments(state, "shape.set_geometry", arguments)
        is True
    )
    assert arguments == original


def test_focused_read_of_another_page_requests_readback_not_another_move() -> None:
    other_page = _inspect(4, TARGET_GEOMETRY)
    other_page.result["context_hint"]["slides"] = _slides(TARGET_GEOMETRY)[:1]
    other_page.proposed["arguments"] = {"slides": [0]}
    state = _state(
        [
            _inspect(1, SOURCE_GEOMETRY),
            _event(2, "shape.set_geometry", _edge_arguments(), _edge_result()),
            _save(3),
            other_page,
        ]
    )

    assert impress_semantics.next_picture_edge_action(state) is None
    assert not impress_semantics.picture_edge_readback_satisfied(state)
    assert impress_semantics.completion_missing(state) == [
        "after moving the picture, save and run presentation.inspect; its exact "
        "observation-derived geometry must place it at the top edge"
    ]
    target_page = _inspect(5, TARGET_GEOMETRY)
    target_page.result["context_hint"]["slides"] = _slides(TARGET_GEOMETRY)[1:]
    target_page.proposed["arguments"] = {"slides": [1]}
    state.events.append(target_page)
    preserved = deepcopy(state.events)

    assert impress_semantics.picture_edge_readback_satisfied(state)
    assert impress_semantics.completion_missing(state) == []
    assert state.events == preserved


@pytest.mark.parametrize(
    "arguments",
    [
        {**_edge_arguments(), "edge": "bottom"},
        {**_edge_arguments(), "selector": {"path": [5]}},
        {**_edge_arguments(), "x": TARGET_GEOMETRY["x"]},
        {**_edge_arguments(), "selector": {"path": [4], "name": "wrong"}},
    ],
)
def test_edge_form_validation_rejects_mismatched_model_arguments(
    arguments: dict[str, Any],
) -> None:
    state = _state([_inspect(1, SOURCE_GEOMETRY)])

    with pytest.raises(ValueError, match="semantic action must match"):
        impress_semantics.validate_arguments(state, "shape.set_geometry", arguments)


@pytest.mark.parametrize(
    ("case", "arguments", "result"),
    [
        (
            "wrong edge",
            _edge_arguments(),
            _edge_result(edge="bottom"),
        ),
        (
            "wrong selector",
            _edge_arguments(selector=[5]),
            _edge_result(),
        ),
        (
            "unverified",
            _edge_arguments(),
            _edge_result(verified=False),
        ),
        (
            "missing same-layer verification",
            _edge_arguments(),
            _edge_result(include_inner_verification=False),
        ),
        (
            "wrong geometry",
            _edge_arguments(),
            _edge_result(geometry={**TARGET_GEOMETRY, "x": 1801}),
        ),
        (
            "numeric injection",
            {**_edge_arguments(), "x": TARGET_GEOMETRY["x"]},
            _edge_result(),
        ),
    ],
)
def test_edge_form_rejects_nonmatching_or_unverified_results(
    case: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> None:
    del case
    state = _state(
        [
            _inspect(1, SOURCE_GEOMETRY),
            _event(2, "shape.set_geometry", arguments, result),
        ]
    )
    plan = impress_semantics.picture_edge_plan(state)
    assert plan is not None

    assert (
        impress_semantics._matching_step_events(
            state, plan["step"], expected_edge=plan["edge"]
        )
        == []
    )
    assert impress_semantics.next_picture_edge_action(state) == plan["step"]


def test_numeric_geometry_match_remains_compatible() -> None:
    state = _state(
        [
            _inspect(1, SOURCE_GEOMETRY),
            _event(
                2,
                "shape.set_geometry",
                {
                    "slide": 1,
                    "selector": {"path": [4]},
                    **TARGET_GEOMETRY,
                },
                {"status": "ok"},
            ),
        ]
    )
    plan = impress_semantics.picture_edge_plan(state)
    assert plan is not None
    assert impress_semantics._matching_step_events(
        state, plan["step"], expected_edge=plan["edge"]
    )
