from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.clipboard_path_semantics import (
    argument_contract_errors,
    completion_errors,
    observed_find_paths,
    pending_actions,
    required_actions,
    requests_found_path_to_clipboard,
)
from integrations.lite_agent.instruction_semantics import (
    strict_instruction_required_actions,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools


INSTRUCTION = (
    'I remember there is a file named "report-sample.docx" on this computer. '
    "Find the path where it is stored and copy it to the clipboard."
)
PATH = "/home/user/Documents/archive/report-sample.docx"
OTHER_PATH = "/home/user/Documents/archive/other.docx"


def _event(
    step: int,
    action: str,
    arguments: dict[str, Any],
    body: dict[str, Any],
    *,
    wrapper: str | None = None,
) -> ExecutionEvent:
    if wrapper == "nested":
        proposed = {
            "kind": "adapter",
            "action": "adapter.call",
            "arguments": {
                "adapter": "os",
                "action": action,
                "payload": {"params": copy.deepcopy(arguments)},
            },
        }
    elif wrapper == "flattened":
        proposed = {
            "kind": "adapter",
            "action": "adapter.call",
            "downstream_adapter": "os",
            "downstream_action": action,
            "arguments": copy.deepcopy(arguments),
        }
    else:
        proposed = {
            "kind": "adapter",
            "action": action,
            "arguments": copy.deepcopy(arguments),
        }
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-09-01T00:00:00Z",
        proposed=proposed,
        executed=True,
        result={
            "status": "ok",
            "result": body,
            "verification": {"passed": True},
        },
    )


def _find_event(
    *,
    paths: tuple[str, ...] = (PATH,),
    wrapper: str | None = None,
) -> ExecutionEvent:
    return _event(
        1,
        "filesystem.find",
        {
            "roots": ["~/"],
            "name_patterns": ["report-sample.docx"],
            "kind": "file",
            "recursive": True,
        },
        {
            "match_count": len(paths),
            "returned_count": len(paths),
            "truncated": False,
            "matches": [
                {"path": path, "name": path.rsplit("/", 1)[-1], "kind": "file"}
                for path in paths
            ],
        },
        wrapper=wrapper,
    )


def _clipboard_event(
    step: int, text: str, *, wrapper: str | None = None
) -> ExecutionEvent:
    return _event(
        step,
        "clipboard.set",
        {"text": text},
        {"text": text, "verified": True},
        wrapper=wrapper,
    )


def _catalog_event(*routes: tuple[str, str]) -> ExecutionEvent:
    return ExecutionEvent(
        step=0,
        timestamp_utc="2026-09-01T00:00:00Z",
        proposed={
            "kind": "catalog",
            "tool": "tools_search",
            "action": "tools_search",
            "arguments": {"query": "find a file path and set the clipboard"},
        },
        executed=True,
        result={
            "status": "ok",
            "matches": [
                {
                    "action": "adapter.call",
                    "adapter": adapter,
                    "downstream_action": action,
                }
                for adapter, action in routes
            ],
        },
    )


def _state(
    events: list[ExecutionEvent], *, instruction: str = INSTRUCTION
) -> RuntimeState:
    return RuntimeState(
        task_id="synthetic-clipboard-path",
        domain="multi_apps",
        instruction=instruction,
        events=events,
    )


@pytest.mark.parametrize(
    "instruction",
    [
        INSTRUCTION,
        "Locate memo.odt and place its full file path in the clipboard.",
        "Search for slides.pptx, then put the location where it is stored on the clip board.",
    ],
)
def test_path_clipboard_intent_accepts_generic_paraphrases(instruction: str) -> None:
    assert requests_found_path_to_clipboard(instruction) is True


@pytest.mark.parametrize(
    "instruction",
    [
        "Set the clipboard text to hello world.",
        "Find memo.odt and copy its contents to the clipboard.",
        "Find the path to memo.odt and copy the file contents to the clipboard.",
        "Find the full file path to memo.odt, then open it and copy its contents to the clipboard.",
        "Find the location of memo.odt and copy the text from it to the clipboard.",
        "Find the path to memo.odt but copy only the document title to the clipboard.",
        "Find the path to memo.odt and copy the document itself to the clipboard.",
        "Find the path to memo.odt and copy its filename to the clipboard.",
        "Copy /home/user/Documents/memo.odt to the clipboard.",
        "Find the path to memo.odt and print it in the terminal.",
    ],
)
def test_non_path_clipboard_intents_do_not_activate(instruction: str) -> None:
    assert requests_found_path_to_clipboard(instruction) is False
    state = _state([_find_event()], instruction=instruction)
    assert argument_contract_errors(state, "clipboard.set", {"text": "any text"}) == []
    assert completion_errors(state) == []


def test_unrelated_path_clause_does_not_turn_content_copy_into_path_copy() -> None:
    instruction = (
        "Find memo.odt and copy its contents to the clipboard. "
        "Also report where the backup is stored."
    )

    assert requests_found_path_to_clipboard(instruction) is False


def test_path_intent_provides_downstream_hints_without_direct_facades() -> None:
    assert required_actions("multi_apps", INSTRUCTION) == [
        "filesystem.find",
        "clipboard.set",
    ]
    assert strict_instruction_required_actions("multi_apps", INSTRUCTION) == []


