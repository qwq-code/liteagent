from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from integrations.lite_agent.spreadsheet_open_semantics import (
    _gui_explicit_path,
    _gui_open_filename,
    _gui_open_location_hint,
    _is_successful_inspection,
    _inspection_matches_open,
    argument_contract_errors,
    gui_request_contract_errors,
    pending_actions,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


def _adapter_call_event(
    step: int,
    action: str,
    params: dict[str, Any],
    *,
    adapter: str = "libreoffice_calc",
    result: dict[str, Any] | None = None,
) -> ExecutionEvent:
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-09-01T00:00:00Z",
        proposed={
            "kind": "adapter",
            "tool": "adapter__adapter_call",
            "action": "adapter.call",
            "arguments": {
                "adapter": adapter,
                "action": action,
                "payload": {"params": copy.deepcopy(params)},
            },
        },
        executed=True,
        result=result or {"status": "ok"},
    )


def _gui_open_event(step: int = 1, *, intent: str) -> ExecutionEvent:
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-09-01T00:00:00Z",
        proposed={
            "tool": "gui_request",
            "arguments_raw": json.dumps({"intent": intent}),
            "arguments": {"intent": intent},
            "kind": "gui",
            "delegation": "qwen_to_holo",
            "gui_request_arguments": {"action": "gui_request", "intent": intent},
            "gui_arguments": {"action": "double_click", "x": 963, "y": 185},
            "holo_grounding": {
                "name": "double_click",
                "arguments": {
                    "element": "spreadsheet file icon",
                    "x": 963,
                    "y": 185,
                },
            },
        },
        executed=True,
        result={
            "environment_acknowledged": True,
            "grounded_action": {"action": "double_click", "x": 963, "y": 185},
        },
    )


def _inspect_event(step: int, *, url: str) -> ExecutionEvent:
    return _adapter_call_event(
        step,
        "workbook.inspect",
        {},
        result={
            "status": "ok",
            "result": {"url": url, "sheets": []},
            "verification": {"passed": True},
        },
    )


def _read_file_event(step: int, *, path: str) -> ExecutionEvent:
    return _adapter_call_event(
        step,
        "workbook.read_file",
        {"path": path, "max_rows": 100},
        result={
            "status": "ok",
            "result": {"url": f"file://{path}", "sheets": [{"name": "Sheet1"}]},
            "verification": {"passed": True},
        },
    )


def _opened_workbook_state(instruction: str) -> RuntimeState:
    return RuntimeState(
        task_id="synthetic-spreadsheet-open",
        domain="multi_apps",
        instruction=instruction,
        events=[
            _gui_open_event(
                intent="Double-click Course Timetable.xlsx on the desktop to open it."
            ),
            _inspect_event(
                2, url="file:///home/user/Desktop/Course%20Timetable.xlsx"
            ),
            _adapter_call_event(
                3,
                "range.write",
                {"sheet": "Schedule", "range": "C7", "values": [["seminar"]]},
            ),
        ],
    )


def test_successful_read_file_observation_unlocks_gui_after_adapter_open() -> None:
    opened = _adapter_call_event(
        1,
        "desktop.open_path",
        {"path": "/home/user/Documents/tally_book.xlsx"},
        adapter="os",
        result={"status": "ok", "verification": {"passed": True}},
    )
    state = RuntimeState(
        task_id="synthetic-read-file-observation",
        domain="multi_apps",
        instruction="Open the workbook and update it.",
        events=[opened, _read_file_event(2, path="/home/user/Documents/tally_book.xlsx")],
    )

    assert _is_successful_inspection(state.events[1], "multi_apps")
    assert gui_request_contract_errors(state, "click the spreadsheet") == []


def _save_call(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "adapter": "libreoffice_calc",
        "action": "workbook.save",
        "payload": {"params": copy.deepcopy(params)},
    }


