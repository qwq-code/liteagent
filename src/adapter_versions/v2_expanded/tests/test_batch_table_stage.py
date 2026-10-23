from __future__ import annotations

import json

from integrations.lite_agent import batch_table_semantics
from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


class _NoAdapterExecutor:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("these surface tests must not execute an Adapter")


OPEN_TARGET_INSTRUCTION = (
    "For each source PDF, extract the records and fill the spreadsheet already "
    "open in Calc."
)


def _agent(*, include_gui: bool = False) -> LiteAgent:
    return LiteAgent(
        LiteAgentConfig(
            base_url="http://unused/v1",
            include_gui=include_gui,
            top_k_actions=7,
        ),
        _NoAdapterExecutor(),  # type: ignore[arg-type]
        gui_executor=(lambda _arguments: {}) if include_gui else None,
    )


def _state(
    *,
    instruction: str = OPEN_TARGET_INSTRUCTION,
    task_id: str = "synthetic-task",
) -> RuntimeState:
    return RuntimeState(task_id=task_id, domain="multi_apps", instruction=instruction)


def _append_batch_result(
    state: RuntimeState,
    *,
    count: int = 3,
    step: int = 1,
    input_pattern: str = "*.pdf",
    max_chars_per_file: int | None = None,
    truncated: bool = False,
) -> None:
    arguments: dict[str, object] = {"input_pattern": input_pattern}
    if max_chars_per_file is not None:
        arguments["max_chars_per_file"] = max_chars_per_file

    files = [
        {
            "path": f"/tmp/source-{index}.pdf",
            "text": "record " * (900 if truncated else 1),
            **(
                {
                    "extracted_chars": 8_000,
                    "truncated": True,
                }
                if truncated
                else {}
            ),
        }
        for index in range(count)
    ]
    state.events.append(
        ExecutionEvent(
            step=step,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__pdf_extract_text_batch",
                "action": "pdf.extract_text_batch",
                "arguments": arguments,
            },
            executed=True,
            result={
                "adapter_response": {
                    "status": "ok",
                    "action": "pdf.extract_text_batch",
                    "result": {
                        "matched_count": count,
                        "files": files,
                    },
                }
            },
        )
    )


def _append_window_batch_result(
    state: RuntimeState,
    *,
    step: int,
    start_char: int,
    end_char: int,
    total_chars: int,
    source_truncated: bool,
) -> None:
    text = "source-window-" * max(1, end_char - start_char)
    text = text[: end_char - start_char]
    state.events.append(
        ExecutionEvent(
            step=step,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__pdf_extract_text_batch",
                "action": "pdf.extract_text_batch",
                "arguments": {
                    "input_pattern": "source-0.pdf",
                    "start_char": start_char,
                    "max_chars_per_file": end_char - start_char,
                },
            },
            executed=True,
            result={
                "adapter_response": {
                    "status": "ok",
                    "action": "pdf.extract_text_batch",
                    "result": {
                        "matched_count": 1,
                        "files": [
                            {
                                "path": "/tmp/source-0.pdf",
                                "text": text,
                                "extracted_chars": total_chars,
                                "source_start_char": start_char,
                                "source_end_char": end_char,
                                "source_total_chars": total_chars,
                                "next_start_char": end_char
                                if source_truncated
                                else None,
                                "source_truncated": source_truncated,
                                "offset_basis": "extracted_text",
                            }
                        ],
                    },
                }
            },
        )
    )


def _append_inspect_result(state: RuntimeState, *, step: int = 2) -> None:
    state.events.append(
        ExecutionEvent(
            step=step,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__spreadsheet_inspect_current",
                "action": "spreadsheet.inspect_current",
                "arguments": {},
            },
            executed=True,
            result={
                "adapter_response": {
                    "status": "ok",
                    "action": "spreadsheet.inspect_current",
                    "result": {
                        "adapter": "libreoffice_calc",
                        "action": "workbook.inspect",
                        "response": {
                            "status": "ok",
                            "result": {
                                "title": "supported.ods",
                                "active_sheet": "Sheet1",
                                "sheets": [{"name": "Sheet1"}],
                            },
                        },
                    },
                }
            },
        )
    )


def _append_failed_inspect(state: RuntimeState) -> None:
    state.events.append(
        ExecutionEvent(
            step=2,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__spreadsheet_inspect_current",
                "action": "spreadsheet.inspect_current",
                "arguments": {},
            },
            executed=False,
            error={"type": "NO_CALC_DOCUMENT"},
        )
    )


