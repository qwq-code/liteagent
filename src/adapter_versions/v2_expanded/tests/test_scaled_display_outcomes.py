"""Native cell contracts for independently chosen value-transfer methods."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.completion_outcomes import completion_outcome_issues
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


INSTRUCTION = (
    'Change the representation of column "Revenue" to show in Millions (M) in Column J '
    'and Billions (B) in Column K. The numbers should be rounded to one decimal place, '
    'and half should be rounded up. Place a white space between the digits and the unit.'
)
SOURCE = [1500000, 150000000, -150000000]
DISPLAYS = [["1.5 M", "0.0 B"], ["150.0 M", "0.2 B"], ["-150.0 M", "-0.2 B"]]


def event(step, action, args=None, payload=None):
    return ExecutionEvent(
        step=step, timestamp_utc="2030-01-01T00:00:00Z", parsed=True,
        validated=True, executed=True,
        proposed={"kind": "adapter", "tool": "adapter__" + action.replace(".", "_"),
                  "action": action, "arguments": args or {}},
        result={"adapter_response": {"status": "ok", "result": payload or {}}},
    )


def cells(sheet, area, display, values, kinds):
    return {"sheet": sheet, "range": area, "display_text": display,
            "values": values, "kinds": kinds, "workbook_url": "file:///tmp/Revenue.xlsx"}


def state(method="range.copy", *, blank=False):
    events = [
        event(1, "workbook.inspect", payload={"url": "file:///tmp/Revenue.xlsx", "sheets": [
            {"name": "Observed", "used_range_a1": "C4:K7"}]}),
        event(2, "range.read", {"sheet": "Observed", "range": "C4:C7"},
              cells("Observed", "C4:C7", [["Revenue"], *[[str(v)] for v in SOURCE]],
                    [["Revenue"], *[[v] for v in SOURCE]], [["string"], *[["number"]] * 3])),
    ]
    for column in ("J", "K"):
        if method == "range.copy":
            args = {"source_sheet": "Observed", "source_range": "C5:C7",
                    "destination_sheet": "Observed", "destination": column + "5"}
        elif method == "cells.set_formulas":
            args = {"sheet": "Observed", "writes": [
                {"cell": f"{column}{row}", "formula": f"=C{row}"} for row in range(5, 8)]}
        else:
            args = {"sheet": "Observed", "range": f"{column}5:{column}7", "values": [[v] for v in SOURCE]}
        events.append(event(len(events) + 1, method, args))
    # Directly formatted text is legal and need not use set_scaled_display.
    if method != "range.write":
        for column, divisor, unit in (("J", 1000000, "M"), ("K", 1000000000, "B")):
            events.append(event(len(events) + 1, "range.set_scaled_display", {
                "sheet": "Observed", "range": f"{column}5:{column}7", "divisor": divisor,
                "decimal_places": 1, "unit": unit, "separator": "space", "rounding_mode": "half_up"}))
    events.append(event(len(events) + 1, "workbook.save"))
    text = [["", ""] for _ in SOURCE] if blank else deepcopy(DISPLAYS)
    values = [[None, None] for _ in SOURCE] if blank else (
        deepcopy(DISPLAYS) if method == "range.write" else [[v, v] for v in SOURCE])
    kind = "blank" if blank else "string" if method == "range.write" else "formula" if method == "cells.set_formulas" else "number"
    events.append(event(len(events) + 1, "range.read", {"sheet": "Observed", "range": "J5:K7"},
                        cells("Observed", "J5:K7", text, values, [[kind, kind] for _ in SOURCE])))
    return RuntimeState(task_id="synthetic-scaled-outcomes", domain="libreoffice_calc",
                        instruction=INSTRUCTION, events=events)


def gate(current):
    return CompletionMixin._generic_completion_gate(current)


def payload(current):
    return current.events[-1].result["adapter_response"]["result"]


def codes(current):
    return {issue["code"] for issue in completion_outcome_issues(current)}


@pytest.mark.parametrize("method", ["range.copy", "cells.set_formulas", "range.write"])
def test_correct_actual_cells_allow_each_independent_transfer_method(method):
    current = state(method)
    assert completion_outcome_issues(current) == []
    assert gate(current)["passed"], gate(current)


@pytest.mark.parametrize("rounded", [False, True])
def test_numeric_formulas_can_store_converted_or_rounded_values(rounded):
    current = state("cells.set_formulas")
    payload(current)["values"] = [[v / 1e6, v / 1e9] for v in SOURCE]
    if rounded:
        payload(current)["values"][1:] = [[150, .2], [-150, -.2]]
    assert gate(current)["passed"], gate(current)


@pytest.mark.parametrize("defect", ["blank", "wrong_value", "wrong_unit", "no_space", "wrong_precision", "half_even", "masked_native_value"])
def test_calls_save_and_read_do_not_override_incorrect_cells(defect):
    current = state(blank=defect == "blank")
    p = payload(current)
    if defect == "wrong_value":
        p["display_text"][0][0] = "999.0 M"
    elif defect == "wrong_unit":
        p["display_text"][0][0] = "1.5 B"
    elif defect == "no_space":
        p["display_text"][0][0] = "1.5M"
    elif defect == "wrong_precision":
        p["display_text"][0][0] = "1.50 M"
    elif defect == "half_even":
        p["display_text"][1][1] = "0.1 B"
    elif defect == "masked_native_value":
        p["values"][0][0] = 999
    assert "scaled_display.output_mismatch" in codes(current)
    assert not gate(current)["passed"]


def test_unrelated_copy_cannot_satisfy_empty_outputs():
    current = state(blank=True)
    for e in current.events:
        if e.proposed["action"] == "range.copy":
            e.proposed["arguments"]["destination"] = "H5"
    assert not gate(current)["passed"]
    issues = completion_outcome_issues(current)
    assert {i["target"]["range"] for i in issues} == {"J5:J7", "K5:K7"}
    assert issues[0]["observed"]["wrong_cells"][0]["source_cell"] == "C5"


@pytest.mark.parametrize("defect", ["partial", "truncated", "other_document", "missing_values", "stale"])
def test_incomplete_or_stale_observation_never_proves_completion(defect):
    current = state()
    p = payload(current)
    if defect == "partial":
        current.events[-1].proposed["arguments"]["range"] = "J5:K6"
        p["range"] = "J5:K6"
        for field in ("display_text", "values", "kinds"):
            p[field] = p[field][:2]
    elif defect == "truncated":
        p["truncated"] = True
    elif defect == "other_document":
        p["workbook_url"] = "file:///tmp/Other.xlsx"
    elif defect == "missing_values":
        del p["values"]
    elif defect == "stale":
        current.events.append(event(len(current.events) + 1, "range.write", {
            "sheet": "Observed", "range": "J5", "values": [[999]]}))
    assert not gate(current)["passed"]


def test_partial_source_does_not_shrink_required_output_rows():
    current = state()
    e = current.events[1]
    e.proposed["arguments"]["range"] = "C4:C6"
    p = e.result["adapter_response"]["result"]
    p["range"] = "C4:C6"
    for key in ("display_text", "values", "kinds"):
        p[key] = p[key][:3]
    assert "scaled_display.source_unverified" in codes(current)
    assert not gate(current)["passed"]


def test_each_output_can_be_verified_in_separate_reads():
    current = state()
    e = current.events.pop()
    p = e.result["adapter_response"]["result"]
    for offset, column in enumerate(("J", "K")):
        current.events.append(event(len(current.events) + 1, "range.read", {
            "sheet": "Observed", "range": f"{column}5:{column}7"},
            cells("Observed", f"{column}5:{column}7", *[
                [[row[offset]] for row in p[key]] for key in ("display_text", "values", "kinds")])))
    assert gate(current)["passed"], gate(current)


def test_half_up_tie_is_checked_from_source_not_just_call_arguments():
    current = state()
    source = current.events[1].result["adapter_response"]["result"]
    source["values"][1][0] = 50000000
    source["display_text"][1][0] = "50000000"
    p = payload(current)
    p["values"][0] = [50000000, 50000000]
    p["display_text"][0] = ["50.0 M", "0.0 B"]
    assert not gate(current)["passed"]  # half-even on 0.05 would incorrectly show 0.0.
    p["display_text"][0][1] = "0.1 B"
    assert gate(current)["passed"], gate(current)


def test_output_issues_survive_successful_reads_and_disappear_only_after_verified_repair():
    current = state(blank=True)
    worker = LiteAgent(LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
                       SimpleNamespace(), model_client=SimpleNamespace(client=object()))
    for _ in range(3):
        read = deepcopy(current.events[-1])
        read.step = len(current.events) + 1
        current.events.append(read)
        assert not gate(current)["passed"]
        names = {t["function"]["name"] for t in worker.tools(current)}
        assert {"adapter__range_copy", "adapter__cells_set_formulas", "adapter__range_write",
                "adapter__range_set_scaled_display", "adapter__range_read", "tools_search"} <= names
        text = json.dumps(worker._messages(current, b"", available_tools=worker.tools(current), protocol_recovery=True))
        assert "completion_outcomes" in text and "wrong_cells" in text
    correct = deepcopy(state().events[-1])
    current.events.append(event(len(current.events) + 1, "range.write", {
        "sheet": "Observed", "range": "J5:K7", "values": [[v, v] for v in SOURCE]}))
    assert not gate(current)["passed"]
    correct.step = len(current.events) + 1
    current.events.append(correct)
    assert not gate(current)["passed"]  # No save after the repair.
    current.events.append(event(len(current.events) + 1, "workbook.save"))
    assert not gate(current)["passed"]  # No read after that save.
    correct = deepcopy(correct)
    correct.step = len(current.events) + 1
    current.events.append(correct)
    assert completion_outcome_issues(current) == []
    assert gate(current)["passed"], gate(current)