def test_generic_save_rejects_unrequested_destination_change_without_rewriting() -> None:
    state = _opened_workbook_state(
        "Open the existing timetable spreadsheet and add a new class slot."
    )
    arguments = _save_call({"url": "file:///home/user/Course%20Timetable.xlsx"})
    original = copy.deepcopy(arguments)

    errors = argument_contract_errors(state, "adapter.call", arguments)

    assert errors
    assert "does not request Save As" in errors[0]
    assert arguments == original


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"url": "file:///home/user/Desktop/Course%20Timetable.xlsx"},
    ],
)
def test_generic_save_accepts_in_place_or_exact_current_url(
    params: dict[str, Any],
) -> None:
    state = _opened_workbook_state(
        "Open the existing timetable spreadsheet and add a new class slot."
    )

    assert argument_contract_errors(state, "adapter.call", _save_call(params)) == []


def test_generic_save_accepts_requested_save_as_destination() -> None:
    state = _opened_workbook_state(
        "Open Course Timetable.xlsx, update it, and save it as revised-timetable.xlsx."
    )

    assert (
        argument_contract_errors(
            state,
            "adapter.call",
            _save_call({"url": "file:///home/user/Documents/revised-timetable.xlsx"}),
        )
        == []
    )


@pytest.mark.parametrize(
    ("intent", "filename"),
    [
        ("Open budget.xlsx and change cell A1.", "budget.xlsx"),
        ("Open budget.xlsx to edit it.", "budget.xlsx"),
        ("Open budget.xlsx.", "budget.xlsx"),
        ("Double-click budget.xlsx.", "budget.xlsx"),
        (
            "Open the existing Course Timetable.xlsx file from the desktop.",
            "Course Timetable.xlsx",
        ),
        (
            "Double-click on Course Timetable.xlsx in the desktop folder.",
            "Course Timetable.xlsx",
        ),
        (
            "Please open the file Course Timetable.xlsx from Desktop.",
            "Course Timetable.xlsx",
        ),
        (
            "Open spreadsheet app and then open Course Timetable.xlsx.",
            "Course Timetable.xlsx",
        ),
        (
            "First open LibreOffice, then open Course Timetable.xlsx and update it.",
            "Course Timetable.xlsx",
        ),
        (
            "Open the spreadsheet file: Course Timetable.xlsx.",
            "Course Timetable.xlsx",
        ),
        (
            "Double-click the file icon for Course Timetable.xlsx on the desktop.",
            "Course Timetable.xlsx",
        ),
        (
            "Double-click the icon labeled Course Timetable.xlsx on the desktop.",
            "Course Timetable.xlsx",
        ),
        (
            "Open the workbook titled Course Timetable.xlsx on the desktop.",
            "Course Timetable.xlsx",
        ),
        (
            "Open the file with name Course Timetable.xlsx from Desktop.",
            "Course Timetable.xlsx",
        ),
        (
            "Open the existing workbook, Course Timetable.xlsx, and update it.",
            "Course Timetable.xlsx",
        ),
        ("Open the selected Course Timetable.xlsx.", "Course Timetable.xlsx"),
        ("Open the chosen Course Timetable.xlsx.", "Course Timetable.xlsx"),
        ("Open the edited Course Timetable.xlsx.", "Course Timetable.xlsx"),
        ("Open a copy of Course Timetable.xlsx.", "Course Timetable.xlsx"),
        ("Open the saved copy of Course Timetable.xlsx.", "Course Timetable.xlsx"),
        ("Open the exported copy of Course Timetable.xlsx.", "Course Timetable.xlsx"),
        ("Open a duplicate of Course Timetable.xlsx.", "Course Timetable.xlsx"),
        (
            'Open the "Course Timetable.xlsx" file on the desktop.',
            "Course Timetable.xlsx",
        ),
        (
            "Open file:///home/user/Desktop/Course%20Timetable.xlsx.",
            "Course Timetable.xlsx",
        ),
    ],
)
def test_gui_open_parser_accepts_one_file_and_purpose_tail(
    intent: str, filename: str
) -> None:
    assert _gui_open_filename(intent) == filename


