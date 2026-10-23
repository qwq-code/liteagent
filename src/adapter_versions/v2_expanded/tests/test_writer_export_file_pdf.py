from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlparse

import jsonschema
import pytest

from integrations.lite_agent.adapter_results import (
    adapter_context_hint, compact_context_hint_for_model, context_hint_for_model,
)
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools, search_actions
from writer_adapter import uno_worker
from writer_adapter.errors import AdapterError
from writer_adapter.schema import validate_action_params


ACTION = "document.export_file_pdf"
DOMAIN = "libreoffice_writer"


@pytest.fixture
def exporter(tmp_path, monkeypatch):
    source = tmp_path / "saved input.odt"
    source.write_bytes(b"SAVED SOURCE BODY")
    output = tmp_path / "export" / "chosen.pdf"
    active = SimpleNamespace(text="OTHER OPEN DOCUMENT", modified=True, closed=False)
    loaded = []
    closed = []

    def local_path(url):
        return Path(unquote(urlparse(url).path))

    def load(url, frame, flags, properties):
        loaded.append((url, frame, flags, dict(properties)))
        assert local_path(url) == source
        assert frame == "_blank"
        doc = SimpleNamespace(
            URL="", supportsService=lambda name: name == "com.sun.star.text.TextDocument",
            close=lambda own: closed.append(own),
        )

        def export(url, properties):
            assert dict(properties)["FilterName"] == "writer_pdf_Export"
            local_path(url).write_bytes(b"%PDF-1.7\n" + source.read_bytes())

        doc.storeToURL = export
        return doc

    session = SimpleNamespace(desktop=SimpleNamespace(loadComponentFromURL=load), doc=active)
    monkeypatch.setattr(uno_worker, "_file_url", lambda value: Path(value).as_uri())
    monkeypatch.setattr(uno_worker, "_url_path", local_path)
    monkeypatch.setattr(uno_worker, "_property", lambda key, value: (key, value))
    monkeypatch.setattr(uno_worker, "_uno_modules", lambda: (
        SimpleNamespace(getConstantByName=lambda name: name), None,
    ))
    return source, output, active, session, loaded, closed


@pytest.mark.parametrize("forwarded", [False, True])
def test_source_and_output_required_in_direct_and_forwarded_schema(forwarded):
    if forwarded:
        tools = constrain_adapter_call_routes(
            build_tools("multi_apps", ["adapter.call"], include_gui=False,
                        include_control_tools=False, strict_generic=True), [(DOMAIN, ACTION)],
        )
        schema = tools[0]["function"]["parameters"]["properties"]["payload"]["properties"]["params"]
    else:
        schema = build_tools(DOMAIN, [ACTION], include_gui=False,
                             include_control_tools=False, strict_generic=True)[0]["function"]["parameters"]
    params = {"source_path": "/tmp/input.odt", "output_path": "/tmp/output.pdf"}
    jsonschema.validate(params, schema)
    validate_action_params(ACTION, params)
    for invalid in ({"output_path": "/tmp/output.pdf"},
                    {"source_path": "/tmp/input.odt"},
                    {**params, "output_path": "/tmp/wrong.docx"},
                    {**params, "source_path": "guessed-relative.odt"},
                    {**params, "path": "/tmp/unrelated.pdf"},
                    {**params, "preserve_soft_wrap_spaces": "false"}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)
        with pytest.raises(AdapterError):
            validate_action_params(ACTION, invalid)


def test_export_saved_source_preserves_other_open_document_and_input(exporter, monkeypatch):
    source, output, active, session, loaded, closed = exporter
    calls = []

    def connect(selector, *, allow_no_document=False):
        calls.append((selector, allow_no_document))
        return session

    monkeypatch.setattr(uno_worker, "WriterSession", connect)
    arguments = {"source_path": str(source), "output_path": str(output),
                 "preserve_soft_wrap_spaces": False}
    original = deepcopy(arguments)
    result = uno_worker.execute({"action": ACTION, "params": arguments})
    assert calls == [({}, True)]
    assert output.read_bytes() == b"%PDF-1.7\nSAVED SOURCE BODY"
    assert source.read_bytes() == b"SAVED SOURCE BODY"
    assert active.text == "OTHER OPEN DOCUMENT" and active.modified and not active.closed
    assert arguments == original
    assert closed == [True]
    assert loaded[0][3] == {
        "Hidden": True, "ReadOnly": True, "AsTemplate": True,
        "MacroExecutionMode": "com.sun.star.document.MacroExecMode.NEVER_EXECUTE",
        "UpdateDocMode": "com.sun.star.document.UpdateDocMode.NO_UPDATE",
    }
    assert result["verification"]["passed"] is True
    assert result["result"]["source_path"] == str(source)
    assert result["result"]["source_url"] == source.as_uri()
    assert result["result"]["export_mode"] == "saved_file_snapshot"
    assert result["result"]["activates_document"] is False
    assert result["result"]["path"] == str(output)
    assert "saved" not in result["result"]


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_source_alias_cannot_be_overwritten(exporter, alias):
    source, output, _active, session, loaded, closed = exporter
    pdf_source = source.with_suffix(".pdf")
    source.rename(pdf_source)
    if alias == "same":
        output = pdf_source
    else:
        output.parent.mkdir()
        if alias == "symlink":
            output.symlink_to(pdf_source)
        else:
            output.hardlink_to(pdf_source)
    with pytest.raises(AdapterError, match="must not overwrite"):
        uno_worker._export_file_pdf(session, {"source_path": str(pdf_source), "output_path": str(output)})
    assert pdf_source.read_bytes() == b"SAVED SOURCE BODY"
    assert not loaded and not closed


