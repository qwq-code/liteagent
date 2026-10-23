from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.lite_agent.adapter_results import filesystem_find_context
from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools
from integrations.lite_agent.local_file_discovery import (
    constrain_zero_match_find_tools,
    unresolved_zero_match_find,
)
from integrations.lite_agent.instruction_semantics import strict_instruction_required_actions
from integrations.lite_agent.tool_catalog import search_actions
from os_adapter.actions import OSActions
from os_adapter.errors import AdapterError as OSAdapterError
from os_adapter.schema import validate_action_params as validate_os_action
from vlc_adapter.errors import AdapterError as VLCAdapterError
from vlc_adapter.schema import validate_action_params as validate_vlc_action


def test_age_organization_search_exposes_only_composable_primitives() -> None:
    instruction = (
        'Compress files last modified 30 days ago under "/tmp/test_files" and '
        "move all other files to a new directory."
    )
    actions = [
        item["action"]
        for item in search_actions(
            "os", instruction, instruction=instruction, limit=6, strict_generic=True
        )
    ]

    assert actions[:4] == [
        "filesystem.find",
        "archive.compress_file",
        "filesystem.rename",
        "filesystem.create_directory",
    ]
    assert "filesystem.organize_by_age" not in actions


def test_find_context_tells_model_to_classify_modified_at() -> None:
    context = filesystem_find_context(
        {
            "match_count": 1,
            "returned_count": 1,
            "truncated": False,
            "kind": "file",
            "matches": [
                {
                    "path": "/tmp/test_files/old.txt",
                    "name": "old.txt",
                    "kind": "file",
                    "size_bytes": 4,
                    "modified_at": "2020-01-02T03:04:05+00:00",
                }
            ],
        }
    )

    assert "modified_at" in context["matches"][0]
    assert "classify each returned file" in context["guidance"]
    assert "does not decide which files are old or recent" in context["guidance"]


def test_find_context_prioritizes_shallow_user_files_over_hidden_cache() -> None:
    matches = [
        {
            "path": f"/home/user/.cache/long/subfolder-{index}/entry.txt",
            "name": "entry.txt", "kind": "file", "modified_at": "2026-10-21T00:00:00Z",
        }
        for index in range(60)
    ]
    matches.append({
        "path": "/home/user/Desktop/bookkeeping.xlsx",
        "name": "bookkeeping.xlsx", "kind": "file",
        "modified_at": "2026-10-21T00:00:00Z",
    })
    context = filesystem_find_context({
        "match_count": len(matches), "returned_count": len(matches),
        "truncated": False, "matches": matches,
    })
    assert context["matches"][0]["path"] == "/home/user/Desktop/bookkeeping.xlsx"
    assert context["matches_omitted"] > 0


def test_copy_to_directories_rejects_multi_source_payload_and_preserves_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "file1"
    source.write_text("payload", encoding="utf-8")

    with pytest.raises(OSAdapterError) as raised:
        validate_os_action(
            "filesystem.copy_to_directories",
            {
                "sources": [str(source), str(source)],
                "destinations": [str(tmp_path / "dir1")],
            },
        )

    assert raised.value.code == "INVALID_REQUEST"
    assert "unsupported" in raised.value.message
    assert source.read_text(encoding="utf-8") == "payload"


def test_copy_to_directories_copies_one_selected_source_to_every_target(
    tmp_path: Path,
) -> None:
    source = tmp_path / "file1"
    source.write_text("payload", encoding="utf-8")
    destinations = [tmp_path / name for name in ("dir1", "dir2", "dir3")]

    result = OSActions().copy_to_directories(
        {"source": str(source), "destinations": [str(path) for path in destinations]},
        1,
    )

    assert result["copied"] == [str(path / "file1") for path in destinations]
    assert all(
        (path / "file1").read_text(encoding="utf-8") == "payload"
        for path in destinations
    )


def test_vlc_playback_requires_one_exact_source() -> None:
    validate_vlc_action(
        "playback.open", {"source": "/home/user/Desktop/video.mp4", "loop": False}
    )

    with pytest.raises(VLCAdapterError) as raised:
        validate_vlc_action(
            "playback.open",
            {
                "media_kind": "video",
                "source_query": "music",
                "search_roots": ["~/Desktop"],
            },
        )

    assert "unsupported" in raised.value.message or "source" in raised.value.message



def _tool_names(tools):
    return {tool["function"]["name"] for tool in tools}


def test_zero_match_find_requires_a_new_scope_and_blocks_exact_replay() -> None:
    state = RuntimeState(task_id="zero-find", domain="os", instruction="Find the folder")
    state.events.append(
        ExecutionEvent(
            step=1,
            timestamp_utc="2026-09-28T00:00:00Z",
            proposed={
                "kind": "adapter",
                "action": "filesystem.find",
                "arguments": {
                    "roots": ["/tmp/test_files"],
                    "name_patterns": ["*"],
                    "kind": "file",
                    "recursive": True,
                    "max_depth": 1,
                },
            },
            executed=True,
            result={"matches": [], "match_count": 0, "returned_count": 0},
        )
    )
    tools = build_tools("os", ["filesystem.find"], include_gui=False, include_control_tools=False, strict_generic=True)
    constrain_zero_match_find_tools(tools, state)
    parameters = tools[0]["function"]["parameters"]
    assert parameters["properties"]["kind"]["enum"] == ["directory", "any"]
    assert parameters["allOf"]