def _append_failed_batch(state: RuntimeState) -> None:
    state.events.append(
        ExecutionEvent(
            step=1,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__pdf_extract_text_batch",
                "action": "pdf.extract_text_batch",
                "arguments": {"input_pattern": "*.pdf"},
            },
            executed=False,
            error={"type": "NO_MATCHES"},
        )
    )


def _append_failed_write(state: RuntimeState, *, step: int = 3) -> None:
    state.events.append(
        ExecutionEvent(
            step=step,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__spreadsheet_write_range",
                "action": "spreadsheet.write_range",
                "arguments": {
                    "sheet": "Sheet1",
                    "range": "A1:B2",
                    "values": [["x", "y"], ["z", "w"]],
                },
            },
            executed=False,
            error={"type": "INVALID_ARGUMENT"},
        )
    )


def _append_failed_read(
    state: RuntimeState,
    *,
    error: dict[str, object],
    step: int = 3,
) -> None:
    state.events.append(
        ExecutionEvent(
            step=step,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__spreadsheet_read_file",
                "action": "spreadsheet.read_file",
                "arguments": {
                    "path": "/tmp/open.xlsx",
                    "sheet": "Sheet1",
                    "range": "A1:I10",
                },
            },
            executed=False,
            error=error,
        )
    )


def _append_successful_read(
    state: RuntimeState,
    *,
    step: int,
    target_range: str = "A1:I10",
) -> None:
    state.events.append(
        ExecutionEvent(
            step=step,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__spreadsheet_read_file",
                "action": "spreadsheet.read_file",
                "arguments": {
                    "path": "/tmp/open.xlsx",
                    "sheet": "Sheet1",
                    "range": target_range,
                },
            },
            executed=True,
            result={"adapter_response": {"status": "ok", "result": {}}},
        )
    )


def _append_header_only_create(state: RuntimeState) -> None:
    state.events.append(
        ExecutionEvent(
            step=3,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__spreadsheet_create_workbook",
                "action": "spreadsheet.create_workbook",
                "arguments": {
                    "output_path": "/tmp/result.ods",
                    "headers": ["University"],
                },
            },
            executed=True,
            result={
                "adapter_response": {
                    "status": "ok",
                    "action": "spreadsheet.create_workbook",
                    "result": {
                        "sheet": "Sheet1",
                        "table_state": "header_only",
                    },
                }
            },
        )
    )


def test_truncated_batch_keeps_observed_reader_before_bounded_consumers() -> None:
    state = _state()
    state.events.append(
        ExecutionEvent(
            step=1,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__pdf_extract_text_batch",
                "action": "pdf.extract_text_batch",
                "arguments": {"input_pattern": "*.pdf"},
            },
            executed=True,
            result={
                "adapter_response": {
                    "status": "ok",
                    "action": "pdf.extract_text_batch",
                    "result": {
                        "matched_count": 2,
                        "files": [
                            {
                                "path": f"/tmp/source-{index}.pdf",
                                "text": "record " * 900,
                                "extracted_chars": 8_000,
                                "truncated": True,
                            }
                            for index in range(2)
                        ],
                    },
                }
            },
        )
    )
    _append_inspect_result(state)

    actions = batch_table_semantics.pending_consumer_actions(state, [])

    assert actions[0] == "pdf.extract_text_batch"
    assert actions[1:] == batch_table_semantics.CONSUMER_ACTIONS


def test_source_continuation_preserves_target_probe_and_moves_to_consumers() -> None:
    state = _state()
    state.events.append(
        ExecutionEvent(
            step=1,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__pdf_extract_text_batch",
                "action": "pdf.extract_text_batch",
                "arguments": {"input_pattern": "*.pdf"},
            },
            executed=True,
            result={
                "adapter_response": {
                    "status": "ok",
                    "action": "pdf.extract_text_batch",
                    "result": {
                        "matched_count": 1,
                        "files": [
                            {
                                "path": "/tmp/source.pdf",
                                "text": "record " * 900,
                                "extracted_chars": 8_000,
                                "truncated": True,
                            }
                        ],
                    },
                }
            },
        )
    )
    _append_inspect_result(state)
    assert batch_table_semantics.inspection_pending(state) is False

    state.events.append(
        ExecutionEvent(
            step=3,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__pdf_extract_text_batch",
                "action": "pdf.extract_text_batch",
                "arguments": {"input_pattern": "source.pdf"},
            },
            executed=True,
            result={
                "adapter_response": {
                    "status": "ok",
                    "action": "pdf.extract_text_batch",
                    "result": {
                        "matched_count": 1,
                        "files": [
                            {
                                "path": "/tmp/source.pdf",
                                "text": "complete record",
                                "extracted_chars": 15,
                                "truncated": False,
                            }
                        ],
                    },
                }
            },
        )
    )

    assert batch_table_semantics.batch_continuation_action(state) is None
    assert batch_table_semantics.inspection_pending(state) is False
    assert batch_table_semantics.pending_consumer_actions(state, []) == (
        batch_table_semantics.CONSUMER_ACTIONS
    )


