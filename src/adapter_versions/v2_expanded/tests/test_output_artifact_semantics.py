from __future__ import annotations

from typing import Any

import pytest

from integrations.lite_agent.output_artifact_semantics import (
    completion_errors,
    requested_output_targets,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


def _event(step: int, action: str, arguments: dict[str, Any], result: dict[str, Any]) -> ExecutionEvent:
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-10-24T00:00:00Z",
        proposed={"kind": "adapter", "action": action, "arguments": arguments},
        executed=True,
        result={"status": "ok", "result": result, "verification": {"passed": True}},
    )


def _state(instruction: str, events: list[ExecutionEvent]) -> RuntimeState:
    return RuntimeState(
        task_id="synthetic-output-artifact",
        domain="multi_apps",
        instruction=instruction,
        events=events,
    )


def test_requested_output_targets_covers_zip_text_and_named_document() -> None:
    instruction = (
        "Save the output to 'System_Resources_Report.txt' on Desktop, then compress "
        "the folder into '/home/user/Desktop/presenter.zip'. Create a document named "
        "'gemini_results.docx'."
    )

    assert requested_output_targets(instruction) == [
        "System_Resources_Report.txt",
        "/home/user/Desktop/presenter.zip",
        "gemini_results.docx",
    ]


@pytest.mark.parametrize("verb", ["name", "title"])
def test_imperative_filename_requires_observed_output(verb: str) -> None:
    instruction = f'Convert the audio and {verb} the file "Interview Mix.mp3".'
    assert requested_output_targets(instruction) == ["Interview Mix.mp3"]
    assert completion_errors(_state(instruction, []))
    assert not completion_errors(_state(instruction, [
        _event(1, "media.extract_audio", {},
               {"output_path": "/home/user/Desktop/Interview Mix.mp3"}),
    ]))


def test_named_input_is_not_misclassified_as_missing_output() -> None:
    instruction = 'Read the file named "source.csv" and save the result as "output.xlsx".'
    assert requested_output_targets(instruction) == ["output.xlsx"]
    assert not completion_errors(_state(instruction, [
        _event(1, "workbook.save", {}, {"path": "/tmp/output.xlsx"}),
    ]))


def test_sentence_period_inside_filename_quotes() -> None:
    assert requested_output_targets('Convert the audio and title the file "Song.mp3."') == [
        "Song.mp3",
    ]


@pytest.mark.parametrize("path,accepted", [
    ("/home/alex/authors.xlsx", True),
    ("file:///home/alex/authors.xlsx", True),
    ("/root/authors.xlsx", True),
    ("~/authors.xlsx", True),
    ("/tmp/authors.xlsx", False),
    ("/home/alex/Desktop/authors.xlsx", False),
    ("/home/alex/Authors.xlsx", False),
])
def test_home_relative_destination_matches_actual_save_path(path, accepted):
    state = _state('Save the table as "~/authors.xlsx".', [
        _event(1, "workbook.save", {}, {"path": path}),
    ])
    assert (completion_errors(state) == []) is accepted


def test_completion_requires_named_output_evidence() -> None:
    instruction = "Compress the folder into '/home/user/Desktop/presenter.zip'."
    state = _state(
        instruction,
        [_event(1, "archive.create_zip", {"input_paths": ["/tmp/presenter"]}, {"member_count": 1})],
    )

    errors = completion_errors(state)

    assert errors and "presenter.zip" in errors[0]


def test_completion_accepts_nested_archive_path_evidence() -> None:
    instruction = "Compress the folder into '/home/user/Desktop/presenter.zip'."
    state = _state(
        instruction,
        [
            _event(
                1,
                "archive.create_zip",
                {"archive_path": "/home/user/Desktop/presenter.zip"},
                {
                    "archive_path": "/home/user/Desktop/presenter.zip",
                    "archive_size_bytes": 120,
                    "integrity_verified": True,
                },
            )
        ],
    )

    assert completion_errors(state) == []


def test_command_output_path_is_counted_for_desktop_report() -> None:
    instruction = "Run sar and save the output to 'System_Resources_Report.txt' on Desktop."
    state = RuntimeState(
        task_id="synthetic-terminal-output",
        domain="os",
        instruction=instruction,
        events=[
            _event(
                1,
                "command.run",
                {"argv": ["sar"], "stdout_path": "/home/user/Desktop/System_Resources_Report.txt"},
                {"stdout_path": "/home/user/Desktop/System_Resources_Report.txt", "output_saved": True},
            )
        ],
    )

    assert completion_errors(state) == []
