from copy import deepcopy

import pytest

from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.completion_recovery import _multi_apps_completion_tools
from integrations.lite_agent.generic_completion import STRICT_COMPLETION_PERSIST_AND_READBACK
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


def event(step, domain, action, params=None, result=None, executed=True):
    return ExecutionEvent(
        step=step, timestamp_utc="2026-10-01T00:00:00Z", executed=executed,
        proposed={"kind": "adapter", "action": "adapter.call", "arguments": {
            "adapter": domain, "action": action, "payload": {"params": params or {}},
        }},
        result=result if result is not None else {"status": "ok", "verification": {"passed": True}},
    )


@pytest.mark.parametrize("action,params,instruction", [
    ("audio.insert", {"slide": 0, "path": "/tmp/recording.wav"},
     "Insert the extracted audio in the current presentation and keep the result."),
    ("slide.set_notes", {"slide": 0, "text": "Observed source notes"},
     "Put these speaking notes in the current presentation."),
    ("shape.insert_image", {"slide": 0, "path": "/tmp/photo.png"},
     "Insert the selected image in the current presentation."),
])
def test_verified_live_office_edit_still_requires_persistence_and_readback(action, params, instruction):
    domain = "libreoffice_impress"
    state = RuntimeState(task_id="synthetic-cross-app-persistence", domain="multi_apps",
                         instruction=instruction, events=[event(1, domain, action, params)])
    original = deepcopy(state.events)
    gate = CompletionMixin._generic_completion_gate(state)
    assert not gate["passed"]
    assert any("save" in s for s in gate["missing"])
    assert any("read-back" in s for s in gate["missing"])
    assert state.events == original

    # An unrelated read or another application's save is not this document's evidence.
    state.events.extend([
        event(2, "os", "filesystem.find"),
        event(3, "libreoffice_calc", "workbook.save"),
        event(4, "libreoffice_calc", "workbook.inspect"),
    ])
    gate = CompletionMixin._generic_completion_gate(state)
    assert not gate["passed"]
    assert any("save" in s for s in gate["missing"])
    assert any("read-back" in s for s in gate["missing"])

    state.events.append(event(5, domain, "presentation.save"))
    assert CompletionMixin._generic_completion_gate(state) == {
        "passed": False, "missing": ["perform structural read-back after the final mutation"],
    }
    state.events.append(event(6, domain, "presentation.inspect", executed=False))
    assert not CompletionMixin._generic_completion_gate(state)["passed"]
    state.events.append(event(7, domain, "presentation.inspect"))
    assert CompletionMixin._generic_completion_gate(state) == {"passed": True, "missing": []}


def test_later_archive_does_not_hide_unsaved_presentation():
    state = RuntimeState(task_id="synthetic-presentation-archive", domain="multi_apps",
                         instruction="Insert audio in the presentation, then archive the output.", events=[
                             event(1, "libreoffice_impress", "audio.insert", {"slide": 0, "path": "/tmp/a.wav"}),
                             event(2, "os", "archive.create_zip", {"output_path": "/tmp/output.zip"}),
                         ])
    gate = CompletionMixin._generic_completion_gate(state)
    assert not gate["passed"]
    assert any("save the LibreOffice presentation" in s for s in gate["missing"])
    state.events.append(event(3, "libreoffice_impress", "presentation.save", executed=False))
    assert not CompletionMixin._generic_completion_gate(state)["passed"]
    tools = _multi_apps_completion_tools(state, STRICT_COMPLETION_PERSIST_AND_READBACK)
    assert "tools_search" in {t["function"]["name"] for t in tools}
    assert "adapter__adapter_call" not in {t["function"]["name"] for t in tools}
    state.events.append(ExecutionEvent(
        step=4, timestamp_utc="2026-10-01T00:00:00Z", executed=True,
        proposed={"kind": "catalog", "action": "tools_search", "arguments": {"query": "save presentation"}},
        result={"status": "ok", "matches": [
            {"action": "adapter.call", "adapter": "libreoffice_impress", "downstream_action": "presentation.save"},
            {"action": "adapter.call", "adapter": "libreoffice_impress", "downstream_action": "presentation.inspect"},
            {"action": "adapter.call", "adapter": "os", "downstream_action": "filesystem.find"},
        ]},
    ))
    tools = _multi_apps_completion_tools(state, STRICT_COMPLETION_PERSIST_AND_READBACK)
    schema = next(t for t in tools if t["function"]["name"] == "adapter__adapter_call")["function"]["parameters"]
    routes = {(s["properties"]["adapter"]["enum"][0], s["properties"]["action"]["enum"][0])
              for s in schema["oneOf"]}
    assert routes == {("libreoffice_impress", "presentation.save"),
                      ("libreoffice_impress", "presentation.inspect")}


def test_independent_saved_file_export_does_not_need_an_editor_save():
    params = {"source_path": "/tmp/input.odt", "output_path": "/tmp/output.pdf"}
    result = {"status": "ok", "verification": {"passed": True}, "result": {
        "source_path": params["source_path"], "output_path": params["output_path"],
        "output_bytes": 200, "output_sha256": "a" * 64,
    }}
    state = RuntimeState(task_id="synthetic-export-output", domain="multi_apps",
                         instruction="Export the saved input document to PDF.", events=[
                             event(1, "libreoffice_writer", "document.export_file_pdf", params, result),
                         ])
    assert CompletionMixin._generic_completion_gate(state) == {"passed": True, "missing": []}
