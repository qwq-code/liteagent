from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from impress_adapter import uno_worker
from impress_adapter.errors import AdapterError
from impress_adapter.schema import parse_action_request
from impress_adapter.service import create_app
from integrations.lite_agent.adapter_executor import AdapterExecutor
from integrations.lite_agent.recovery_surface import last_failure_summary
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


class NativeShape:
    ShapeType = "com.sun.star.drawing.CustomShape"
    Name = "Synthetic constrained shape"

    def __init__(self, *, ignore_height=False):
        self.Position = SimpleNamespace(X=300, Y=500)
        self._size = SimpleNamespace(Width=2400, Height=1200)
        self.ignore_height = ignore_height

    @property
    def Size(self):
        return deepcopy(self._size)

    @Size.setter
    def Size(self, value):
        self._size.Width = value.Width
        if not self.ignore_height:
            self._size.Height = value.Height


class NativeText:
    value = "Alpha\nBeta Alpha"

    def __init__(self, ignored_weights=()):
        self.ignored_weights = set(ignored_weights)
        self.properties = [
            {"CharWeight": 100, "CharHeight": 18} for _ in self.value
        ]

    def getString(self):
        return self.value

    def createTextCursor(self):
        text = self

        class Cursor:
            start = 0
            end = 0

            def gotoStart(self, _select):
                self.start = self.end = 0

            def gotoEnd(self, _select):
                self.end = len(text.value)

            def goRight(self, count, select):
                self.end += count
                if not select:
                    self.start = self.end

            def setPropertyValue(self, name, value):
                for index in range(self.start, self.end):
                    if name != "CharWeight" or index not in text.ignored_weights:
                        text.properties[index][name] = int(value)

            def getPropertyValue(self, name):
                values = {
                    item[name] for item in text.properties[self.start:self.end]
                }
                return values.pop() if len(values) == 1 else None

        return Cursor()


def arguments():
    return {
        "slide": 1, "selector": {"path": [2, 1]},
        "width_measurement": {"value": 6, "unit": "cm"},
        "height_measurement": {"value": 4, "unit": "cm"},
    }


def install_session(monkeypatch, shape):
    session = SimpleNamespace(
        page=lambda _index: SimpleNamespace(Width=16000, Height=9000),
        shape=lambda _page, _selector: shape,
    )
    monkeypatch.setattr(uno_worker, "ImpressSession", lambda _document: session)
    return session


def test_native_size_refusal_returns_failure_with_actual_partial_state(monkeypatch):
    shape = NativeShape(ignore_height=True)
    install_session(monkeypatch, shape)
    params = arguments()
    original = deepcopy(params)
    payload = parse_action_request({"action": "shape.set_geometry", "params": params})

    with pytest.raises(AdapterError) as failure:
        uno_worker.execute(payload.to_worker_payload())

    assert failure.value.code == "VERIFICATION_FAILED"
    assert failure.value.http_status == 422
    details = failure.value.details
    assert details["state_may_have_changed"] is True
    assert details["selector"] == original["selector"]
    observed = details["observed"]
    assert observed["verification_passed"] is False
    assert observed["resolved_geometry"] == {"width": 6000, "height": 4000}
    assert (observed["width"], observed["height"]) == (6000, 1200)
    assert observed["path"] == [2, 1]
    assert shape.Size.Width == 6000
    assert params == original


def test_successful_native_geometry_keeps_observed_identity_and_verification(monkeypatch):
    shape = NativeShape()
    install_session(monkeypatch, shape)
    params = arguments()
    original = deepcopy(params)
    payload = parse_action_request({"action": "shape.set_geometry", "params": params})

    response = uno_worker.execute(payload.to_worker_payload())

    assert response["verification"]["passed"] is True
    assert response["result"]["verification_passed"] is True
    assert response["result"]["path"] == [2, 1]
    assert (response["result"]["width"], response["result"]["height"]) == (6000, 4000)
    assert params == original


