from __future__ import annotations

import gzip
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_context_hint_for_model,
    filesystem_find_context,
)
from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.instruction_semantics import (
    strict_instruction_required_actions,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import (
    DIRECT_ACTION_SCHEMAS,
    public_actions,
    search_actions,
)
from os_adapter.actions import OSActions
import os_adapter.actions as os_actions
from os_adapter.errors import AdapterError as OSAdapterError
from os_adapter.schema import ACTIONS as OS_ACTIONS
from os_adapter.schema import validate_action_params as validate_os_action
from os_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS as OS_SCHEMAS
from vlc_adapter.errors import AdapterError as VLCAdapterError
from vlc_adapter.schema import ACTIONS as VLC_ACTIONS
from vlc_adapter.schema import validate_action_params as validate_vlc_action
from vlc_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS as VLC_SCHEMAS


RETIRED_OS_WORKFLOWS = {
    "filesystem.copy_matching",
    "filesystem.organize_by_age",
}
RETIRED_VLC_WORKFLOWS = {"playback.open_unique"}
OS_PRIMITIVES = {
    "filesystem.find",
    "filesystem.create_directory",
    "filesystem.copy",
    "filesystem.rename",
    "archive.compress_file",
}


@pytest.mark.parametrize(
    "instruction",
    [
        "Convert the video to audio on my desktop to play whenever I choose.",
        "Export the music clip to Downloads so I can play it on another device.",
        "Save the video to my home folder to open later.",
    ],
)
def test_future_media_use_does_not_require_immediate_playback(instruction) -> None:
    assert "playback.open" not in strict_instruction_required_actions(
        "vlc", instruction
    )


@pytest.mark.parametrize(
    "instruction",
    [
        "Please play the video from Downloads.",
        "I would like you to open the audio on my desktop.",
        "I would like you to open the desktop video now and export it for later.",
        "Export the clip to Music so I can play it later, then play it now.",
        "Save the video to Downloads to play later. Then open the video now.",
    ],
)
def test_explicit_media_playback_remains_required(instruction) -> None:
    assert "playback.open" in strict_instruction_required_actions("vlc", instruction)


class _PdfTextRunner:
    def __init__(self, text: str) -> None:
        self.text = text

    def run(self, argv, *, timeout=None, check=True, cwd=None):
        output_path = Path(argv[-1])
        output_path.write_text(self.text, encoding="utf-8")
        return {"returncode": 0, "duration_ms": 1, "stderr": ""}


def test_task_shaped_actions_are_absent_and_primitives_are_public() -> None:
    os_surfaces = (
        set(OS_ACTIONS),
        set(OS_SCHEMAS),
        set(DIRECT_ACTION_SCHEMAS["os"]),
        set(public_actions("os")),
    )
    vlc_surfaces = (
        set(VLC_ACTIONS),
        set(VLC_SCHEMAS),
        set(DIRECT_ACTION_SCHEMAS["vlc"]),
        set(public_actions("vlc")),
    )

    assert all(RETIRED_OS_WORKFLOWS.isdisjoint(surface) for surface in os_surfaces)
    assert all(OS_PRIMITIVES.issubset(surface) for surface in os_surfaces)
    assert all(RETIRED_VLC_WORKFLOWS.isdisjoint(surface) for surface in vlc_surfaces)
    assert all("playback.open" in surface for surface in vlc_surfaces)


def test_copy_uses_one_exact_source_and_destination(tmp_path) -> None:
    source = tmp_path / "source-2037.txt"
    destination_parent = tmp_path / "selected-output"
    destination = destination_parent / "renamed-copy.txt"
    source.write_text("counterfactual payload\n", encoding="utf-8")
    destination_parent.mkdir()
    arguments = {
        "source": str(source),
        "destination": str(destination),
        "replace": False,
    }

    validate_os_action("filesystem.copy", arguments)
    result = OSActions().copy_file(arguments, 1)

    assert result["source"] == str(source.resolve())
    assert result["destination"] == str(destination.resolve())
    assert destination.read_text(encoding="utf-8") == "counterfactual payload\n"


def test_copy_matching_tree_resolves_relative_paths_from_active_terminal(
    tmp_path, monkeypatch
) -> None:
    terminal_root = tmp_path / "terminal-workspace"
    nested = terminal_root / "source" / "nested"
    nested.mkdir(parents=True)
    (nested / "keep_failed.ipynb").write_text("notebook", encoding="utf-8")
    (nested / "keep.txt").write_text("other", encoding="utf-8")
    monkeypatch.setattr(
        os_actions, "_active_terminal_working_directory", lambda: terminal_root
    )

    result = OSActions().copy_matching_tree(
        {"source": ".", "destination": "./fails", "pattern": "*failed.ipynb"},
        1,
    )

    assert result["source"] == str(terminal_root.resolve())
    assert result["destination"] == str((terminal_root / "fails").resolve())
    assert result["copied_relative_paths"] == ["source/nested/keep_failed.ipynb"]
    assert (terminal_root / "fails/source/nested/keep_failed.ipynb").read_text(
        encoding="utf-8"
    ) == "notebook"
    assert not (tmp_path / "fails").exists()


def test_copy_matching_tree_keeps_absolute_paths_independent_of_terminal(
    tmp_path, monkeypatch
) -> None:
    source = tmp_path / "absolute-source"
    source.mkdir()
    (source / "absolute_failed.ipynb").write_text("absolute", encoding="utf-8")
    destination = tmp_path / "absolute-destination"
    monkeypatch.setattr(
        os_actions,
        "_active_terminal_working_directory",
        lambda: (_ for _ in ()).throw(
            AssertionError("absolute paths must not inspect cwd")
        ),
    )

    result = OSActions().copy_matching_tree(
        {
            "source": str(source),
            "destination": str(destination),
            "pattern": "*failed.ipynb",
        },
        1,
    )

    assert result["source"] == str(source.resolve())
    assert (destination / "absolute_failed.ipynb").exists()


def test_copy_to_directories_explains_relative_path_recovery_without_terminal(
    tmp_path, monkeypatch
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("payload", encoding="utf-8")

    def unavailable() -> Path:
        raise OSAdapterError(
            "TERMINAL_UNAVAILABLE",
            "no active user shell working directory is observable",
            http_status=422,
        )

    monkeypatch.setattr(os_actions, "_active_terminal_working_directory", unavailable)

    with pytest.raises(OSAdapterError) as raised:
        OSActions().copy_to_directories(
            {"source": str(source), "destinations": ["copied-reports"]}, 1
        )

    assert raised.value.code == "TERMINAL_UNAVAILABLE"
    assert raised.value.details["relative_paths"] == ["copied-reports"]
    assert "intended parent directory" in raised.value.details["retry"]
    assert "not the current folder" in raised.value.details["retry"]
    assert "relative filesystem paths" in raised.value.message


@pytest.mark.parametrize(
    "arguments",
    [
        {"source_query": "photos", "destination_name": "copies"},
        {"source": "/tmp/input", "destination": "/tmp/output", "pattern": "*.jpg"},
    ],
)
def test_copy_rejects_implicit_search_or_pattern_arguments(arguments: dict) -> None:
    with pytest.raises(OSAdapterError):
        validate_os_action("filesystem.copy", arguments)


def test_compress_file_uses_explicit_paths_and_explicit_source_lifecycle(
    tmp_path,
) -> None:
    source = tmp_path / "observed-log-2038.txt"
    destination_parent = tmp_path / "archive"
    destination = destination_parent / "observed-log-2038.txt.gz"
    source.write_bytes(b"a structurally different input\n" * 20)
    destination_parent.mkdir()
    arguments = {
        "source": str(source),
        "destination": str(destination),
        "remove_source": True,
        "overwrite": False,
    }

    validate_os_action("archive.compress_file", arguments)
    result = OSActions().compress_file(arguments, 1)

    assert not source.exists()
    assert result["source_exists"] is False
    with gzip.open(destination, "rb") as archive:
        assert archive.read() == b"a structurally different input\n" * 20


def test_pdf_batch_returns_a_model_selected_window_and_resume_cursor(
    tmp_path, monkeypatch
) -> None:
    source = tmp_path / "observed-source.pdf"
    source.write_bytes(b"placeholder")
    full_text = "0123456789" * 100
    monkeypatch.setattr(os_actions.shutil, "which", lambda name: "/usr/bin/pdftotext")

    result = OSActions(runner=_PdfTextRunner(full_text)).extract_pdf_text_batch(
        {
            "input_pattern": source.name,
            "cwd_source": "explicit",
            "cwd_path": str(tmp_path),
            "start_char": 120,
            "max_chars_per_file": 25,
            "preserve_layout": False,
        },
        5,
    )

    file_result = result["files"][0]
    assert file_result["text"] == full_text[120:145]
    assert file_result["source_start_char"] == 120
    assert file_result["source_end_char"] == 145
    assert file_result["source_total_chars"] == len(full_text)
    assert file_result["next_start_char"] == 145
    assert file_result["offset_basis"] == "extracted_text"
    assert file_result["source_truncated"] is True


def test_file_observation_preserves_modification_time_for_model_classification() -> (
    None
):
    context = filesystem_find_context(
        {
            "match_count": 2,
            "returned_count": 2,
            "truncated": False,
            "matches": [
                {
                    "path": "/tmp/example/a.txt",
                    "name": "a.txt",
                    "kind": "file",
                    "size_bytes": 14,
                    "modified_at": "2034-05-06T07:08:09+00:00",
                },
                {
                    "path": "/tmp/example/b.txt",
                    "name": "b.txt",
                    "kind": "file",
                    "size_bytes": 23,
                    "modified_at": "2035-06-07T08:09:10+00:00",
                },
            ],
        }
    )

    assert [item["modified_at"] for item in context["matches"]] == [
        "2034-05-06T07:08:09+00:00",
        "2035-06-07T08:09:10+00:00",
    ]


@pytest.mark.parametrize(
    ("kind", "expected_kinds", "zero_guidance"),
    [
        (None, {"file"}, "excluded directories"),
        ("file", {"file"}, "excluded directories"),
        ("directory", {"directory"}, "excluded files"),
        ("any", {"file", "directory"}, "including files and directories"),
    ],
)
def test_find_feedback_retains_effective_kind_and_type_scope(
    tmp_path, kind, expected_kinds, zero_guidance
) -> None:
    (tmp_path / "records.txt").write_text("synthetic input", encoding="utf-8")
    (tmp_path / "report-inputs").mkdir()
    params = {
        "roots": [str(tmp_path)],
        "name_patterns": ["*"],
        "recursive": False,
    }
    if kind is not None:
        params["kind"] = kind
    original_params = deepcopy(params)

    result = OSActions().find_files(params, 1)
    original_result = deepcopy(result)
    context = filesystem_find_context(result)

    assert result["kind"] == (kind or "file")
    assert context["kind"] == result["kind"]
    assert {item["kind"] for item in context["matches"]} == expected_kinds
    assert result == original_result
    assert params == original_params

    empty_result = OSActions().find_files(
        {**params, "name_patterns": ["missing-name"]}, 1
    )
    original_empty = deepcopy(empty_result)
    empty_context = filesystem_find_context(empty_result)

    assert empty_context["match_count"] == 0
    assert empty_context["kind"] == result["kind"]
    assert zero_guidance in empty_context["guidance"]
    assert empty_result == original_empty


def test_find_resolves_unnamed_home_folder_from_desktop(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os_actions.Path, "home", classmethod(lambda cls: tmp_path))
    desktop_photos = tmp_path / "Desktop" / "photos"
    desktop_photos.mkdir(parents=True)
    (desktop_photos / "holiday.jpg").write_bytes(b"jpg")

    result = OSActions().find_files(
        {
            "roots": ["~/photos"],
            "name_patterns": ["*.jpg"],
            "recursive": True,
        },
        1,
    )

    assert result["requested_roots"] == ["~/photos"]
    assert result["roots"] == [str(desktop_photos.resolve())]
    assert result["root_aliases"] == {str(tmp_path / "photos"): str(desktop_photos.resolve())}
    assert [item["path"] for item in result["matches"]] == [str((desktop_photos / "holiday.jpg").resolve())]


def test_default_file_filter_reaches_request_before_explicit_directory_retry(
    tmp_path,
) -> None:
    directory = tmp_path / "report-inputs"
    directory.mkdir()
    (tmp_path / "records.txt").write_text("synthetic input", encoding="utf-8")
    params = {
        "roots": [str(tmp_path)],
        "name_patterns": [directory.name],
        "recursive": False,
    }
    original_params = deepcopy(params)
    raw_result = OSActions().find_files(params, 1)
    original_result = deepcopy(raw_result)
    body = {
        "status": "ok",
        "result": {
            "adapter": "os",
            "action": "filesystem.find",
            "response": {"status": "ok", "result": raw_result},
        },
    }
    original_body = deepcopy(body)
    hint = adapter_context_hint("multi_apps", "adapter.call", body)
    compact = compact_context_hint_for_model(hint, remaining_chars=4_000)
    event = ExecutionEvent(
        step=1,
        timestamp_utc="2026-09-13T00:00:00Z",
        proposed={
            "kind": "adapter",
            "tool": "adapter__adapter_call",
            "action": "adapter.call",
            "arguments": {
                "adapter": "os",
                "action": "filesystem.find",
                "payload": {"params": params},
            },
        },
        executed=True,
        result={"context_hint": compact},
    )
    state = RuntimeState(
        task_id="synthetic-directory-filter-feedback",
        domain="multi_apps",
        instruction="Find the requested input directory.",
        events=[event],
    )
    original_events = deepcopy(state.events)
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused.invalid/v1"),
        adapter_executor=object(),
        model_client=SimpleNamespace(client=object()),
    )

    messages = agent._messages(state, b"png", execution_recovery=True)
    state_text = messages[2]["content"][0]["text"]
    summary = json.loads(state_text.split("\n")[1])
    observed = next(item for item in summary if item.get("step") == 1)["result"][
        "context_hint"
    ]["downstream_context"]

    assert directory.is_dir()
    assert observed["match_count"] == 0
    assert observed["matches"] == []
    assert observed["kind"] == "file"
    assert "excluded directories" in observed["guidance"]
    assert "kind=directory or kind=any" in observed["guidance"]
    assert "cannot create a directory or prove" in observed["guidance"]
    assert state.task_id not in state_text

    # The caller explicitly chooses the correction; projection never rewrites it.
    retry_params = {**params, "kind": "directory"}
    original_retry = deepcopy(retry_params)
    corrected = OSActions().find_files(retry_params, 1)

    assert corrected["kind"] == "directory"
    assert [item["path"] for item in corrected["matches"]] == [str(directory)]
    assert params == original_params
    assert "kind" not in params
    assert retry_params == original_retry
    assert raw_result == original_result
    assert body == original_body
    assert state.events == original_events


def test_vlc_open_requires_the_model_selected_source() -> None:
    validate_vlc_action(
        "playback.open", {"source": "/tmp/selected-media-2039.webm", "loop": True}
    )

    with pytest.raises(VLCAdapterError):
        validate_vlc_action(
            "playback.open", {"media_kind": "video", "search_roots": ["~/Desktop"]}
        )


def test_generic_search_recalls_only_atomic_replacements() -> None:
    os_matches = {
        item["action"]
        for query in (
            "copy exact observed file to destination path",
            "gzip one selected old file",
        )
        for item in search_actions(
            "os", query, instruction=query, limit=8, strict_generic=True
        )
    }
    vlc_matches = {
        item["action"]
        for item in search_actions(
            "vlc",
            "open and play selected local video",
            instruction="Play the selected local video in VLC.",
            limit=8,
            strict_generic=True,
        )
    }

    assert {"filesystem.copy", "archive.compress_file"}.issubset(os_matches)
    assert RETIRED_OS_WORKFLOWS.isdisjoint(os_matches)
    assert "playback.open" in vlc_matches
    assert RETIRED_VLC_WORKFLOWS.isdisjoint(vlc_matches)
