from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from impress_adapter.errors import AdapterError as ImpressError
from impress_adapter.schema import ACTIONS as IMPRESS_ACTIONS
from impress_adapter.schema import validate_action_params as validate_impress
from impress_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS as IMPRESS_SCHEMAS
from impress_adapter.uno_worker import _create_slides_from_images
from integrations.lite_agent.tool_catalog import build_tools, search_actions
from integrations.lite_agent.instruction_semantics import (
    requested_max_system_volume,
    strict_instruction_required_actions,
)
from integrations.lite_agent.tool_surface import ToolSurfaceMixin
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.agent import LiteAgent
from writer_adapter.errors import AdapterError as WriterError
from writer_adapter.paragraph_dedup import plan_paragraph_deduplication
from writer_adapter.schema import ACTIONS as WRITER_ACTIONS
from writer_adapter.schema import validate_action_params as validate_writer
from writer_adapter.text_format import set_text_format_in_match
from writer_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS as WRITER_SCHEMAS


class Page:
    def __init__(self, name: str) -> None:
        self.name = name
        self.Layout = 0
        self.shapes: list[str] = []

    def getCount(self) -> int:
        return len(self.shapes)

    def getByIndex(self, index: int) -> str:
        return self.shapes[index]

    def remove(self, shape: str) -> None:
        self.shapes.remove(shape)


class Pages:
    def __init__(self, pages: list[Page]) -> None:
        self.items = pages

    def getCount(self) -> int:
        return len(self.items)

    def getByIndex(self, index: int) -> Page:
        return self.items[index]

    def insertNewByIndex(self, index: int) -> Page:
        page = Page(f"new-{len(self.items)}")
        self.items.insert(index, page)
        return page

    def remove(self, page: Page) -> None:
        self.items.remove(page)


def test_impress_image_sequence_is_public_and_replaces_template_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    action = "slides.create_from_images"
    params = {
        "image_paths": [str(tmp_path / "pic1.png"), str(tmp_path / "pic2.png")],
        "replace_existing_slides": True,
        "fit_mode": "stretch",
    }
    for path in params["image_paths"]:
        Path(path).write_bytes(b"png")
    assert action in IMPRESS_ACTIONS
    validate_impress(action, params)
    exposed = build_tools(
        "libreoffice_impress", [action], include_gui=False,
        include_control_tools=False, strict_generic=True,
    )[0]["function"]["parameters"]
    assert exposed["properties"] == IMPRESS_SCHEMAS[action]["properties"]
    assert exposed["required"] == IMPRESS_SCHEMAS[action]["required"]
    jsonschema.Draft202012Validator.check_schema(exposed)

    original = Page("template-with-placeholders")
    original.shapes.extend(["title-placeholder", "body-placeholder"])
    session = SimpleNamespace(pages=Pages([original]))

    def insert_image(session, payload):
        page = session.pages.getByIndex(payload["slide"])
        page.shapes.append(Path(payload["path"]).name)
        return {"index": len(page.shapes) - 1}

    def fit_to_slide(session, payload):
        return {"index": payload["selector"]["index"]}

    monkeypatch.setattr("impress_adapter.uno_worker._insert_image", insert_image)
    monkeypatch.setattr("impress_adapter.uno_worker._fit_to_slide", fit_to_slide)
    result = _create_slides_from_images(session, params)

    assert result["slide_count"] == 2
    assert result["removed_slide_count"] == 1
    assert [page.shapes for page in session.pages.items] == [["pic1.png"], ["pic2.png"]]


def test_impress_summary_slide_route_is_searchable_and_validated() -> None:
    action = "presentation.create_summary_slide"
    assert action in IMPRESS_ACTIONS
    params = {"slides": [0, 2], "title": "Summary Slide"}
    validate_impress(action, params)
    exposed = build_tools(
        "libreoffice_impress", [action], include_gui=False,
        include_control_tools=False, strict_generic=True,
    )[0]["function"]["parameters"]
    jsonschema.Draft202012Validator.check_schema(exposed)
    matches = search_actions("libreoffice_impress", "Summary Slide")
    assert matches[0]["action"] == action