def test_incomplete_source_lease_survives_a_successful_continuation() -> None:
    state = _state()
    _append_batch_result(state, count=2, step=1, truncated=True)
    _append_inspect_result(state, step=2)
    assert (
        batch_table_semantics.batch_continuation_action(state)
        == "pdf.extract_text_batch"
    )

    _append_batch_result(
        state,
        count=1,
        step=3,
        input_pattern="source-0.pdf",
        max_chars_per_file=20_000,
        truncated=True,
    )

    assert (
        batch_table_semantics.batch_continuation_action(state)
        == "pdf.extract_text_batch"
    )
    actions = batch_table_semantics.pending_consumer_actions(state, [])
    assert actions[0] == "pdf.extract_text_batch"
    assert actions[1:] == batch_table_semantics.CONSUMER_ACTIONS


def test_complete_source_with_context_only_truncation_does_not_replay_batch() -> None:
    state = _state()
    text = "complete-source " * 2_000
    state.events.append(
        ExecutionEvent(
            step=1,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__pdf_extract_text_batch",
                "action": "pdf.extract_text_batch",
                "arguments": {"input_pattern": "*.pdf"},
            },
            executed=True,
            result={
                "adapter_response": {
                    "status": "ok",
                    "action": "pdf.extract_text_batch",
                    "result": {
                        "matched_count": 1,
                        "files": [
                            {
                                "path": "/tmp/complete.pdf",
                                "source_truncated": False,
                                "extracted_chars": len(text),
                                "returned_chars": len(text),
                                "text": text,
                            }
                        ],
                    },
                }
            },
        )
    )
    _append_inspect_result(state)

    projection = batch_table_semantics._batch_model_projection(state.events[0])
    assert projection is not None
    assert projection["source_has_more"] is False
    assert projection["context_truncated"] is True
    assert batch_table_semantics.batch_continuation_action(state) is None


def test_layout_compacted_complete_source_does_not_replay_batch() -> None:
    state = _state()
    _append_batch_result(state, count=1, step=1, truncated=False)
    item = state.events[0].result["adapter_response"]["result"]["files"][0]
    item.update(
        {
            "extracted_chars": len(item["text"]) + 320,
            "raw_extracted_chars": len(item["text"]) + 1_100,
            "layout_compacted": True,
            "source_truncated": False,
            "truncated": False,
        }
    )
    _append_inspect_result(state)

    projection = batch_table_semantics._batch_model_projection(state.events[0])
    assert projection is not None
    assert projection["source_has_more"] is False
    assert batch_table_semantics.batch_continuation_action(state) is None


def test_context_omitted_complete_source_does_not_schedule_batch_replay() -> None:
    """Model file-count caps are projection loss, not source pagination."""
    state = _state()
    _append_batch_result(state, count=25, step=1, truncated=False)
    _append_inspect_result(state, step=2)

    projection = batch_table_semantics._batch_model_projection(state.events[0])
    assert projection is not None
    assert projection["files_omitted"] == 5
    assert projection["context_files_omitted"] == 5
    assert projection["source_has_more"] is False
    assert projection["context_truncated"] is True
    assert batch_table_semantics.batch_continuation_action(state) is None


def test_complete_source_failed_write_recovery_does_not_replay_producer() -> None:
    """A consumer rejection must not turn projection-only truncation into a reread."""
    state = _state()
    _append_batch_result(state, count=9, step=1, truncated=False)
    _append_inspect_result(state, step=2)
    _append_successful_read(state, step=3, target_range="A1:I10")
    _append_failed_write(state, step=4)

    assert batch_table_semantics.batch_continuation_action(state) is None
    actions = batch_table_semantics.pending_consumer_recovery_actions(state, [])
    assert actions == batch_table_semantics.CONSUMER_ACTIONS


def test_narrow_source_continuation_does_not_shrink_source_cardinality() -> None:
    state = _state()
    _append_batch_result(state, count=3, step=1, truncated=True)
    _append_inspect_result(state, step=2)
    _append_batch_result(
        state,
        count=1,
        step=3,
        input_pattern="source-0.pdf",
        truncated=True,
    )

    assert batch_table_semantics.expected_record_count(state) == 3


