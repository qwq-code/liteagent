from copy import deepcopy

import pytest

from writer_adapter.errors import AdapterError, error_payload
from writer_adapter.schema import validate_action_params


@pytest.mark.parametrize("action,extra", [
    ("bookmark.create", {"name": "SelectedSource"}),
    ("cross_reference.insert", {"bookmark_name": "SelectedSource", "display": "text"}),
    ("text.set_format", {"bold": True}),
])
def test_range_mismatch_explains_caller_lengths_and_how_to_read_exact_offsets(action, extra):
    text = "Snow 雪🙂  keep\tspacing"
    params = {
        "paragraph_index": 7,
        "start_offset": 3,
        "end_offset": 15,
        "expected_text": text,
        **extra,
    }
    original = deepcopy(params)

    with pytest.raises(AdapterError) as caught:
        validate_action_params(action, params)

    error = error_payload(caught.value)
    assert error["code"] == "INVALID_REQUEST"
    assert error["details"]["start_offset"] == 3
    assert error["details"]["end_offset"] == 15
    assert error["details"]["range_length"] == 12
    assert error["details"]["text_length"] == len(text)
    assert error["details"]["offset_basis"] == "zero_based_end_exclusive"
    assert f"expected_text length = {len(text)}" in error["message"]
    assert "end_offset - start_offset = 12" in error["message"]
    assert "text.find" in error["message"]
    assert "matched_text becomes expected_text" in error["message"]
    assert params == original


@pytest.mark.parametrize("action,extra", [
    ("bookmark.create", {"name": "SelectedSource"}),
    ("cross_reference.insert", {"bookmark_name": "SelectedSource", "display": "text"}),
])
def test_reference_empty_insertion_range_remains_valid(action, extra):
    params = {
        "paragraph_index": 7,
        "start_offset": 3,
        "end_offset": 3,
        "expected_text": "",
        **extra,
    }
    original = deepcopy(params)

    validate_action_params(action, params)

    assert params == original
