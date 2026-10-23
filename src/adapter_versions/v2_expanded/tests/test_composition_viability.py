from __future__ import annotations

import pytest

from integrations.lite_agent import completion_recovery
from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.completion_policy import (
    action_is_read_only,
    local_document_paths_match,
)
from integrations.lite_agent.generic_completion import STRICT_COMPLETION_DONE
from integrations.lite_agent.stall_policy import request_stall_replan
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


class NoAdapterExecutor:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("Adapter execution is not expected")


def make_agent() -> LiteAgent:
    return LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        NoAdapterExecutor(),  # type: ignore[arg-type]
    )


def _impress_inspect_event(step: int, url: str | None) -> ExecutionEvent:
    identity = {"url": url} if url is not None else {}
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-08-31T00:00:00Z",
        proposed={
            "kind": "adapter",
            "tool": "adapter__presentation_inspect",
            "action": "presentation.inspect",
            "arguments": {},
        },
        executed=True,
        result={"context_hint": {"identity": identity}},
    )


def _impress_save_event(
    step: int,
    selected_url: str | None,
    result_url: str,
    size: int | None,
    *,
    status: str = "ok",
) -> ExecutionEvent:
    arguments = {"url": selected_url} if selected_url is not None else {}
    saved = {"url": result_url}
    if size is not None:
        saved["size"] = size
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-08-31T00:00:00Z",
        proposed={
            "kind": "adapter",
            "tool": "adapter__presentation_save",
            "action": "presentation.save",
            "arguments": arguments,
        },
        executed=True,
        result={"status": status, "result": saved},
    )


def _impress_save_gate(events: list[ExecutionEvent]) -> dict:
    return CompletionMixin._generic_completion_gate(
        RuntimeState(
            task_id="synthetic-save-as",
            domain="libreoffice_impress",
            instruction="Save the presentation as renamed-deck.pptx.",
            events=events,
        )
    )


def test_destination_changing_save_counts_as_mutation_after_readback() -> None:
    source_url = "file:///home/user/Downloads/source-deck.pptx"
    destination_url = "file:///home/user/Documents/renamed-deck.pptx"

    gate = _impress_save_gate(
        [
            _impress_inspect_event(1, source_url),
            _impress_save_event(2, destination_url, destination_url, 4096),
            _impress_inspect_event(3, destination_url),
        ]
    )

    assert gate == {"passed": True, "missing": []}


def test_destination_changing_save_still_requires_post_save_readback() -> None:
    source_url = "file:///home/user/Downloads/source-deck.pptx"
    destination_url = "file:///home/user/Documents/renamed-deck.pptx"

    gate = _impress_save_gate(
        [
            _impress_inspect_event(1, source_url),
            _impress_save_event(2, destination_url, destination_url, 4096),
        ]
    )

    assert gate["passed"] is False
    assert "perform structural read-back after the final mutation" in gate["missing"]


def test_same_url_save_is_not_a_task_changing_action() -> None:
    current_url = "file:///home/user/Documents/current-deck.pptx"

    gate = _impress_save_gate(
        [
            _impress_inspect_event(1, current_url),
            _impress_save_event(2, current_url, current_url, 4096),
            _impress_inspect_event(3, current_url),
        ]
    )

    assert gate["passed"] is False
    assert "no successful task-changing Adapter action is recorded" in gate["missing"]


def _spreadsheet_inspect_event(step: int, url: str) -> ExecutionEvent:
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-09-01T00:00:00Z",
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
        result={
            "adapter_response": {
                "result": {
                    "response": {
                        "status": "ok",
                        "result": {"url": url, "sheets": []},
                        "verification": {"passed": True},
                    }
                }
            }
        },
    )


def _spreadsheet_save_event(
    step: int,
    output_path: str,
    *,
    result_path: str,
    result_url: str,
) -> ExecutionEvent:
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-09-01T00:00:00Z",
        proposed={
            "kind": "adapter",
            "tool": "adapter__adapter_call",
            "action": "adapter.call",
            "arguments": {
                "adapter": "libreoffice_calc",
                "action": "workbook.save",
                "payload": {"params": {"url": output_path}},
            },
        },
        executed=True,
        result={
            "adapter_response": {
                "result": {
                    "response": {
                        "status": "ok",
                        "result": {
                            "path": result_path,
                            "url": result_url,
                            "size": 4096,
                        },
                        "verification": {"passed": True},
                    }
                }
            }
        },
    )


