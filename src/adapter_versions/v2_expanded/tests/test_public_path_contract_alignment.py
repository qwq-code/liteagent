from __future__ import annotations

import json
import re

import jsonschema
import pytest

from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import (
    DIRECT_ACTION_SCHEMAS,
    _catalog_signature,
    build_tools,
)
from integrations.openapa_osworld.tool_catalog import action_signature
from os_adapter.schema import validate_action_params as validate_os
from os_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS as OS_SCHEMAS
from thunderbird_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as THUNDERBIRD_SCHEMAS,
)
from vscode_adapter.schema import validate_action_params as validate_vscode
from vscode_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as VSCODE_SCHEMAS,
)
from writer_adapter.schema import validate_action_params as validate_writer
from writer_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as WRITER_SCHEMAS,
)


@pytest.mark.parametrize(
    ("schema", "params"),
    [
        (OS_SCHEMAS["filesystem.find"], {"roots": ["Desktop"], "name_patterns": ["*.txt"]}),
        (OS_SCHEMAS["desktop.open_path"], {"path": "report.txt"}),
        (
            WRITER_SCHEMAS["document.extract_images"],
            {"source_path": "report.docx", "output_directory": "images"},
        ),
        (
            VSCODE_SCHEMAS["debug.breakpoint.set"],
            {"window_id": "0x1", "path": "main.py", "line": 1},
        ),
        (
            THUNDERBIRD_SCHEMAS["contacts.export_csv"],
            {"address_book": "Personal Address Book", "output_path": "contacts.csv"},
        ),
    ],
)
def test_public_schema_rejects_relative_paths_that_runtime_rejects(schema, params) -> None:
    assert not jsonschema.Draft202012Validator(schema).is_valid(params)


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize(
    ("domain", "action", "usage_text"),
    [
        ("libreoffice_writer", "table.read", "first character of the observed text"),
        ("libreoffice_writer", "table.set_cell_text_color", "red is #FF0000"),
        (
            "libreoffice_impress",
            "shape.export_image",
            "does not apply the shape's on-slide brightness or crop effects",
        ),
        ("libreoffice_impress", "shape.fit_to_slide", "observed content and geometry"),
        ("libreoffice_calc", "range.write", "cell part can reference text labels"),
        (
            "os",
            "filesystem.copy_to_directories",
            "~/ means home, not the current folder",
        ),
        ("os", "command.run", "set stdout_path alongside argv"),
        ("os", "desktop.set_setting", "gsettings list-relocatable-schemas"),
        (
            "vs_code",
            "file.replace_literal",
            "Surrounding and following lines stay unchanged",
        ),
        (
            "vs_code",
            "file.replace_literal",
            "a declaration alone does not include its body",
        ),
        ("os", "terminal.launch", "not the child exit status"),
        (
            "os",
            "terminal.show_output",
            "Tilde paths and environment variables are not expanded",
        ),
    ],
)
def test_repair_usage_is_visible_in_direct_and_forwarded_tools(
    wrapped, domain, action, usage_text
) -> None:
    if wrapped:
        tools = constrain_adapter_call_routes(
            build_tools(
                "multi_apps", ["adapter.call"], include_gui=False, strict_generic=True
            ),
            [(domain, action)],
        )
    else:
        tools = build_tools(domain, [action], include_gui=False, strict_generic=True)
    assert usage_text in json.dumps(tools)


@pytest.mark.parametrize("wrapped", [False, True])
def test_argument_placement_description_matches_the_tool_schema(wrapped) -> None:
    tools = build_tools(
        "multi_apps" if wrapped else "os",
        ["adapter.call"] if wrapped else ["command.run"],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )
    function = tools[0]["function"]
    description = function["description"]
    properties = function["parameters"]["properties"]

    if wrapped:
        assert "payload.params" in description
        assert "params" in properties["payload"]["properties"]
        assert "action params directly as top-level" not in description
    else:
        assert "action params directly as top-level" in description
        assert "argv" in properties
        assert "payload.params" not in description


@pytest.mark.parametrize("wrapped", [False, True])
def test_native_tool_description_keeps_usage_without_a_second_schema(wrapped) -> None:
    domain, action = "libreoffice_writer", "paragraph.set_format"
    owner = DIRECT_ACTION_SCHEMAS[domain][action]
    if wrapped:
        function = constrain_adapter_call_routes(
            build_tools("multi_apps", ["adapter.call"], include_gui=False),
            [(domain, action)],
        )[0]["function"]
        params = function["parameters"]["oneOf"][0]["properties"]["payload"][
            "properties"
        ]["params"]
        assert owner["description"] == params["description"]
    else:
        function = build_tools(domain, [action], include_gui=False)[0]["function"]
        params = function["parameters"]
        assert owner["description"] in function["description"]
    assert "properties=" not in function["description"]
    assert params["properties"] == owner["properties"]
    assert params["required"] == owner["required"]
    assert params["allOf"] == owner["allOf"]
    assert params["additionalProperties"] is False
    assert "nonempty body paragraphs" in json.dumps(params)
    assert "properties=" in _catalog_signature(domain, action)


