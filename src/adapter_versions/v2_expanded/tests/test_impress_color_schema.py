from __future__ import annotations

import jsonschema
import pytest

from impress_adapter.errors import AdapterError
from impress_adapter.tool_manifest import RGB_COLOR, STRICT_ACTION_PARAM_SCHEMAS
from impress_adapter.uno_worker import _color
from integrations.lite_agent.impress_colors import (
    model_color_schema,
    normalize_impress_color,
)
from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS, build_tools


ACTION = "slide.format_text_roles"


def _exposed_schema() -> dict:
    tools = build_tools(
        "libreoffice_impress",
        [ACTION],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )
    return tools[0]["function"]["parameters"]


def test_impress_color_schema_is_adapter_owned_and_shared() -> None:
    manifest = STRICT_ACTION_PARAM_SCHEMAS[ACTION]
    direct = DIRECT_ACTION_SCHEMAS["libreoffice_impress"][ACTION]
    exposed = _exposed_schema()

    assert direct == manifest
    for schema in (manifest["properties"]["color"], exposed["properties"]["color"]):
        assert schema["oneOf"] == RGB_COLOR["oneOf"]
    jsonschema.Draft202012Validator.check_schema(exposed)
    jsonschema.Draft202012Validator.check_schema(model_color_schema())


@pytest.mark.parametrize(
    "value",
    [
        "dark red 2",
        "Dark Red 2",
        "DARK   red  2",
        "  dArK\tReD 2  ",
        "#aBc123",
        0xC9211E,
    ],
)
def test_color_schema_matches_runtime_normalization(value) -> None:
    arguments = {"slide": 0, "roles": ["all"], "color": value}
    for color_schema in (
        _exposed_schema()["properties"]["color"],
        model_color_schema(),
    ):
        assert not list(
            jsonschema.Draft202012Validator(
                {"type": "object", "properties": {"color": color_schema}}
            ).iter_errors({"color": value})
        )
    assert not list(
        jsonschema.Draft202012Validator(_exposed_schema()).iter_errors(arguments)
    )
    assert normalize_impress_color(value) is not None
    if isinstance(value, str):
        assert _color(value) == _color(normalize_impress_color(value))
    else:
        assert _color(value) == value


@pytest.mark.parametrize("value", ["chartreuse", "dark red", "#12345", None, True])
def test_unknown_or_malformed_colors_fail_closed(value) -> None:
    for color_schema in (
        _exposed_schema()["properties"]["color"],
        model_color_schema(),
    ):
        errors = list(
            jsonschema.Draft202012Validator(
                {"type": "object", "properties": {"color": color_schema}}
            ).iter_errors({"color": value})
        )
        assert errors
    with pytest.raises(AdapterError):
        _color(value)
