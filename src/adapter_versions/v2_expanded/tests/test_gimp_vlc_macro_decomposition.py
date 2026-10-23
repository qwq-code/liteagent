from __future__ import annotations

import pytest

import gimp_adapter.worker as gimp_worker
from gimp_adapter.errors import AdapterError as GimpAdapterError
from gimp_adapter.schema import ACTIONS as GIMP_ACTIONS
from gimp_adapter.schema import parse_action_request as parse_gimp_request
from gimp_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS as GIMP_SCHEMAS
from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS, build_tools
from integrations.openapa_osworld.tool_catalog import public_actions
from multi_apps_adapter.actions import MultiAppsActions
from multi_apps_adapter.errors import AdapterError as MultiAppsAdapterError
from multi_apps_adapter.schema import ACTIONS as MULTI_APPS_ACTIONS
from multi_apps_adapter.schema import parse_action_request as parse_multi_apps_request
from multi_apps_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as MULTI_APPS_SCHEMAS,
)
from vlc_adapter.actions import VlcActions
from vlc_adapter.errors import AdapterError as VlcAdapterError
from vlc_adapter.schema import ACTIONS as VLC_ACTIONS
from vlc_adapter.schema import parse_action_request as parse_vlc_request
from vlc_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS as VLC_SCHEMAS
from vlc_adapter.worker import execute as execute_vlc


GIMP_MACRO = "image.rearrange_equal_sections"
GIMP_RETIRED_FACADES = frozenset({"image.replace_background", "ui.open_action"})
VLC_MACRO = "media.frame_to_wallpaper"
VLC_RETIRED_FACADES = frozenset({VLC_MACRO, "media.flip_vertical"})


def test_gimp_rearrangement_macro_is_absent_from_public_surfaces() -> None:
    for surface in (GIMP_ACTIONS, GIMP_SCHEMAS, MULTI_APPS_ACTIONS, MULTI_APPS_SCHEMAS):
        assert GIMP_MACRO not in surface

    assert {"image.crop", "image.export", "layer.add", "layer.translate"}.issubset(
        GIMP_ACTIONS
    )
    assert "image.crop" in GIMP_SCHEMAS


def test_gimp_task_shaped_facades_are_absent_from_all_runtime_surfaces() -> None:
    public = set(public_actions("gimp"))
    direct = set(DIRECT_ACTION_SCHEMAS["gimp"])
    for action in GIMP_RETIRED_FACADES:
        assert action not in GIMP_ACTIONS
        assert action not in GIMP_SCHEMAS
        assert action not in public
        assert action not in direct

        with pytest.raises(GimpAdapterError) as parsed_error:
            parse_gimp_request({"action": action, "params": {}})
        assert parsed_error.value.code == "UNSUPPORTED_ACTION"

        with pytest.raises(GimpAdapterError) as dispatch_error:
            gimp_worker.execute({"action": action, "params": {}})
        assert dispatch_error.value.code == "UNSUPPORTED_ACTION"

    assert not hasattr(gimp_worker, "replace_background")
    assert not hasattr(gimp_worker, "open_action")


def test_gimp_inspect_requires_exact_path_across_adapter_and_model_contracts() -> None:
    manifest = GIMP_SCHEMAS["image.inspect"]
    assert manifest["required"] == ["path"]
    assert set(manifest["properties"]) == {"path"}
    assert DIRECT_ACTION_SCHEMAS["gimp"]["image.inspect"] == manifest

    tool = build_tools(
        "gimp",
        ["image.inspect"],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )[0]
    parameters = tool["function"]["parameters"]
    assert parameters["required"] == ["path"]
    assert set(parameters["properties"]) == {"path"}

    with pytest.raises(GimpAdapterError, match="params.path"):
        parse_gimp_request({"action": "image.inspect", "params": {}})
    parsed = parse_gimp_request(
        {"action": "image.inspect", "params": {"path": "/tmp/input.png"}}
    )
    assert parsed.params == {"path": "/tmp/input.png"}


def test_vlc_wallpaper_macro_is_absent_and_atomic_steps_remain_public() -> None:
    assert VLC_MACRO not in VLC_ACTIONS
    assert VLC_MACRO not in VLC_SCHEMAS
    assert "media.extract_frame" in VLC_ACTIONS
    assert not hasattr(VlcActions, "media_frame_to_wallpaper")


def test_gimp_rejects_retired_macro_at_parse_and_worker_boundaries() -> None:
    with pytest.raises(GimpAdapterError) as parsed_error:
        parse_gimp_request({"action": GIMP_MACRO, "params": {}})
    assert parsed_error.value.code == "UNSUPPORTED_ACTION"

    with pytest.raises(GimpAdapterError) as dispatch_error:
        gimp_worker.execute({"action": GIMP_MACRO, "params": {}})
    assert dispatch_error.value.code == "UNSUPPORTED_ACTION"
    assert not hasattr(gimp_worker, "rearrange_equal_sections")


def test_multi_apps_rejects_retired_gimp_facade() -> None:
    with pytest.raises(MultiAppsAdapterError) as parsed_error:
        parse_multi_apps_request({"action": GIMP_MACRO, "params": {}})
    assert parsed_error.value.code == "UNSUPPORTED_ACTION"

    with pytest.raises(MultiAppsAdapterError) as dispatch_error:
        MultiAppsActions().dispatch(GIMP_MACRO, {}, 0.1)
    assert dispatch_error.value.code == "UNSUPPORTED_ACTION"


def test_vlc_rejects_retired_macro_at_parse_and_worker_boundaries() -> None:
    for action in VLC_RETIRED_FACADES:
        with pytest.raises(VlcAdapterError) as parsed_error:
            parse_vlc_request({"action": action, "params": {}})
        assert parsed_error.value.code == "UNSUPPORTED_ACTION"

        with pytest.raises(VlcAdapterError) as dispatch_error:
            execute_vlc({"action": action, "params": {}})
        assert dispatch_error.value.code == "UNSUPPORTED_ACTION"

    assert not hasattr(VlcActions, "media_flip_vertical")


def test_vlc_frame_extraction_requires_explicit_source_and_position() -> None:
    with pytest.raises(VlcAdapterError) as current_error:
        parse_vlc_request(
            {
                "action": "media.extract_frame",
                "params": {
                    "output_path": "/tmp/frame.png",
                    "current_playback": True,
                },
            }
        )
    assert current_error.value.code == "INVALID_REQUEST"

    parsed = parse_vlc_request(
        {
            "action": "media.extract_frame",
            "params": {
                "input_path": "/tmp/source.mp4",
                "output_path": "/tmp/frame.png",
                "time_seconds": 8,
            },
        }
    )
    assert parsed.params == {
        "input_path": "/tmp/source.mp4",
        "output_path": "/tmp/frame.png",
        "time_seconds": 8,
    }
