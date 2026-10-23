from types import SimpleNamespace

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


INSTRUCTION = (
    "Update my bookkeeping spreadsheet with the recent expenses "
    "from the provided folder."
)


def _agent():
    return LiteAgent(
        LiteAgentConfig(base_url="http://unused.invalid/v1"),
        adapter_executor=object(),
        model_client=SimpleNamespace(client=object()),
    )


def _find_event(paths):
    return ExecutionEvent(
        step=2,
        timestamp_utc="2026-10-21T00:00:00Z",
        proposed={
            "kind": "adapter", "action": "adapter.call",
            "arguments": {"adapter": "os", "action": "filesystem.find", "payload": {
                "params": {"roots": ["~/Desktop"], "name_patterns": ["*"]}
            }},
        },
        executed=True,
        result={"context_hint": {
            "downstream_action": "filesystem.find",
            "downstream_context": {"matches": [
                {"path": path, "kind": "file"} for path in paths
            ], "match_count": len(paths)},
        }},
    )


def _catalog_event():
    return ExecutionEvent(
        step=3,
        timestamp_utc="2026-10-21T00:00:01Z",
        proposed={"kind": "catalog", "action": "tools_search", "arguments": {
            "query": "files and OCR"
        }},
        executed=True,
        result={"matches": [
            {"action": "adapter.call", "adapter": "os", "downstream_action": action}
            for action in ("filesystem.find", "image.extract_text_batch")
        ]},
    )


def test_directory_table_reader_waits_for_actual_ocr_source():
    state = RuntimeState(task_id="bookkeeping", domain="multi_apps", instruction=INSTRUCTION)
    state.events.append(_find_event([
        "/home/user/requirement.txt",
    ]))
    assert _agent()._directory_table_reader_pending(state)
    assert _agent()._directory_table_ocr_roots(state) == []
    state.events.append(_catalog_event())
    tools = _agent().tools(state)
    assert [tool["function"]["name"] for tool in tools if tool["function"]["name"].startswith("adapter__")] == ["adapter__adapter_call"]
    assert "source image or PDF" in tools[0]["function"]["description"]

    state.events.append(_find_event(["/home/user/Desktop/bookkeeping.xlsx"]))
    state.events.append(_catalog_event())
    tools = _agent().tools(state)
    call = next(tool for tool in tools if tool["function"]["name"] == "adapter__adapter_call")
    params = call["function"]["parameters"]["properties"]["payload"]["properties"]["params"]
    assert params["properties"]["cwd_path"]["enum"] == ["/home/user/Desktop"]
    assert params["properties"]["input_pattern"]["enum"] == ["*"]

    state.events.append(_find_event([
        "/home/user/Desktop/receipt_0.jpeg",
        "/home/user/Desktop/receipt_1.jpg",
        "/home/user/Desktop/receipt_2.pdf",
    ]))
    assert _agent()._directory_table_ocr_roots(state) == ["/home/user/Desktop"]
    state.events.append(_catalog_event())
    tools = _agent().tools(state)
    call = next(tool for tool in tools if tool["function"]["name"] == "adapter__adapter_call")
    params = call["function"]["parameters"]["properties"]["payload"]["properties"]["params"]
    assert params["properties"]["cwd_path"]["enum"] == ["/home/user/Desktop"]
    assert params["properties"]["input_pattern"]["enum"] == ["*"]


def test_directory_table_write_exposes_row_items_after_read():
    state = RuntimeState(task_id="bookkeeping", domain="multi_apps", instruction=INSTRUCTION)
    state.events.append(_find_event(["/home/user/Desktop/bookkeeping.xlsx"]))
    for step, adapter, action in (
        (3, "os", "image.extract_text_batch"),
        (4, "libreoffice_calc", "workbook.inspect"),
        (5, "libreoffice_calc", "range.read"),
    ):
        state.events.append(ExecutionEvent(
            step=step,
            timestamp_utc="2026-10-21T00:00:01Z",
            proposed={"kind": "adapter", "action": "adapter.call", "arguments": {
                "adapter": adapter, "action": action, "payload": {"params": {}}
            }},
            executed=True,
            result={"status": "ok", "verification": {"passed": True}},
        ))
    state.events.append(ExecutionEvent(
        step=6,
        timestamp_utc="2026-10-21T00:00:02Z",
        proposed={"kind": "catalog", "action": "tools_search", "arguments": {
            "query": "range.write"
        }},
        executed=True,
        result={"matches": [{
            "action": "adapter.call", "adapter": "libreoffice_calc",
            "downstream_action": "range.write",
        }]},
    ))
    tools = _agent().tools(state)
    call = next(tool for tool in tools if tool["function"]["name"] == "adapter__adapter_call")
    params = call["function"]["parameters"]["properties"]["payload"]["properties"]["params"]
    assert params["properties"]["values"]["items"]["type"] == "array"
