"""Malformed envelopes must be explained, never silently executed."""
import copy

import pytest

from integrations.lite_agent.atomic_tool_surface import atomic_provider_surface
from integrations.lite_agent.model_client import StructuredToolProtocolError
from test_atomic_provider_surface import client_call, wrapper
from test_protocol_recovery import RecordingModelClient, _agent, _large_state


def test_direct_function_name_wrapper_is_rejected_with_specific_feedback():
    name = "adapter__debugging_configure"
    tools = [{"type": "function", "function": {
        "name": name, "description": "Configure debugger",
        "parameters": {"type": "object", "properties": {
            "focus_editor_on_break": {"type": "boolean"}},
            "required": ["focus_editor_on_break"], "additionalProperties": False},
    }}]
    bad = {name: {"focus_editor_on_break": False}}
    before = copy.deepcopy(bad)
    with pytest.raises(StructuredToolProtocolError) as exc:
        client_call(tools, name, bad)
    assert "function name is already selected" in exc.value.schema_hints[0]
    assert bad == before
    result, request = client_call(tools, name, {"focus_editor_on_break": False})
    assert result["arguments_raw"] == '{"focus_editor_on_break": false}'
    assert request["tool_choice"] == "required"
    assert "Do not nest arguments under the function name" in request["messages"][0]["content"]


@pytest.mark.parametrize("envelope", ["payload", "arguments", "adapter__adapter_call"])
def test_atomic_legacy_envelopes_stay_invalid_and_recovery_uses_flat_contract(envelope):
    tools = wrapper()
    surface, _ = atomic_provider_surface(tools)
    name = surface[0]["function"]["name"]
    with pytest.raises(StructuredToolProtocolError) as exc:
        client_call(tools, name, {envelope: {"private-marker": "not-for-feedback"}})
    hints = exc.value.schema_hints
    assert "atomic function, not adapter.call" in hints[0]
    assert "private-marker" not in str(hints)
    assert "not-for-feedback" not in str(hints)
    messages = _agent(RecordingModelClient())._messages(
        _large_state(), b"png", protocol_recovery=True,
        protocol_error={"tool": name, "schema_hints": list(hints)},
    )
    assert "Regenerate its flat parameters" in messages[0]["content"]
    assert "call that wrapper on the next turn" not in messages[0]["content"]
