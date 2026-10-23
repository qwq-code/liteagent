from unittest.mock import Mock

import jsonschema
import pytest

from gimp_adapter.errors import AdapterError
from gimp_adapter.schema import parse_action_request
from gimp_adapter import worker
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools, search_actions


def schema(forwarded):
    if not forwarded:
        return build_tools("gimp", ["image.export"], include_gui=False,
                           include_control_tools=False, strict_generic=True)[0]["function"]["parameters"]
    tools = constrain_adapter_call_routes(
        build_tools("multi_apps", ["adapter.call"], include_gui=False,
                    include_control_tools=False, strict_generic=True), [("gimp", "image.export")])
    return tools[0]["function"]["parameters"]["properties"]["payload"]["properties"]["params"]


@pytest.mark.parametrize("forwarded", [False, True])
@pytest.mark.parametrize("extra", [{}, {"loader": "jpeg", "quality": 0.75}])
def test_export_requires_matching_model_and_adapter_parameters(forwarded, extra):
    params = {"input_path": "/tmp/input.xcf", "output_path": "/tmp/output.png", **extra}
    jsonschema.validate(params, schema(forwarded))
    assert parse_action_request({"action": "image.export", "params": params}).params == params


@pytest.mark.parametrize("forwarded", [False, True])
@pytest.mark.parametrize("invalid", [
    {"input_path": "/tmp/in.png", "output_path": "/tmp/out.png", "file_type": "png"},
    {}, {"path": "/tmp/output.png", "file_type": "png"},
    {"input_path": "/tmp/input.xcf"}, {"output_path": "/tmp/output.png"},
    {"input_path": " ", "output_path": "/tmp/output.png"},
    {"input_path": "/tmp/in.png", "output_path": "/tmp/out.png", "quality": 90},
    {"input_path": "/tmp/in.png", "output_path": "/tmp/out.png", "loader": "xcf"},
])
def test_incomplete_or_invented_export_params_are_rejected_on_both_sides(forwarded, invalid):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema(forwarded))
    with pytest.raises(AdapterError):
        parse_action_request({"action": "image.export", "params": invalid})


def test_search_includes_real_required_export_fields():
    hit = search_actions("multi_apps", "gimp image.export", strict_generic=True)[0]
    assert hit["parameter_summary"]["required"] == ["input_path", "output_path"]
    assert "quality" in hit["parameter_summary"]["fields"]


def test_native_dispatch_keeps_model_source_destination_and_quality(monkeypatch):
    runner = Mock()
    runner.export.return_value = {"output_path": "/tmp/chosen.png"}
    monkeypatch.setattr(worker, "ScriptFuRunner", lambda lifecycle: runner)
    monkeypatch.setattr(worker, "verify_specs", lambda checks, result: {"passed": True})
    params = {"input_path": "/tmp/source.xcf", "output_path": "/tmp/chosen.png", "quality": 0.7}
    parsed = parse_action_request({"action": "image.export", "params": params})
    worker.execute({"action": parsed.action, "params": parsed.params, "timeout_ms": 45000})
    runner.export.assert_called_once_with("/tmp/source.xcf", "/tmp/chosen.png",
                                         loader="auto", quality=0.7, timeout_seconds=44.0)
