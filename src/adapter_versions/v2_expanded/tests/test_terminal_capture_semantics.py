from __future__ import annotations

import pytest

from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.terminal_capture_semantics import completion_errors


INSTRUCTION = (
    "Run uname -a in a terminal and save a screenshot of that terminal window as "
    "~/Desktop/kernel-audit.png."
)
TERMINAL_TITLE = "OSWorld OS Adapter Terminal Output synthetic"


def _show_event(step: int, window_id: str = "0x04a00001") -> ExecutionEvent:
    arguments = {
        "argv": ["uname", "-a"],
        "cwd_source": "home",
        "provenance": "shell_history",
    }
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-08-31T00:00:00Z",
        proposed={
            "kind": "adapter",
            "action": "terminal.show_output",
            "arguments": arguments,
        },
        executed=True,
        result={
            "verification": {"passed": True},
            "result": {
                **arguments,
                "returncode": 0,
                "completion_marker": "[command exited with status 0]",
                "terminal": {
                    "title": TERMINAL_TITLE,
                    "windows": [f"{window_id} 0 user host {TERMINAL_TITLE}"],
                    "command_completed": True,
                    "output_visible": True,
                },
                "verified": True,
            },
        },
    )


def _capture_event(
    step: int,
    *,
    window_id: str = "0x04a00001",
    selected_path: str = "~/Desktop/kernel-audit.png",
    observed_path: str = "/home/user/Desktop/kernel-audit.png",
    verified: bool = True,
) -> ExecutionEvent:
    arguments = {
        "title_contains": TERMINAL_TITLE,
        "output_path": selected_path,
        "overwrite": True,
    }
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-08-31T00:00:00Z",
        proposed={
            "kind": "adapter",
            "action": "window.capture",
            "arguments": arguments,
        },
        executed=True,
        result={
            "verification": {"passed": verified},
            "result": {
                "title_contains": TERMINAL_TITLE,
                "window_id": window_id,
                "window": f"{window_id} 0 user host {TERMINAL_TITLE}",
                "output_path": observed_path,
                "verified": verified,
            },
        },
    )


def _errors(events: list[ExecutionEvent], instruction: str = INSTRUCTION) -> list[str]:
    return completion_errors(
        RuntimeState(
            task_id="synthetic-terminal-capture",
            domain="os",
            instruction=instruction,
            events=events,
        )
    )


def test_capture_before_terminal_output_cannot_satisfy_handoff() -> None:
    errors = _errors([_capture_event(1), _show_event(2)])

    assert len(errors) == 1
    assert "captured after terminal.show_output" in errors[0]


def test_capture_of_different_window_cannot_satisfy_handoff() -> None:
    errors = _errors(
        [_show_event(1, "0x04a00001"), _capture_event(2, window_id="0x04a00002")]
    )

    assert len(errors) == 1
    assert "same Adapter-confirmed terminal window" in errors[0]


def test_matching_capture_after_terminal_output_satisfies_handoff() -> None:
    assert _errors([_show_event(1), _capture_event(2)]) == []


@pytest.mark.parametrize(
    ("capture",),
    [
        (_capture_event(2, verified=False),),
        (_capture_event(2, observed_path="/home/user/Desktop/other.png"),),
    ],
    ids=["unverified", "output-path-mismatch"],
)
def test_unverified_or_mismatched_capture_cannot_satisfy_handoff(
    capture: ExecutionEvent,
) -> None:
    assert _errors([_show_event(1), capture])


def test_non_terminal_screenshot_instruction_is_unchanged() -> None:
    instruction = (
        "Save a screenshot of the current Writer document as "
        "~/Desktop/document-audit.png."
    )

    assert _errors([], instruction) == []
