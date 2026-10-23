from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace
from typing import Any

import pytest

from integrations.lite_agent.action_selection import ActionSelectionMixin
from integrations.lite_agent import impress_semantics
from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.completion_policy import action_is_read_only
from integrations.lite_agent.completion_recovery import (
    strict_proactive_completion_tools,
)
from integrations.lite_agent.episode_control import (
    begin_same_vm_soft_restart,
    mark_tool_result_for_audit,
)
from integrations.lite_agent.instruction_semantics import (
    strict_instruction_required_actions,
)
from integrations.lite_agent.semantic_requirements import (
    strict_semantic_action_equivalents,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import (
    FORBIDDEN_DATASET_ACTIONS,
    build_tools,
)


INSTRUCTION = "Make all textboxes underlined on slides 1 and 3."
DOCUMENT_URL = "file:///tmp/synthetic-underline-wiring.pptx"


def _textbox(
    path: list[int], *, underline: bool = False, text: str = "text"
) -> dict[str, Any]:
    return {
        "index": path[0],
        "path": path,
        "name": f"Textbox {path}",
        "kind": "com.sun.star.drawing.CustomShape",
        "is_text": True,
        "x": 100,
        "y": 100,
        "width": 1000,
        "height": 500,
        "lines": [text],
        "text_style": {"underline": underline},
    }


def _slides(
    *, slide_one_underlined: bool = False, slide_three_underlined: bool = False
) -> list[dict[str, Any]]:
    return [
        {
            "slide": 0,
            "width": 10000,
            "height": 8000,
            "recursive_text_shapes": [
                _textbox([0], underline=slide_one_underlined),
                _textbox([1, 0], underline=slide_one_underlined),
            ],
            "text_shapes": [
                _textbox([0], underline=slide_one_underlined),
                _textbox([1, 0], underline=slide_one_underlined),
            ],
        },
        {
            "slide": 1,
            "width": 10000,
            "height": 8000,
            "recursive_text_shapes": [_textbox([4])],
            "text_shapes": [_textbox([4])],
        },
        {
            "slide": 2,
            "width": 10000,
            "height": 8000,
            "recursive_text_shapes": [
                _textbox([2], underline=slide_three_underlined),
            ],
            "text_shapes": [
                _textbox([2], underline=slide_three_underlined),
            ],
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


def _inspect(step: int, slides: list[dict[str, Any]]) -> ExecutionEvent:
    return _event(
        step,
        "presentation.inspect",
        {},
        {
            "context_hint": {
                "identity": {"url": DOCUMENT_URL},
                "slide_count": len(slides),
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


def _state(events: list[ExecutionEvent]) -> RuntimeState:
    return RuntimeState(
        task_id="synthetic-underline-wiring",
        domain="libreoffice_impress",
        instruction=INSTRUCTION,
        events=events,
    )


def _shape_tools() -> list[dict[str, Any]]:
    return build_tools(
        "libreoffice_impress",
        ["presentation.inspect", "shape.format_text", "slide.set_background"],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )


def _focused_inspect(step: int, slides: list[dict[str, Any]]) -> ExecutionEvent:
    event = _inspect(step, slides)
    indices = [slide["slide"] for slide in slides]
    event.proposed["arguments"] = {"slides": indices}
    event.result["context_hint"].update({"slide_count": 3, "inspected_slides": indices})
    return event


def test_first_seen_pages_accumulate_without_overwriting_initial_formatting():
    initial = _slides()
    state = _state([_focused_inspect(1, [initial[2]])])
    assert impress_semantics.textbox_underline_plan(state) is None
    state.events.extend(
        [
            _focused_inspect(2, [initial[0]]),
            _focused_inspect(3, _slides(slide_three_underlined=True)),
        ]
    )
    preserved = deepcopy(state.events)

    hint = state.initial_presentation_context_hint()
    assert hint["inspected_slides"] == [0, 1, 2]
    assert hint["slides"] == initial
    plan = impress_semantics.textbox_underline_plan(state)
    assert plan is not None
    assert len(plan["steps"]) == 3
    assert state.events == preserved


def test_split_initial_reads_allow_existing_completion_after_all_work_is_verified():
    initial = _slides()
    state = _state(
        [_focused_inspect(1, [initial[2]]), _focused_inspect(2, [initial[0]])]
    )
    for step, (slide, path) in enumerate([(0, [0]), (0, [1, 0]), (2, [2])], 3):
        state.events.append(
            _event(
                step,
                "shape.format_text",
                {"slide": slide, "selector": {"path": path}, "underline": True},
                {"ok": True},
            )
        )
    assert impress_semantics.completion_missing(state)
    state.events.append(_save(6))
    assert impress_semantics.completion_missing(state)
    state.events.append(_focused_inspect(7, [_slides(slide_one_underlined=True)[0]]))
    assert impress_semantics.completion_missing(state)
    assert impress_semantics.next_textbox_underline_spec(state) is None
    state.events.append(_focused_inspect(8, [_slides(slide_three_underlined=True)[2]]))
    preserved = deepcopy(state.events)

    assert impress_semantics.textbox_underline_readback_satisfied(state)
    assert impress_semantics.completion_missing(state) == []
    assert state.events == preserved


def test_post_save_page_observations_keep_the_latest_read_of_each_page():
    initial = _slides(slide_one_underlined=True, slide_three_underlined=True)
    state = _state(
        [
            _inspect(1, initial),
            _save(2),
            _focused_inspect(3, [initial[0]]),
            _focused_inspect(4, [initial[2]]),
            _focused_inspect(5, [_slides()[0]]),
        ]
    )
    preserved = deepcopy(state.events)

    assert not impress_semantics.textbox_underline_readback_satisfied(state)
    target = impress_semantics.next_textbox_underline_spec(state)
    assert target is not None
    assert target["slide"] == 0
    assert target["selector"] == {"path": [0]}
    assert state.events == preserved


@pytest.mark.parametrize("boundary", ["save", "document", "page_count", "mutation"])
def test_post_save_page_observations_do_not_mix_different_snapshots(boundary):
    initial = _slides(slide_one_underlined=True, slide_three_underlined=True)
    state = _state([_inspect(1, initial), _save(2), _focused_inspect(3, [initial[0]])])
    later = _focused_inspect(5, [initial[2]])
    if boundary == "save":
        state.events.append(_save(4))
    elif boundary == "mutation":
        state.events.append(_event(4, "slide.move", {"slide": 0, "to_index": 1}, {}))
    elif boundary == "document":
        later.result["context_hint"]["identity"] = {"url": "file:///tmp/other.odp"}
    else:
        later.result["context_hint"]["slide_count"] = 4
    state.events.append(later)
    preserved = deepcopy(state.events)

    readback = impress_semantics._latest_post_save_inspection(state, 1)
    assert readback is not None
    assert [
        page["slide"] for page in impress_semantics._inspection_slides(readback)
    ] == [2]
    assert state.events == preserved


@pytest.mark.parametrize("change", ["document", "page_order", "page_count"])
def test_first_seen_pages_do_not_merge_across_document_or_page_identity_changes(change):
    initial = _slides()
    first = _focused_inspect(1, [initial[2]])
    later = _focused_inspect(3, [initial[0]])
    state = _state([first])
    if change == "document":
        later.result["context_hint"]["identity"]["url"] = "file:///tmp/another.odp"
    elif change == "page_order":
        state.events.append(_event(2, "slide.move", {"slide": 0, "index": 1}, {}))
    else:
        later.result["context_hint"]["slide_count"] = 4
    state.events.append(later)

    assert state.initial_presentation_context_hint() == first.result["context_hint"]
    assert impress_semantics.textbox_underline_plan(state) is None


def test_multislide_underline_stages_each_model_selected_target() -> None:
    state = _state([])

    assert strict_instruction_required_actions("libreoffice_impress", INSTRUCTION) == [
        "presentation.inspect",
        "shape.format_text",
    ]
    assert impress_semantics.next_action(state) == "presentation.inspect"
    assert impress_semantics.next_structured_action(state) is None
    assert [
        tool["function"]["name"]
        for tool in impress_semantics.filter_tools(state, _shape_tools())
    ] == ["adapter__presentation_inspect"]

    slides = _slides()
    state.events.append(_inspect(1, slides))
    plan = impress_semantics.textbox_underline_plan(state)
    assert plan is not None
    assert [target["slide"] for target in plan["resolved_targets"]] == [0, 0, 2]

    first = plan["resolved_targets"][0]["step"]
    assert impress_semantics.next_action(state) == "shape.format_text"
    assert impress_semantics.next_structured_action(state) == first
    assert impress_semantics.stage_actions(
        state, ["presentation.inspect", "shape.format_text", "slide.set_background"]
    ) == ["presentation.inspect", "shape.format_text"]
    assert [
        tool["function"]["name"]
        for tool in impress_semantics.filter_tools(state, _shape_tools())
    ] == ["adapter__presentation_inspect", "adapter__shape_format_text"]

    model_arguments = deepcopy(first["arguments"])
    ActionSelectionMixin._validate_stateful_arguments(
        state, "shape.format_text", model_arguments
    )
    assert model_arguments == first["arguments"]

    state.events.append(_event(2, "shape.format_text", model_arguments, {"ok": True}))
    second = plan["resolved_targets"][1]["step"]
    assert impress_semantics.next_structured_action(state) == second
    assert impress_semantics.next_action(state) == "shape.format_text"


@pytest.mark.parametrize("completed_targets", [0, 1])
def test_partial_underline_keeps_inspection_and_model_selected_format_arguments(
    completed_targets: int,
) -> None:
    state = _state([_inspect(1, _slides())])
    if completed_targets:
        state.events.append(
            _event(
                2,
                "shape.format_text",
                {"slide": 0, "selector": {"path": [0]}, "underline": True},
                {"ok": True},
            )
        )
    before = deepcopy(state.events)

    def no_execution(*args, **kwargs):
        pytest.fail("Building tools must not execute an Adapter action")

    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
        SimpleNamespace(execute=no_execution),
    )
    try:
        functions = {
            tool["function"]["name"]: tool["function"] for tool in agent.tools(state)
        }
        assert "adapter__presentation_inspect" in functions
        assert "adapter__shape_format_text" in functions
        native = {tool["function"]["name"]: tool["function"] for tool in _shape_tools()}
        for name in ("adapter__presentation_inspect", "adapter__shape_format_text"):
            assert functions[name]["parameters"] == native[name]["parameters"]
        assert agent._generic_completion_gate(state)["passed"] is False
        assert state.events == before
    finally:
        agent.client.close()


def test_underline_matching_accepts_index_alias_and_slide_number() -> None:
    state = _state([_inspect(1, _slides())])
    plan = impress_semantics.textbox_underline_plan(state)
    assert plan is not None
    target = plan["resolved_targets"][0]
    expected = target["step"]
    model_arguments = {
        "slide_number": expected["arguments"]["slide"] + 1,
        "selector": {"index": target["selector"].get("path", [])[0]},
        "underline": True,
    }
    original_arguments = deepcopy(model_arguments)
    assert (
        impress_semantics.validate_arguments(
            state, "shape.format_text", model_arguments
        )
        is True
    )
    assert model_arguments == original_arguments
    event = _event(2, "shape.format_text", model_arguments, {"ok": True})
    state.events.append(event)

    # The old exact-dict matcher treated this successful call as a missing
    # mutation because the plan uses path while the public model call uses index.
    assert impress_semantics._matching_step_events(state, expected) == []
    assert impress_semantics._matching_step_events(
        state, expected, allow_textbox_selector_aliases=True
    ) == [event]
    assert (
        impress_semantics.next_textbox_underline_spec(state)
        == plan["resolved_targets"][1]
    )


def test_underline_matching_accepts_path_alias_for_index_plan() -> None:
    state = _state([_inspect(1, _slides())])
    step = {
        "action": "shape.format_text",
        "arguments": {
            "slide": 0,
            "selector": {"index": 0},
            "underline": True,
        },
    }
    model_arguments = {
        "slide_number": 1,
        "selector": {"path": [0]},
        "underline": True,
    }
    event = _event(2, "shape.format_text", model_arguments, {"ok": True})
    state.events.append(event)

    assert impress_semantics._matching_step_events(
        state, step, allow_textbox_selector_aliases=True
    ) == [event]


@pytest.mark.parametrize(
    "selector",
    [
        {"index": 99},
        {"index": 1},
        {"index": 0, "path": [0]},
        {"index": 0, "name": "Textbox [0]"},
        {"name": "Textbox [0]"},
    ],
)
def test_underline_selector_aliases_reject_wrong_or_non_single_identity(
    selector: dict[str, Any],
) -> None:
    state = _state([_inspect(1, _slides())])
    plan = impress_semantics.textbox_underline_plan(state)
    assert plan is not None
    target = plan["resolved_targets"][0]
    arguments = {
        "slide": target["slide"],
        "selector": selector,
        "underline": True,
    }
    event = _event(2, "shape.format_text", arguments, {"ok": True})

    assert (
        impress_semantics._matching_step_events(
            state,
            target["step"],
            allow_textbox_selector_aliases=True,
        )
        == []
    )
    assert event.proposed["arguments"] == arguments


@pytest.mark.parametrize(
    "selector",
    [
        {"index": 99},
        {"index": 1},
        {"index": 0, "path": [0]},
        {"index": 0, "name": "Textbox [0]"},
        {"name": "Textbox [0]"},
    ],
)
def test_underline_validation_rejects_wrong_or_non_single_identity(
    selector: dict[str, Any],
) -> None:
    state = _state([_inspect(1, _slides())])
    plan = impress_semantics.textbox_underline_plan(state)
    assert plan is not None
    target = plan["resolved_targets"][0]
    arguments = {
        "slide_number": target["slide"] + 1,
        "selector": selector,
        "underline": True,
    }

    with pytest.raises(ValueError, match="semantic action must match"):
        impress_semantics.validate_arguments(state, "shape.format_text", arguments)


def test_underline_completion_matches_index_aliases_without_rewriting_arguments() -> (
    None
):
    initial = _slides()
    state = _state([_inspect(1, initial)])
    plan = impress_semantics.textbox_underline_plan(state)
    assert plan is not None

    model_arguments_by_target: list[dict[str, Any]] = []
    for step, target in enumerate(plan["resolved_targets"], start=2):
        path = target["selector"]["path"]
        arguments = {
            "slide_number": target["slide"] + 1,
            "selector": {"index": path[0]},
            "underline": True,
        }
        model_arguments_by_target.append(deepcopy(arguments))
        state.events.append(_event(step, "shape.format_text", arguments, {"ok": True}))

    assert impress_semantics.next_action(state) is None
    assert any(
        "save and run presentation.inspect" in item
        for item in impress_semantics.completion_missing(state)
    )

    state.events.extend(
        [
            _save(5),
            _inspect(
                6,
                _slides(slide_one_underlined=True, slide_three_underlined=True),
            ),
        ]
    )
    assert impress_semantics.textbox_underline_readback_satisfied(state)
    assert impress_semantics.completion_missing(state) == []
    assert [
        event.proposed["arguments"]
        for event in state.events
        if event.proposed.get("action") == "shape.format_text"
    ] == model_arguments_by_target


def _role_format(step: int, action: str, slides: list[int]) -> ExecutionEvent:
    arguments = {"roles": ["all"], "underline": True}
    arguments.update(
        {"slide": slides[0]}
        if action == "slide.format_text_roles"
        else {"slides": slides}
    )
    pages = [
        {
            "slide": slide,
            "rules": [
                {
                    "index": 0,
                    "normalized_roles": ["all"],
                    "formatted": [
                        {"path": shape["path"], "properties": {"CharUnderline": "1"}}
                        for shape in _slides()[slide]["recursive_text_shapes"]
                    ],
                }
            ],
        }
        for slide in slides
    ]
    result = pages[0] if action == "slide.format_text_roles" else {"slides": pages}
    return _event(step, action, arguments, {"status": "ok", "result": result})


@pytest.mark.parametrize(
    "action", ["slide.format_text_roles", "slides.format_text_roles"]
)
def test_role_underlining_counts_without_duplicate_shape_calls_and_keeps_readback(
    action,
):
    state = _state([_inspect(1, _slides())])
    if action == "slide.format_text_roles":
        state.events.extend(
            [_role_format(2, action, [0]), _role_format(3, action, [2])]
        )
    else:
        state.events.append(_role_format(2, action, [0, 2]))
    original = deepcopy(state.events)
    claim = {"reason": "Applied underlining.", "evidence": ["native properties"]}

    assert action in strict_semantic_action_equivalents(state)["shape.format_text"]
    assert impress_semantics.next_action(state) is None
    assert not CompletionMixin._generic_completion_gate(state, claim)["passed"]
    state.events.extend([_save(4), _inspect(5, _slides(slide_one_underlined=True))])
    assert not impress_semantics.textbox_underline_readback_satisfied(state)
    assert not CompletionMixin._generic_completion_gate(state, claim)["passed"]
    state.events.append(
        _inspect(6, _slides(slide_one_underlined=True, slide_three_underlined=True))
    )

    assert CompletionMixin._generic_completion_gate(state, claim) == {
        "passed": True,
        "missing": [],
    }
    assert state.events[: len(original)] == original


@pytest.mark.parametrize("residual", ["missing_child", "override_removes_underline"])
def test_role_receipts_must_cover_the_observed_textbox_with_requested_property(
    residual,
):
    event = _role_format(2, "slides.format_text_roles", [0, 2])
    rules = event.result["result"]["slides"][0]["rules"]
    if residual == "missing_child":
        rules[0]["formatted"].pop()
    else:
        event.proposed["arguments"]["overrides"] = [
            {"roles": ["text"], "underline": False}
        ]
        rules.append(
            {
                "index": 1,
                "formatted": [{"path": [1, 0], "properties": {"CharUnderline": "0"}}],
            }
        )
    state = _state([_inspect(1, _slides()), event])

    missing = impress_semantics.next_textbox_underline_spec(state)
    assert missing is not None
    assert missing["selector"] == {"path": [1, 0]}
    assert not impress_semantics.textbox_underline_readback_satisfied(state)


def test_underline_completion_requires_every_target_and_persisted_readback() -> None:
    initial = _slides()
    state = _state([_inspect(1, initial)])
    plan = impress_semantics.textbox_underline_plan(state)
    assert plan is not None

    for step, target in enumerate(plan["resolved_targets"], start=2):
        state.events.append(
            _event(step, "shape.format_text", target["step"]["arguments"], {"ok": True})
        )

    assert impress_semantics.next_action(state) is None
    assert any(
        "save and run presentation.inspect" in item
        for item in impress_semantics.completion_missing(state)
    )

    state.events.extend(
        [
            _save(5),
            _inspect(
                6,
                _slides(slide_one_underlined=True, slide_three_underlined=True),
            ),
        ]
    )
    assert impress_semantics.textbox_underline_readback_satisfied(state)
    assert impress_semantics.completion_missing(state) == []


def test_underline_negative_readback_keeps_completion_open() -> None:
    state = _state([_inspect(1, _slides())])
    plan = impress_semantics.textbox_underline_plan(state)
    assert plan is not None
    for step, target in enumerate(plan["resolved_targets"], start=2):
        state.events.append(
            _event(step, "shape.format_text", target["step"]["arguments"], {"ok": True})
        )
    state.events.extend([_save(5), _inspect(6, _slides(slide_one_underlined=True))])

    assert not impress_semantics.textbox_underline_readback_satisfied(state)
    missing = impress_semantics.completion_missing(state)
    assert any("requested underline state" in item for item in missing)


def test_already_underlined_targets_need_no_mutation_but_still_readback() -> None:
    state = _state(
        [_inspect(1, _slides(slide_one_underlined=True, slide_three_underlined=True))]
    )

    plan = impress_semantics.textbox_underline_plan(state)
    assert plan is not None
    assert plan["steps"] == []
    assert impress_semantics.next_action(state) is None
    assert any(
        "save and run presentation.inspect" in item
        for item in impress_semantics.completion_missing(state)
    )


@pytest.mark.parametrize(
    "instruction",
    [
        "Make all textboxes bold on slides 1 and 3.",
        "Set the title underline on slide 1.",
        "Move the picture on page 2 to the top edge.",
    ],
)
def test_non_underline_instructions_do_not_activate_textbox_wiring(
    instruction: str,
) -> None:
    state = RuntimeState(
        task_id="synthetic-non-underline",
        domain="libreoffice_impress",
        instruction=instruction,
    )

    assert impress_semantics.parse_textbox_underline_intent(instruction) is None
    assert impress_semantics.textbox_underline_plan(state) is None
    assert impress_semantics._next_textbox_underline_action(state) is None


def test_soft_restart_retains_four_target_mutation_ledger_and_stages_persistence() -> (
    None
):
    """A bounded recovery must not make the next observed textbox target regress."""
    initial_slides = _slides()
    # Add a second textbox on slide 3 so the instruction yields four targets.
    extra = _textbox([3])
    initial_slides[2]["recursive_text_shapes"].append(extra)
    initial_slides[2]["text_shapes"].append(deepcopy(extra))
    state = _state([_inspect(1, initial_slides)])
    plan = impress_semantics.textbox_underline_plan(state)
    assert plan is not None
    assert len(plan["resolved_targets"]) == 4

    # Three successful model-selected mutations are followed by persistence,
    # readback, and a failed retry. This is the order-61 soft-restart boundary
    # where the bounded projection previously hid the mutation tail.
    for step, target in enumerate(plan["resolved_targets"][:3], start=2):
        state.events.append(
            _event(
                step,
                "shape.format_text",
                deepcopy(target["step"]["arguments"]),
                {"ok": True},
            )
        )
    state.events.extend([_save(5), _inspect(6, initial_slides)])
    failed = _event(
        7,
        "shape.format_text",
        deepcopy(plan["resolved_targets"][3]["step"]["arguments"]),
        {},
    )
    failed.executed = False
    failed.error = {"type": "ValidationError", "detail": "synthetic retry"}
    state.events.append(failed)
    events = state.events
    proposals_before_restart = [deepcopy(event.proposed) for event in events]
    mark_tool_result_for_audit(state, events[-1])
    decision = begin_same_vm_soft_restart(
        state,
        "local_step_limit",
        trigger_step=events[-1].step,
        context_limit=4,
    )

    assert decision.accepted is True
    assert state.events is events
    assert [event.proposed for event in events] == proposals_before_restart
    assert decision.summary["retained_event_count"] == 7
    assert decision.summary["retained_executed_event_count"] == 6
    ledger = decision.summary["successful_mutation_ledger"]
    assert [item["step"] for item in ledger] == [2, 3, 4]
    assert all(item["action"] == "shape.format_text" for item in ledger)
    assert all(
        item["action"] not in {"presentation.inspect", "presentation.save"}
        for item in ledger
    )
    assert "synthetic-underline-wiring" not in str(ledger)
    projected = state.context_summary(limit=4, strict_generic=True)
    ledger_markers = [
        item["recovery_mutation_ledger"]
        for item in projected
        if "recovery_mutation_ledger" in item
    ]
    assert ledger_markers == [ledger]
    assert any(
        item.get("recovery_mutation_ledger") == ledger
        for item in state.context_summary(limit=1, strict_generic=True)
        if isinstance(item, dict)
    )
    assert (
        impress_semantics.next_textbox_underline_spec(state)
        == plan["resolved_targets"][3]
    )

    protocol_messages = AgentProtocolMixin()._messages(
        state,
        b"png",
        execution_recovery=True,
    )
    protocol_text = protocol_messages[2]["content"][0]["text"]
    protocol_payload = protocol_text.split("\n", 1)[1].rsplit(
        "\nReturn exactly one tool call now.",
        1,
    )[0]
    protocol_projection = json.loads(protocol_payload)
    assert any(
        item.get("recovery_mutation_ledger") == ledger
        for item in protocol_projection
        if isinstance(item, dict)
    )
    assert state.record_model_audit({"tool": "adapter__shape_format_text"}) is not None
    assert state.pending_model_audit is None
    assert state.recovery_context is not None
    assert state.recovery_projection_turns_remaining == 3

    # Completing the expected mutation count does not replace the model's
    # completion claim or remove its ability to correct the observed result.
    state.events.append(
        _event(
            8,
            "shape.format_text",
            deepcopy(plan["resolved_targets"][3]["step"]["arguments"]),
            {"ok": True},
        )
    )
    completion = {
        "reason": "Applied all requested text formatting.",
        "evidence": ["verified"],
    }
    gate = CompletionMixin._generic_completion_gate(state, completion)
    assert gate["passed"] is False
    proactive = strict_proactive_completion_tools(
        state,
        gate,
        strict_instruction_required_actions,
        FORBIDDEN_DATASET_ACTIONS,
        action_is_read_only,
        lambda _state: [
            "presentation.inspect",
            "shape.format_text",
            "presentation.save",
        ],
        strict_semantic_action_equivalents,
    )
    assert proactive is None

    final_slides = _slides(slide_one_underlined=True, slide_three_underlined=True)
    final_extra = _textbox([3], underline=True)
    final_slides[2]["recursive_text_shapes"].append(final_extra)
    final_slides[2]["text_shapes"].append(deepcopy(final_extra))
    state.events.extend([_save(9), _inspect(10, final_slides)])
    assert CompletionMixin._generic_completion_gate(state, completion) == {
        "passed": True,
        "missing": [],
    }