def test_summary_slide_multi_app_search_prioritizes_atomic_route() -> None:
    matches = search_actions("multi_apps", "summary slide presentation")
    routes = [(item.get("adapter"), item.get("downstream_action")) for item in matches]
    assert routes[0] == ("libreoffice_impress", "presentation.create_summary_slide")


def test_saved_document_export_does_not_reuse_unverified_active_document() -> None:
    matches = search_actions(
        "multi_apps",
        "adapter__adapter_call libreoffice_writer document.export_pdf",
        completed_routes=[("libreoffice_writer", "document.read_file")],
        strict_generic=True,
    )
    assert [(item["adapter"], item["downstream_action"]) for item in matches] == [
        ("libreoffice_writer", "document.export_file_pdf"),
    ]


def test_mail_folder_flag_workflow_is_staged_through_query_and_update() -> None:
    query = "add a star to every email in local Bills folder"
    first = search_actions("multi_apps", query, strict_generic=True)
    assert [(item["adapter"], item["downstream_action"]) for item in first] == [
        ("thunderbird", "messages.query")
    ]
    after_query = search_actions(
        "multi_apps",
        query,
        completed_routes=[("thunderbird", "messages.query")],
        strict_generic=True,
    )
    assert [(item["adapter"], item["downstream_action"]) for item in after_query] == [
        ("thunderbird", "messages.update_flags")
    ]


def test_saved_email_attachment_image_request_prefers_writer_extraction() -> None:
    matches = search_actions(
        "multi_apps",
        "extract first image from attached docx",
        instruction=(
            "Export the first image from the doc file attached in the most recent email "
            "in Notes folder and set this image as the new desktop background."
        ),
        completed_routes=[("thunderbird", "attachments.save")],
        strict_generic=True,
    )
    assert (matches[0]["adapter"], matches[0]["downstream_action"]) == (
        "libreoffice_writer", "document.extract_images"
    )


def test_writer_match_segment_format_resolves_exact_absolute_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action = "text.set_format_in_match"
    params = {
        "literal": "H2O",
        "occurrence": 1,
        "match_start_offset": 1,
        "match_end_offset": 2,
        "script": "subscript",
    }
    assert action in WRITER_ACTIONS
    validate_writer(action, params)
    exposed = build_tools(
        "libreoffice_writer", [action], include_gui=False,
        include_control_tools=False, strict_generic=True,
    )[0]["function"]["parameters"]
    assert exposed["properties"] == WRITER_SCHEMAS[action]["properties"]
    assert exposed["required"] == WRITER_SCHEMAS[action]["required"]
    jsonschema.Draft202012Validator.check_schema(exposed)

    paragraphs = [SimpleNamespace(String="H2O heading"), SimpleNamespace(String="Use H2O here")]
    captured: dict = {}
    monkeypatch.setattr("writer_adapter.text_search._body_paragraphs", lambda doc: paragraphs)

    def apply(_session, selected):
        captured.update(selected)
        return {"text": selected["expected_text"], "format": {"script": "subscript"}}

    monkeypatch.setattr("writer_adapter.text_format.set_text_format", apply)
    result = set_text_format_in_match(SimpleNamespace(doc=object()), params)
    assert captured == {
        "paragraph_index": 1,
        "start_offset": 5,
        "end_offset": 6,
        "expected_text": "2",
        "script": "subscript",
    }
    assert result["matched_text"] == "H2O"


def test_mail_query_search_exposes_attachment_save_together() -> None:
    routes = {
        (item.get("adapter"), item.get("downstream_action"))
        for item in search_actions("multi_apps", "thunderbird messages query")
    }
    assert ("thunderbird", "messages.query") in routes
    assert ("thunderbird", "attachments.save") in routes


