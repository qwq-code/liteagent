from __future__ import annotations

from copy import deepcopy

import jsonschema
import pytest

from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import search_actions
from integrations.lite_agent.tool_catalog import build_tools
from os_adapter.archive import create_zip, extract_zip
from os_adapter.errors import AdapterError
from os_adapter.schema import parse_action_request, validate_action_params
from os_adapter.verifier import verify_specs
from os_adapter.worker import _default_specs


CREATE = "archive.create_zip"
EXTRACT = "archive.extract_zip"


def _schema(action: str, wrapped: bool) -> dict:
    if not wrapped:
        return build_tools(
            "os", [action], include_gui=False, include_control_tools=False, strict_generic=True
        )[0]["function"]["parameters"]
    tools = constrain_adapter_call_routes(
        build_tools(
            "multi_apps", ["adapter.call"], include_gui=False, strict_generic=True
        ),
        [("os", action)],
    )
    function = next(
        tool["function"]
        for tool in tools
        if tool["function"]["name"] == "adapter__adapter_call"
    )
    return function["parameters"]["properties"]["payload"]["properties"]["params"]


@pytest.mark.parametrize("wrapped", [False, True])
def test_archive_actions_are_atomic_and_have_distinct_schemas(wrapped: bool) -> None:
    create = _schema(CREATE, wrapped)
    extract = _schema(EXTRACT, wrapped)
    assert set(create["required"]) == {"archive_path", "input_paths"}
    assert set(extract["required"]) == {"archive_path", "destination_directory"}
    assert set(create["properties"]) == {
        "archive_path", "input_paths", "base_directory", "overwrite"
    }
    assert set(extract["properties"]) == {
        "archive_path", "destination_directory", "overwrite"
    }


@pytest.mark.parametrize("wrapped", [False, True])
def test_archive_valid_calls_reach_runtime_contract(wrapped: bool) -> None:
    create = {
        "archive_path": "/tmp/synthetic-bundle.zip",
        "input_paths": ["/tmp/synthetic-notes.txt"],
        "base_directory": "/tmp",
        "overwrite": True,
    }
    extract = {
        "archive_path": "/tmp/synthetic-bundle.zip",
        "destination_directory": "/tmp/synthetic-unpacked",
        "overwrite": True,
    }
    for action, params in ((CREATE, create), (EXTRACT, extract)):
        before = deepcopy(params)
        jsonschema.validate(params, _schema(action, wrapped))
        validate_action_params(action, params)
        assert params == before


@pytest.mark.parametrize("action", [CREATE, EXTRACT])
def test_retired_combined_archive_action_is_rejected(action: str) -> None:
    with pytest.raises(AdapterError):
        parse_action_request(
            {
                "action": "archive.create_extract",
                "params": {"mode": "create", "archive_path": "/tmp/a.zip", "input_paths": ["/tmp/a"]},
            }
        )


def test_archive_actions_reject_cross_mode_fields_with_recovery() -> None:
    with pytest.raises(AdapterError, match="archive.extract_zip"):
        validate_action_params(
            CREATE,
            {
                "archive_path": "/tmp/a.zip",
                "input_paths": ["/tmp/a"],
                "destination_directory": "/tmp/out",
            },
        )
    with pytest.raises(AdapterError, match="archive.create_zip"):
        validate_action_params(
            EXTRACT,
            {
                "archive_path": "/tmp/a.zip",
                "destination_directory": "/tmp/out",
                "input_paths": ["/tmp/a"],
            },
        )


def test_archive_round_trip_and_default_verification(tmp_path) -> None:
    source = tmp_path / "essay.txt"
    source.write_text("synthetic essay\n", encoding="utf-8")
    archive_path = tmp_path / "submission.zip"
    create_params = {"archive_path": str(archive_path), "input_paths": [str(source)]}
    created = create_zip(create_params, 5.0)
    create_specs = _default_specs(CREATE, create_params, created)
    assert verify_specs(create_specs, created)["passed"] is True

    destination = tmp_path / "unpacked"
    extract_params = {
        "archive_path": str(archive_path),
        "destination_directory": str(destination),
    }
    extracted = extract_zip(extract_params, 5.0)
    extract_specs = _default_specs(EXTRACT, extract_params, extracted)
    assert verify_specs(extract_specs, extracted)["passed"] is True
    assert (destination / source.name).read_text(encoding="utf-8") == "synthetic essay\n"


def test_submission_organization_search_does_not_promote_rename() -> None:
    matches = search_actions("os", "organize files for submission")
    actions = [item["action"] for item in matches]
    assert "filesystem.rename" not in actions
    assert "archive.create_zip" in actions
