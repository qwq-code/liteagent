from __future__ import annotations

from copy import deepcopy

import jsonschema
import pytest

from vscode_adapter.actions import VscodeActions
from vscode_adapter.errors import AdapterError
from vscode_adapter.schema import parse_action_request
from vscode_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from vscode_adapter.verifier import verify_specs
from vscode_adapter.worker import _default_specs, execute


@pytest.fixture
def text_file(tmp_path):
    path = tmp_path / "unicode notes.txt"
    path.write_text("前缀é🙂\nAlpha beta\n尾行", encoding="utf-8")
    return path


def test_nonzero_unicode_window_is_exact_and_verified(text_file):
    original_bytes = text_file.read_bytes()
    source = text_file.read_text(encoding="utf-8")
    params = {"path": str(text_file), "start_char": 3, "max_chars": 6}
    original_params = deepcopy(params)
    parsed = parse_action_request({"action": "file.read_text", "params": params})
    jsonschema.validate(params, STRICT_ACTION_PARAM_SCHEMAS["file.read_text"])
    output = execute(parsed.to_worker_payload())
    result = output["result"]
    assert output["verification"]["passed"] is True
    assert result["content"] == source[3:9] == "🙂\nAlph"
    assert result["source_start_char"] == 3
    assert result["source_end_char"] == result["next_start_char"] == 9
    assert result["source_total_chars"] == result["total_chars"] == len(source)
    assert result["offset_basis"] == "unicode_characters"
    assert result["source_truncated"] is result["truncated"] is True
    assert result["path"] == str(text_file)
    assert params == original_params
    assert text_file.read_bytes() == original_bytes


@pytest.mark.parametrize("remaining_chars", [0, 2])
def test_eof_and_tail_windows_are_complete(text_file, remaining_chars):
    source = text_file.read_text(encoding="utf-8")
    start = len(source) - remaining_chars
    params = {"path": str(text_file), "start_char": start, "max_chars": 100}
    result = VscodeActions().file_read_text(params, 1)
    assert result["content"] == source[start:]
    assert result["source_end_char"] == len(source)
    assert result["next_start_char"] is None
    assert result["source_truncated"] is result["truncated"] is False
    assert (
        verify_specs(_default_specs("file.read_text", params, result), result)["passed"]
        is True
    )


def test_start_beyond_eof_reports_actual_length(text_file):
    length = len(text_file.read_text(encoding="utf-8"))
    with pytest.raises(AdapterError) as caught:
        VscodeActions().file_read_text(
            {"path": str(text_file), "start_char": length + 1}, 1
        )
    assert caught.value.code == "INVALID_REQUEST"
    assert caught.value.details["source_total_chars"] == length
    assert caught.value.details["start_char"] == length + 1


@pytest.mark.parametrize("start_char", [-1, True, 1.5])
def test_schema_rejects_invalid_character_offset(text_file, start_char):
    with pytest.raises(AdapterError) as caught:
        parse_action_request(
            {
                "action": "file.read_text",
                "params": {
                    "path": str(text_file),
                    "start_char": start_char,
                },
            }
        )
    assert caught.value.code == "INVALID_REQUEST"


def test_verifier_binds_slice_to_requested_offset_not_existing_prefix(tmp_path):
    path = tmp_path / "repeated text.txt"
    path.write_text("SAME---DIFF---SAME", encoding="utf-8")
    wrong_result = VscodeActions().file_read_text(
        {"path": str(path), "max_chars": 4}, 1
    )
    requested = {"path": str(path), "start_char": 7, "max_chars": 4}
    specs = _default_specs("file.read_text", requested, wrong_result)
    verification = verify_specs(specs, wrong_result)
    assert verification["passed"] is False
    observed = verification["checks"][0]["observed"]
    assert observed["prefix_matches"] is True
    assert observed["window_matches"] is False
    assert specs[0]["start_char"] == requested["start_char"]


def test_default_zero_offset_and_legacy_snapshot_remain_compatible(text_file):
    source = text_file.read_text(encoding="utf-8")
    params = {"path": str(text_file)}
    result = VscodeActions().file_read_text(params, 1)
    assert result["content"] == source
    assert result["source_start_char"] == 0
    assert (
        verify_specs(_default_specs("file.read_text", params, result), result)["passed"]
        is True
    )
    legacy = {
        "type": "text_snapshot",
        "path": str(text_file),
        "content": source[:3],
        "total_chars": len(source),
        "truncated": True,
    }
    assert verify_specs([legacy], result)["passed"] is True
    legacy["truncated"] = False
    assert verify_specs([legacy], result)["passed"] is False
