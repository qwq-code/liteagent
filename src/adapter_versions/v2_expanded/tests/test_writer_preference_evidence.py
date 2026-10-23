from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from integrations.lite_agent.adapter_executor import AdapterExecutor
from integrations.lite_agent.adapter_results import execution_context_summary
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from writer_adapter import uno_worker
from writer_adapter.service import create_app


@pytest.fixture
def native_settings(monkeypatch):
    values = {"Standard": "Liberation Mono"}
    calls = []

    class Access:
        def getPropertyValue(self, key):
            calls.append(("read", key))
            return values[key]

        def setPropertyValue(self, key, value):
            calls.append(("write", key, value))
            values[key] = value

        def commitChanges(self):
            calls.append(("commit",))

    provider = SimpleNamespace(createInstanceWithArguments=lambda *_args: Access())
    session = SimpleNamespace(
        context=object(),
        service_manager=SimpleNamespace(createInstanceWithContext=lambda *_args: provider),
    )
    monkeypatch.setattr(
        uno_worker, "_property", lambda name, value: SimpleNamespace(Name=name, Value=value)
    )
    return session, values, calls


def test_default_font_verifier_reads_native_value_not_requested_value(native_settings):
    session, values, _calls = native_settings
    check = {"type": "default_font", "font_name": "Unobserved Font"}

    assert uno_worker._observed(session, check) == values["Standard"]


def test_default_font_verifier_rejects_mismatched_expectation(native_settings):
    session, values, _calls = native_settings
    verification = uno_worker._verify_requested(
        session,
        [{"type": "default_font", "font_name": "Unobserved Font", "expected": "Unobserved Font"}],
    )

    assert verification["passed"] is False
    assert verification["observed_state"] == {"0": values["Standard"]}


@pytest.mark.parametrize("font_name", ["Noto Sans", "DejaVu Serif"])
def test_preference_receipt_verifies_profile_without_document_file(native_settings, font_name):
    session, values, calls = native_settings
    params = {"font_name": font_name}
    original = deepcopy(params)
    result = uno_worker._set_default_font(session, params)
    verification = uno_worker._implicit_action_verification(
        "settings.set_default_font", session, result
    )

    assert values["Standard"] == font_name
    assert ("commit",) in calls
    assert calls[-1] == ("read", "Standard")
    assert result["font_name"] == font_name
    assert verification["passed"] is True
    assert verification["scope"] == "application_settings"
    assert verification["observed_state"] == {"0": font_name}
    assert all(check["type"] == "default_font" for check in verification["checks"])
    assert params == original


def preference_state(verification, *, wrapped=False, action="settings.set_default_font"):
    result = {"status": "ok", "result": {"font_name": "Noto Sans"}, "verification": verification}
    event = ExecutionEvent(
        step=1,
        timestamp_utc="2026-09-07T00:00:00Z",
        proposed={
            "kind": "adapter", "action": action,
            "arguments": {"font_name": "Noto Sans"},
        },
        executed=True,
        result={"adapter_response": result} if wrapped else result,
    )
    return RuntimeState(
        task_id="synthetic-default-font",
        domain="libreoffice_writer",
        instruction="Make Noto Sans the default font." if action.startswith("settings.") else "Change the document font to Noto Sans.",
        events=[event],
    )


@pytest.mark.parametrize("wrapped", [False, True])
def test_native_settings_readback_can_satisfy_completion_without_document_io(wrapped):
    state = preference_state(
        {"passed": True, "scope": "application_settings", "checks": [{"type": "default_font", "passed": True}]},
        wrapped=wrapped,
    )
    original = deepcopy(state.events[0].proposed)

    assert CompletionMixin._generic_completion_gate(state) == {"passed": True, "missing": []}
    assert state.done is False
    assert state.events[0].proposed == original


def test_document_file_verification_does_not_prove_application_settings():
    state = preference_state(
        {"passed": True, "checks": [{"type": "file_saved", "passed": True}]}
    )

    assert CompletionMixin._generic_completion_gate(state)["passed"] is False


def test_document_font_change_still_requires_document_evidence():
    state = preference_state(
        {"passed": True, "scope": "application_settings"}, action="document.set_font"
    )
    gate = CompletionMixin._generic_completion_gate(state)

    assert gate["passed"] is False
    assert "save the LibreOffice document after the final mutation" in gate["missing"]
    assert "perform structural read-back after the final mutation" in gate["missing"]


def test_later_preference_does_not_clear_an_earlier_document_obligation():
    state = preference_state({"passed": True, "scope": "application_settings"})
    earlier = preference_state({}, action="document.set_font").events[0]
    state.events[0].step = 2
    state.events.insert(0, earlier)

    assert CompletionMixin._generic_completion_gate(state)["passed"] is False


def test_native_preference_evidence_survives_service_executor_and_model_projection(
    native_settings, monkeypatch
):
    session, _values, _calls = native_settings
    monkeypatch.setattr(uno_worker, "WriterSession", lambda _document: session)
    app = create_app(
        lifecycle=SimpleNamespace(listener_ready=lambda: True),
        runner=SimpleNamespace(
            run=lambda request: uno_worker.execute(request.to_worker_payload())
        ),
    )
    client = app.test_client()

    def post(_url, *, json, timeout):
        response = client.post("/v1/actions", json=json)
        return SimpleNamespace(
            ok=response.status_code == 200,
            status_code=response.status_code,
            json=response.get_json,
        )

    monkeypatch.setattr("integrations.lite_agent.adapter_executor.requests.post", post)
    executor = AdapterExecutor({"libreoffice_writer": "http://synthetic-adapter"})
    arguments = {"font_name": "Noto Sans"}
    original = deepcopy(arguments)
    response = executor.execute(
        "libreoffice_writer", "settings.set_default_font", arguments, {}
    )
    state = preference_state({})
    state.events[0].result = response["result"]

    assert response["executed"] is True, response
    assert response["result"]["verification"]["scope"] == "application_settings"
    assert response["result"]["verification"]["observed_state"] == {"0": "Noto Sans"}
    assert CompletionMixin._generic_completion_gate(state)["passed"] is True
    projected = execution_context_summary(state.events, state.domain, strict_generic=True)
    assert projected[0]["result"]["result"]["font_name"] == "Noto Sans"
    assert projected[0]["result"]["verification"]["observed_state"] == {"0": "Noto Sans"}
    assert arguments == original