@pytest.mark.parametrize("action", ["shape.fit_to_slide", "shape.insert_image"])
def test_existing_native_failure_flags_are_not_overridden_by_empty_checks(monkeypatch, action):
    install_session(monkeypatch, NativeShape())
    observed = {"verification_passed": False, "name": "Synthetic image", "width": 1400}
    monkeypatch.setitem(uno_worker.ACTIONS, action, lambda _session, _params: observed)

    with pytest.raises(AdapterError) as failure:
        uno_worker.execute({"action": action, "params": {}, "verify": []})

    assert failure.value.details["observed"] == observed
    assert failure.value.details["action"] == action


def test_native_failure_reaches_http_executor_and_model_recovery(monkeypatch):
    install_session(monkeypatch, NativeShape(ignore_height=True))
    client = create_app(
        lifecycle=SimpleNamespace(listener_ready=lambda: True),
        runner=SimpleNamespace(run=lambda parsed: uno_worker.execute(parsed.to_worker_payload())),
    ).test_client()
    captured = []

    def post(_url, *, json, timeout):
        captured.append(deepcopy(json))
        response = client.post("/v1/actions", json=json)
        return SimpleNamespace(
            ok=response.status_code == 200,
            status_code=response.status_code,
            json=response.get_json,
        )

    monkeypatch.setattr("integrations.lite_agent.adapter_executor.requests.post", post)
    params = arguments()
    result = AdapterExecutor({"libreoffice_impress": "http://synthetic"}).execute(
        "libreoffice_impress", "shape.set_geometry", params, {}
    )

    assert result["executed"] is False
    assert result["http_status"] == 422
    assert result["error"]["error"]["code"] == "VERIFICATION_FAILED"
    assert result["error"]["error"]["details"]["observed"]["height"] == 1200
    assert captured[0]["params"] == params
    state = RuntimeState(
        task_id="synthetic-native-geometry",
        domain="libreoffice_impress",
        instruction="Resize the selected object.",
        events=[ExecutionEvent(
            step=1, timestamp_utc="2026-09-09T00:00:00Z",
            proposed={"kind": "adapter", "action": "shape.set_geometry", "arguments": params},
            executed=False, error=result["error"],
        )],
    )
    summary = last_failure_summary(state)
    assert summary["error_type"] == "VERIFICATION_FAILED"
    assert "native read-back" in summary["error_hint"]


@pytest.mark.parametrize("accept_url", [True, False])
def test_audio_insert_checks_native_url_and_returns_partial_failure(
    monkeypatch, tmp_path, accept_url
):
    audio = tmp_path / "Synthetic intro.wav"
    audio.write_bytes(b"synthetic audio")

    class Media:
        _url = ""

        @property
        def MediaURL(self):
            return self._url

        @MediaURL.setter
        def MediaURL(self, value):
            if accept_url:
                self._url = value

    shapes = [NativeShape()]
    page = SimpleNamespace(
        add=shapes.append, getCount=lambda: len(shapes), getByIndex=shapes.__getitem__
    )
    session = SimpleNamespace(
        doc=SimpleNamespace(createInstance=lambda _: Media()),
        page=lambda _: page,
        shape=lambda selected_page, selector: selected_page.getByIndex(selector["index"]),
    )
    monkeypatch.setattr(uno_worker, "ImpressSession", lambda _: session)
    monkeypatch.setattr(uno_worker, "_file_url", lambda value: Path(value).as_uri())
    monkeypatch.setattr(uno_worker, "_uno_modules", lambda: (
        SimpleNamespace(createUnoStruct=lambda _, x, y: SimpleNamespace(
            X=x, Y=y, Width=x, Height=y
        )), None,
    ))
    client = create_app(
        lifecycle=SimpleNamespace(listener_ready=lambda: True),
        runner=SimpleNamespace(run=lambda parsed: uno_worker.execute(parsed.to_worker_payload())),
    ).test_client()
    params = {"slide": 2, "path": audio.as_uri()}
    original = deepcopy(params)
    response = client.post("/v1/actions", json={"action": "audio.insert", "params": params})
    body = response.get_json()

    assert params == original
    assert len(shapes) == 2
    if accept_url:
        assert response.status_code == 200
        assert body["result"]["shape_index"] == 1
        verification = body["verification"]
        assert verification["passed"] is True
        assert verification["observed_state"]["0"]["media_url"] == audio.as_uri()
    else:
        assert response.status_code == 422
        assert body["error"]["code"] == "VERIFICATION_FAILED"
        details = body["error"]["details"]
        assert details["state_may_have_changed"] is True
        assert details["selector"] == {"index": 1}
        assert details["observed"]["media_url"] == ""
        verification = details["verification"]
        assert verification["passed"] is False
    assert verification["checks"] == [
        {"index": 0, "type": "shape_properties", "passed": accept_url}
    ]
    assert verification["expected_state"]["0"] == {"media_url": audio.as_uri()}