@pytest.mark.parametrize(
    "intent",
    [
        "Avoid double-clicking budget.xlsx.",
        "Do not open budget.xlsx.",
        "Open the Files app and locate budget.xlsx file.",
        "Open budget.xlsx and open other.xlsx.",
    ],
)
def test_gui_open_parser_fails_closed_for_negation_search_or_multiple_files(
    intent: str,
) -> None:
    assert _gui_open_filename(intent) is None


def test_gui_open_identity_requires_exact_explicit_path_or_named_directory() -> None:
    desktop = _gui_open_event(
        intent="Double-click budget.xlsx on the desktop to open it."
    )
    assert _inspection_matches_open(
        _inspect_event(2, url="file:///home/user/Desktop/budget.xlsx"),
        desktop,
        "multi_apps",
    )
    assert not _inspection_matches_open(
        _inspect_event(2, url="file:///home/user/Documents/budget.xlsx"),
        desktop,
        "multi_apps",
    )

    explicit_intent = "Open /home/user/Documents/budget.xlsx."
    explicit = _gui_open_event(intent=explicit_intent)
    assert _gui_explicit_path(explicit_intent, "budget.xlsx") == (
        "/home/user/Documents/budget.xlsx"
    )
    assert _inspection_matches_open(
        _inspect_event(2, url="file:///home/user/Documents/budget.xlsx"),
        explicit,
        "multi_apps",
    )
    assert not _inspection_matches_open(
        _inspect_event(2, url="file:///tmp/budget.xlsx"),
        explicit,
        "multi_apps",
    )


def test_filename_only_gui_open_is_released_by_observed_active_workbook() -> None:
    state = RuntimeState(
        task_id="synthetic-filename-only-open",
        domain="multi_apps",
        instruction="Open Inventory Summary.xlsx and update the stock count.",
        events=[_gui_open_event(intent="Open Inventory Summary.xlsx.")],
    )
    arguments = _adapter_call_event(
        4,
        "range.write",
        {"sheet": "Stock", "range": "D4", "values": [[12]]},
    ).proposed["arguments"]
    original_arguments = copy.deepcopy(arguments)
    before_inspection = copy.deepcopy(state)

    errors = argument_contract_errors(state, "adapter.call", arguments)
    assert errors and "workbook.inspect" in errors[0]
    assert gui_request_contract_errors(state, "Click the stock cell.")
    assert pending_actions(state)
    assert state == before_inspection
    assert arguments == original_arguments

    save_arguments = _save_call({})
    original_save_arguments = copy.deepcopy(save_arguments)
    for observation in (
        _inspect_event(2, url="file:///home/user/Documents/Inventory%20Summary.xlsx"),
        _read_file_event(3, path="/home/user/Documents/Inventory Summary.xlsx"),
    ):
        state.events.append(observation)
        after_observation = copy.deepcopy(state)

        assert argument_contract_errors(state, "adapter.call", arguments) == []
        assert argument_contract_errors(state, "adapter.call", save_arguments) == []
        assert gui_request_contract_errors(state, "Click the stock cell.") == []
        assert pending_actions(state) is None
        assert state == after_observation
        assert arguments == original_arguments
        assert save_arguments == original_save_arguments


@pytest.mark.parametrize(
    "inspection",
    [
        _inspect_event(2, url="file:///home/user/Documents/Other%20Inventory.xlsx"),
        _read_file_event(2, path="/home/user/Documents/Inventory Summary.xlsx"),
    ],
    ids=["different-active-workbook", "same-name-file-read"],
)
def test_filename_only_gui_open_stays_pending_without_matching_active_workbook(
    inspection: ExecutionEvent,
) -> None:
    state = RuntimeState(
        task_id="synthetic-filename-only-open",
        domain="multi_apps",
        instruction="Open Inventory Summary.xlsx and update the stock count.",
        events=[
            _gui_open_event(intent="Open Inventory Summary.xlsx."),
            copy.deepcopy(inspection),
        ],
    )
    arguments = _adapter_call_event(
        3,
        "range.write",
        {"sheet": "Stock", "range": "D4", "values": [[12]]},
    ).proposed["arguments"]
    original_state = copy.deepcopy(state)
    original_arguments = copy.deepcopy(arguments)

    assert _is_successful_inspection(inspection, "multi_apps")
    assert argument_contract_errors(state, "adapter.call", arguments)
    assert gui_request_contract_errors(state, "Click the stock cell.")
    assert pending_actions(state)
    assert state == original_state
    assert arguments == original_arguments


