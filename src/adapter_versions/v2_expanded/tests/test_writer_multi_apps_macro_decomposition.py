from __future__ import annotations

import io
import json

import pytest

import multi_apps_adapter.actions as multi_apps_actions
from multi_apps_adapter.actions import MultiAppsActions
from multi_apps_adapter.errors import AdapterError as MultiAppsAdapterError
from multi_apps_adapter.schema import ACTIONS as MULTI_APPS_ACTIONS
from multi_apps_adapter.schema import parse_action_request as parse_multi_apps_request
from multi_apps_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as MULTI_APPS_SCHEMAS,
)
from writer_adapter.errors import AdapterError as WriterAdapterError
from writer_adapter.schema import ACTIONS as WRITER_ACTIONS
from writer_adapter.schema import parse_action_request as parse_writer_request
from writer_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS as WRITER_SCHEMAS
from writer_adapter.uno_worker import GENERIC_ACTIONS as WRITER_DISPATCH
from writer_adapter.uno_worker import execute as execute_writer


RETIRED_WRITER_MACROS = {
    "document.create_from_image",
    "document.create_from_text_files",
    "document.create_from_presentation",
    "document.create_from_spreadsheet",
    "document.deduplicate_records",
    "paragraph.apply_split_tabstop",
    "table.from_delimited_text",
    "text.resize_italic_runs",
    "text.set_subscript_matches",
}
RETIRED_MULTI_APPS_ACTIONS = {
    "artifact.verify",
    "archive.create_extract",
    "clipboard.get",
    "clipboard.set",
    "command.capture_output",
    "command.run",
    "contacts.export_csv",
    "desktop.open_path",
    "desktop.set_default_application",
    "desktop.set_wallpaper",
    "document.convert_batch",
    "document.create_from_image",
    "document.create_from_json_values",
    "document.create_from_presentation",
    "document.create_from_spreadsheet",
    "document.create_from_text_files",
    "document.extract_images",
    "document.insert_table_after_text",
    "document.read_file",
    "file.read_text",
    "file.replace_literal",
    "file.write_text",
    "filesystem.create_directory",
    "filesystem.find",
    "filesystem.move",
    "image.crop",
    "image.extract_text_batch",
    "image.rearrange_equal_sections",
    "mail.compose_recipients",
    "mail.query_latest_messages",
    "mail.query_messages",
    "mail.save_attachment",
    "media.extract_audio",
    "media.extract_current_audio",
    "media.extract_current_frame",
    "media.inspect_current",
    "pdf.extract_text_batch",
    "pdf.split_by_outline",
    "presentation.inspect_current",
    "presentation.fill_missing_notes_from_document",
    "presentation.insert_audio",
    "presentation.set_background_image",
    "spreadsheet.concatenate_single_columns",
    "spreadsheet.convert_file",
    "spreadsheet.create_workbook",
    "spreadsheet.inspect_current",
    "spreadsheet.insert_matching_rows_into_document",
    "spreadsheet.open_in_terminal",
    "spreadsheet.read_file",
    "spreadsheet.save",
    "spreadsheet.write_range",
    "state.verify",
    "table.sort",
    "terminal.show_output",
    "window.capture",
    "workspace.find_files",
}


def test_writer_workflow_macros_are_absent_from_every_public_surface() -> None:
    for surface in (WRITER_ACTIONS, WRITER_SCHEMAS, WRITER_DISPATCH):
        assert RETIRED_WRITER_MACROS.isdisjoint(surface)


def test_multi_apps_exposes_only_the_generic_adapter_call() -> None:
    assert MULTI_APPS_ACTIONS == {"adapter.call"}
    assert set(MULTI_APPS_SCHEMAS) == {"adapter.call"}


@pytest.mark.parametrize("action", sorted(RETIRED_WRITER_MACROS))
def test_writer_rejects_retired_workflow_requests(action: str) -> None:
    with pytest.raises(WriterAdapterError) as parsed_error:
        parse_writer_request({"action": action, "document": {}, "params": {}})
    assert parsed_error.value.code == "UNSUPPORTED_OPERATION"

    with pytest.raises(WriterAdapterError) as dispatch_error:
        execute_writer({"action": action, "document": {}, "params": {}})
    assert dispatch_error.value.code == "UNSUPPORTED_OPERATION"


@pytest.mark.parametrize("action", sorted(RETIRED_MULTI_APPS_ACTIONS))
def test_multi_apps_rejects_every_retired_flat_action(action: str) -> None:
    with pytest.raises(MultiAppsAdapterError) as parsed_error:
        parse_multi_apps_request({"action": action, "params": {}})
    assert parsed_error.value.code == "UNSUPPORTED_ACTION"

    with pytest.raises(MultiAppsAdapterError) as dispatch_error:
        MultiAppsActions().dispatch(action, {}, 0.1)
    assert dispatch_error.value.code == "UNSUPPORTED_ACTION"


def test_atomic_writer_replacements_remain_public() -> None:
    replacements = {
        "document.inspect",
        "document.save",
        "document.append_paragraphs",
        "paragraph.replace_text",
        "table.read",
        "table.insert_after_text",
        "image.insert_at_cursor",
    }

    assert replacements.issubset(WRITER_ACTIONS)
    assert replacements.issubset(WRITER_DISPATCH)
    assert replacements - {"document.inspect", "document.save"} <= WRITER_SCHEMAS.keys()


def test_adapter_call_remains_valid_and_preserves_the_selected_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def fake_urlopen(request, *, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return io.BytesIO(b'{"status":"ok","result":{"observed":true}}')

    monkeypatch.setattr(multi_apps_actions, "urlopen", fake_urlopen)
    params = {
        "adapter": "gimp",
        "action": "image.crop",
        "payload": {
            "params": {
                "input_path": "/tmp/source.png",
                "output_path": "/tmp/cropped.png",
                "unit": "pixels",
                "left": 7,
            }
        },
    }

    parsed = parse_multi_apps_request({"action": "adapter.call", "params": params})
    result = MultiAppsActions().dispatch(parsed.action, parsed.params, 5.0)

    assert captured == {
        "url": "http://127.0.0.1:8768/v1/actions",
        "payload": {
            "adapter": "gimp",
            "action": "image.crop",
            "params": params["payload"]["params"],
            "timeout_ms": 5_000,
        },
        "timeout": 5.0,
    }
    assert result["adapter"] == "gimp"
    assert result["action"] == "image.crop"