def _spreadsheet_save_gate(events: list[ExecutionEvent]) -> dict:
    return CompletionMixin._generic_completion_gate(
        RuntimeState(
            task_id="synthetic-spreadsheet-save-as",
            domain="multi_apps",
            instruction="Save the current spreadsheet as renamed.xlsx.",
            events=events,
        )
    )


def test_multi_apps_output_path_save_as_counts_as_mutation() -> None:
    source_url = "file:///home/user/Desktop/source.xlsx"
    destination_path = "/home/user/Documents/renamed.xlsx"
    destination_url = "file:///home/user/Documents/renamed.xlsx"

    gate = _spreadsheet_save_gate(
        [
            _spreadsheet_inspect_event(1, source_url),
            _spreadsheet_save_event(
                2,
                "~/Documents/renamed.xlsx",
                result_path=destination_path,
                result_url=destination_url,
            ),
            _spreadsheet_inspect_event(3, destination_url),
        ]
    )

    assert gate == {"passed": True, "missing": []}


def test_multi_apps_output_path_save_as_requires_post_save_readback() -> None:
    source_url = "file:///home/user/Desktop/source.xlsx"
    destination_path = "/home/user/Documents/renamed.xlsx"

    gate = _spreadsheet_save_gate(
        [
            _spreadsheet_inspect_event(1, source_url),
            _spreadsheet_save_event(
                2,
                "~/Documents/renamed.xlsx",
                result_path=destination_path,
                result_url="file:///home/user/Documents/renamed.xlsx",
            ),
        ]
    )

    assert gate["passed"] is False
    assert "perform structural read-back after the final mutation" in gate["missing"]


def test_multi_apps_tilde_alias_save_to_current_path_is_not_save_as() -> None:
    current_url = "file:///home/user/Desktop/current.xlsx"

    gate = _spreadsheet_save_gate(
        [
            _spreadsheet_inspect_event(1, current_url),
            _spreadsheet_save_event(
                2,
                "~/Desktop/current.xlsx",
                result_path="/home/user/Desktop/current.xlsx",
                result_url=current_url,
            ),
            _spreadsheet_inspect_event(3, current_url),
        ]
    )

    assert gate["passed"] is False
    assert "no successful task-changing Adapter action is recorded" in gate["missing"]


def test_calc_save_as_requires_the_latest_verified_target_inspection() -> None:
    source_url = "file:///home/user/Desktop/source.xlsx"
    destination_url = "file:///home/user/Documents/renamed.xlsx"
    failed_target_inspect = _spreadsheet_inspect_event(4, destination_url)
    failed_target_inspect.result["adapter_response"]["result"]["response"][
        "verification"
    ]["passed"] = False

    gate = _spreadsheet_save_gate(
        [
            _spreadsheet_inspect_event(1, source_url),
            _spreadsheet_save_event(
                2,
                "~/Documents/renamed.xlsx",
                result_path="/home/user/Documents/renamed.xlsx",
                result_url=destination_url,
            ),
            _spreadsheet_inspect_event(3, destination_url),
            failed_target_inspect,
        ]
    )

    assert gate["passed"] is False
    assert "perform structural read-back after the final mutation" in gate["missing"]


def test_calc_save_as_does_not_reuse_identity_after_failed_latest_inspection() -> None:
    source_url = "file:///home/user/Desktop/source.xlsx"
    destination_url = "file:///home/user/Documents/renamed.xlsx"
    failed_inspect = _spreadsheet_inspect_event(2, source_url)
    failed_inspect.executed = False
    failed_inspect.result = None
    failed_inspect.error = {"type": "AdapterError", "detail": "inspection failed"}

    gate = _spreadsheet_save_gate(
        [
            _spreadsheet_inspect_event(1, source_url),
            failed_inspect,
            _spreadsheet_save_event(
                3,
                "~/Documents/renamed.xlsx",
                result_path="/home/user/Documents/renamed.xlsx",
                result_url=destination_url,
            ),
            _spreadsheet_inspect_event(4, destination_url),
        ]
    )

    assert gate["passed"] is False
    assert "no successful task-changing Adapter action is recorded" in gate["missing"]


