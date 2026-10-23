from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from calc_adapter import uno_worker
from calc_adapter.errors import AdapterError
from calc_adapter.service import create_app
from integrations.lite_agent.adapter_executor import AdapterExecutor
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools, search_actions


def routes(query):
    return [
        (item["adapter"], item["downstream_action"])
        for item in search_actions("multi_apps", query, limit=6, strict_generic=True)
    ]


@pytest.mark.parametrize("query", [
    "get current workbook path",
    "read the spreadsheet already open in Calc",
    "find active spreadsheet identity and worksheet ranges",
])
def test_active_workbook_inspection_is_retrievable_without_knowing_its_route(query):
    assert ("libreoffice_calc", "workbook.inspect") in routes(query)[:3]


@pytest.mark.parametrize("query, expected", [
    ("read local CSV file", ("libreoffice_calc", "workbook.read_file")),
    ("find invoice.xlsx file path", ("os", "filesystem.find")),
    ("find files in current vscode workspace", ("vs_code", "workspace.find_files")),
])
def test_active_workbook_keywords_preserve_explicit_file_and_editor_discovery(query, expected):
    assert expected in routes(query)[:3]


def test_discovered_active_workbook_contract_needs_no_guessed_path():
    tools = constrain_adapter_call_routes(
        build_tools(
            "multi_apps", ["adapter.call"], include_gui=False,
            include_control_tools=False, strict_generic=True,
        ),
        routes("get current workbook path"),
    )
    branches = tools[0]["function"]["parameters"]["oneOf"]
    branch = next(
        entry for entry in branches
        if entry["properties"]["adapter"]["enum"] == ["libreoffice_calc"]
        and entry["properties"]["action"]["enum"] == ["workbook.inspect"]
    )
    schema = branch["properties"]["payload"]["properties"]["params"]
    assert schema["properties"] == {}
    assert schema["required"] == []
    assert "currently open" in schema["description"]
    assert "No file path" in schema["description"]


@pytest.fixture
def native_path_urls(monkeypatch):
    monkeypatch.setattr(uno_worker, "_file_url", lambda value: Path(value).as_uri())


def test_missing_file_reports_live_open_workbooks_without_selecting_or_reading_one(tmp_path, native_path_urls):
    documents = [
        SimpleNamespace(URL=(tmp_path / "native report.xlsx").as_uri(), Title="Native report"),
        SimpleNamespace(URL="", Title="Untitled 2"),
    ]
    session = SimpleNamespace(
        _documents=lambda: documents,
        _identity=lambda doc: {"url": doc.URL, "title": doc.Title},
    )
    params = {"path": str(tmp_path / "missing.xlsx")}
    original = deepcopy(params)

    with pytest.raises(AdapterError) as failure:
        uno_worker._read_file(session, params)

    assert failure.value.code == "FILE_NOT_FOUND"
    assert failure.value.details["path"] == original["path"]
    assert failure.value.details["open_documents"] == [
        {"url": documents[0].URL, "title": "Native report"},
        {"url": "", "title": "Untitled 2"},
    ]
    assert "not confirmed substitutes" in failure.value.message
    assert params == original


def test_missing_file_keeps_original_error_when_native_document_listing_fails(tmp_path, native_path_urls):
    def unavailable():
        raise RuntimeError("native document enumeration unavailable")

    session = SimpleNamespace(_documents=unavailable)
    with pytest.raises(AdapterError) as failure:
        uno_worker._read_file(session, {"path": str(tmp_path / "absent.ods")})

    assert failure.value.code == "FILE_NOT_FOUND"
    assert "open_documents" not in failure.value.details
    assert "enumeration unavailable" in failure.value.details["open_documents_error"]


def test_live_open_workbook_identity_survives_http_and_model_error_projection(
    tmp_path, native_path_urls, monkeypatch
):
    observed = {"url": (tmp_path / "observed.xlsx").as_uri(), "title": "Observed workbook"}
    session = SimpleNamespace(_documents=lambda: [object()], _identity=lambda _doc: observed)
    client = create_app(
        lifecycle=SimpleNamespace(listener_ready=lambda: True),
        runner=SimpleNamespace(run=lambda request: uno_worker._read_file(session, request.params)),
    ).test_client()

    def post(_url, *, json, timeout):
        response = client.post("/v1/actions", json=json)
        return SimpleNamespace(ok=response.status_code == 200, status_code=response.status_code, json=response.get_json)

    monkeypatch.setattr("integrations.lite_agent.adapter_executor.requests.post", post)
    params = {"path": str(tmp_path / "guessed.xlsx")}
    response = AdapterExecutor({"libreoffice_calc": "http://synthetic"}).execute(
        "libreoffice_calc", "workbook.read_file", params, {}
    )
    assert response["executed"] is False and response["http_status"] == 404
    assert response["error"]["error"]["details"]["open_documents"] == [observed]
    state = RuntimeState(
        task_id="synthetic-open-workbook", domain="libreoffice_calc",
        instruction="Read the open workbook.",
        events=[ExecutionEvent(
            step=1, timestamp_utc="2026-09-09T00:00:00Z",
            proposed={"kind": "adapter", "action": "workbook.read_file", "arguments": params},
            executed=False, error=response["error"],
        )],
    )
    projected = state.context_summary()
    assert observed["url"] in str(projected)
    assert "FILE_NOT_FOUND" in str(projected)