def test_source_cursor_progress_keeps_continuation_until_window_is_complete() -> None:
    state = _state()
    _append_window_batch_result(
        state,
        step=1,
        start_char=0,
        end_char=100,
        total_chars=300,
        source_truncated=True,
    )
    _append_inspect_result(state)

    assert batch_table_semantics.batch_continuation_action(state) == (
        "pdf.extract_text_batch"
    )

    _append_window_batch_result(
        state,
        step=3,
        start_char=100,
        end_char=200,
        total_chars=300,
        source_truncated=True,
    )
    assert batch_table_semantics.batch_continuation_action(state) == (
        "pdf.extract_text_batch"
    )

    _append_window_batch_result(
        state,
        step=4,
        start_char=200,
        end_char=300,
        total_chars=300,
        source_truncated=False,
    )
    assert batch_table_semantics.batch_continuation_action(state) is None


def test_repeated_target_probe_does_not_reset_continuation_cap() -> None:
    state = _state()
    _append_batch_result(state, count=2, step=1, truncated=True)
    _append_inspect_result(state, step=2)
    for step, pattern in enumerate(
        ("source-0.pdf", "source-1.pdf", "source-2.pdf"), start=3
    ):
        _append_batch_result(
            state,
            count=1,
            step=step,
            input_pattern=pattern,
            truncated=True,
        )
        _append_inspect_result(state, step=step + 1)

    assert batch_table_semantics.batch_continuation_action(state) is None


def test_incomplete_source_lease_rejects_an_exact_successful_replay() -> None:
    state = _state()
    _append_batch_result(state, count=2, step=1, truncated=True)
    _append_inspect_result(state, step=2)
    _append_batch_result(state, count=2, step=3, truncated=True)

    assert batch_table_semantics.batch_continuation_action(state) is None
    assert batch_table_semantics.pending_consumer_actions(state, []) == (
        batch_table_semantics.CONSUMER_ACTIONS
    )


def test_incomplete_source_lease_has_a_finite_attempt_cap() -> None:
    state = _state()
    _append_batch_result(state, count=2, step=1, truncated=True)
    _append_inspect_result(state, step=2)
    for step, pattern in enumerate(
        ("source-0.pdf", "source-1.pdf", "source-2.pdf"), start=3
    ):
        _append_batch_result(
            state,
            count=1,
            step=step,
            input_pattern=pattern,
            max_chars_per_file=20_000,
            truncated=True,
        )

    assert batch_table_semantics.batch_continuation_action(state) is None
    assert batch_table_semantics.pending_consumer_actions(state, []) == (
        batch_table_semantics.CONSUMER_ACTIONS
    )


def test_incomplete_source_lease_stops_after_a_successful_mutation() -> None:
    state = _state()
    _append_batch_result(state, count=2, step=1, truncated=True)
    _append_inspect_result(state, step=2)
    _append_batch_result(
        state,
        count=1,
        step=3,
        input_pattern="source-0.pdf",
        truncated=True,
    )
    state.events.append(
        ExecutionEvent(
            step=4,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__spreadsheet_write_range",
                "action": "spreadsheet.write_range",
                "arguments": {"sheet": "Sheet1", "range": "A1:B2", "values": []},
            },
            executed=True,
            result={"adapter_response": {"status": "ok"}},
        )
    )

    assert batch_table_semantics.batch_continuation_action(state) is None


def test_incomplete_source_lease_stops_after_a_successful_gui_action() -> None:
    state = _state()
    _append_batch_result(state, count=2, step=1, truncated=True)
    _append_inspect_result(state, step=2)
    _append_batch_result(
        state,
        count=1,
        step=3,
        input_pattern="source-0.pdf",
        truncated=True,
    )
    state.events.append(
        ExecutionEvent(
            step=4,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "gui",
                "tool": "gui_action",
                "action": "click",
                "arguments": {"x": 10, "y": 20},
            },
            executed=True,
            result={"status": "ok"},
        )
    )

    assert batch_table_semantics.batch_continuation_action(state) is None
    assert batch_table_semantics.pending_consumer_actions(state, []) == (
        batch_table_semantics.CONSUMER_ACTIONS
    )


