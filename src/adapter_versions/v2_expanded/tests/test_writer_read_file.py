from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import jsonschema
import pytest

from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_context_hint_for_model,
    context_hint_for_model,
)
from integrations.lite_agent.completion_policy import action_is_read_only
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools, search_actions
from writer_adapter import uno_worker
from writer_adapter.errors import AdapterError
from writer_adapter.schema import validate_action_params


ACTION = "document.read_file"
DOMAIN = "libreoffice_writer"


@pytest.mark.parametrize("forwarded", [False, True])
def test_saved_file_read_and_pdf_export_explain_active_document(forwarded):
    descriptions = {}
    for action in (ACTION, "document.export_pdf"):
        if forwarded:
            tools = constrain_adapter_call_routes(
                build_tools(
                    "multi_apps", ["adapter.call"], include_gui=False,
                    include_control_tools=False, strict_generic=True,
                ),
                [(DOMAIN, action)],
            )
            schema = tools[0]["function"]["parameters"]["properties"]["payload"]["properties"]["params"]
            descriptions[action] = schema.get("description", "")
        else:
            tool = build_tools(
                DOMAIN, [action], include_gui=False,
                include_control_tools=False, strict_generic=True,
            )[0]
            descriptions[action] = tool["function"]["description"]

    assert "does not change the active Writer document" in descriptions[ACTION]
    export = descriptions["document.export_pdf"]
    assert "currently open Writer document" in export
    assert "output destination, not a source file" in export
    assert "document.read_file does not activate" in export


def test_pdf_export_destination_rejects_source_document_path():
    tools = build_tools(
        DOMAIN, ["document.export_pdf"], include_gui=False,
        include_control_tools=False, strict_generic=True,
    )
    params = tools[0]["function"]["parameters"]
    path_schema = params["properties"]["path"]
    assert params["required"] == ["path"]
    assert "same_basename" not in params["properties"]
    assert "source .docx path" in path_schema["description"]
    jsonschema.validate("/home/user/essay.pdf", path_schema)
    for invalid in ("/home/user/essay.docx", ".pdf"):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, path_schema)

    validate_action_params("document.export_pdf", {"path": "/home/user/essay.pdf"})
    validate_action_params("document.export_pdf", {"same_basename": True})
    with pytest.raises(AdapterError, match="params.path must be a PDF destination"):
        validate_action_params("document.export_pdf", {"path": "/home/user/essay.docx"})


class Enumeration:
    def __init__(self, values):
        self.values = iter(values)
        self.next_value = next(self.values, None)

    def hasMoreElements(self):
        return self.next_value is not None

    def nextElement(self):
        value = self.next_value
        self.next_value = next(self.values, None)
        return value


def text(*elements):
    return SimpleNamespace(createEnumeration=lambda: Enumeration(elements))


def paragraph(value):
    return SimpleNamespace(
        String=value,
        supportsService=lambda name: name == "com.sun.star.text.Paragraph",
    )


@pytest.fixture
def native_reader(tmp_path, monkeypatch):
    source = tmp_path / "meeting notes.docx"
    source.write_bytes(b"synthetic persisted document")
    cells = {
        "B2": "second\nline", "A2": "2", "B1": "Value", "A1": "Key",
    }
    table = SimpleNamespace(
        supportsService=lambda name: name == "com.sun.star.text.TextTable",
        getCellNames=lambda: list(cells),
        getCellByName=lambda name: SimpleNamespace(
            Text=text(*(paragraph(line) for line in cells[name].split("\n")))
        ),
    )
    closed = []
    doc = SimpleNamespace(
        Text=text(paragraph("Caf\u00e9 notes"), table, paragraph("End.")),
        supportsService=lambda name: name == "com.sun.star.text.TextDocument",
        close=lambda own: closed.append(own),
    )
    loads = []

    def load(url, frame, flags, properties):
        loads.append((url, frame, flags, dict(properties)))
        return doc

    session = SimpleNamespace(desktop=SimpleNamespace(loadComponentFromURL=load))
    monkeypatch.setattr(uno_worker, "_file_url", lambda value: source.as_uri())
    monkeypatch.setattr(uno_worker, "_property", lambda key, value: (key, value))
    monkeypatch.setattr(
        uno_worker, "_uno_modules",
        lambda: (SimpleNamespace(getConstantByName=lambda name: name), None),
    )
    return source, session, doc, loads, closed


def test_native_read_keeps_body_and_table_order_without_writing(native_reader):
    source, session, _doc, loads, closed = native_reader
    before = source.read_bytes()
    arguments = {"path": str(source)}
    original = deepcopy(arguments)

    result = uno_worker._read_file(session, arguments)

    assert result["text"] == "Caf\u00e9 notes\nKey\tValue\n2\tsecond\nline\nEnd."
    assert result["read_mode"] == "saved_file_snapshot"
    assert result["activates_document"] is False
    assert result["source_total_chars"] == len(result["text"])
    assert result["next_start_char"] is None
    assert result["source_truncated"] is False
    assert loads[0][3] == {
        "Hidden": True, "ReadOnly": True, "AsTemplate": True,
        "MacroExecutionMode": "com.sun.star.document.MacroExecMode.NEVER_EXECUTE",
        "UpdateDocMode": "com.sun.star.document.UpdateDocMode.NO_UPDATE",
    }
    assert closed == [True]
    assert source.read_bytes() == before
    assert arguments == original


def test_pages_reconstruct_the_same_native_text(native_reader):
    source, session, _doc, _loads, closed = native_reader
    full = uno_worker._read_file(session, {"path": str(source)})["text"]
    cursor = 0
    chunks = []
    while cursor is not None:
        result = uno_worker._read_file(
            session, {"path": str(source), "start_char": cursor, "max_chars": 7}
        )
        assert result["source_start_char"] == cursor
        assert result["source_end_char"] == cursor + len(result["text"])
        assert result["text"] == full[cursor:cursor + 7]
        chunks.append(result["text"])
        cursor = result["next_start_char"]
    assert "".join(chunks) == full
    assert len(closed) == len(chunks) + 1


