from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from writer_adapter import service
from writer_adapter.errors import AdapterError


class FakeOffice:
    def __init__(self, clock, *, ready=False, error=None, prepare_seconds=3.0):
        self.clock = clock
        self.ready = ready
        self.error = error
        self.prepare_seconds = prepare_seconds
        self.prepare_calls = []
        self.prepared = {"ready": True, "already_running": False, "port": 2002}

    def listener_ready(self):
        return self.ready

    def prepare(self, timeout_seconds):
        self.prepare_calls.append(timeout_seconds)
        self.clock.now += self.prepare_seconds
        if self.error is not None:
            raise self.error
        self.ready = True
        return deepcopy(self.prepared)


def _client(monkeypatch, *, ready=False, error=None, prepare_seconds=3.0):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(service, "time", SimpleNamespace(monotonic=lambda: clock.now))
    office = FakeOffice(
        clock, ready=ready, error=error, prepare_seconds=prepare_seconds
    )
    requests = []

    def run(parsed):
        requests.append(
            {**deepcopy(parsed.to_worker_payload()), "timeout_ms": parsed.timeout_ms}
        )
        return {
            "result": {"text": "Existing paragraph Ω\n"},
            "verification": {"passed": True},
            "duration_ms": 25,
            "logs": [],
        }

    client = service.create_app(
        lifecycle=office, runner=SimpleNamespace(run=run)
    ).test_client()
    return client, office, requests


def _request(timeout_ms=20_000):
    return {
        "request_id": "synthetic-writer-read",
        "action": "document.read_file",
        "timeout_ms": timeout_ms,
        "document": {"url": "file:///tmp/source%20notes.docx"},
        "params": {"path": "/tmp/source notes.docx", "max_chars": 2048},
        "verify": [{"type": "document_identity", "url": "file:///tmp/source%20notes.docx"}],
    }


@pytest.mark.parametrize("timeout_ms", [6_000, 20_000])
def test_missing_writer_listener_prepares_within_original_budget(
    monkeypatch, timeout_ms
):
    client, office, requests = _client(monkeypatch)
    payload = _request(timeout_ms)
    original = deepcopy(payload)

    response = client.post("/v1/actions", json=payload)

    assert response.status_code == 200, response.get_json()
    assert office.prepare_calls == [min(15.0, timeout_ms / 1000)]
    assert requests == [{**payload, "timeout_ms": timeout_ms - 3_000}]
    result = response.get_json()
    assert result["request_id"] == payload["request_id"]
    assert result["result"]["text"] == "Existing paragraph Ω\n"
    assert result["verification"]["passed"] is True
    assert result["lifecycle"] == {
        "operation": "ensure_listener", "status": "ready", "result": office.prepared
    }
    assert payload == original


def test_ready_writer_dispatches_once_without_preparation(monkeypatch):
    client, office, requests = _client(monkeypatch, ready=True)
    payload = _request()

    response = client.post("/v1/actions", json=payload)

    assert response.status_code == 200, response.get_json()
    assert office.prepare_calls == []
    assert requests == [payload]
    assert response.get_json().get("lifecycle") is None


def test_failed_writer_preparation_keeps_native_error_without_dispatch(monkeypatch):
    error = AdapterError(
        "LIBREOFFICE_NOT_READY", "UNO listener did not become ready", {"port": 2002}, 503
    )
    client, office, requests = _client(monkeypatch, error=error)
    payload = _request()

    response = client.post("/v1/actions", json=payload)

    assert response.status_code == 503
    assert office.prepare_calls == [15.0]
    assert requests == []
    result = response.get_json()
    assert result["request_id"] == payload["request_id"]
    assert result["status"] == "error" and result["result"] is None
    assert result["error"] == {
        "code": error.code, "message": error.message, "details": error.details
    }
    assert result["lifecycle"] == {"operation": "ensure_listener", "status": "failed"}


def test_writer_preparation_cannot_extend_worker_deadline(monkeypatch):
    client, office, requests = _client(monkeypatch, prepare_seconds=6.0)
    payload = _request(timeout_ms=6_000)

    response = client.post("/v1/actions", json=payload)

    assert response.status_code == 504
    assert office.prepare_calls == [6.0]
    assert requests == []
    result = response.get_json()
    assert result["request_id"] == payload["request_id"]
    assert result["error"]["code"] == "TIMEOUT"
    assert result["lifecycle"]["status"] == "ready"
