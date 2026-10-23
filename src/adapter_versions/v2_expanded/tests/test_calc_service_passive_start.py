from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from calc_adapter import service
from calc_adapter.errors import AdapterError


class FakeOffice:
    def __init__(self, clock, *, ready=False, error=None):
        self.clock = clock
        self.ready = ready
        self.error = error
        self.prepare_calls = []
        self.prepared = {"ready": True, "already_running": False, "port": 2002}

    def listener_ready(self):
        return self.ready

    def prepare(self, timeout_seconds, *, restart_existing=True):
        self.prepare_calls.append((timeout_seconds, restart_existing))
        self.clock.now += 3.0
        if self.error is not None:
            raise self.error
        self.ready = True
        return deepcopy(self.prepared)


def _client(monkeypatch, *, ready=False, error=None):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(service, "time", SimpleNamespace(monotonic=lambda: clock.now))
    office = FakeOffice(clock, ready=ready, error=error)
    requests = []

    def run(parsed):
        requests.append({**deepcopy(parsed.to_worker_payload()), "timeout_ms": parsed.timeout_ms})
        return {
            "result": {"sheet": "Data", "display_text": [["0042", None, "Ω"]]},
            "verification": {"passed": True},
            "duration_ms": 25,
            "logs": [],
        }

    client = service.create_app(
        lifecycle=office, runner=SimpleNamespace(run=run),
    ).test_client()
    return client, office, requests


def _request(timeout_ms=20_000):
    return {
        "request_id": "synthetic-calc-read",
        "action": "workbook.read_file",
        "timeout_ms": timeout_ms,
        "params": {"path": "/tmp/report Ω.xlsx", "sheet": "Data", "range": "B2:D5"},
    }


@pytest.mark.parametrize("timeout_ms", [6000, 20_000])
def test_stopped_calc_starts_passively_within_original_request_budget(
    monkeypatch, timeout_ms,
) -> None:
    client, office, requests = _client(monkeypatch)
    payload = _request(timeout_ms)
    original = deepcopy(payload)

    response = client.post("/v1/actions", json=payload)

    assert response.status_code == 200, response.get_json()
    assert office.prepare_calls == [(min(timeout_ms / 1000, 15.0), False)]
    assert len(requests) == 1
    assert requests[0]["action"] == payload["action"]
    assert requests[0]["params"] == payload["params"]
    assert requests[0]["request_id"] == payload["request_id"]
    assert requests[0]["timeout_ms"] == timeout_ms - 3000
    result = response.get_json()
    assert result["lifecycle"] == {
        "operation": "ensure_listener", "status": "ready", "result": office.prepared,
    }
    assert result["result"]["display_text"] == [["0042", None, "Ω"]]
    assert result["verification"]["passed"] is True
    assert payload == original


def test_ready_calc_executes_without_preparing(monkeypatch) -> None:
    client, office, requests = _client(monkeypatch, ready=True)
    payload = _request()

    response = client.post("/v1/actions", json=payload)

    assert response.status_code == 200, response.get_json()
    assert office.prepare_calls == []
    assert len(requests) == 1
    assert requests[0]["params"] == payload["params"]
    assert requests[0]["timeout_ms"] == payload["timeout_ms"]
    assert response.get_json().get("lifecycle") is None


def test_passive_prepare_failure_keeps_typed_error_and_does_not_run_worker(
    monkeypatch,
) -> None:
    error = AdapterError(
        "LIBREOFFICE_NOT_READY",
        "LibreOffice is running without the required listener",
        {"live_processes": ["soffice.bin"]},
        503,
    )
    client, office, requests = _client(monkeypatch, error=error)
    payload = _request()

    response = client.post("/v1/actions", json=payload)

    assert response.status_code == 503
    assert office.prepare_calls == [(15.0, False)]
    assert requests == []
    result = response.get_json()
    assert result["request_id"] == payload["request_id"]
    assert result["status"] == "error" and result["result"] is None
    assert result["error"] == {
        "code": error.code, "message": error.message, "details": error.details,
    }
    assert result["lifecycle"] == {"operation": "ensure_listener", "status": "failed"}
