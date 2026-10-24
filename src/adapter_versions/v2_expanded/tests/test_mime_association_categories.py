from __future__ import annotations

import jsonschema
import pytest

from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools
from os_adapter.desktop import set_mime_associations
from os_adapter.errors import AdapterError
from os_adapter.schema import validate_action_params


ACTION = "desktop.mime_associations.set"
DESKTOP_ID = "sample.desktop"


class Runner:
    def __init__(self) -> None:
        self.associations: dict[str, str] = {}
        self.writes: list[str] = []

    def run(self, argv: list[str], **_kwargs: object) -> dict[str, object]:
        if argv[1:3] == ["query", "default"]:
            return {"stdout": self.associations.get(argv[3], "")}
        self.writes.append(argv[3])
        self.associations[argv[3]] = argv[2]
        return {"stdout": ""}


def _application_dir(tmp_path, mime_types: list[str]):
    directory = tmp_path / "applications"
    directory.mkdir()
    (directory / DESKTOP_ID).write_text(
        "[Desktop Entry]\nName=Sample\nType=Application\nMimeType="
        + ";".join(mime_types)
        + ";\n",
        encoding="utf-8",
    )
    return directory


def _schemas(wrapped: bool) -> tuple[dict, dict]:
    if wrapped:
        tools = constrain_adapter_call_routes(
            build_tools("multi_apps", ["adapter.call"], include_gui=False, strict_generic=True),
            [("os", ACTION)],
        )
        parameters = next(
            tool["function"]["parameters"]
            for tool in tools
            if tool["function"]["name"] == "adapter__adapter_call"
        )["properties"]["payload"]["properties"]["params"]
    else:
        parameters = build_tools(
            "os", [ACTION], include_gui=False, include_control_tools=False, strict_generic=True
        )[0]["function"]["parameters"]
    branches = parameters["oneOf"]
    return parameters, branches[0], branches[1]


@pytest.mark.parametrize("wrapped", [False, True])
def test_prefix_expands_all_advertised_types_and_reads_back_each(tmp_path, wrapped):
    mime_types = [f"video/x-format-{index}" for index in range(43)]
    directory = _application_dir(tmp_path, mime_types)
    runner = Runner()
    arguments = {"desktop_id": DESKTOP_ID, "mime_type_prefixes": ["video"]}
    schema, exact_branch, prefix_branch = _schemas(wrapped)

    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(arguments, prefix_branch)
    jsonschema.validate(arguments, schema)
    validate_action_params(ACTION, arguments)
    result = set_mime_associations(runner, arguments, 5, [directory])

    assert result["mime_types"] == sorted(mime_types)
    assert set(result["observed"]) == set(mime_types)
    assert runner.writes == sorted(mime_types)
    assert len(runner.associations) == 43


def test_exact_type_selection_keeps_the_existing_bounded_contract(tmp_path):
    mime_types = [f"video/x-format-{index}" for index in range(23)]
    directory = _application_dir(tmp_path, mime_types)
    runner = Runner()
    selected = mime_types[:2]
    arguments = {"desktop_id": DESKTOP_ID, "mime_types": selected}
    schema, exact_branch, _prefix_branch = _schemas(False)

    jsonschema.validate(arguments, exact_branch)
    jsonschema.validate(arguments, schema)
    validate_action_params(ACTION, arguments)
    result = set_mime_associations(runner, arguments, 5, [directory])

    assert result["mime_types"] == selected
    assert set(result["observed"]) == set(selected)
    assert runner.writes == selected


@pytest.mark.parametrize(
    "arguments",
    [
        {"desktop_id": DESKTOP_ID},
        {"desktop_id": DESKTOP_ID, "mime_types": ["video/mp4"], "mime_type_prefixes": ["video"]},
        {"desktop_id": DESKTOP_ID, "mime_type_prefixes": ["Video"]},
        {"desktop_id": DESKTOP_ID, "mime_type_prefixes": ["video", "video"]},
    ],
)
def test_invalid_selector_combinations_and_values_are_rejected(arguments):
    with pytest.raises(AdapterError):
        validate_action_params(ACTION, arguments)


def test_unadvertised_exact_types_are_rejected(tmp_path):
    directory = _application_dir(tmp_path, ["video/mp4"])

    with pytest.raises(AdapterError, match="not advertised"):
        set_mime_associations(
            Runner(),
            {"desktop_id": DESKTOP_ID, "mime_types": ["audio/ogg"]},
            5,
            [directory],
        )


def test_empty_prefix_expansion_fails_before_writes(tmp_path):
    directory = _application_dir(tmp_path, ["audio/ogg"])
    runner = Runner()

    with pytest.raises(AdapterError, match="no matching MIME types"):
        set_mime_associations(
            runner,
            {"desktop_id": DESKTOP_ID, "mime_type_prefixes": ["video"]},
            5,
            [directory],
        )

    assert runner.writes == []


def test_one_of_branches_are_self_contained():
    _schema, exact_branch, prefix_branch = _schemas(True)

    for branch, selector in ((exact_branch, "mime_types"), (prefix_branch, "mime_type_prefixes")):
        assert branch["type"] == "object"
        assert branch["additionalProperties"] is False
        assert set(branch["required"]) == {"desktop_id", selector}