def test_writer_record_deduplication_is_one_stable_atomic_operation() -> None:
    rows = [
        "06:01:10,E201,SHS,1",
        "06:06:28,E209,SHS,1",
        "06:19:13,E201,FAN,2",
        "06:20:12,E213,SHS,1",
        "06:28:34,E209,UNI,1",
    ]
    plan = plan_paragraph_deduplication(rows, delimiter=",", key_column=1)
    assert plan["keep_indices"] == [0, 1, 3]
    assert plan["remove_indices"] == [2, 4]
    assert plan["duplicate_keys"] == ["E201", "E209"]

    assert "document.deduplicate_records" in WRITER_ACTIONS
    params = {"delimiter": ",", "key_column": 1}
    validate_writer("document.deduplicate_records", params)
    exposed = build_tools(
        "libreoffice_writer", ["document.deduplicate_records"],
        include_gui=False, include_control_tools=False, strict_generic=True,
    )[0]["function"]["parameters"]
    jsonschema.Draft202012Validator.check_schema(exposed)
    assert exposed["required"] == ["delimiter", "key_column"]


def test_writer_record_deduplication_is_selected_for_generic_train_records() -> None:
    instruction = (
        "Remove duplicated train records by train_id, keeping the first line "
        "for each train and preserving the original order."
    )
    required = strict_instruction_required_actions("libreoffice_writer", instruction)
    assert required[:2] == ["document.inspect", "document.deduplicate_records"]


def test_xlsx_find_result_keeps_calc_reader_and_drops_writer_fallback() -> None:
    state = RuntimeState(
        task_id="synthetic-xlsx-reader", domain="multi_apps",
        instruction="Read the spreadsheet found on disk.",
        expanded_actions=["adapter.call"],
    )
    state.events = [
        # The event shape matches the persisted multi-app adapter result.
        ExecutionEvent(
            step=1, timestamp_utc="2026-10-24T00:00:00Z", executed=True,
            proposed={"kind": "adapter", "action": "adapter.call", "arguments": {
                "adapter": "os", "action": "filesystem.find", "payload": {"params": {}}
            }},
            result={"context_hint": {"downstream_context": {"matches": [
                {"path": "/home/user/input.xlsx", "kind": "file"}
            ]}}},
        ),
        ExecutionEvent(
            step=2, timestamp_utc="2026-10-24T00:00:01Z", executed=True,
            proposed={"kind": "catalog", "tool": "tools_search", "arguments": {"query": "read file"}},
            result={"matches": [
                {"action": "adapter.call", "adapter": "libreoffice_calc", "downstream_action": "workbook.read_file"},
                {"action": "adapter.call", "adapter": "libreoffice_writer", "downstream_action": "document.read_file"},
            ]},
        ),
    ]
    agent = object.__new__(LiteAgent)
    agent.config = SimpleNamespace(top_k_actions=7, include_gui=False)
    agent.holo_grounder = None
    agent.holo_gui_gateway = None
    agent.gui_executor = None
    tools = ToolSurfaceMixin._apply_common_tool_constraints(
        build_tools("multi_apps", ["adapter.call"], include_gui=False, strict_generic=True), state
    )
    params = next(tool["function"]["parameters"] for tool in tools if tool["function"]["name"] == "adapter__adapter_call")
    route = params.get("x-route")
    assert route == {"adapter": "libreoffice_calc", "action": "workbook.read_file"}


def test_qualitative_max_volume_exposes_only_normal_100_percent() -> None:
    instruction = "Please turn the system volume up to the max."
    assert requested_max_system_volume("os", instruction)
    assert "audio.set_volume" in strict_instruction_required_actions("os", instruction)
    state = RuntimeState(task_id="synthetic-volume", domain="os", instruction=instruction)
    tools = build_tools("os", ["audio.set_volume"], include_gui=False,
                        include_control_tools=False, strict_generic=True)
    tools = ToolSurfaceMixin._constrain_max_system_volume(tools, state)
    percent = tools[0]["function"]["parameters"]["properties"]["percent"]
    assert percent["enum"] == [100]
    assert "maximum" not in percent