def test_incomplete_source_lease_resolves_wrapped_batch_route() -> None:
    state = _state()
    _append_batch_result(state, count=2, step=1, truncated=True)
    _append_inspect_result(state, step=2)
    _append_batch_result(
        state,
        count=1,
        step=3,
        input_pattern="source-0.pdf",
        truncated=True,
    )
    latest = state.events[-1]
    latest.proposed = {
        "kind": "adapter",
        "tool": "adapter__adapter_call",
        "action": "adapter.call",
        "arguments": {
            "adapter": "os",
            "action": "pdf.extract_text_batch",
            "payload": {"params": {"input_pattern": "source-0.pdf"}},
        },
    }

    assert batch_table_semantics.batch_continuation_action(state) == (
        "pdf.extract_text_batch"
    )


def test_incomplete_source_lease_resolves_wrapped_target_probe() -> None:
    state = _state()
    _append_batch_result(state, count=2, step=1, truncated=True)
    _append_inspect_result(state, step=2)
    state.events[-1].proposed = {
        "kind": "adapter",
        "tool": "adapter__adapter_call",
        "action": "adapter.call",
        "arguments": {
            "adapter": "libreoffice_calc",
            "action": "workbook.inspect",
            "payload": {"params": {}},
        },
    }
    _append_batch_result(
        state,
        count=1,
        step=3,
        input_pattern="source-0.pdf",
        truncated=True,
    )

    assert batch_table_semantics._valid_target_inspection(state) is not None
    assert batch_table_semantics.batch_continuation_action(state) == (
        "pdf.extract_text_batch"
    )


def test_source_continuation_preserves_probe_across_target_read() -> None:
    state = _state()
    _append_batch_result(state, step=1)
    _append_inspect_result(state, step=2)
    state.events.append(
        ExecutionEvent(
            step=3,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__spreadsheet_read_file",
                "action": "spreadsheet.read_file",
                "arguments": {"path": "/tmp/open.xlsx", "sheet": "Sheet1"},
            },
            executed=True,
            result={"adapter_response": {"status": "ok", "result": {}}},
        )
    )
    state.events.append(
        ExecutionEvent(
            step=4,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__pdf_extract_text_batch",
                "action": "pdf.extract_text_batch",
                "arguments": {"input_pattern": "source.pdf"},
            },
            executed=True,
            result={
                "adapter_response": {
                    "status": "ok",
                    "action": "pdf.extract_text_batch",
                    "result": {
                        "matched_count": 1,
                        "files": [
                            {
                                "path": "/tmp/source.pdf",
                                "text": "complete record",
                                "extracted_chars": 15,
                                "truncated": False,
                            }
                        ],
                    },
                }
            },
        )
    )

    assert batch_table_semantics._valid_target_inspection(state) is not None
    assert batch_table_semantics.inspection_pending(state) is False
    assert batch_table_semantics.pending_consumer_actions(state, []) == (
        batch_table_semantics.CONSUMER_ACTIONS
    )


def test_source_continuation_does_not_trust_gui_read_named_action() -> None:
    state = _state()
    _append_batch_result(state, step=1)
    _append_inspect_result(state, step=2)
    state.events.append(
        ExecutionEvent(
            step=3,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "gui",
                "tool": "gui_action",
                "action": "window.read",
                "arguments": {"x": 1, "y": 2},
            },
            executed=True,
            result={"status": "ok"},
        )
    )
    _append_batch_result(state, count=1, step=4)

    assert batch_table_semantics._valid_target_inspection(state) is None
    assert batch_table_semantics.inspection_pending(state) is True


def test_source_continuation_resolves_read_only_adapter_call() -> None:
    state = _state()
    _append_batch_result(state, step=1)
    _append_inspect_result(state, step=2)
    state.events.append(
        ExecutionEvent(
            step=3,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__adapter_call",
                "action": "adapter.call",
                "arguments": {
                    "adapter": "libreoffice_calc",
                    "action": "workbook.inspect",
                    "payload": {"params": {}},
                },
            },
            executed=True,
            result={"adapter_response": {"status": "ok", "result": {}}},
        )
    )
    _append_batch_result(state, count=1, step=4)

    assert batch_table_semantics._valid_target_inspection(state) is not None
    assert batch_table_semantics.inspection_pending(state) is False


def test_inspection_before_batch_is_not_reused_as_target_probe() -> None:
    state = _state()
    _append_inspect_result(state, step=1)
    _append_batch_result(state, step=2)

    assert batch_table_semantics.inspection_pending(state) is True


def test_complete_batch_does_not_readd_observed_reader() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)

    actions = batch_table_semantics.pending_consumer_actions(state, [])

    assert actions == batch_table_semantics.CONSUMER_ACTIONS
    assert "pdf.extract_text_batch" not in actions


