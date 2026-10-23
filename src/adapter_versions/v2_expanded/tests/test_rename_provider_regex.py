import pytest

from os_adapter.errors import AdapterError
from os_adapter.schema import validate_action_params
from os_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


def test_rename_provider_patterns_avoid_unsupported_regex_features() -> None:
    properties = STRICT_ACTION_PARAM_SCHEMAS["filesystem.rename"]["properties"]
    for field in ("source", "destination", "source_query", "new_name"):
        pattern = properties[field]["pattern"]
        assert "(?!" not in pattern
        assert "(?=" not in pattern
        assert "\\x00" not in pattern


@pytest.mark.parametrize("operand", [".", "..", "bad\x00name"])
def test_rename_runtime_still_rejects_invalid_basename(operand: str) -> None:
    with pytest.raises(AdapterError, match="one concrete basename"):
        validate_action_params(
            "filesystem.rename",
            {"source": operand, "destination": "renamed.txt"},
        )