def test_native_tool_description_preserves_strict_parameter_overlay() -> None:
    function = build_tools(
        "libreoffice_calc", ["chart.create"], include_gui=False, strict_generic=True
    )[0]["function"]
    params = function["parameters"]
    assert "properties=" not in function["description"]
    assert "source_sheet" in params["required"]
    assert params["properties"]["data_row_source"]["enum"] == ["auto"]
    assert "source-range geometry" in params["properties"]["data_row_source"]["description"]


def test_untyped_tool_keeps_the_only_textual_parameter_contract() -> None:
    domain, action = "chrome", "page.fill"
    assert action not in DIRECT_ACTION_SCHEMAS.get(domain, {})
    function = build_tools(domain, [action], include_gui=False)[0]["function"]
    assert action_signature(domain, action) in function["description"]
    assert "Pass action params inside the params object" in function["description"]
    assert "params" in function["parameters"]["properties"]


def test_restricted_route_description_explains_how_to_search_another_operation() -> None:
    tools = constrain_adapter_call_routes(
        build_tools("multi_apps", ["adapter.call"], include_gui=False, strict_generic=True),
        [("vs_code", "file.read_text")],
    )
    function = next(
        tool["function"] for tool in tools
        if tool["function"]["name"] == "adapter__adapter_call"
    )

    assert "call tools_search again" in function["description"]
    assert "do not substitute a different listed action" in function["description"]
    assert any(tool["function"]["name"] == "tools_search" for tool in tools)
    branches = function["parameters"]["oneOf"]
    assert len(branches) == 1
    assert branches[0]["properties"]["action"]["enum"] == ["file.read_text"]


def test_runtime_contracts_keep_the_same_absolute_path_rule() -> None:
    with pytest.raises(Exception, match="absolute"):
        validate_os("desktop.open_path", {"path": "report.txt"})
    with pytest.raises(Exception, match="absolute"):
        validate_writer(
            "document.extract_images",
            {"source_path": "report.docx", "output_directory": "images"},
        )
    with pytest.raises(Exception, match="absolute"):
        validate_vscode(
            "debug.breakpoint.set",
            {"window_id": "0x1", "path": "main.py", "line": 1},
        )


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize(
    ("domain", "action", "field", "paths"),
    [
        ("vs_code", "editor.open_file", "path", ["/srv/project/main.py", "~/project/main.py"]),
        ("vs_code", "debug.breakpoint.set", "path", ["/srv/project/debug.py"]),
        ("os", "filesystem.copy", "source", ["/srv/source/report.txt", "~/source/report.txt"]),
        ("os", "command.run", "cwd_path", ["/srv/project", "/srv/my project"]),
        ("os", "filesystem.find", "roots", ["/srv/project", "~/project", "~"]),
        ("os", "user.ensure_account", "home", ["/srv/users/example"]),
        ("thunderbird", "contacts.export_csv", "output_path", ["/srv/export/contacts.csv", "~/contacts.csv"]),
        ("vlc", "preferences.configure", "recording_directory", ["/srv/media/captures"]),
        ("libreoffice_calc", "workbook.export", "url", ["/srv/export/report.pdf", "file:///srv/export/report.pdf"]),
    ],
)
def test_public_path_pattern_accepts_complete_decoder_strings(
    wrapped, domain, action, field, paths
) -> None:
    if wrapped:
        tools = constrain_adapter_call_routes(
            build_tools(
                "multi_apps", ["adapter.call"], include_gui=False,
                include_control_tools=False, strict_generic=True,
            ),
            [(domain, action)],
        )
        schema = tools[0]["function"]["parameters"]["oneOf"][0]["properties"]["payload"][
            "properties"
        ]["params"]
    else:
        schema = build_tools(
            domain, [action], include_gui=False, include_control_tools=False,
            strict_generic=True,
        )[0]["function"]["parameters"]
    field_schema = schema["properties"][field]
    path_schema = field_schema.get("items", field_schema)
    validator = jsonschema.Draft202012Validator(path_schema)

    # xgrammar 0.2.4 compiles JSON Schema patterns as full-string matches.
    for path in paths:
        assert validator.is_valid(path)
        assert re.fullmatch(path_schema["pattern"], path), (domain, action, path)
    for invalid in ("relative/report.txt", "~someone/report.txt"):
        assert not validator.is_valid(invalid)
        assert not re.fullmatch(path_schema["pattern"], invalid)
