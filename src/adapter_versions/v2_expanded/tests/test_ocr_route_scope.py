"""OCR must not turn unrelated workflows into spreadsheet imports."""
from types import SimpleNamespace

import pytest

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools


def make_state(instruction, routes, *, reader="image.extract_text_batch", read_ok=True):
    state = RuntimeState(
        task_id="synthetic-ocr-followup", domain="multi_apps",
        instruction=instruction, expanded_actions=["adapter.call"],
    )
    state.events = [
        ExecutionEvent(
            step=1, timestamp_utc="2026-10-23T00:00:00Z", executed=read_ok,
            proposed={"kind": "adapter", "action": "adapter.call", "arguments": {
                "adapter": "os", "action": reader,
                "payload": {"params": {"input_pattern": "*.png", "cwd_source": "explicit",
                                       "cwd_path": "/tmp/example"}},
            }},
            result={"context_hint": {"downstream_adapter": "os", "downstream_action": reader,
                                     "verification_passed": read_ok,
                                     "downstream_context": {"files": []}}},
            error=None if read_ok else {"code": "OCR_FAILED"},
        ),
        ExecutionEvent(
            step=2, timestamp_utc="2026-10-23T00:00:01Z", executed=True,
            proposed={"kind": "catalog", "tool": "tools_search",
                      "arguments": {"query": "available next operation"}},
            result={"matches": [{"action": "adapter.call", "adapter": adapter,
                                 "downstream_action": action} for adapter, action in routes]},
        ),
    ]
    return state


def surface(state):
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
        SimpleNamespace(), model_client=SimpleNamespace(client=object()),
    )
    tools = build_tools("multi_apps", ["adapter.call"], include_gui=False, strict_generic=True)
    return agent._apply_common_tool_constraints(tools, state)


def selected_route(tools):
    tool = next(item["function"] for item in tools
                if item["function"]["name"] == "adapter__adapter_call")
    return tool["parameters"].get("x-route")


@pytest.mark.parametrize("reader", ["image.extract_text_batch", "pdf.extract_text_batch"])
@pytest.mark.parametrize("route", [
    ("os", "filesystem.copy"), ("os", "archive.create_zip"),
    ("libreoffice_writer", "document.append_paragraphs"),
])
def test_nonspreadsheet_ocr_preserves_discovered_route(reader, route):
    state = make_state("Read the source and prepare a separate output file.", [route], reader=reader)
    assert selected_route(surface(state)) == {"adapter": route[0], "action": route[1]}


def test_spreadsheet_import_still_requires_observed_workbook():
    state = make_state("Import receipts from the folder into the spreadsheet.", [
        ("libreoffice_calc", "workbook.inspect"), ("libreoffice_calc", "range.write"),
    ])
    assert selected_route(surface(state)) == {
        "adapter": "libreoffice_calc", "action": "workbook.inspect",
    }


def test_filtered_empty_routes_offer_search_without_unrestricted_call():
    state = make_state("Import receipts from the folder into the spreadsheet.", [
        ("os", "archive.create_zip"),
    ])
    names = {tool["function"]["name"] for tool in surface(state)}
    assert "adapter__adapter_call" not in names
    assert "tools_search" in names


def test_failed_ocr_does_not_mark_content_read():
    route = ("os", "image.extract_text_batch")
    state = make_state("Import receipts from the folder into the spreadsheet.", [route], read_ok=False)
    assert selected_route(surface(state)) == {"adapter": route[0], "action": route[1]}