@pytest.mark.parametrize(
    "domain",
    [
        "libreoffice_writer",
        "libreoffice_calc",
        "libreoffice_impress",
        "vlc",
        "thunderbird",
        "chrome",
    ],
)
def test_path_clipboard_workflow_does_not_capture_other_domains(domain: str) -> None:
    state = RuntimeState(
        task_id="synthetic-other-domain",
        domain=domain,
        instruction=INSTRUCTION,
    )

    assert required_actions(domain, INSTRUCTION) == []
    assert pending_actions(state) is None
    assert "adapter__filesystem_find" not in _tool_names(state)


def test_any_model_observed_path_is_allowed_but_unobserved_text_is_not() -> None:
    state = _state([_find_event(paths=(PATH, OTHER_PATH))])

    assert observed_find_paths(state) == {PATH, OTHER_PATH}
    assert argument_contract_errors(state, "clipboard.set", {"text": PATH}) == []
    assert argument_contract_errors(state, "clipboard.set", {"text": OTHER_PATH}) == []
    assert argument_contract_errors(
        state, "clipboard.set", {"text": "/home/user/unobserved.docx"}
    )


def test_model_must_select_an_exact_observed_path_without_argument_rewrite() -> None:
    state = _state([_find_event()])
    arguments = {"text": "Report text, not a path."}
    original = copy.deepcopy(arguments)

    errors = argument_contract_errors(state, "clipboard.set", arguments)

    assert errors and "exact file path returned" in errors[0]
    assert arguments == original


def test_nested_adapter_call_uses_the_same_argument_contract() -> None:
    state = _state([_find_event(wrapper="nested")])
    arguments = {
        "adapter": "os",
        "action": "clipboard.set",
        "payload": {"params": {"text": PATH}},
    }

    assert argument_contract_errors(state, "adapter.call", arguments) == []
    arguments["payload"]["params"]["text"] = "document contents"
    assert argument_contract_errors(state, "adapter.call", arguments)


@pytest.mark.parametrize("wrapper", [None, "nested", "flattened"])
def test_completion_uses_the_last_verified_clipboard_state(
    wrapper: str | None,
) -> None:
    correct = _state(
        [_find_event(wrapper=wrapper), _clipboard_event(2, PATH, wrapper=wrapper)]
    )
    overwritten = _state(
        [
            _find_event(wrapper=wrapper),
            _clipboard_event(2, PATH, wrapper=wrapper),
            _clipboard_event(3, "document contents", wrapper=wrapper),
        ]
    )

    assert completion_errors(correct) == []
    errors = completion_errors(overwritten)
    assert errors and "last verified clipboard.set" in errors[0]


def test_clipboard_path_must_be_observed_before_it_is_written() -> None:
    state = _state([_clipboard_event(1, PATH), _find_event()])

    errors = completion_errors(state)

    assert errors and "prior verified filesystem.find" in errors[0]


class _NoAdapterExecutor:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("invalid clipboard payload reached the Adapter")


def test_execution_boundary_rejects_unobserved_clipboard_text() -> None:
    state = _state(
        [
            _catalog_event(("os", "clipboard.set")),
            _find_event(wrapper="nested"),
            _clipboard_event(2, PATH, wrapper="nested"),
        ]
    )
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        _NoAdapterExecutor(),  # type: ignore[arg-type]
    )
    visible_tools = build_tools(
        "multi_apps",
        ["adapter.call"],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )
    arguments = {
        "adapter": "os",
        "action": "clipboard.set",
        "payload": {"params": {"text": "document contents"}},
    }

    event = agent.execute_proposal(
        state,
        {
            "tool": "adapter__adapter_call",
            "arguments_raw": json.dumps(arguments),
            "_model_visible_tools": visible_tools,
        },
    )

    assert event.executed is False
    assert "exact file path returned" in event.error["detail"]
    assert event.proposed["arguments"] == arguments


class _HoloGateway:
    def __call__(self, *_args, **_kwargs):
        raise AssertionError("GUI execution is not expected")


def _tool_names(state: RuntimeState) -> set[str]:
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=True),
        _NoAdapterExecutor(),  # type: ignore[arg-type]
        holo_gui_gateway=_HoloGateway(),
    )
    return {tool["function"]["name"] for tool in agent.tools(state)}


def test_multi_apps_tool_surface_uses_search_then_adapter_call() -> None:
    initial = _state([])
    discovered = _state(
        [
            _catalog_event(
                ("os", "filesystem.find"),
                ("os", "clipboard.set"),
            )
        ]
    )

    assert _tool_names(initial) == {
        "tools_search",
        "gui_request",
        "propose_done",
        "fail_task",
    }
    assert _tool_names(discovered) == {
        "adapter__adapter_call",
        "tools_search",
        "gui_request",
        "propose_done",
        "fail_task",
    }


def test_terminal_audit_keeps_the_generic_multi_apps_surface_available() -> None:
    state = _state(
        [
            _catalog_event(("os", "clipboard.set")),
            _find_event(wrapper="nested"),
            _clipboard_event(2, PATH, wrapper="nested"),
        ]
    )
    state.pending_terminal = {
        "status": "done",
        "tool": "propose_done",
        "event_step": 3,
    }

    assert _tool_names(state) == {
        "adapter__adapter_call",
        "tools_search",
        "gui_request",
        "propose_done",
        "fail_task",
    }


def test_failed_find_returns_to_generic_recovery_surface() -> None:
    failed = _find_event()
    failed.executed = False
    failed.result = None
    failed.error = {"type": "PATH_NOT_FOUND", "detail": "no match"}

    assert pending_actions(_state([failed])) is None