def test_multi_app_empty_find_keeps_file_discovery_active() -> None:
    state = RuntimeState(
        task_id="empty-receipts",
        domain="multi_apps",
        instruction="Add each receipt file from the folder to the spreadsheet table.",
    )
    state.events.append(
        ExecutionEvent(
            step=1,
            timestamp_utc="2026-09-28T00:00:00Z",
            proposed={
                "kind": "adapter",
                "action": "adapter.call",
                "arguments": {
                    "domain": "os",
                    "action": "filesystem.find",
                    "payload": {
                        "params": {
                            "roots": ["~/Downloads"],
                            "name_patterns": ["*.pdf"],
                            "kind": "file",
                        }
                    },
                },
            },
            executed=True,
            result={"adapter_response": {"result": {"matches": [], "match_count": 0}}},
        )
    )
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused.invalid/v1"),
        adapter_executor=object(),
        model_client=SimpleNamespace(client=object()),
    )
    assert unresolved_zero_match_find(state)
    assert not agent._directory_table_reader_pending(state)
    assert _tool_names(agent.tools(state)) == {"adapter__adapter_call"}

    state.events.append(
        ExecutionEvent(
            step=2,
            timestamp_utc="2026-09-28T00:00:01Z",
            proposed={
                "kind": "adapter",
                "action": "adapter.call",
                "arguments": {
                    "domain": "os",
                    "action": "filesystem.find",
                    "payload": {"params": {"roots": ["~/Desktop"], "name_patterns": ["*.pdf"]}},
                },
            },
            executed=True,
            result={"adapter_response": {"result": {"matches": [{"path": "~/Desktop/receipt.pdf"}]}}},
        )
    )
    assert not unresolved_zero_match_find(state)
    assert agent._directory_table_reader_pending(state)


def test_truncated_completion_retry_exposes_only_terminal_controls_after_verification() -> None:
    state = RuntimeState(task_id="compact-done", domain="multi_apps", instruction="Copy the file")
    state.completion_rejections = 1
    state.events.extend(
        [
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-09-28T00:00:00Z",
                proposed={"kind": "adapter", "action": "adapter.call", "arguments": {}},
                executed=True,
                result={"status": "ok", "verification": {"passed": True}},
            ),
            ExecutionEvent(
                step=2,
                timestamp_utc="2026-09-28T00:00:00Z",
                proposed={"kind": "completion", "action": "propose_done", "arguments": {}},
                executed=False,
                error={
                    "status": "rejected",
                    "missing": ["the model response was incomplete (finish_reason='stop')"],
                },
            ),
        ]
    )
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused.invalid/v1"),
        adapter_executor=object(),
        model_client=SimpleNamespace(client=object()),
    )
    assert _tool_names(agent.tools(state)) == {"propose_done", "fail_task"}


def test_truncated_completion_retry_keeps_recovery_tools_without_verification() -> None:
    state = RuntimeState(task_id="unverified-copy", domain="multi_apps", instruction="Copy the file")
    state.completion_rejections = 1
    state.events.extend(
        [
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-09-28T00:00:00Z",
                proposed={"kind": "adapter", "action": "adapter.call", "arguments": {}},
                executed=True,
                result={"status": "ok"},
            ),
            ExecutionEvent(
                step=2,
                timestamp_utc="2026-09-28T00:00:00Z",
                proposed={"kind": "completion", "action": "propose_done", "arguments": {}},
                executed=False,
                error={
                    "status": "rejected",
                    "missing": ["the model response was incomplete (finish_reason='stop')"],
                },
            ),
        ]
    )
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused.invalid/v1"),
        adapter_executor=object(),
        model_client=SimpleNamespace(client=object()),
    )
    assert "tools_search" in _tool_names(agent.tools(state))


def test_vlc_local_media_discovery_precedes_playback_open(tmp_path: Path) -> None:
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"placeholder")
    instruction = "Please play the video saved on my Desktop."
    assert strict_instruction_required_actions("vlc", instruction) == [
        "playback.find_local",
        "playback.open",
    ]
    validate_vlc_action(
        "playback.find_local",
        {"roots": [str(tmp_path)], "name_patterns": ["*.mp4"]},
    )


def test_vlc_empty_discovery_cannot_advance_to_playback() -> None:
    state = RuntimeState(
        task_id="empty-media", domain="vlc",
        instruction="Play the music video saved on my desktop via vlc.",
    )
    state.events.append(
        ExecutionEvent(
            step=1,
            timestamp_utc="2026-09-28T00:00:00Z",
            proposed={
                "kind": "adapter", "action": "playback.find_local",
                "arguments": {
                    "roots": ["~/Desktop"],
                    "name_patterns": ["Truncated label"],
                    "kind": "file",
                },
            },
            executed=True,
            result={"context_hint": {"matches": [], "match_count": 0}},
        )
    )
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused.invalid/v1"),
        adapter_executor=object(),
        model_client=SimpleNamespace(client=object()),
    )
    tools = agent.tools(state)
    assert "adapter__playback_find_local" in _tool_names(tools)
    assert "adapter__playback_open" not in _tool_names(tools)
    find = next(
        tool for tool in tools
        if tool["function"]["name"] == "adapter__playback_find_local"
    )
    assert find["function"]["parameters"]["allOf"]
