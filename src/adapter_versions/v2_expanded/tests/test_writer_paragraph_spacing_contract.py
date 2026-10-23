from __future__ import annotations

from copy import deepcopy
from typing import Any

import jsonschema
import pytest

from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS, build_tools
from writer_adapter.errors import AdapterError
from writer_adapter.schema import parse_action_request, validate_action_params
from writer_adapter.service import create_app
from writer_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


ACTIONS = ("paragraph.replace_text", "document.append_paragraphs")


def _arguments(action: str, paragraphs: list[str], gap: int | None) -> dict[str, Any]:
    arguments: dict[str, Any] = {"paragraphs": paragraphs}
    if action == "paragraph.replace_text":
        arguments["index"] = 4
    else:
        arguments["blank_paragraphs_before"] = 1
    if gap is not None:
        arguments["blank_paragraphs_between"] = gap
    return arguments


def _exposed_tool(action: str) -> dict[str, Any]:
    tools = build_tools(
        "libreoffice_writer",
        [action],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )
    return tools[0]


def _exposed_schema(action: str) -> dict[str, Any]:
    return _exposed_tool(action)["function"]["parameters"]


@pytest.mark.parametrize("action", ACTIONS)
def test_spacing_rule_is_adapter_owned_and_model_visible(action: str) -> None:
    manifest = STRICT_ACTION_PARAM_SCHEMAS[action]

    assert DIRECT_ACTION_SCHEMAS["libreoffice_writer"][action] == manifest
    tool = _exposed_tool(action)
    exposed = tool["function"]["parameters"]
    jsonschema.Draft202012Validator.check_schema(exposed)
    assert exposed["allOf"] == manifest["allOf"]
    assert "explicit blank strings" in tool["function"]["description"]


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize(
    ("paragraphs", "gap"),
    [
        (["Alpha.", "Beta!"], 1),
        (["  Alpha.  ", "Beta!"], 2),
        (["North\u2019s notes.", "\u201cKeep this wording.\u201d"], 1),
        (["Alpha.", "", "Beta!"], 0),
        (["Alpha.", "", "", "Beta!"], None),
        (["If this stays one string! So does this text."], 1),
    ],
)
def test_legal_spacing_representations_are_accepted_without_rewrite(
    action: str, paragraphs: list[str], gap: int | None
) -> None:
    arguments = _arguments(action, paragraphs, gap)
    original = deepcopy(arguments)

    assert not list(
        jsonschema.Draft202012Validator(_exposed_schema(action)).iter_errors(arguments)
    )
    validate_action_params(action, arguments)
    parsed = parse_action_request(
        {
            "request_id": "synthetic-spacing-request",
            "adapter": "libreoffice_writer",
            "action": action,
            "params": arguments,
        }
    )

    assert arguments == original
    assert parsed.params == original


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("blank", ["", " \t\n"])
def test_automatic_spacing_rejects_explicit_blank_strings_without_rewrite(
    action: str, blank: str
) -> None:
    arguments = _arguments(action, ["Alpha.", blank, "Beta!"], 1)
    original = deepcopy(arguments)

    assert list(
        jsonschema.Draft202012Validator(_exposed_schema(action)).iter_errors(arguments)
    )
    with pytest.raises(AdapterError) as raised:
        validate_action_params(action, arguments)

    assert arguments == original
    assert raised.value.code == "INVALID_REQUEST"
    assert raised.value.details == {
        "conflicting_fields": ["paragraphs", "blank_paragraphs_between"],
        "allowed_modes": [
            {
                "mode": "automatic_spacing",
                "paragraphs": "non_blank_strings",
                "blank_paragraphs_between": "positive_integer",
            },
            {
                "mode": "explicit_spacing",
                "paragraphs": "blank_strings_allowed",
                "blank_paragraphs_between": 0,
            },
        ],
    }


class _MustNotReachLifecycle:
    def listener_ready(self) -> bool:
        raise AssertionError("invalid spacing reached Writer lifecycle")


class _MustNotReachWorker:
    def run(self, _request: Any) -> dict[str, Any]:
        raise AssertionError("invalid spacing reached Writer worker")


@pytest.mark.parametrize("action", ACTIONS)
def test_parse_rejects_spacing_conflict_before_lifecycle_or_worker(action: str) -> None:
    app = create_app(
        lifecycle=_MustNotReachLifecycle(),
        runner=_MustNotReachWorker(),
    )
    response = app.test_client().post(
        "/v1/actions",
        json={
            "request_id": "synthetic-pre-mutation-request",
            "adapter": "libreoffice_writer",
            "action": action,
            "params": _arguments(action, ["Alpha.", "   ", "Beta!"], 1),
        },
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["details"]["allowed_modes"][0]["mode"] == ("automatic_spacing")
