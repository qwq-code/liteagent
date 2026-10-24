from __future__ import annotations

from types import SimpleNamespace

import pytest

from calc_adapter.errors import AdapterError
from calc_adapter.schema import ACTIONS as CALC_ACTIONS
from calc_adapter.schema import parse_action_request, validate_action_params
from calc_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from calc_adapter import uno_worker
from integrations.lite_agent.action_selection import ActionSelectionMixin
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.calc_scaled_display import missing_scaled_display_outputs
from integrations.lite_agent.instruction_semantics import (
    strict_instruction_required_actions,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


RETIRED_COMPOSITES = {
    "range.copy_with_scaled_display",
    "range.set_text_and_format",
    "table.aggregate_columns",
    "table.append_summary_rows",
    "table.create_year_over_year_summary",
    "table.add_ratio_column",
    "table.compose_text_column",
    "chart.create_from_summary_rows",
    "chart.create_by_headers",
    "pivot.create_stacked",
    "pivot.create_stacked_aggregate",
    "range.format_date_matches",
    "range.format_extreme",
    "rows.set_hidden_matching",
}

ATOMIC_REPLACEMENTS = {
    "range.read",
    "range.write",
    "cells.set_formulas",
    "range.copy",
    "range.fill_down",
    "range.format",
    "range.set_scaled_display",
    "rows.set_hidden",
    "chart.create",
    "pivot.create",
}


def test_composites_are_unreachable_and_atomic_replacements_remain() -> None:
    surfaces = (set(CALC_ACTIONS), set(STRICT_ACTION_PARAM_SCHEMAS), set(uno_worker.ACTIONS))

    assert all(RETIRED_COMPOSITES.isdisjoint(surface) for surface in surfaces)
    assert ATOMIC_REPLACEMENTS.issubset(CALC_ACTIONS)
    assert ATOMIC_REPLACEMENTS.issubset(uno_worker.ACTIONS)
    assert "range.set_scaled_display" in STRICT_ACTION_PARAM_SCHEMAS


@pytest.mark.parametrize("action", sorted(RETIRED_COMPOSITES))
def test_retired_composites_are_rejected_before_worker_start(action: str) -> None:
    with pytest.raises(AdapterError, match="action is not supported") as exc_info:
        parse_action_request({"action": action, "params": {}})

    assert exc_info.value.code == "UNSUPPORTED_OPERATION"

    with pytest.raises(AdapterError, match="action is not supported") as exc_info:
        validate_action_params(action, {})

    assert exc_info.value.code == "UNSUPPORTED_OPERATION"


def test_scaled_display_accepts_one_explicit_existing_range() -> None:
    validate_action_params(
        "range.set_scaled_display",
        {
            "sheet": "Forecast 2037",
            "range": "J4:J28",
            "divisor": 1_000_000,
            "decimal_places": 2,
            "unit": "M",
            "separator": "space",
            "rounding_mode": "half_up",
            "locale": "en-US",
        },
    )

    schema = STRICT_ACTION_PARAM_SCHEMAS["range.set_scaled_display"]
    assert {"sheet", "range", "divisor", "decimal_places", "unit"}.issubset(
        schema["required"]
    )
    assert "source_range" not in schema["properties"]
    assert "destination" not in schema["properties"]


@pytest.mark.parametrize(
    ("transfer_action", "formula_divisor", "display_divisor"),
    [
        ("range.copy", None, 1_000_000),
        ("cells.set_formulas", None, 1_000_000),
        ("cells.set_formulas", 1_000_000, 1),
    ],
)
def test_scaled_display_allows_model_selected_value_transfer(
    transfer_action: str, formula_divisor: int | None, display_divisor: int
) -> None:
    instruction = (
        "Represent column 'Revenue' in millions (M) in column J with 2 decimal "
        "places, whitespace before the unit, and round halves up."
    )
    required = strict_instruction_required_actions("libreoffice_calc", instruction)
    assert "range.set_scaled_display" in required
    assert "range.copy" not in required
    assert "range.copy_with_scaled_display" not in required

    state = RuntimeState(
        task_id="synthetic-scaled-copy",
        domain="libreoffice_calc",
        instruction=instruction,
    )
    transfer_arguments = (
        {
            "source_sheet": "Observed",
            "source_range": "B2:B9",
            "destination_sheet": "Observed",
            "destination": "J2",
            "preserve_format": False,
        }
        if transfer_action == "range.copy"
        else {
            "sheet": "Observed",
            "writes": [
                {
                    "cell": f"J{row}",
                    "formula": (
                        f"=B{row}/{formula_divisor}"
                        if formula_divisor is not None
                        else f"=B{row}"
                    ),
                }
                for row in range(2, 10)
            ],
        }
    )
    display_arguments = {
        "sheet": "Observed",
        "range": "J2:J9",
        "divisor": display_divisor,
        "decimal_places": 2,
        "unit": "M",
        "separator": "space",
        "rounding_mode": "half_up",
    }

    validate_action_params(transfer_action, transfer_arguments)
    validate_action_params("range.set_scaled_display", display_arguments)
    ActionSelectionMixin._validate_stateful_arguments(
        state,
        transfer_action,
        transfer_arguments,
    )
    ActionSelectionMixin._validate_stateful_arguments(
        state,
        "range.set_scaled_display",
        display_arguments,
    )

    def event(step: int, action: str, arguments: dict) -> ExecutionEvent:
        return ExecutionEvent(
            step=step,
            timestamp_utc="2026-09-03T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": f"adapter__{action.replace('.', '_')}",
                "action": action,
                "arguments": arguments,
            },
            executed=True,
            result={"status": "ok"},
        )

    state.events = [event(1, "workbook.inspect", {})]
    selector = ActionSelectionMixin()
    selector.config = SimpleNamespace(top_k_actions=7)
    assert "range.set_scaled_display" in selector.selected_actions(state)

    state.events.extend(
        [
            event(2, transfer_action, transfer_arguments),
            event(3, "range.set_scaled_display", display_arguments),
            event(4, "workbook.save", {}),
            event(5, "range.read", {"sheet": "Observed", "range": "J2:J9"}),
        ]
    )
    # Schema-valid calls are permitted, but this synthetic ledger contains no
    # native source or target cells. Operation names alone cannot prove success.
    gate = CompletionMixin._generic_completion_gate(state)
    assert not gate["passed"]
    assert any("source_unverified" in item for item in gate["missing"])

    state.events[2].executed = False
    missing = CompletionMixin._generic_completion_gate(state)["missing"]
    assert any("source_unverified" in item for item in missing)


