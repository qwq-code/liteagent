from __future__ import annotations

import pytest

from integrations.lite_agent.tool_catalog import (
    DIRECT_ACTION_SCHEMAS,
    build_tools,
    search_actions,
)
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from vscode_adapter.actions import VscodeActions
from vscode_adapter.errors import AdapterError
from vscode_adapter.verifier import verify_specs
from vscode_adapter.worker import _default_specs


def _result(matches: list[dict]) -> dict:
    return {
        "matches": matches,
        "workspace_name": "snake",
        "workspace_roots": ["/home/user/Desktop/snake"],
    }


def test_workspace_open_description_prefers_exact_nested_path() -> None:
    description = DIRECT_ACTION_SCHEMAS["vs_code"]["workspace.open"]["description"]

    assert "complete path directly" in description
    assert "parent directory first" in description


def test_workspace_find_files_has_read_only_shape_verification() -> None:
    result = _result([{"name": "main.py", "path": "/home/user/Desktop/snake/main.py"}])
    specs = _default_specs("workspace.find_files", {}, result)

    verification = verify_specs(specs, result)

    assert verification["passed"] is True
    assert verification["checks"][0]["type"] == "workspace_files"


def test_workspace_find_files_rejects_missing_match_list() -> None:
    result = {"workspace_name": "snake", "workspace_roots": []}
    specs = _default_specs("workspace.find_files", {}, result)

    verification = verify_specs(specs, result)

    assert verification["passed"] is False


def test_missing_source_path_explains_discovery_without_changing_the_path(
    tmp_path,
) -> None:
    path = str(tmp_path / "absent-project" / "processor.py")
    params = {"path": path}

    with pytest.raises(AdapterError) as caught:
        VscodeActions().file_read_text(params, 1.0)

    error = caught.value
    assert error.code == "PATH_NOT_FOUND"
    assert error.http_status == 404
    assert path in error.message
    assert "workspace.find_files" in error.message
    assert "name_patterns" in error.message
    assert "tools_search" in error.message
    assert params == {"path": path}
    assert not (tmp_path / "absent-project").exists()


def test_forwarded_read_schema_explains_live_path_discovery() -> None:
    tools = constrain_adapter_call_routes(
        build_tools(
            "multi_apps", ["adapter.call"], include_gui=False, strict_generic=True
        ),
        [("vs_code", "file.read_text")],
    )
    function = next(
        tool["function"]
        for tool in tools
        if tool["function"]["name"] == "adapter__adapter_call"
    )
    path_schema = function["parameters"]["properties"]["payload"][
        "properties"
    ]["params"]["properties"]["path"]

    assert "workspace.find_files" in path_schema["description"]
    assert "tools_search" in path_schema["description"]
    assert "enum" not in path_schema
    assert "default" not in path_schema


@pytest.mark.parametrize("domain", ["vs_code", "multi_apps"])
@pytest.mark.parametrize(
    "query",
    [
        "processor.py file in analytics project",
        "locate report.R in the current project",
        "find parser.js in the open code project",
        "project source files named renderer.ts",
        "files in the active workspace",
        "workspace.find_files",
    ],
)
def test_project_file_search_retrieves_existing_discovery_action(domain, query) -> None:
    first = search_actions(domain, query, limit=5, strict_generic=True)[0]

    assert first.get("adapter", domain) == "vs_code"
    assert first.get("downstream_action", first["action"]) == "workspace.find_files"


@pytest.mark.parametrize(
    ("query", "excluded_routes"),
    [
        ("file operations merge text into docx", ()),
        (
            "vs_code file read text adapter action",
            (("vs_code", "file.read_text"), ("os", "filesystem.find")),
        ),
    ],
)
def test_project_discovery_survives_compound_document_search(query, excluded_routes):
    matches = search_actions(
        "multi_apps",
        query,
        limit=5,
        instruction="Combine all .log files from the VS Code project into a Writer report.",
        excluded_routes=excluded_routes,
        strict_generic=True,
    )
    routes = [(match["adapter"], match["downstream_action"]) for match in matches]

    assert ("vs_code", "workspace.find_files") in routes
    assert not set(excluded_routes).intersection(routes)
    if excluded_routes:
        assert routes[0] == ("vs_code", "workspace.find_files")


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("libreoffice writer open new document", ("os", "terminal.launch")),
        (
            "libreoffice_writer document create new document adapter action",
            ("libreoffice_writer", "document.create"),
        ),
        ("open /tmp/draft.odt", ("os", "desktop.open_path")),
        ("document.save", ("libreoffice_writer", "document.save")),
    ],
)
@pytest.mark.parametrize("workspace_word", ["project", "workspace"])
def test_document_query_overrides_project_composition_context(
    query, expected, workspace_word
):
    matches = search_actions(
        "multi_apps",
        query,
        limit=5,
        instruction=f"Combine all .log files from the VS Code {workspace_word} into a Writer report.",
        strict_generic=True,
    )

    assert (matches[0]["adapter"], matches[0]["downstream_action"]) == expected


@pytest.mark.parametrize("domain", ["vs_code", "multi_apps"])
@pytest.mark.parametrize(
    "query",
    [
        "open processor.py file in editor",
        "open parser.js file in the editor",
        "source file in the editor",
    ],
)
def test_editor_file_search_includes_path_discovery(domain, query) -> None:
    matches = search_actions(domain, query, limit=5, strict_generic=True)

    assert any(
        match.get("adapter", domain) == "vs_code"
        and match.get("downstream_action", match["action"]) == "workspace.find_files"
        for match in matches
    )