@pytest.mark.parametrize(
    "scope,selected",
    [
        ({}, set(range(16))),
        ({"lines": [1]}, set(range(6, 16))),
        ({"match_text": "Alpha"}, set(range(5)) | set(range(11, 16))),
    ],
)
def test_text_format_returns_native_values_for_only_the_selected_text(
    monkeypatch, scope, selected
):
    text = NativeText()
    install_session(monkeypatch, SimpleNamespace(getText=lambda: text, ParaAdjust="CENTER"))
    params = {"slide": 1, "selector": {"path": [2, 1]}, "bold": True, **scope}
    original = deepcopy(params)
    payload = parse_action_request({"action": "shape.format_text", "params": params})

    response = uno_worker.execute(payload.to_worker_payload())

    # The native test backend returns int 150; the requested UNO value is 150.0.
    assert response["result"]["properties"] == {"CharWeight": "150"}
    assert response["verification"]["passed"] is True
    assert [item["CharWeight"] for item in text.properties] == [
        150 if index in selected else 100 for index in range(16)
    ]
    assert params == original


def test_ineffective_text_weight_write_reports_observed_partial_state(monkeypatch):
    text = NativeText(ignored_weights=range(16))
    install_session(monkeypatch, SimpleNamespace(getText=lambda: text, ParaAdjust="CENTER"))
    params = {
        "slide": 1, "selector": {"path": [2, 1]}, "bold": True, "font_size": 22,
    }
    original = deepcopy(params)
    payload = parse_action_request({"action": "shape.format_text", "params": params})

    with pytest.raises(AdapterError) as failure:
        uno_worker.execute(payload.to_worker_payload())

    assert failure.value.code == "VERIFICATION_FAILED"
    assert failure.value.http_status == 422
    assert failure.value.details["mismatches"] == {
        "CharWeight": {"expected": "150.0", "observed": "100"},
    }
    assert failure.value.details["selector"] == original["selector"]
    assert failure.value.details["state_may_have_changed"] is True
    assert all(item == {"CharWeight": 100, "CharHeight": 22} for item in text.properties)
    assert params == original


def test_text_format_checks_every_selected_occurrence(monkeypatch):
    text = NativeText(ignored_weights=range(11, 16))
    install_session(monkeypatch, SimpleNamespace(getText=lambda: text, ParaAdjust="CENTER"))
    params = {
        "slide": 1, "selector": {"path": [2, 1]}, "bold": True, "match_text": "Alpha",
    }
    payload = parse_action_request({"action": "shape.format_text", "params": params})

    with pytest.raises(AdapterError) as failure:
        uno_worker.execute(payload.to_worker_payload())

    assert failure.value.code == "VERIFICATION_FAILED"
    assert failure.value.details["span"] == {"start": 11, "length": 5}
    assert failure.value.details["mismatches"]["CharWeight"]["observed"] == "100"
