from __future__ import annotations

from integrations.lite_agent.bounded_recovery import (
    recover_tools,
    recovery_guidance,
    repeated_tool,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


def _event(step: int, proposal: dict, *, result=None, error=None, executed=True):
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-10-23T00:00:00Z",
        proposed=proposal,
        executed=executed,
        result=result,
        error=error,
    )


def _state(events: list[ExecutionEvent]) -> RuntimeState:
    return RuntimeState(
        task_id="synthetic-bounded-recovery",
        domain="multi_apps",
        instruction="Complete the requested document update.",
        events=events,
    )


def test_identical_catalog_search_without_new_information_is_paused():
    proposal = {
        "kind": "catalog",
        "tool": "tools_search",
        "arguments": {"query": "summary slide"},
    }
    result = {"matches": [{"action": "presentation.inspect"}]}
    state = _state([_event(step, proposal, result=result) for step in range(1, 4)])
    tools = [
        {"function": {"name": "tools_search"}},
        {"function": {"name": "adapter__presentation_inspect"}},
        {"function": {"name": "propose_done"}},
    ]

    assert repeated_tool(state) == "tools_search"
    assert [tool["function"]["name"] for tool in recover_tools(tools, state)] == [
        "adapter__presentation_inspect",
        "propose_done",
    ]


def test_distinct_search_queries_are_not_paused_even_with_same_matches():
    result = {"matches": [{"action": "presentation.inspect"}]}
    events = [
        _event(
            step,
            {"kind": "catalog", "tool": "tools_search", "arguments": {"query": query}},
            result=result,
        )
        for step, query in enumerate(("slide notes", "summary slide", "slide layout"), 1)
    ]

    assert repeated_tool(_state(events)) is None


def test_same_query_with_changed_search_result_is_not_paused():
    proposal = {
        "kind": "catalog",
        "tool": "tools_search",
        "arguments": {"query": "summary slide"},
    }
    events = [
        _event(1, proposal, result={"matches": []}),
        _event(2, proposal, result={"matches": [{"action": "presentation.inspect"}]}),
        _event(3, proposal, result={"matches": [{"action": "presentation.add_slide"}]}),
    ]

    assert repeated_tool(_state(events)) is None


def test_different_failed_requests_are_not_collapsed_into_one_retry_loop():
    events = [
        _event(
            step,
            {
                "kind": "adapter",
                "tool": "adapter__range_write",
                "action": "range.write",
                "arguments": {"range": target},
            },
            error={"type": "INVALID_REQUEST"},
            executed=False,
        )
        for step, target in enumerate(("A1", "A2", "A3"), 1)
    ]
    events[-1].error = {"type": "RepeatedActionBlocked"}

    assert repeated_tool(_state(events)) is None


def test_text_range_error_references_observed_match_and_zero_based_offsets():
    state = _state([
        _event(
            1,
            {"kind": "adapter", "tool": "adapter__text_set_format", "arguments": {}},
            error={
                "type": "TEXT_MISMATCH",
                "message": "expected_text length = 3; range length = 1",
            },
            executed=False,
        )
    ])

    guidance = recovery_guidance(state)

    assert "matched_text" in guidance
    assert "zero-based" in guidance
    assert "Do not guess" in guidance


def _transforms(destinations):
    return [
        _event(step, {
            "kind": "adapter", "tool": "adapter__range_text_transform",
            "action": "range.text_transform", "arguments": {
                "source_sheet": "Sheet1", "source_range": "B2:B9",
                "destination_sheet": "Sheet1", "destination": destination,
                "operation": ("title_case", "trim", "collapse_whitespace")[(step - 1) % 3],
            },
        })
        for step, destination in enumerate(destinations, 1)
    ]


def test_overwriting_transformation_cycle_yields_to_readback():
    state = _state(_transforms(["C2"] * 6))
    state.domain = "libreoffice_calc"
    tools = [{"function": {"name": name}} for name in (
        "adapter__range_text_transform", "adapter__range_read", "propose_done")]
    assert repeated_tool(state) == "adapter__range_text_transform"
    assert [t["function"]["name"] for t in recover_tools(tools, state)] == [
        "adapter__range_read", "propose_done"]
    assert "discards earlier transformations" in recovery_guidance(state)


def test_valid_transformation_composition_and_distinct_targets_are_not_cycles():
    for destinations in (["C2"] * 3, ["C2", "D2", "E2", "F2", "G2", "H2"]):
        state = _state(_transforms(destinations))
        state.domain = "libreoffice_calc"
        assert repeated_tool(state) is None


def test_transform_cycle_does_not_cross_restarts():
    state = _state(_transforms(["C2"] * 6))
    state.domain = "libreoffice_calc"
    state.events[-1].retry = 1
    assert repeated_tool(state) is None