@pytest.mark.parametrize("domain", ["vs_code", "multi_apps"])
@pytest.mark.parametrize(
    "query",
    ["editing source files", "modifying source files", "replacing source text"],
)
def test_file_edit_search_recognizes_common_word_forms(domain, query) -> None:
    matches = search_actions(domain, query, limit=6, strict_generic=True)

    assert any(
        match.get("adapter", domain) == "vs_code"
        and match.get("downstream_action", match["action"]) == "file.replace_literal"
        for match in matches
    )


def test_edit_file_command_search_keeps_source_read_available(domain="multi_apps") -> None:
    matches = search_actions(domain, "edit file command line", limit=6, strict_generic=True)

    assert any(
        match.get("adapter", domain) == "vs_code"
        and match.get("downstream_action", match["action"]) == "file.read_text"
        for match in matches
    )


@pytest.mark.parametrize(
    "query",
    ["command.run for editing files with sed", "command.run for modifying files"],
)
def test_command_edit_search_keeps_command_and_existing_literal_alternative(query) -> None:
    matches = search_actions("multi_apps", query, limit=6, strict_generic=True)
    routes = [(match["adapter"], match["downstream_action"]) for match in matches]

    assert routes[0] == ("os", "command.run")
    assert ("vs_code", "file.replace_literal") in routes


def test_execution_only_search_does_not_prefer_file_editing() -> None:
    matches = search_actions(
        "multi_apps", "command.run execute a program", limit=6, strict_generic=True
    )
    routes = [(match["adapter"], match["downstream_action"]) for match in matches]

    assert routes[0] == ("os", "command.run")
    assert ("vs_code", "file.replace_literal") not in routes


@pytest.mark.parametrize(
    ("domain", "query", "expected"),
    [
        ("vs_code", "read /tmp/report.txt", "file.read_text"),
        ("vs_code", "replace literal text in /tmp/report.txt", "file.replace_literal"),
        ("multi_apps", "replace literal text in /tmp/report.txt", "file.replace_literal"),
        (
            "multi_apps",
            "copy /tmp/report.txt to /tmp/archive/report.txt",
            "filesystem.copy_to_directories",
        ),
    ],
)
def test_explicit_file_operations_keep_search_precedence(domain, query, expected) -> None:
    first = search_actions(domain, query, limit=5, strict_generic=True)[0]

    assert first.get("downstream_action", first["action"]) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("find minutes docx file in /home/researcher", "filesystem.find"),
        ("locate a saved document in Downloads", "filesystem.find"),
        ("search files under a directory", "filesystem.find"),
        ("open minutes.docx file in LibreOffice Writer", "desktop.open_path"),
        ("open /tmp/draft.odt", "desktop.open_path"),
        ("open this image file", "desktop.open_path"),
    ],
)
def test_local_file_discovery_and_opening_retrieve_owning_actions(query, expected) -> None:
    first = search_actions("multi_apps", query, limit=6, strict_generic=True)[0]

    assert (first["adapter"], first["downstream_action"]) == ("os", expected)


@pytest.mark.parametrize(
    ("query", "expected_adapter", "expected_action"),
    [
        ("read body text from the saved document", "libreoffice_writer", "document.read_file"),
        ("export docx to pdf libreoffice writer", "libreoffice_writer", "document.export_file_pdf"),
        ("open processor.py file in editor", "vs_code", "editor.open_file"),
    ],
)
def test_local_file_discovery_preserves_distinct_operation_precedence(
    query, expected_adapter, expected_action
) -> None:
    first = search_actions("multi_apps", query, limit=6, strict_generic=True)[0]

    assert (first["adapter"], first["downstream_action"]) == (
        expected_adapter, expected_action
    )


def test_write_pdf_search_exposes_explicit_source_semantics() -> None:
    matches = search_actions(
        "multi_apps", "libreoffice_writer document.write_pdf",
        limit=6, strict_generic=True,
    )
    assert [(item["adapter"], item["downstream_action"]) for item in matches] == [
        ("libreoffice_writer", "document.export_file_pdf"),
        ("libreoffice_writer", "document.export_pdf"),
    ]

    matches = search_actions(
        "multi_apps", "libreoffice_writer document.write_pdf",
        limit=6, strict_generic=True,
        completed_routes=[("os", "desktop.open_path")],
    )
    assert [(item["adapter"], item["downstream_action"]) for item in matches] == [
        ("libreoffice_writer", "document.export_file_pdf"),
        ("libreoffice_writer", "document.export_pdf"),
    ]


def test_saved_document_search_exposes_one_stage_at_a_time() -> None:
    query = "read file docx desktop reminder"
    matches = search_actions("multi_apps", query, limit=6, strict_generic=True)
    assert [(item["adapter"], item["downstream_action"]) for item in matches] == [
        ("os", "filesystem.find")
    ]

    matches = search_actions(
        "multi_apps", query, limit=6, strict_generic=True,
        completed_routes=[("os", "filesystem.find")],
    )
    assert [(item["adapter"], item["downstream_action"]) for item in matches] == [
        ("libreoffice_writer", "document.read_file")
    ]


@pytest.mark.parametrize(
    ("route", "query"),
    [
        (
            ("libreoffice_writer", "document.read_file"),
            "libreoffice_writer.document.read_file",
        ),
        (("os", "filesystem.rename"), "os.filesystem.rename"),
    ],
)
def test_explicit_route_can_be_reused_for_another_file(route, query) -> None:
    matches = search_actions(
        "multi_apps", query, limit=6, strict_generic=True,
        completed_routes=[route],
    )

    assert [(item["adapter"], item["downstream_action"]) for item in matches] == [route]
