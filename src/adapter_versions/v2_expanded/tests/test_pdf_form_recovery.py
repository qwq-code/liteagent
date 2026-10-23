from __future__ import annotations

import json

import pytest

from integrations.lite_agent.adapter_results import adapter_context_hint
from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.episode_control import mark_tool_result_for_audit
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


@pytest.mark.parametrize("forwarded", [False, True])
@pytest.mark.parametrize("recovery", ["protocol", "execution"])
def test_form_recovery_keeps_source_records_and_exact_target_fields(
    forwarded: bool, recovery: str
) -> None:
    fields = [
        {
            "field_name": f"panel_{index // 16}.choice_{index:03d}",
            "label": f"Option {index} in the current document",
            "field_type": "/Sig" if index == 119 else "/Tx",
            "writable": index % 17 != 0 and index != 119,
            "value": "Existing text" if index == 2 else None,
            **({"max_length": 32} if index == 3 else {}),
        }
        for index in range(120)
    ]
    rows = [[f"Column {column}" for column in range(24)]] + [
        [f"r{row}c{column} value" for column in range(24)]
        for row in range(8)
    ]
    observations = [
        ("os", "filesystem.find", {"matches": [{"path": "/tmp/source.xlsx"}]}),
        (
            "libreoffice_calc",
            "workbook.read_file",
            {
                "path": "/tmp/source.xlsx",
                "sheet_count": 1,
                "sheets": [
                    {
                        "name": "Records",
                        "returned_range": "A1:X9",
                        "returned_rows": 9,
                        "returned_columns": 24,
                        "display_text": rows,
                        "truncated": False,
                    }
                ],
                "truncated": False,
            },
        ),
        ("os", "filesystem.find", {"matches": [{"path": "/tmp/form.pdf"}]}),
        (
            "os",
            "pdf.form.inspect",
            {
                "input_path": "/tmp/form.pdf",
                "page_count": 2,
                "total_fields": len(fields),
                "field_offset": 0,
                "next_offset": None,
                "truncated": False,
                "fields": fields,
            },
        ),
    ]
    state = RuntimeState(
        task_id="synthetic-pdf-recovery",
        domain="multi_apps" if forwarded else "os",
        instruction="Copy the records into separately named forms using their actual fields.",
    )
    for step, (owner, action, result) in enumerate(observations, 1):
        body = {"status": "ok", "result": result}
        if forwarded:
            body = {
                "status": "ok",
                "result": {"adapter": owner, "action": action, "response": body},
            }
        hint = adapter_context_hint(
            "multi_apps" if forwarded else owner,
            "adapter.call" if forwarded else action,
            body,
        )
        if action == "workbook.read_file":
            source = hint["downstream_context"] if forwarded else hint
            assert source["sheets"][0]["display_text"] == rows
        event = ExecutionEvent(
            step=step,
            timestamp_utc="2026-09-12T00:00:00Z",
            proposed={
                "kind": "adapter",
                "action": "adapter.call" if forwarded else action,
                "arguments": {},
            },
            executed=True,
            result={"context_hint": hint},
        )
        state.events.append(event)
        mark_tool_result_for_audit(state, event)
    messages = AgentProtocolMixin()._messages(
        state,
        b"synthetic-screenshot",
        protocol_recovery=recovery == "protocol",
        execution_recovery=recovery == "execution",
    )
    summary = json.loads(messages[2]["content"][0]["text"].split("\n")[1])

    def observed(step: int) -> dict:
        entry = next(item for item in summary if item.get("step") == step)
        hint = entry["result"]["context_hint"]
        return hint["downstream_context"] if forwarded else hint

    form = observed(4)
    assert [field["field_name"] for field in form["fields"]] == [
        field["field_name"] for field in fields
    ]
    for actual, original in zip(form["fields"], fields, strict=True):
        assert actual["label"] == original["label"]
        assert actual.get("field_type", "/Tx") == original["field_type"]
        assert actual.get("writable", True) == original["writable"]
        assert actual.get("value") == original["value"]
        assert actual.get("max_length") == original.get("max_length")
    assert observed(2)["sheets"][0]["display_text"] == rows
    assert not form.get("context_truncated", False)
