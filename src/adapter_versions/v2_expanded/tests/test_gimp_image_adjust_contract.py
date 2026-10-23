from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import jsonschema
import pytest

from gimp_adapter.errors import AdapterError
from gimp_adapter.schema import parse_action_request
from gimp_adapter.scriptfu import ScriptFuRunner
from gimp_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools, search_actions


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("make exported photo brighter", ("gimp", "image.adjust")),
        ("adjust picture contrast", ("gimp", "image.adjust")),
        ("reduce photograph saturation", ("gimp", "image.adjust")),
        ("crop image edges", ("gimp", "image.crop")),
        (
            "set slide background image",
            ("libreoffice_impress", "slide.set_background"),
        ),
    ],
)
def test_image_adjustment_search_and_neighboring_operations(query, expected):
    match = search_actions("multi_apps", query, limit=6, strict_generic=True)[0]
    assert (match["adapter"], match["downstream_action"]) == expected


@pytest.mark.parametrize(
    "adjustment", [{"brightness": 17.9}, {"contrast": -4.2}, {"saturation": 28.5}]
)
def test_adjustment_contract_matches_direct_and_forwarded_tools(adjustment):
    params = {
        "input_path": "/tmp/source.png",
        "output_path": "/tmp/result.png",
        **adjustment,
    }
    manifest = STRICT_ACTION_PARAM_SCHEMAS["image.adjust"]
    jsonschema.validate(params, manifest)
    assert (
        parse_action_request({"action": "image.adjust", "params": params}).params
        == params
    )

    tools = build_tools(
        "gimp",
        ["image.adjust"],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )
    jsonschema.validate(params, tools[0]["function"]["parameters"])
    wrapped = constrain_adapter_call_routes(
        build_tools(
            "multi_apps",
            ["adapter.call"],
            include_gui=False,
            include_control_tools=False,
            strict_generic=True,
        ),
        [("gimp", "image.adjust")],
    )
    function = next(
        tool["function"]
        for tool in wrapped
        if tool["function"]["name"] == "adapter__adapter_call"
    )
    jsonschema.validate(
        {"adapter": "gimp", "action": "image.adjust", "payload": {"params": params}},
        function["parameters"],
    )
    for surface in (tools, wrapped):
        assert "positive values brighten" in json.dumps(surface)
        assert "different file" in json.dumps(surface)


def test_manifest_requires_an_adjustment_like_the_existing_adapter():
    params = {"input_path": "/tmp/source.png", "output_path": "/tmp/result.png"}
    with pytest.raises(AdapterError, match="requires an adjustment"):
        parse_action_request({"action": "image.adjust", "params": params})
    assert not jsonschema.Draft202012Validator(
        STRICT_ACTION_PARAM_SCHEMAS["image.adjust"]
    ).is_valid(params)


def test_adjustment_retains_existing_numeric_conversion(monkeypatch):
    runner = ScriptFuRunner()
    operation = Mock(return_value={"result": "synthetic"})
    monkeypatch.setattr(runner, "_run_image_operation", operation)
    params = {
        "input_path": "/tmp/source.png",
        "output_path": "/tmp/result.png",
        "brightness": 17.9,
        "contrast": -4.2,
        "saturation": 28.5,
    }

    runner.adjust(params, 3)

    operation.assert_called_once_with(
        "/tmp/source.png",
        "/tmp/result.png",
        "(gimp-brightness-contrast drawable 17 -4)\n  (gimp-hue-saturation drawable 0 0 0 28.5)",
        open_in_gui=False,
        timeout_seconds=3,
    )
    assert params["brightness"] == 17.9
    assert params["contrast"] == -4.2


@pytest.mark.parametrize("alias", [False, True])
def test_output_collision_preserves_source_and_returns_actionable_error(
    tmp_path, monkeypatch, alias
):
    source = tmp_path / "source.png"
    original = b"synthetic source"
    source.write_bytes(original)
    output = tmp_path / "alias.png" if alias else source
    if alias:
        output.symlink_to(source)
    metadata = Path(str(output) + ".meta.tsv")
    metadata.write_text("preexisting metadata")
    runner = ScriptFuRunner()
    run_scheme = Mock()
    monkeypatch.setattr(runner, "run_scheme", run_scheme)

    with pytest.raises(AdapterError, match="different output_path") as caught:
        runner.adjust(
            {"input_path": str(source), "output_path": str(output), "brightness": 9}, 1
        )

    assert caught.value.code == "INVALID_REQUEST"
    assert source.read_bytes() == original
    assert metadata.read_text() == "preexisting metadata"
    run_scheme.assert_not_called()


def test_separate_output_keeps_source_and_existing_artifact_cleanup(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.png"
    output = tmp_path / "result.png"
    metadata = Path(str(output) + ".meta.tsv")
    source.write_bytes(b"synthetic source")
    output.write_bytes(b"stale output")
    metadata.write_text("stale metadata")
    runner = ScriptFuRunner()

    def run_scheme(body, timeout_seconds):
        assert source.read_bytes() == b"synthetic source"
        assert not output.exists()
        assert not metadata.exists()
        assert "(gimp-brightness-contrast drawable 9 0)" in body
        output.write_bytes(b"synthetic result")
        metadata.write_text("8\t6\tLayer\t8\t6\t0\t0")
        return {"returncode": 0}

    monkeypatch.setattr(runner, "run_scheme", run_scheme)
    result = runner.adjust(
        {"input_path": str(source), "output_path": str(output), "brightness": 9}, 1
    )

    assert result["output_path"] == str(output)
    assert result["metadata"]["image_width"] == 8
    assert source.read_bytes() == b"synthetic source"