def test_calc_save_as_rejects_outer_failure_around_inner_success() -> None:
    source_url = "file:///home/user/Desktop/source.xlsx"
    destination_url = "file:///home/user/Documents/renamed.xlsx"
    save = _spreadsheet_save_event(
        2,
        "~/Documents/renamed.xlsx",
        result_path="/home/user/Documents/renamed.xlsx",
        result_url=destination_url,
    )
    save.result["status"] = "error"

    gate = _spreadsheet_save_gate(
        [
            _spreadsheet_inspect_event(1, source_url),
            save,
            _spreadsheet_inspect_event(3, destination_url),
        ]
    )

    assert gate["passed"] is False
    assert "no successful task-changing Adapter action is recorded" in gate["missing"]


@pytest.mark.parametrize(
    "action",
    [
        "mail.query_messages",
        "workspace.find_files",
        "artifact.verify",
        "spreadsheet.read_file",
    ],
)
def test_calc_save_as_does_not_accept_unrelated_read_as_post_save_readback(
    action: str,
) -> None:
    source_url = "file:///home/user/Desktop/source.xlsx"
    destination_url = "file:///home/user/Documents/renamed.xlsx"
    unrelated = ExecutionEvent(
        step=3,
        timestamp_utc="2026-09-01T00:00:00Z",
        proposed={
            "kind": "adapter",
            "action": action,
            "arguments": {},
        },
        executed=True,
        result={"status": "ok", "verification": {"passed": True}},
    )
    gate = _spreadsheet_save_gate(
        [
            _spreadsheet_inspect_event(1, source_url),
            _spreadsheet_save_event(
                2,
                "~/Documents/renamed.xlsx",
                result_path="/home/user/Documents/renamed.xlsx",
                result_url=destination_url,
            ),
            unrelated,
        ]
    )

    assert gate["passed"] is False
    assert "perform structural read-back after the final mutation" in gate["missing"]


def test_local_tilde_alias_is_bound_to_the_active_guest_user() -> None:
    assert local_document_paths_match(
        "~/Desktop/current.xlsx", "file:///home/user/Desktop/current.xlsx"
    )
    assert not local_document_paths_match(
        "~/Desktop/current.xlsx", "file:///home/other/Desktop/current.xlsx"
    )


@pytest.mark.parametrize(
    ("prior_url", "selected_url", "result_url", "size", "status"),
    [
        (
            "file:///home/user/Downloads/source-deck.pptx",
            "file:///home/user/Documents/renamed-deck.pptx",
            "file:///home/user/Documents/other-deck.pptx",
            4096,
            "ok",
        ),
        (
            None,
            "file:///home/user/Documents/renamed-deck.pptx",
            "file:///home/user/Documents/renamed-deck.pptx",
            4096,
            "ok",
        ),
        (
            "file:///home/user/Downloads/source-deck.pptx",
            "file:///home/user/Documents/renamed-deck.pptx",
            "file:///home/user/Documents/renamed-deck.pptx",
            None,
            "ok",
        ),
        (
            "file:///home/user/Downloads/source-deck.pptx",
            None,
            "file:///home/user/Documents/renamed-deck.pptx",
            4096,
            "ok",
        ),
        (
            "file:///home/user/Downloads/source-deck.pptx",
            "file:///home/user/Documents/renamed-deck.pptx",
            "file:///home/user/Documents/renamed-deck.pptx",
            4096,
            "error",
        ),
    ],
    ids=(
        "result-mismatch",
        "no-prior-identity",
        "no-size",
        "no-model-url",
        "non-ok-result",
    ),
)
def test_save_without_complete_identity_evidence_is_not_task_changing(
    prior_url: str | None,
    selected_url: str | None,
    result_url: str,
    size: int | None,
    status: str,
) -> None:
    gate = _impress_save_gate(
        [
            _impress_inspect_event(1, prior_url),
            _impress_save_event(
                2,
                selected_url,
                result_url,
                size,
                status=status,
            ),
            _impress_inspect_event(3, result_url),
        ]
    )

    assert gate["passed"] is False
    assert "no successful task-changing Adapter action is recorded" in gate["missing"]


