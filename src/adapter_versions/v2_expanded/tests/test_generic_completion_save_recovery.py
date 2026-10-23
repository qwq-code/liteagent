from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from jsonschema import validate

from integrations.lite_agent import completion_recovery
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.completion_policy import action_is_read_only
from integrations.lite_agent.completion_recovery import (
    strict_proactive_completion_tools,
)
from integrations.lite_agent.instruction_semantics import (
    strict_instruction_required_actions,
)
from integrations.lite_agent.semantic_requirements import (
    strict_semantic_action_equivalents,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import FORBIDDEN_DATASET_ACTIONS
from integrations.lite_agent.generic_completion import (
    STRICT_COMPLETION_PERSIST,
    STRICT_COMPLETION_PERSIST_AND_READBACK,
    STRICT_COMPLETION_READBACK,
)


def _event(
    step: int,
    proposed: dict[str, Any],
    *,
    executed: bool = True,
    result: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> ExecutionEvent:
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-09-02T00:00:00Z",
        proposed=proposed,
        executed=executed,
        result=result,
        error=error,
    )


def _adapter_call_event(
    step: int,
    adapter: str,
    action: str,
    params: dict[str, Any],
    *,
    result: dict[str, Any] | None = None,
) -> ExecutionEvent:
    return _event(
        step,
        {
            "kind": "adapter",
            "tool": "adapter__adapter_call",
            "action": "adapter.call",
            "arguments": {
                "adapter": adapter,
                "action": action,
                "payload": {"params": params},
            },
        },
        result=result or {"status": "ok"},
    )


def _catalog_event(step: int, routes: list[tuple[str, str]]) -> ExecutionEvent:
    return _event(
        step,
        {
            "kind": "catalog",
            "tool": "tools_search",
            "action": "tools_search",
            "arguments": {"query": "save and inspect the current document"},
        },
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


def _rejected_completion(step: int) -> ExecutionEvent:
    return _event(
        step,
        {
            "kind": "completion",
            "tool": "propose_done",
            "action": "propose_done",
            "arguments": {},
        },
        executed=False,
        error={"status": "rejected", "missing": ["persist and read back"]},
    )


def _calc_write(step: int = 1) -> ExecutionEvent:
    return _adapter_call_event(
        step,
        "libreoffice_calc",
        "range.write",
        {"sheet": "Sheet1", "range": "D5", "values": [["Lecture"]]},
    )


def _state(events: list[ExecutionEvent]) -> RuntimeState:
    return RuntimeState(
        task_id="synthetic-generic-recovery",
        domain="multi_apps",
        instruction="Update the current workbook and keep the change.",
        completion_rejections=1,
        events=events,
    )


def _strict_proactive(state: RuntimeState) -> list[dict[str, Any]] | None:
    return strict_proactive_completion_tools(
        state,
        CompletionMixin._generic_completion_gate(state),
        strict_instruction_required_actions,
        FORBIDDEN_DATASET_ACTIONS,
        action_is_read_only,
        lambda _state: ["adapter.call"],
        strict_semantic_action_equivalents,
    )


def _tool_names(tools: list[dict[str, Any]] | None) -> set[str]:
    return {tool["function"]["name"] for tool in tools or []}


def _advertised_routes(tools: list[dict[str, Any]] | None) -> set[tuple[str, str]]:
    adapter_call = next(
        tool
        for tool in tools or []
        if tool["function"]["name"] == "adapter__adapter_call"
    )
    parameters = adapter_call["function"]["parameters"]
    if "x-route" in parameters:
        route = parameters["x-route"]
        return {(route["adapter"], route["action"])}
    alternatives = parameters["oneOf"]
    return {
        (
            alternative["properties"]["adapter"]["enum"][0],
            alternative["properties"]["action"]["enum"][0],
        )
        for alternative in alternatives
    }


@pytest.mark.parametrize(
    "domain,save,inspect",
    [
        ("libreoffice_impress", "presentation.save", "presentation.inspect"),
        ("libreoffice_writer", "document.save", "document.inspect"),
    ],
)
def test_persistence_recovery_keeps_owning_inspection_when_only_save_is_selected(
    domain, save, inspect
):
    tools = completion_recovery.build_tools(
        domain, [save], include_gui=False, strict_generic=True
    )
    recovered = completion_recovery.proactive_completion_tools(
        domain, STRICT_COMPLETION_PERSIST, tools, is_read_only_action=action_is_read_only
    )

    assert "adapter__" + inspect.replace(".", "_") in _tool_names(recovered)
    assert "adapter__" + save.replace(".", "_") in _tool_names(recovered)


@pytest.mark.parametrize("forwarded", [False, True])
def test_calc_save_recovery_keeps_in_place_and_save_as_without_expert_filter(forwarded):
    if forwarded:
        tools = _strict_proactive(
            _state([
                _calc_write(),
                _catalog_event(2, [("libreoffice_calc", "workbook.save")]),
                _rejected_completion(3),
            ])
        )
        function = next(
            tool["function"] for tool in tools
            if tool["function"]["name"] == "adapter__adapter_call"
        )
        route_schema = function["parameters"]
        assert route_schema["x-route"] == {
            "adapter": "libreoffice_calc", "action": "workbook.save"
        }
        parameters = route_schema["properties"]["payload"]["properties"]["params"]
    else:
        function = completion_recovery.build_tools(
            "libreoffice_calc", ["workbook.save"],
            include_gui=False, strict_generic=True,
        )[0]["function"]
        parameters = function["parameters"]

    assert set(parameters["properties"]) == {"url"}
    for arguments in ({}, {"url": "file:///tmp/budget.ods"}, {"url": "/tmp/revenue.xlsx"}):
        validate(arguments, parameters)
    # Building a strict or forwarded contract must not mutate the legacy API.
    legacy = completion_recovery.build_tools(
        "libreoffice_calc", ["workbook.save"],
        include_gui=False, strict_generic=False,
    )[0]["function"]
    assert "filter_name" in legacy["parameters"]["properties"]


def test_multi_apps_persistence_keeps_discovered_reads_without_new_routes():
    state = _state(
        [
            _calc_write(),
            _catalog_event(
                2,
                [
                    ("libreoffice_calc", "workbook.save"),
                    ("libreoffice_calc", "workbook.inspect"),
                    ("libreoffice_calc", "range.write"),
                    ("libreoffice_writer", "document.inspect"),
                ],
            ),
            _rejected_completion(3),
        ]
    )
    tools = completion_recovery._multi_apps_completion_tools(
        state, STRICT_COMPLETION_PERSIST
    )

    assert _advertised_routes(tools) == {
        ("libreoffice_calc", "workbook.save"),
        ("libreoffice_calc", "workbook.inspect"),
    }
    assert CompletionMixin._generic_completion_gate(state)["passed"] is False


def test_recovery_without_discovered_routes_does_not_invent_facade_actions() -> None:
    state = _state([_calc_write(), _rejected_completion(2)])

    names = _tool_names(_strict_proactive(state))

    assert names == {"tools_search", "fail_task"}
    assert not any(name.startswith("adapter__spreadsheet_") for name in names)


@pytest.mark.parametrize("captured", [False, True])
def test_source_output_recovery_keeps_discovered_route_across_adapter_owners(
    captured: bool,
) -> None:
    source_path, output_path = "/tmp/source.py", "/tmp/result.txt"
    state = _state(
        [
            _catalog_event(1, [
                ("vs_code", "file.read_text"),
                ("vs_code", "file.replace_literal"),
                ("os", "command.run"),
                ("os", "filesystem.find"),
                ("libreoffice_writer", "document.save"),
            ]),
            _adapter_call_event(2, "vs_code", "file.read_text", {"path": source_path},
                                result={"path": source_path, "verification": {"passed": True}}),
            _adapter_call_event(3, "vs_code", "file.replace_literal",
                                {"path": source_path, "old": "pass", "new": "print(1)"},
                                result={"path": source_path, "verification": {"passed": True}}),
        ]
    )
    state.instruction = "Complete source.py and save its output as result.txt."
    capture_params = {
        "argv": ["python3", source_path], "stdout_path": output_path,
        "cwd_source": "home", "provenance": "none",
    }
    if captured:
        state.events.append(_adapter_call_event(
            4, "os", "command.run", capture_params,
            result={"stdout_path": output_path, "verification": {"passed": True}},
        ))
    phase = STRICT_COMPLETION_READBACK if captured else STRICT_COMPLETION_PERSIST
    tools = completion_recovery._multi_apps_completion_tools(state, phase)
    required_route = ("vs_code", "file.read_text") if captured else ("os", "command.run")
    assert required_route in _advertised_routes(tools)
    assert ("vs_code", "file.replace_literal") not in _advertised_routes(tools)
    assert ("libreoffice_writer", "document.save") not in _advertised_routes(tools)
    call = {
        "adapter": required_route[0], "action": required_route[1],
        "payload": {"params": {"path": output_path} if captured else capture_params},
    }
    original = deepcopy(call)
    function = next(tool["function"] for tool in tools
                    if tool["function"]["name"] == "adapter__adapter_call")
    validate(call, function["parameters"])
    assert call == original

    state.events[0].result["matches"] = [
        match for match in state.events[0].result["matches"]
        if (match["adapter"], match["downstream_action"]) != required_route
    ]
    assert required_route not in _advertised_routes(
        completion_recovery._multi_apps_completion_tools(state, phase)
    )


def test_discovered_calc_routes_are_exposed_only_through_adapter_call() -> None:
    state = _state(
        [
            _calc_write(),
            _catalog_event(
                2,
                [
                    ("libreoffice_calc", "workbook.save"),
                    ("libreoffice_calc", "workbook.inspect"),
                    ("libreoffice_writer", "document.save"),
                ],
            ),
            _rejected_completion(3),
        ]
    )

    tools = _strict_proactive(state)

    assert _tool_names(tools) == {
        "adapter__adapter_call",
        "tools_search",
        "fail_task",
    }
    assert _advertised_routes(tools) == {
        ("libreoffice_calc", "workbook.save"),
        ("libreoffice_calc", "workbook.inspect"),
    }


def test_recovery_does_not_reuse_routes_from_another_owning_adapter() -> None:
    state = _state(
        [
            _adapter_call_event(
                1,
                "thunderbird",
                "messages.send",
                {"to": ["ana@example.com"], "subject": "Hello", "body": "Done"},
            ),
            _catalog_event(
                2,
                [
                    ("libreoffice_calc", "workbook.save"),
                    ("libreoffice_calc", "workbook.inspect"),
                ],
            ),
            _rejected_completion(3),
        ]
    )

    assert _tool_names(_strict_proactive(state)) == {"tools_search", "fail_task"}


def test_generic_recovery_waits_for_a_rejected_completion_claim() -> None:
    state = _state(
        [
            _calc_write(),
            _catalog_event(2, [("libreoffice_calc", "workbook.save")]),
        ]
    )

    assert _strict_proactive(state) is None


def test_rejected_completion_without_mutation_does_not_invent_work() -> None:
    state = _state([_rejected_completion(1)])

    assert _strict_proactive(state) is None


def test_generic_save_and_readback_clear_completion_requirements() -> None:
    inspect_result = {
        "status": "ok",
        "result": {"url": "file:///home/user/Desktop/current.xlsx"},
        "verification": {"passed": True},
    }
    state = _state(
        [
            _calc_write(),
            _adapter_call_event(
                2,
                "libreoffice_calc",
                "workbook.save",
                {},
                result={
                    "status": "ok",
                    "result": {
                        "url": "file:///home/user/Desktop/current.xlsx",
                        "size": 123,
                    },
                    "verification": {"passed": True},
                },
            ),
            _adapter_call_event(
                3,
                "libreoffice_calc",
                "workbook.inspect",
                {},
                result=inspect_result,
            ),
        ]
    )

    assert CompletionMixin._generic_completion_gate(state) == {
        "passed": True,
        "missing": [],
    }


@pytest.mark.parametrize("forwarded", [False, True])
def test_export_is_a_mutation_and_persists_its_output(forwarded) -> None:
    export = _adapter_call_event(
        1,
        "libreoffice_calc",
        "workbook.export",
        {"format": "csv", "url": "file:///tmp/observations.csv", "sheet": "Data"},
        result={
            "status": "ok",
            "result": {"path": "/tmp/observations.csv", "size": 37, "format": "csv"},
        },
    )
    readback = _adapter_call_event(
        2,
        "libreoffice_calc",
        "workbook.read_file",
        {"path": "/tmp/observations.csv"},
    )
    if not forwarded:
        for event in (export, readback):
            route = event.proposed["arguments"]
            event.proposed = {
                "kind": "adapter",
                "action": route["action"],
                "arguments": route["payload"]["params"],
            }
        # Match the direct Adapter's actual response. Office completion still
        # requires a later structural read, even when verification passed.
        export.result["verification"] = {"passed": True, "checks": []}
    state = RuntimeState(
        task_id="synthetic-export-evidence",
        domain="multi_apps" if forwarded else "libreoffice_calc",
        instruction="Export the current sheet to CSV.",
        events=[export],
    )
    original_proposal = deepcopy(export.proposed)
    assert CompletionMixin._generic_completion_gate(state) == {
        "passed": False,
        "missing": ["perform structural read-back after the final mutation"],
    }
    state.events.append(readback)
    assert CompletionMixin._generic_completion_gate(state) == {
        "passed": True,
        "missing": [],
    }
    assert export.proposed == original_proposal

    export.executed = False
    assert not CompletionMixin._generic_completion_gate(state)["passed"]


def test_in_place_save_does_not_substitute_for_a_document_change() -> None:
    state = _state(
        [
            _adapter_call_event(1, "libreoffice_calc", "workbook.save", {}),
            _adapter_call_event(2, "libreoffice_calc", "workbook.inspect", {}),
        ]
    )
    assert not CompletionMixin._generic_completion_gate(state)["passed"]


@pytest.mark.parametrize(
    "phase",
    [
        STRICT_COMPLETION_PERSIST,
        STRICT_COMPLETION_PERSIST_AND_READBACK,
        STRICT_COMPLETION_READBACK,
    ],
)
def test_structural_phase_does_not_hide_corrections_before_model_claim(
    monkeypatch, phase
) -> None:
    state = RuntimeState(
        task_id="synthetic-format-scope",
        domain="libreoffice_impress",
        instruction="Change the font size of one line in the active presentation.",
        events=[
            _event(
                1,
                {
                    "kind": "adapter",
                    "action": "shape.format_text",
                    "arguments": {"slide": 4, "selector": {"index": 2}, "font_size": 20},
                },
                result={"status": "ok", "verification": {"passed": True}},
            )
        ],
    )
    monkeypatch.setattr(
        completion_recovery, "strict_completion_phase", lambda *_args, **_kwargs: phase
    )

    tools = strict_proactive_completion_tools(
        state,
        {"passed": False, "missing": ["save and read back"]},
        strict_instruction_required_actions,
        FORBIDDEN_DATASET_ACTIONS,
        action_is_read_only,
        lambda _state: ["shape.format_text", "presentation.inspect", "presentation.save"],
    )

    assert tools is None
    assert CompletionMixin._generic_completion_gate(state)["passed"] is False


def test_new_mutation_reopens_work_after_an_older_rejected_claim() -> None:
    state = _state(
        [
            _calc_write(),
            _catalog_event(2, [("libreoffice_calc", "workbook.save")]),
            _rejected_completion(3),
            _calc_write(4),
        ]
    )

    assert _strict_proactive(state) is None


@pytest.mark.parametrize("action", ["workbook.inspect", "workbook.save"])
def test_read_and_save_keep_explicit_rejected_claim_recovery(action) -> None:
    state = _state(
        [
            _calc_write(),
            _catalog_event(
                2,
                [
                    ("libreoffice_calc", "workbook.save"),
                    ("libreoffice_calc", "workbook.inspect"),
                ],
            ),
            _rejected_completion(3),
            _adapter_call_event(4, "libreoffice_calc", action, {}),
        ]
    )

    assert _strict_proactive(state) is not None


@pytest.mark.parametrize("domain", ["libreoffice_impress", "multi_apps"])
def test_recovery_tool_usage_explains_current_missing_state(monkeypatch, domain):
    state = _state(
        [
            _calc_write(),
            _catalog_event(2, [("libreoffice_calc", "workbook.inspect")]),
            _rejected_completion(3),
            _adapter_call_event(4, "libreoffice_calc", "workbook.inspect", {}),
        ]
    )
    state.domain = domain
    current_missing = "read-back is incomplete: inspect the full requested scope"
    gate = {"passed": False, "missing": [current_missing]}
    original_gate, original_events = deepcopy(gate), deepcopy(state.events)
    monkeypatch.setattr(
        completion_recovery, "strict_completion_phase",
        lambda *_args, **_kwargs: STRICT_COMPLETION_READBACK,
    )

    for _ in range(2):
        tools = strict_proactive_completion_tools(
            state, gate, strict_instruction_required_actions,
            FORBIDDEN_DATASET_ACTIONS, action_is_read_only,
            lambda _state: ["presentation.inspect"],
        )
        expected = (
            "adapter__adapter_call" if domain == "multi_apps"
            else "adapter__presentation_inspect"
        )
        usage = next(t["function"]["description"] for t in tools if t["function"]["name"] == expected)
        assert usage.count(current_missing) == 1
        assert "persist and read back" not in usage
        assert "propose_done" not in _tool_names(tools)
    assert gate == original_gate
    assert state.events == original_events