def test_batch_producer_is_detected_before_any_producer_attempt() -> None:
    state = _state()

    assert batch_table_semantics.pending_producer_actions(state, []) == (
        "pdf.extract_text_batch",
    )


def test_batch_producer_detection_survives_unrelated_failure() -> None:
    state = _state()
    state.events.append(
        ExecutionEvent(
            step=1,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "gui",
                "tool": "gui_action",
                "action": "click",
                "arguments": {"x": "504", "y": "76"},
            },
            executed=False,
            error={"type": "ValidationError"},
        )
    )

    assert batch_table_semantics.pending_producer_actions(state, []) == (
        "pdf.extract_text_batch",
    )


def test_failed_batch_attempt_releases_producer_gate() -> None:
    state = _state()
    _append_failed_batch(state)

    assert batch_table_semantics.pending_producer_actions(state, []) == ()
    names = {tool["function"]["name"] for tool in _agent(include_gui=True).tools(state)}
    assert "tools_search" in names
    assert "propose_done" in names
    assert "fail_task" in names
    assert "gui_action" in names


def test_image_batch_producer_uses_same_detection_helper() -> None:
    state = _state(
        instruction=(
            "For each image, extract the labels and put one record per image in the table."
        )
    )

    assert batch_table_semantics.pending_producer_actions(state, []) == (
        "image.extract_text_batch",
    )


def test_batch_probe_remains_pending_after_unrelated_gui_failure() -> None:
    state = _state()
    _append_batch_result(state)
    state.events.append(
        ExecutionEvent(
            step=2,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "gui",
                "tool": "gui_action",
                "action": "click",
                "arguments": {"x": "504", "y": "76"},
            },
            executed=False,
            error={"type": "ValidationError"},
        )
    )

    assert batch_table_semantics.inspection_pending(state)


def test_failed_batch_probe_releases_discovery_only_gate() -> None:
    state = _state(instruction="For each source PDF, create a new spreadsheet.")
    _append_batch_result(state)
    _append_failed_inspect(state)

    assert not batch_table_semantics.inspection_pending(state)
    names = {tool["function"]["name"] for tool in _agent().tools(state)}
    assert "propose_done" in names
    assert "fail_task" in names


def test_recoverable_failed_consumer_write_is_classified_for_recovery() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    _append_failed_write(state)

    assert batch_table_semantics.pending_consumer_recovery_actions(state, []) == (
        batch_table_semantics.CONSUMER_ACTIONS
    )


def test_failed_consumer_write_precedes_incomplete_source_continuation() -> None:
    """A write contract error must not make the source reader the next attractor."""
    state = _state()
    _append_batch_result(state, truncated=True)
    _append_inspect_result(state)
    _append_failed_write(state)

    actions = batch_table_semantics.pending_consumer_recovery_actions(state, [])
    assert actions[: len(batch_table_semantics.CONSUMER_ACTIONS)] == (
        batch_table_semantics.CONSUMER_ACTIONS
    )
    assert actions[-1] == "pdf.extract_text_batch"


def test_nested_downstream_range_error_is_recoverable() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    _append_failed_write(state)
    state.events[-1].error = {
        "status": "error",
        "error": {
            "code": "DOWNSTREAM_FAILED",
            "details": {
                "response": {
                    "status": "error",
                    "error": {
                        "code": "RANGE_INVALID",
                        "message": "typed matrix dimensions do not match target",
                    },
                }
            },
        },
    }

    assert batch_table_semantics.pending_consumer_recovery_actions(state, []) == (
        batch_table_semantics.CONSUMER_ACTIONS
    )


def test_partial_commit_write_error_releases_bounded_surface() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    _append_failed_write(state)
    state.events[-1].error = {
        "status": "error",
        "committed": True,
        "error": {"code": "RANGE_INVALID"},
    }

    assert batch_table_semantics.pending_consumer_recovery_actions(state, []) == ()


def test_write_io_error_releases_bounded_surface() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    _append_failed_write(state)
    state.events[-1].error = {
        "status": "error",
        "error": {"code": "SPREADSHEET_PATH_NOT_FOUND"},
    }

    assert batch_table_semantics.pending_consumer_recovery_actions(state, []) == ()


def test_duplicate_read_is_classified_for_consumer_recovery() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    _append_failed_read(
        state,
        error={
            "type": "ValueError",
            "detail": "identical successful action already executed at step 3; inspect state or choose a different action",
        },
    )

    actions = batch_table_semantics.pending_consumer_recovery_actions(state, [])
    assert actions == batch_table_semantics.CONSUMER_ACTIONS