def test_same_url_save_still_persists_an_ordinary_mutation_lifecycle() -> None:
    current_url = "file:///home/user/Documents/current-deck.pptx"
    transition = ExecutionEvent(
        step=2,
        timestamp_utc="2026-08-31T00:00:00Z",
        proposed={
            "kind": "adapter",
            "tool": "adapter__slide_set_transition",
            "action": "slide.set_transition",
            "arguments": {"slide": 0, "transition": "fade"},
        },
        executed=True,
        result={"status": "ok", "result": {"slide": 0, "transition": "fade"}},
    )
    state = RuntimeState(
        task_id="synthetic-mutation-save",
        domain="libreoffice_impress",
        instruction="Set the slide transition and save the presentation.",
        events=[
            _impress_inspect_event(1, current_url),
            transition,
            _impress_save_event(3, current_url, current_url, 4096),
            _impress_inspect_event(4, current_url),
        ],
    )

    assert CompletionMixin._generic_completion_gate(state) == {
        "passed": True,
        "missing": [],
    }


def test_wrapped_calc_lifecycle_counts_for_save_and_readback() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="multi_apps",
        instruction="Update the current workbook and save it.",
        recommended_actions=["spreadsheet.write_range"],
        events=[
            ExecutionEvent(
                step=1,
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
                result={"sheet": "Sheet1", "used_range": "A1:B2"},
            ),
            ExecutionEvent(
                step=2,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__adapter_call",
                    "action": "adapter.call",
                    "arguments": {
                        "adapter": "libreoffice_calc",
                        "action": "range.write",
                        "payload": {
                            "params": {
                                "sheet": "Sheet1",
                                "range": "A1:B2",
                                "values": [["a", "b"], ["c", "d"]],
                            }
                        },
                    },
                },
                executed=True,
                result={"status": "ok"},
            ),
            ExecutionEvent(
                step=3,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__adapter_call",
                    "action": "adapter.call",
                    "arguments": {
                        "adapter": "libreoffice_calc",
                        "action": "workbook.save",
                        "payload": {"params": {}},
                    },
                },
                executed=True,
                result={
                    "path": "/tmp/current.ods",
                    "size": 10,
                    "verification": {"passed": True},
                },
            ),
            ExecutionEvent(
                step=4,
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
                result={
                    "sheet": "Sheet1",
                    "used_range": "A1:B2",
                    "verification": {"passed": True},
                },
            ),
        ],
    )

    assert CompletionMixin._completion_gate(state) == {
        "passed": True,
        "missing": [],
    }


def test_wrapped_calc_mutation_without_save_is_rejected() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="multi_apps",
        instruction="Update the current workbook and save it.",
        recommended_actions=["spreadsheet.write_range"],
        events=[
            ExecutionEvent(
                step=1,
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
                result={"sheet": "Sheet1", "used_range": "A1:B2"},
            ),
            ExecutionEvent(
                step=2,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__adapter_call",
                    "action": "adapter.call",
                    "arguments": {
                        "adapter": "libreoffice_calc",
                        "action": "range.write",
                        "payload": {
                            "params": {
                                "sheet": "Sheet1",
                                "range": "A1:B2",
                                "values": [["a", "b"], ["c", "d"]],
                            }
                        },
                    },
                },
                executed=True,
                result={"status": "ok"},
            ),
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
                result={"sheet": "Sheet1", "used_range": "A1:B2"},
            ),
        ],
    )

    gate = CompletionMixin._completion_gate(state)

    assert gate["passed"] is False
    assert any("save" in item.casefold() for item in gate["missing"])


@pytest.mark.parametrize(
    "route_shape", ["nested", "flat_top", "flat_inner_params", "flat_inner_direct"]
)
def test_calc_completion_canonicalizes_nested_and_flattened_routes(
    route_shape: str,
) -> None:
    """All persisted adapter.call shapes share the same completion identity."""

    def proposal(action: str, arguments: dict) -> dict:
        if route_shape == "nested":
            return {
                "kind": "adapter",
                "action": "adapter.call",
                "arguments": {
                    "adapter": "libreoffice_calc",
                    "action": action,
                    "payload": {"params": arguments},
                },
            }
        if route_shape == "flat_top":
            return {
                "kind": "adapter",
                "action": "adapter.call",
                "downstream_adapter": "libreoffice_calc",
                "downstream_action": action,
                "arguments": arguments,
            }
        if route_shape == "flat_inner_params":
            return {
                "kind": "adapter",
                "action": "adapter.call",
                "arguments": {
                    "downstream_adapter": "libreoffice_calc",
                    "downstream_action": action,
                    "params": arguments,
                },
            }
        return {
            "kind": "adapter",
            "action": "adapter.call",
            "arguments": {
                "adapter": "libreoffice_calc",
                "action": action,
                **arguments,
            },
        }

    def event(step: int, action: str, arguments: dict, result: dict) -> ExecutionEvent:
        return ExecutionEvent(
            step=step,
            timestamp_utc="2026-09-01T00:00:00Z",
            proposed=proposal(action, arguments),
            executed=True,
            result=result,
        )

    inspect_result = {
        "status": "ok",
        "result": {"url": "file:///home/user/Desktop/current.xlsx"},
        "verification": {"passed": True},
    }
    state = RuntimeState(
        task_id="synthetic-flat-route-completion",
        domain="multi_apps",
        instruction="Update the current workbook and save it.",
        events=[
            event(1, "workbook.inspect", {}, inspect_result),
            event(
                2,
                "range.write",
                {"sheet": "Sheet1", "range": "A1", "values": [["updated"]]},
                {"status": "ok"},
            ),
            event(
                3,
                "workbook.save",
                {},
                {
                    "status": "ok",
                    "result": {
                        "url": "file:///home/user/Desktop/current.xlsx",
                        "size": 10,
                    },
                    "verification": {"passed": True},
                },
            ),
            event(4, "workbook.inspect", {}, inspect_result),
        ],
    )

    assert CompletionMixin._generic_completion_gate(state) == {
        "passed": True,
        "missing": [],
    }


