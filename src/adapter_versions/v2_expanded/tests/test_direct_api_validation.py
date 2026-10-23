from __future__ import annotations

import pytest

from scripts.run_direct_api_validation import validate_operator_command


def test_action_command_is_preserved_unchanged() -> None:
    command = {
        "command": "action",
        "domain": "synthetic_documents",
        "action": "paragraph.set_style",
        "arguments": {
            "path": "/srv/samples/different.odt",
            "paragraphs": [2, 5],
            "font_size": 13,
        },
    }

    assert validate_operator_command(command) == command


@pytest.mark.parametrize(
    "arguments",
    [
        {"task_id": "opaque"},
        {"payload": {"dataset_order": 12}},
        {"items": [{"golden": "answer.bin"}]},
        {"evaluator": {"func": "compare"}},
    ],
)
def test_action_command_rejects_runtime_evaluation_metadata(
    arguments: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="forbidden metadata"):
        validate_operator_command(
            {
                "command": "action",
                "domain": "synthetic",
                "action": "item.update",
                "arguments": arguments,
            }
        )


def test_action_command_rejects_uuid_in_arguments() -> None:
    with pytest.raises(ValueError, match="task UUID"):
        validate_operator_command(
            {
                "command": "action",
                "domain": "synthetic",
                "action": "file.open",
                "arguments": {"path": "/tmp/17f65a2d-808c-4ea3-9ad3-870159c91bd0.txt"},
            }
        )


def test_command_shape_is_fail_closed() -> None:
    with pytest.raises(ValueError, match="keys mismatch"):
        validate_operator_command(
            {
                "command": "action",
                "domain": "synthetic",
                "action": "item.read",
                "arguments": {},
                "task": "hidden",
            }
        )


@pytest.mark.parametrize("name", ["initial-state", "after_02", "final.png"])
def test_screenshot_command_accepts_safe_basenames(name: str) -> None:
    command = {"command": "screenshot", "name": name}
    assert validate_operator_command(command) == command


@pytest.mark.parametrize("name", ["../escape", "two words", "", "/absolute"])
def test_screenshot_command_rejects_unsafe_basenames(name: str) -> None:
    with pytest.raises(ValueError, match="safe"):
        validate_operator_command({"command": "screenshot", "name": name})


def test_finish_has_no_answer_or_action_payload() -> None:
    assert validate_operator_command({"command": "finish"}) == {"command": "finish"}
    with pytest.raises(ValueError, match="keys mismatch"):
        validate_operator_command({"command": "finish", "reward": 1.0})