def test_scaled_display_coverage_still_requires_requested_column_and_unit() -> None:
    instruction = "Represent revenue in millions (M) in column J."
    call = {"range": "J2:J9", "divisor": 1, "unit": "M"}

    assert missing_scaled_display_outputs(instruction, [call]) == []
    assert missing_scaled_display_outputs(instruction, [{**call, "range": "K2:K9"}])
    assert missing_scaled_display_outputs(instruction, [{**call, "unit": "k"}])


@pytest.mark.parametrize("divisor", [0, 10, 1_000_001, True])
def test_scaled_display_rejects_non_power_of_thousand(divisor: object) -> None:
    with pytest.raises(AdapterError):
        validate_action_params(
            "range.set_scaled_display",
            {
                "sheet": "Synthetic",
                "range": "C2:C9",
                "divisor": divisor,
                "decimal_places": 1,
                "unit": "k",
                "separator": "none",
                "rounding_mode": "half_up",
            },
        )


def test_scaled_display_worker_formats_only_the_selected_range(monkeypatch) -> None:
    target = object()
    sheet = SimpleNamespace(getCellRangeByName=lambda cell_range: target)
    doc = SimpleNamespace(calculateAll=lambda: None)
    session = SimpleNamespace(sheet=lambda sheet_name: sheet, doc=doc)
    applied: list[tuple[object, str, str | None]] = []

    monkeypatch.setattr(
        uno_worker,
        "_apply_number_format",
        lambda received_doc, received_target, code, locale=None: applied.append(
            (received_target, code, locale)
        ),
    )
    monkeypatch.setattr(
        uno_worker,
        "_range_snapshot",
        lambda received_target, received_doc: {"display_text": [["1.25 M"]]},
    )

    result = uno_worker._set_scaled_display(
        session,
        {
            "sheet": "Metrics",
            "range": "D5:D8",
            "divisor": 1_000_000,
            "decimal_places": 2,
            "unit": "M",
            "separator": "space",
            "rounding_mode": "half_up",
            "locale": "en-US",
        },
    )

    assert applied == [(target, '0.00,," M"', "en-US")]
    assert result["sheet"] == "Metrics"
    assert result["range"] == "D5:D8"
    assert "destination_range" not in result