def test_repeated_read_block_is_classified_for_consumer_recovery() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    _append_failed_read(
        state,
        error={
            "type": "RepeatedActionBlocked",
            "blocked_action": "spreadsheet.read_file",
            "argument_signature": "synthetic",
            "error_signature": "PATH_NOT_FOUND",
            "block_scope": "episode",
        },
    )

    assert batch_table_semantics.pending_consumer_recovery_actions(state, []) == (
        batch_table_semantics.CONSUMER_ACTIONS
    )


def test_consecutive_failed_reads_keep_consumer_recovery_classification() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    _append_failed_read(
        state,
        error={"type": "ValueError", "detail": "synthetic schema failure"},
    )
    _append_failed_read(
        state,
        step=4,
        error={
            "type": "RepeatedActionBlocked",
            "blocked_action": "spreadsheet.read_file",
            "argument_signature": "synthetic",
            "error_signature": "SCHEMA_ERROR",
            "block_scope": "episode",
        },
    )

    assert batch_table_semantics.pending_consumer_recovery_actions(state, []) == (
        batch_table_semantics.CONSUMER_ACTIONS
    )


def test_successful_changed_read_keeps_lease_despite_old_read_block() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    _append_failed_read(
        state,
        error={"type": "ValueError", "detail": "synthetic schema failure"},
    )
    _append_failed_read(
        state,
        step=4,
        error={
            "type": "RepeatedActionBlocked",
            "blocked_action": "spreadsheet.read_file",
            "argument_signature": "synthetic",
            "error_signature": "SCHEMA_ERROR",
            "block_scope": "episode",
        },
    )
    _append_successful_read(state, step=5, target_range="A2:I10")

    assert state.active_request_blocks()
    assert batch_table_semantics.pending_consumer_recovery_actions(state, []) == (
        batch_table_semantics.CONSUMER_ACTIONS
    )


def test_successful_read_does_not_override_unrelated_active_block() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    state.events.append(
        ExecutionEvent(
            step=3,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "gui",
                "tool": "gui_action",
                "action": "click",
                "arguments": {"x": 5, "y": 5},
            },
            executed=False,
            error={
                "type": "RepeatedActionBlocked",
                "blocked_action": "gui_action",
                "argument_signature": "synthetic",
                "error_signature": "GUI_ERROR",
                "block_scope": "episode",
            },
        )
    )
    _append_successful_read(state, step=4, target_range="A2:I10")

    assert batch_table_semantics.pending_consumer_recovery_actions(state, []) == ()


def test_structured_read_failure_uses_consumer_recovery() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    _append_failed_read(
        state,
        error={
            "status": "error",
            "error_code": "SPREADSHEET_PATH_NOT_FOUND",
            "error": "the requested spreadsheet path does not exist",
        },
    )

    assert batch_table_semantics.pending_consumer_recovery_actions(state, [])


def test_schema_read_failure_uses_consumer_recovery() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    _append_failed_read(
        state,
        error={
            "type": "ValueError",
            "detail": (
                "arguments violate the current model-visible schema for "
                "adapter__spreadsheet_read_file"
            ),
        },
    )

    assert batch_table_semantics.pending_consumer_recovery_actions(state, []) == (
        batch_table_semantics.CONSUMER_ACTIONS
    )


def test_non_adapter_read_failure_does_not_claim_consumer_recovery() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    _append_failed_read(
        state,
        error={"type": "ValueError", "detail": "synthetic GUI boundary failure"},
    )
    state.events[-1].proposed["kind"] = "gui"

    assert batch_table_semantics.pending_consumer_recovery_actions(state, []) == ()


def test_read_failure_after_successful_write_does_not_retain_consumer_lease() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    _append_failed_write(state)
    state.events[-1].executed = True
    state.events[-1].error = None
    state.events[-1].result = {"adapter_response": {"status": "ok"}}
    _append_failed_read(
        state,
        step=4,
        error={"type": "ValueError", "detail": "synthetic schema failure"},
    )

    assert batch_table_semantics.pending_consumer_recovery_actions(state, []) == ()


def test_read_failure_after_recoverable_write_keeps_consumer_lease() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    _append_failed_write(state)
    _append_failed_read(
        state,
        step=4,
        error={"type": "ValueError", "detail": "synthetic schema failure"},
    )

    assert batch_table_semantics.pending_consumer_recovery_actions(state, []) == (
        batch_table_semantics.CONSUMER_ACTIONS
    )


