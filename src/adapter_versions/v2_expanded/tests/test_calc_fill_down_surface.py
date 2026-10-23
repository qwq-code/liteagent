from __future__ import annotations

from copy import deepcopy

import pytest

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.semantic_requirements import (
    strict_semantic_requirement_errors,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import tool_name


class NoExecutor:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("No application action should run during tool selection")


def _event(step: int, action: str, arguments: dict) -> ExecutionEvent:
    return ExecutionEvent(
        step=step,
        timestamp_utc="2032-04-09T00:00:00Z",
        proposed={
            "kind": "adapter",
            "tool": tool_name(action),
            "action": action,
            "arguments": arguments,
        },
        parsed=True,
        validated=True,
        executed=True,
        result={"status": "success", "verification": {"status": "passed"}},
    )


def _state(filled: tuple[str, ...]) -> RuntimeState:
    return RuntimeState(
        task_id="synthetic-task",
        domain="libreoffice_calc",
        instruction=(
            "Fill down columns C and F from row 3. "
            "Then write a summary label in column G."
        ),
        recommended_actions=[
            "workbook.inspect",
            "range.read",
            "range.fill_down",
            "range.write",
            "workbook.save",
        ],
        events=[
            _event(1, "workbook.inspect", {}),
            *[
                _event(
                    index + 2,
                    "range.fill_down",
                    {
                        "sheet": "Measurements",
                        "range": f"{column}3:{column}9",
                        "mode": "previous_nonblank",
                    },
                )
                for index, column in enumerate(filled)
            ],
        ],
    )


@pytest.mark.parametrize("filled", [(), ("C",)])
def test_pending_fill_keeps_read_and_search_available(filled: tuple[str, ...]):
    state = _state(filled)
    before = deepcopy(state.events)
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=False), NoExecutor()
    )
    names = {tool["function"]["name"] for tool in agent.tools(state)}
    assert {
        "adapter__range_fill_down",
        "adapter__range_read",
        "tools_search",
    }.issubset(names)
    assert state.events == before


def test_pending_column_completion_feedback_is_unchanged():
    errors = strict_semantic_requirement_errors(_state(("C",)))
    assert any("missing columns ['F']" in error for error in errors)


def test_completed_columns_no_longer_report_missing_fill():
    errors = strict_semantic_requirement_errors(_state(("C", "F")))
    assert not any("range.fill_down" in error for error in errors)


def _date_column_state() -> RuntimeState:
    return RuntimeState(
        task_id="synthetic-task",
        domain="libreoffice_calc",
        instruction="Compute each expiry date in an additional column with a header.",
        events=[_event(1, "workbook.inspect", {})],
    )


def test_date_column_can_finish_after_explicit_formulas_without_filling():
    state = _date_column_state()
    state.events.extend(
        [
            _event(
                2,
                "range.write",
                {"sheet": "Schedule", "range": "G1", "values": ["Expiry"]},
            ),
            _event(
                3,
                "cells.set_formulas",
                {
                    "sheet": "Schedule",
                    "writes": [
                        {"cell": "G2", "formula": "=D2+E2"},
                        {"cell": "G3", "formula": "=D3+E3"},
                    ],
                },
            ),
            _event(
                4,
                "range.format",
                {
                    "sheet": "Schedule",
                    "range": "G2:G3",
                    "format": {"number_format": "YYYY-MM-DD"},
                },
            ),
            _event(5, "workbook.save", {}),
            _event(6, "range.read", {"sheet": "Schedule", "range": "G1:G3"}),
        ]
    )
    before = deepcopy(state.events)

    assert CompletionMixin._generic_completion_gate(state) == {
        "passed": True,
        "missing": [],
    }
    assert state.events == before


def test_date_column_can_search_for_fill_as_an_optional_implementation():
    state = _date_column_state()
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=False), NoExecutor()
    )

    event = agent.execute_proposal(
        state,
        {"tool": "tools_search", "arguments_raw": '{"query":"range.fill_down"}'},
    )

    assert event.executed
    assert "range.fill_down" in {item["action"] for item in event.result["matches"]}
    assert "range.fill_down" in state.expanded_actions
    assert "adapter__range_fill_down" in {
        tool["function"]["name"] for tool in agent.tools(state)
    }