@pytest.mark.parametrize("problem", ["not_writer", "store_failed", "invalid_pdf"])
def test_failed_export_closes_private_copy_only(exporter, problem):
    source, output, active, session, _loaded, closed = exporter
    original_load = session.desktop.loadComponentFromURL

    def load(*args):
        doc = original_load(*args)
        if problem == "not_writer":
            doc.supportsService = lambda name: False
        elif problem == "store_failed":
            def fail(*args):
                raise RuntimeError("disk error")
            doc.storeToURL = fail
        else:
            doc.storeToURL = lambda *args: output.write_bytes(b"wrong format")
        return doc

    session.desktop.loadComponentFromURL = load
    with pytest.raises(AdapterError) as error:
        uno_worker._export_file_pdf(session, {"source_path": str(source), "output_path": str(output),
                                             "preserve_soft_wrap_spaces": False})
    assert error.value.code == {"not_writer": "DOCUMENT_OPEN_FAILED", "store_failed": "EXPORT_FAILED",
                                "invalid_pdf": "VERIFICATION_FAILED"}[problem]
    assert closed == [True] and not active.closed
    assert source.read_bytes() == b"SAVED SOURCE BODY"


def test_pdf_discovery_does_not_treat_any_open_as_source_selection():
    expected = {("libreoffice_writer", ACTION), ("libreoffice_writer", "document.export_pdf")}
    for completed in ([], [("os", "desktop.open_path")]):
        matches = search_actions("multi_apps", "export document to PDF", limit=6,
                                 strict_generic=True, completed_routes=completed)
        assert {(m["adapter"], m["downstream_action"]) for m in matches} == expected
        assert matches[0]["downstream_action"] == ACTION


@pytest.mark.parametrize("forwarded", [False, True])
def test_result_context_retains_source_and_output(exporter, forwarded):
    source, output, _active, session, _loaded, _closed = exporter
    result = uno_worker._export_file_pdf(session, {"source_path": str(source), "output_path": str(output),
                                                  "preserve_soft_wrap_spaces": False})
    hint = adapter_context_hint(DOMAIN, ACTION, {"status": "ok", "result": result,
                                               "verification": {"passed": True}})
    assert hint["source_path"] == str(source)
    assert hint["path"] == str(output)
    domain, action = DOMAIN, ACTION
    if forwarded:
        hint = {"downstream_context": hint, "adapter": DOMAIN, "action": ACTION}
        domain, action = "multi_apps", "adapter.call"
    projected = compact_context_hint_for_model(
        context_hint_for_model(domain, action, hint, strict_generic=True), remaining_chars=2000,
    )
    projected = projected.get("downstream_context", projected)
    assert projected["source_path"] == str(source)
    assert projected["path"] == str(output)
    assert projected["activates_document"] is False


@pytest.mark.parametrize("domain", [DOMAIN, "multi_apps"])
def test_export_completion_does_not_request_saving_the_unrelated_open_document(exporter, domain):
    source, output, _active, session, _loaded, _closed = exporter
    params = {"source_path": str(source), "output_path": str(output),
              "preserve_soft_wrap_spaces": False}
    result = uno_worker._export_file_pdf(session, params)
    body = {"status": "ok", "result": result, "verification": {"passed": True}}
    proposed = {"kind": "adapter", "action": ACTION, "arguments": params}
    if domain == "multi_apps":
        proposed.update(action="adapter.call", arguments={
            "adapter": DOMAIN, "action": ACTION, "payload": {"params": params},
        })
    state = RuntimeState(task_id="synthetic-saved-export", domain=domain,
                         instruction=f'Export the saved document "{source}" as "{output}".',
                         events=[ExecutionEvent(step=1, timestamp_utc="2026-10-01T00:00:00Z",
                                                proposed=proposed, executed=True, result=body)])
    before = deepcopy(state.events)
    gate = CompletionMixin._generic_completion_gate(state)
    if domain == "multi_apps":
        assert gate == {"passed": True, "missing": []}
    else:
        # Direct Office episodes retain their existing explicit read-back rule.
        # Persisting this output must not cause a save of the unrelated editor.
        assert gate == {"passed": False, "missing": [
            "perform structural read-back after the final mutation",
        ]}
    assert state.events == before
    state.events[0].executed = False
    assert not CompletionMixin._generic_completion_gate(state)["passed"]