def test_unrecoverable_failed_write_releases_consumer_recovery_surface() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    _append_failed_write(state)
    state.events[-1].error = {
        "status": "error",
        "error": {"code": "PATH_NOT_FOUND"},
    }

    assert batch_table_semantics.pending_consumer_recovery_actions(state, []) == ()
    names = {tool["function"]["name"] for tool in _agent(include_gui=True).tools(state)}
    assert "tools_search" in names
    assert "gui_action" in names


def test_successful_consumer_keeps_readback_actions_pending() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    state.events.append(
        ExecutionEvent(
            step=3,
            timestamp_utc="2026-08-29T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter__spreadsheet_write_range",
                "action": "spreadsheet.write_range",
                "arguments": {
                    "sheet": "Sheet1",
                    "range": "A2:B4",
                    "values": [["a", 1], ["b", 2], ["c", 3]],
                },
            },
            executed=True,
            result={"adapter_response": {"status": "ok", "result": {}}},
        )
    )

    actions = batch_table_semantics.pending_post_mutation_actions(state, [])
    assert actions == (
        batch_table_semantics.READ_ACTION,
        batch_table_semantics.WRITE_ACTION,
        batch_table_semantics.SAVE_ACTION,
    )


def test_post_mutation_surface_ends_after_readback_and_save() -> None:
    state = _state()
    _append_batch_result(state)
    _append_inspect_result(state)
    for step, action, tool in (
        (3, batch_table_semantics.WRITE_ACTION, "adapter__spreadsheet_write_range"),
        (4, batch_table_semantics.READ_ACTION, "adapter__spreadsheet_read_file"),
        (5, batch_table_semantics.SAVE_ACTION, "adapter__spreadsheet_save"),
    ):
        state.events.append(
            ExecutionEvent(
                step=step,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": tool,
                    "action": action,
                    "arguments": {},
                },
                executed=True,
                result={"adapter_response": {"status": "ok", "result": {}}},
            )
        )

    assert batch_table_semantics.pending_post_mutation_actions(state, []) == ()


def test_create_after_failed_probe_enters_creation_lifecycle() -> None:
    state = _state(instruction="For each source PDF, create a new spreadsheet.")
    _append_batch_result(state)
    _append_failed_inspect(state)
    _append_header_only_create(state)

    assert batch_table_semantics.stage_actions(
        state, [batch_table_semantics.CREATE_ACTION]
    ) == [batch_table_semantics.WRITE_ACTION]
    assert batch_table_semantics.completion_errors(state)


def test_creation_constraints_begin_only_after_successful_model_create() -> None:
    state = _state(instruction="For each source PDF, create a new spreadsheet.")
    _append_batch_result(state)

    assert batch_table_semantics.completion_errors(state) == []
    _append_inspect_result(state)
    assert batch_table_semantics.completion_errors(state) == []

    _append_header_only_create(state)
    errors = batch_table_semantics.completion_errors(state)
    assert errors
    assert "exactly 3" in errors[0]

    argument_errors = batch_table_semantics.argument_contract_errors(
        state,
        batch_table_semantics.CREATE_ACTION,
        {
            "output_path": "/tmp/other.ods",
            "headers": ["University"],
            "rows": [["one"], ["two"]],
        },
    )
    assert argument_errors
    assert "exactly 3" in argument_errors[0]


def test_create_before_latest_batch_does_not_satisfy_current_creation_lifecycle() -> (
    None
):
    state = _state(instruction="For each source PDF, create a new spreadsheet.")
    _append_header_only_create(state)
    # The create above predates the producer that starts this workflow and
    # must not activate the current creation lifecycle's completion checks.
    _append_batch_result(state, step=4)

    assert batch_table_semantics.completion_errors(state) == []


def test_batch_stage_is_task_id_invariant_and_does_not_echo_sensitive_metadata() -> (
    None
):
    first = _state(task_id="123e4567-e89b-72d3-a456-426614174000")
    second = _state(task_id="different-task")
    _append_batch_result(first)
    _append_batch_result(second)
    first.events[0].result["task_id"] = "evaluator-secret-42"

    first_surface = _agent().tools(first)
    second_surface = _agent().tools(second)
    assert [tool["function"]["name"] for tool in first_surface] == [
        tool["function"]["name"] for tool in second_surface
    ]
    serialized = json.dumps(first_surface, ensure_ascii=False)
    assert "123e4567" not in serialized
    assert "evaluator-secret-42" not in serialized
    assert "golden" not in serialized.casefold()
