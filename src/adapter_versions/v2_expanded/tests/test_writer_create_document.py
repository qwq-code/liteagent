from types import SimpleNamespace

import jsonschema
import pytest

from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools, search_actions
from writer_adapter import uno_worker
from writer_adapter.errors import AdapterError
from writer_adapter.schema import parse_action_request, validate_action_params


ACTION = "document.create"
DOMAIN = "libreoffice_writer"


@pytest.mark.parametrize("forwarded", [False, True])
def test_create_contract_accepts_only_new_document_path(forwarded):
    if forwarded:
        tools = constrain_adapter_call_routes(
            build_tools("multi_apps", ["adapter.call"], include_gui=False,
                        include_control_tools=False, strict_generic=True), [(DOMAIN, ACTION)])
        schema = tools[0]["function"]["parameters"]["properties"]["payload"]["properties"]["params"]
    else:
        schema = build_tools(DOMAIN, [ACTION], include_gui=False,
                             include_control_tools=False, strict_generic=True)[0]["function"]["parameters"]
    for path in ("/tmp/new.docx", "/tmp/new.odt", "~/Desktop/new.docx", "file:///tmp/new.odt"):
        jsonschema.validate({"path": path}, schema)
        parse_action_request({"action": ACTION, "params": {"path": path}})
    for params in ({}, {"path": "relative.docx"}, {"path": "/tmp/wrong.pdf"},
                   {"path": "/tmp/new.docx", "text": "hidden compound mutation"},
                   {"path": "/tmp/new.docx", "overwrite": True}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(params, schema)
        with pytest.raises(AdapterError):
            validate_action_params(ACTION, params)


@pytest.mark.parametrize("query", ["libreoffice_writer document.create", "create a new blank Writer document"])
def test_create_is_discoverable(query):
    hits = search_actions("multi_apps", query, strict_generic=True, limit=5)
    assert any(hit.get("adapter") == DOMAIN and hit.get("downstream_action") == ACTION for hit in hits)


@pytest.mark.parametrize("kind", ["file", "directory", "dangling_symlink"])
def test_create_never_overwrites_existing_destination(tmp_path, kind):
    path = tmp_path / "existing.docx"
    if kind == "file":
        path.write_bytes(b"KEEP EXISTING CONTENT")
    elif kind == "directory":
        path.mkdir()
    else:
        path.symlink_to(tmp_path / "missing.docx")
    session = SimpleNamespace(desktop=SimpleNamespace(
        loadComponentFromURL=lambda *args: pytest.fail("must reject before creating a document")))
    with pytest.raises(AdapterError, match="already exists"):
        uno_worker._create_blank_document(session, {"path": str(path)})
    if kind == "file":
        assert path.read_bytes() == b"KEEP EXISTING CONTENT"


def test_create_can_start_without_open_writer_and_honors_verification(monkeypatch):
    session = SimpleNamespace()
    calls = []
    def connect(selector, *, allow_no_document=False):
        calls.append((selector, allow_no_document))
        return session
    monkeypatch.setattr(uno_worker, "WriterSession", connect)
    monkeypatch.setattr(uno_worker, "_create_blank_document", lambda s, p: {"path": p["path"]})
    monkeypatch.setattr(uno_worker, "_verify_requested", lambda s, checks: {"passed": False, "checks": checks})
    checks = [{"type": "paragraphs", "expected": ["not blank"]}]
    result = uno_worker.execute({"action": ACTION, "params": {"path": "/tmp/new.docx"}, "verify": checks})
    assert calls == [({}, True)]
    assert result["verification"] == {"passed": False, "checks": checks}


@pytest.mark.parametrize("missing", ["blank", "activates_document", "valid"])
def test_creation_requires_blank_active_valid_document(missing):
    result = {"created": True, "blank": True, "activates_document": True, "exists": True, "valid": True}
    result[missing] = False
    verification = uno_worker._implicit_action_verification(ACTION, SimpleNamespace(), result)
    assert verification["passed"] is False