@pytest.mark.parametrize(
    ("intent", "filename"),
    [
        (
            "Double click on the Course Timetable.xlsx file on desktop.",
            "Course Timetable.xlsx",
        ),
        ("Open existing workbook Course Timetable.xlsx.", "Course Timetable.xlsx"),
        ("Open the spreadsheet file: Course Timetable.xlsx.", "Course Timetable.xlsx"),
    ],
)
def test_gui_open_parser_strips_stacked_leading_fillers(
    intent: str, filename: str
) -> None:
    assert _gui_open_filename(intent) == filename


@pytest.mark.parametrize(
    "intent",
    [
        "Open the spreadsheet application and select Course Timetable.xlsx.",
        "Open the spreadsheet application and choose Course Timetable.xlsx.",
        "Open the spreadsheet application and click Course Timetable.xlsx.",
        "Open the spreadsheet application and view Course Timetable.xlsx.",
        "Open the spreadsheet application and edit Course Timetable.xlsx.",
        "Open the spreadsheet application and selected Course Timetable.xlsx.",
        "Open the spreadsheet application, then clicked Course Timetable.xlsx.",
        "Open the spreadsheet application and copy Course Timetable.xlsx.",
        "Open the spreadsheet application and duplicate Course Timetable.xlsx.",
    ],
)
def test_gui_open_parser_rejects_non_open_file_operations(intent: str) -> None:
    assert _gui_open_filename(intent) is None


@pytest.mark.parametrize(
    "intent",
    [
        r"Open C:\Users\user\Desktop\Course Timetable.xlsx.",
        r"Double-click C:\Users\user\Desktop\Course Timetable.xlsx.",
    ],
)
def test_gui_open_parser_rejects_windows_style_paths(intent: str) -> None:
    assert _gui_open_filename(intent) is None


@pytest.mark.parametrize(
    ("intent", "identity_url", "location_hint"),
    [
        (
            "Open budget.xlsx on the desktop to edit it, then save to ~/Documents/revised.xlsx.",
            "file:///home/user/Desktop/budget.xlsx",
            "desktop",
        ),
        (
            "Open budget.xlsx from Documents then copy it to Desktop.",
            "file:///home/user/Documents/budget.xlsx",
            "documents",
        ),
        (
            "Open budget.xlsx in Downloads, then move it to Desktop.",
            "file:///home/user/Downloads/budget.xlsx",
            "downloads",
        ),
        (
            "Open /home/user/Documents/budget.xlsx and copy to /tmp/budget.xlsx.",
            "file:///home/user/Documents/budget.xlsx",
            "explicit",
        ),
        (
            'Open the document "budget.xlsx" from the Desktop.',
            "file:///home/user/Desktop/budget.xlsx",
            "desktop",
        ),
    ],
)
def test_gui_open_identity_uses_source_clause_not_destination_tail(
    intent: str, identity_url: str, location_hint: str
) -> None:
    event = _gui_open_event(intent=intent)
    assert _gui_open_filename(intent) == "budget.xlsx"
    assert _gui_open_location_hint(intent) == location_hint
    assert _inspection_matches_open(
        _inspect_event(2, url=identity_url), event, "multi_apps"
    )


@pytest.mark.parametrize(
    "intent",
    [
        "Open budget.xlsx, export as PDF, then open revised.xlsx.",
        "Open budget.xlsx, export it as report.pdf, then open revised.xlsx.",
        "Open budget.xlsx, save as revised.xlsx, then open revised.xlsx.",
        "Open budget.xlsx, copy it to revised.xlsx, then open revised.xlsx.",
    ],
)
def test_gui_open_parser_rejects_destination_then_second_source(intent: str) -> None:
    assert _gui_open_filename(intent) is None
