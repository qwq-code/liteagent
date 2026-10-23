from __future__ import annotations

from typing import Any

import pytest

from integrations.lite_agent.filesystem_copy_semantics import (
    collection_copy_path_guidance,
    completion_errors,
    requested_copy_destinations,
    resolved_collection_copy_destination,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


INSTRUCTION = (
    "Recursively scan the folders of the 'source-set' directory and copy any .png files "
    "found into another directory named 'target-set', preserving the directory hierarchy."
)
SOURCE_PATHS = (
    "/home/user/Desktop/source-set/first.png",
    "/home/user/Desktop/source-set/nested/second.png",
    "/home/user/Desktop/source-set/nested/third.png",
)


def _event(
    step: int,
    action: str,
    body: dict[str, Any],
    *,
    wrapper: bool = False,
) -> ExecutionEvent:
    if wrapper:
        proposed = {
            "kind": "adapter",
            "action": "adapter.call",
            "arguments": {
                "adapter": "os",
                "action": action,
                "payload": {"params": {}},
            },
        }
    else:
        proposed = {
            "kind": "adapter",
            "action": action,
            "arguments": {},
        }
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-09-01T00:00:00Z",
        proposed=proposed,
        executed=True,
        result={
            "status": "ok",
            "result": body,
            "verification": {"passed": True},
        },
    )


def _find_event(*, wrapper: bool = False) -> ExecutionEvent:
    return _event(
        1,
        "filesystem.find",
        {
            "kind": "file",
            "name_patterns": ["*.png"],
            "recursive": True,
            "match_count": len(SOURCE_PATHS),
            "returned_count": len(SOURCE_PATHS),
            "truncated": False,
            "matches": [{"kind": "file", "path": path} for path in SOURCE_PATHS],
        },
        wrapper=wrapper,
    )


def _copy_event(step: int, path: str, *, wrapper: bool = False) -> ExecutionEvent:
    return _event(
        step,
        "filesystem.copy_to_directories",
        {
            "source": path,
            "copied": [f"/home/user/Desktop/target-set/{path.rsplit('/', 1)[-1]}"],
        },
        wrapper=wrapper,
    )


def _single_copy_event(step: int, path: str) -> ExecutionEvent:
    return _event(
        step,
        "filesystem.copy",
        {
            "source": path,
            "destination": f"/home/user/Desktop/target-set/{path.rsplit('/', 1)[-1]}",
        },
    )


def _state(
    events: list[ExecutionEvent], *, instruction: str = INSTRUCTION
) -> RuntimeState:
    return RuntimeState(
        task_id="synthetic-copy-collection",
        domain="os",
        instruction=instruction,
        events=events,
    )


@pytest.mark.parametrize("wrapper", [False, True], ids=["direct", "adapter-call"])
def test_complete_collection_copy_covers_every_find_match(wrapper: bool) -> None:
    events = [_find_event(wrapper=wrapper)]
    events.extend(
        _copy_event(index + 2, path, wrapper=wrapper)
        for index, path in enumerate(SOURCE_PATHS)
    )

    assert completion_errors(_state(events)) == []


@pytest.mark.parametrize("wrapper", [False, True], ids=["direct", "adapter-call"])
def test_incomplete_collection_copy_rejects_completion(wrapper: bool) -> None:
    events = [_find_event(wrapper=wrapper)]
    events.extend(
        _copy_event(index + 2, path, wrapper=wrapper)
        for index, path in enumerate(SOURCE_PATHS[:-1])
    )

    errors = completion_errors(_state(events))

    assert errors
    assert "every file returned by filesystem.find" in errors[0]
    assert "third.png" in errors[0]


def test_repeated_find_preserves_prior_copy_progress() -> None:
    repeated_find = _find_event()
    repeated_find.step = 4
    events = [
        _find_event(),
        _copy_event(2, SOURCE_PATHS[0]),
        _copy_event(3, SOURCE_PATHS[1]),
        repeated_find,
    ]

    errors = completion_errors(_state(events))
    assert errors and SOURCE_PATHS[2] in errors[0]