def test_tool_surface_counts_wrapped_mutation_as_required_facade_attempt() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="multi_apps",
        instruction="Update the current workbook.",
        recommended_actions=["spreadsheet.write_range"],
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": "adapter__adapter_call",
                    "action": "adapter.call",
                    "arguments": {
                        "adapter": "libreoffice_calc",
                        "action": "range.write",
                        "payload": {
                            "params": {
                                "sheet": "Sheet1",
                                "range": "A1:B2",
                                "values": [["a", "b"], ["c", "d"]],
                            }
                        },
                    },
                },
                executed=True,
                result={"status": "ok"},
            )
        ],
    )

    agent = LiteAgent(
        LiteAgentConfig(
            base_url="http://unused/v1",
            include_gui=True,
        ),
        NoAdapterExecutor(),  # type: ignore[arg-type]
        gui_executor=lambda _arguments: {},
    )
    names = {tool["function"]["name"] for tool in agent.tools(state)}

    # Once the wrapped write is recognized, the required-mutation guard no
    # longer suppresses the normal post-mutation surface (including GUI as a
    # fallback).  The direct facade remains available through the public
    # catalog; the assertion is about the stage decision, not tool removal.
    assert "gui_action" in names


def test_proactive_done_never_replaces_the_normal_tool_surface(monkeypatch) -> None:
    state = RuntimeState(
        task_id="test-task",
        domain="os",
        instruction="Set the clipboard text to hello.",
    )
    monkeypatch.setattr(
        completion_recovery,
        "strict_completion_phase",
        lambda *_args, **_kwargs: STRICT_COMPLETION_DONE,
    )

    tools = completion_recovery.strict_proactive_completion_tools(
        state,
        {"passed": True, "missing": []},
        lambda _domain, _instruction: ["clipboard.set"],
        (),
        action_is_read_only,
        lambda _state: ["clipboard.set"],
    )

    assert tools is None


def test_rejected_completion_claim_keeps_normal_work_tools_available() -> None:
    state = RuntimeState(
        task_id="test-task",
        domain="os",
        instruction="Set the clipboard text to hello.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-28T00:00:00Z",
                proposed={"kind": "completion", "tool": "propose_done"},
                error={
                    "status": "rejected",
                    "recovery": {
                        "mode": "claim_only",
                        "guidance": "Retry or continue from truthful state.",
                    },
                },
            )
        ],
    )

    names = {tool["function"]["name"] for tool in make_agent().tools(state)}

    assert "tools_search" in names
    assert names != {"propose_done", "fail_task"}


def test_no_progress_stall_grants_exactly_one_model_replan() -> None:
    state = RuntimeState(
        task_id="test-task",
        domain="os",
        instruction="Organize the visible files.",
    )
    stall = {"type": "stalled_no_progress", "reason": "repeated_action_search_cycle"}

    assert request_stall_replan(state, stall) is True
    assert state.runner_replans_requested == 1
    assert state.pending_runner_replan == {
        "type": "no_progress_replan",
        "reason": "repeated_action_search_cycle",
    }
    assert "materially different model-selected action" in make_agent()._system_message(
        state
    )

    state.pending_runner_replan = None
    assert request_stall_replan(state, stall) is False