def test_worker_read_needs_no_active_document_and_does_not_save(native_reader, monkeypatch):
    source, session, _doc, _loads, _closed = native_reader
    calls = []

    def connect(selector, *, allow_no_document=False):
        calls.append((selector, allow_no_document))
        return session

    monkeypatch.setattr(uno_worker, "WriterSession", connect)
    result = uno_worker.execute({"action": ACTION, "params": {"path": str(source)}})

    assert calls == [({}, True)]
    assert result["verification"]["passed"] is True
    assert result["result"]["text"].startswith("Caf\u00e9 notes")
    assert "saved" not in result["result"]
    assert action_is_read_only(ACTION)


def test_end_of_file_is_empty_but_beyond_eof_is_a_normal_error(native_reader):
    source, session, _doc, _loads, closed = native_reader
    total = uno_worker._read_file(session, {"path": str(source)})["source_total_chars"]
    result = uno_worker._read_file(session, {"path": str(source), "start_char": total})
    assert result["text"] == ""
    assert result["source_start_char"] == result["source_end_char"] == total
    assert result["next_start_char"] is None
    with pytest.raises(AdapterError, match="start_char exceeds"):
        uno_worker._read_file(session, {"path": str(source), "start_char": total + 1})
    assert len(closed) == 3


def test_non_writer_input_closes_only_loaded_copy(native_reader):
    source, session, doc, _loads, closed = native_reader
    doc.supportsService = lambda name: False

    with pytest.raises(AdapterError) as raised:
        uno_worker._read_file(session, {"path": str(source)})

    assert raised.value.code == "DOCUMENT_OPEN_FAILED"
    assert closed == [True]


def test_native_read_error_still_closes_copy(native_reader):
    source, session, doc, _loads, closed = native_reader
    doc.Text = None

    with pytest.raises(AdapterError) as raised:
        uno_worker._read_file(session, {"path": str(source)})

    assert raised.value.code == "DOCUMENT_READ_FAILED"
    assert closed == [True]


@pytest.mark.parametrize("forwarded", [False, True])
def test_public_reader_schema_and_path_are_preserved(forwarded):
    direct = build_tools(
        DOMAIN, [ACTION], include_gui=False, include_control_tools=False,
        strict_generic=True,
    )[0]["function"]["parameters"]
    if forwarded:
        tools = constrain_adapter_call_routes(
            build_tools("multi_apps", ["adapter.call"], include_gui=False, strict_generic=True),
            [(DOMAIN, ACTION)],
        )
        function = next(t["function"] for t in tools if t["function"]["name"] == "adapter__adapter_call")
        schema = function["parameters"]["properties"]["payload"]["properties"]["params"]
        assert schema["properties"] == direct["properties"]
    else:
        schema = direct
    arguments = {"path": "/tmp/briefing.odt", "start_char": 12, "max_chars": 40}
    original = deepcopy(arguments)
    jsonschema.validate(arguments, schema)
    validate_action_params(ACTION, arguments)
    assert arguments == original
    assert schema["required"] == ["path"]


@pytest.mark.parametrize("arguments", [
    {}, {"path": "relative.docx"}, {"path": "/tmp/a.docx", "start_char": -1},
    {"path": "/tmp/a.docx", "max_chars": 12001},
])
def test_invalid_reader_arguments_return_normal_errors(arguments):
    with pytest.raises(AdapterError):
        validate_action_params(ACTION, arguments)


@pytest.mark.parametrize("query", [
    "read docx file content", "read text from an ODT document", "extract Word file body text",
])
def test_document_text_search_finds_native_reader(query):
    matches = search_actions("multi_apps", query, 5, strict_generic=True)
    routes = [(match["adapter"], match["downstream_action"]) for match in matches]
    assert (DOMAIN, ACTION) in routes


@pytest.mark.parametrize("forwarded", [False, True])
def test_model_projection_keeps_text_and_continuation_cursor(forwarded):
    result = {
        "path": "/tmp/briefing.docx", "status": "ok", "text": "Page text " * 180,
        "source_kind": "writer_body_text", "source_start_char": 2000,
        "source_end_char": 3800, "source_total_chars": 5000,
        "returned_chars": 1800, "source_truncated": True,
        "next_start_char": 3800, "offset_basis": "writer_body_text",
    }
    body = {"status": "ok", "result": result, "verification": {"passed": True}}
    hint = adapter_context_hint(DOMAIN, ACTION, body)
    domain, action = DOMAIN, ACTION
    if forwarded:
        hint = {"downstream_context": hint, "adapter": DOMAIN, "action": ACTION}
        domain, action = "multi_apps", "adapter.call"
    projected = context_hint_for_model(domain, action, hint, strict_generic=True)
    projected = compact_context_hint_for_model(projected, remaining_chars=4200)
    projected = projected.get("downstream_context", projected)
    observed = projected["files"][0]
    assert projected["reader_action"] == ACTION
    guidance = projected["guidance"]
    for field in (ACTION, "path", "start_char", "max_chars", "end_char", "next_start_char"):
        assert field in guidance
    for field in ("input_pattern", "cwd", "max_chars_per_file"):
        assert field not in guidance
    assert "writer_body_text" in guidance
    assert observed["handle"]["path"] == result["path"]
    assert observed["next_start_char"] == 3800
    for chunk in observed["chunks"]:
        assert chunk["text"] == result["text"][chunk["start_char"] - 2000:chunk["end_char"] - 2000]