def test_repeated_find_after_complete_copy_remains_complete() -> None:
    repeated_find = _find_event()
    repeated_find.step = 5
    events = [
        _find_event(),
        *(_copy_event(index + 2, path) for index, path in enumerate(SOURCE_PATHS)),
        repeated_find,
    ]

    assert completion_errors(_state(events)) == []


@pytest.mark.parametrize("instruction", [INSTRUCTION, 'Copy all files matching "*.png" in the current directory tree to "./fails" preserving the directory hierarchy'])
def test_collection_copy_guidance_resolves_relative_destination_from_observed_root(instruction: str) -> None:
    state = _state([_find_event()], instruction=instruction)
    guidance = collection_copy_path_guidance(state)
    assert guidance is not None
    assert ("/home/user/Desktop/source-set/target-set" in guidance) or ("/home/user/Desktop/source-set/fails" in guidance)
    assert "relative parent path" in guidance
    assert "one exact full file path" in guidance
    assert "do not pass a glob" in guidance
    assert "create_parents=true" in guidance


def test_flat_collection_copy_guidance_does_not_invent_source_hierarchy() -> None:
    instruction = (
        "Recursively go through the folders of the 'photos' directory and copy any .jpg "
        "files found into another directory named 'cpjpg'."
    )
    event = _find_event()
    event.result["result"]["name_patterns"] = ["*.jpg"]
    event.result["result"]["matches"] = [
        {"kind": "file", "path": path.replace(".png", ".jpg")}
        for path in SOURCE_PATHS
    ]
    state = _state([event], instruction=instruction)
    guidance = collection_copy_path_guidance(state)

    assert guidance is not None
    assert "flat destination" in guidance
    assert "/home/user/Desktop/cpjpg" in guidance
    assert "original basename" in guidance
    assert "relative parent path" not in guidance
    assert "do not append source subdirectories" in guidance


def test_collection_copy_destination_parser_ignores_source_directory() -> None:
    instruction = (
        "Recursively go through the folders of the 'photos' directory and copy any .jpg "
        "files found into another directory named 'cpjpg'."
    )

    assert requested_copy_destinations(instruction) == ["cpjpg"]


def test_flat_collection_copy_destination_resolves_from_find_evidence() -> None:
    instruction = (
        "Recursively go through the folders of the 'photos' directory and copy any .jpg "
        "files found into another directory named 'cpjpg'."
    )
    event = _find_event()
    event.result["result"]["name_patterns"] = ["*.jpg"]
    event.result["result"]["matches"] = [
        {"kind": "file", "path": path.replace(".png", ".jpg")}
        for path in SOURCE_PATHS
    ]
    state = _state([event], instruction=instruction)

    assert resolved_collection_copy_destination(state) == "/home/user/Desktop/cpjpg"


def test_non_collection_copy_instruction_is_unchanged() -> None:
    events = [_find_event(), _copy_event(2, SOURCE_PATHS[0])]

    assert (
        completion_errors(
            _state(
                events,
                instruction="Copy one observed image.png into an archive directory.",
            )
        )
        == []
    )


def test_collection_find_truncation_fails_closed() -> None:
    event = _find_event()
    event.result["result"]["returned_count"] = len(SOURCE_PATHS) - 1
    event.result["result"]["truncated"] = True
    events = [
        event,
        *(_copy_event(index + 2, path) for index, path in enumerate(SOURCE_PATHS)),
    ]

    errors = completion_errors(_state(events))

    assert errors
    assert "truncated" in errors[0]


def test_wrapper_result_source_paths_remain_model_argument_agnostic() -> None:
    events = [_find_event(wrapper=True), _copy_event(2, SOURCE_PATHS[0], wrapper=True)]
    state = _state(events)
    original_arguments = state.events[1].proposed["arguments"].copy()

    completion_errors(state)

    assert state.events[1].proposed["arguments"] == original_arguments


def test_single_file_copy_facade_counts_toward_collection() -> None:
    events = [_find_event()]
    events.extend(
        _single_copy_event(index + 2, path) for index, path in enumerate(SOURCE_PATHS)
    )

    assert completion_errors(_state(events)) == []
