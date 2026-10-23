from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from impress_adapter import service
from impress_adapter.errors import AdapterError


def _client(monkeypatch, *, ready=False, prepare_error=None, worker_error=None):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(service, "time", SimpleNamespace(monotonic=lambda: clock.now))
    prepare_calls, worker_calls = [], []
    prepared = {"ready": True, "attached_to_running": True, "port": 2002}

    def prepare(timeout_seconds, *, restart_existing=True):
        prepare_calls.append((timeout_seconds, restart_existing))
        clock.now += 3.0
        if prepare_error is not None:
            raise prepare_error
        return prepared

    def run(parsed):
        worker_calls.append({**deepcopy(parsed.to_worker_payload()), "timeout_ms": parsed.timeout_ms})
        if worker_error is not None:
            raise worker_error
        return {"result": {"count": 2}, "verification": {"passed": True}}

    office = SimpleNamespace(listener_ready=lambda: ready, prepare=prepare)
    app = service.create_app(lifecycle=office, runner=SimpleNamespace(run=run))
    return app.test_client(), prepare_calls, worker_calls, prepared


def _request(timeout_ms=20_000):
    return {
        "request_id": "synthetic-impress-mutation",
        "action": "shape.delete",
        "timeout_ms": timeout_ms,
        "document": {"title": "Synthetic deck"},
        "params": {"slide": 0, "selector": {"name": "Disposable note"}},
        "verify": [{"type": "slide_count", "expected": 3}],
    }


@pytest.mark.parametrize("timeout_ms", [6000, 20_000])
def test_passive_listener_recovery_preserves_semantics_and_original_request_budget(
    monkeypatch, timeout_ms,
):
    client, prepare_calls, worker_calls, prepared = _client(monkeypatch)
    payload = _request(timeout_ms)
    original = deepcopy(payload)

    response = client.post("/v1/actions", json=payload)

    assert response.status_code == 200, response.get_json()
    assert prepare_calls == [(min(15.0, timeout_ms / 1000), False)]
    assert worker_calls == [{**original, "timeout_ms": timeout_ms - 3000}]
    assert response.get_json()["lifecycle"] == {
        "operation": "ensure_listener", "status": "ready", "result": prepared,
    }
    assert response.get_json()["result"] == {"count": 2}
    assert payload == original


def test_ready_listener_does_not_prepare_or_rewrite_the_request(monkeypatch):
    client, prepare_calls, worker_calls, _ = _client(monkeypatch, ready=True)
    payload = _request()

    response = client.post("/v1/actions", json=payload)

    assert response.status_code == 200
    assert prepare_calls == []
    assert worker_calls == [payload]
    assert "lifecycle" not in response.get_json()


def test_expired_startup_budget_does_not_execute_the_mutation(monkeypatch):
    client, prepare_calls, worker_calls, _ = _client(monkeypatch)

    response = client.post("/v1/actions", json=_request(2000))

    assert response.status_code == 504
    assert response.get_json()["error"]["code"] == "TIMEOUT"
    assert response.get_json()["lifecycle"]["status"] == "ready"
    assert prepare_calls == [(2.0, False)]
    assert worker_calls == []


def test_passive_failure_preserves_real_error_and_does_not_execute_mutation(monkeypatch):
    error = AdapterError(
        "LIBREOFFICE_NOT_READY", "listener stayed closed",
        {"live_processes": ["soffice.bin"], "last_exit_code": 0}, 503,
    )
    client, prepare_calls, worker_calls, _ = _client(monkeypatch, prepare_error=error)

    response = client.post("/v1/actions", json=_request())

    assert response.status_code == 503
    assert response.get_json()["error"] == {
        "code": error.code, "message": error.message, "details": error.details,
    }
    assert response.get_json()["lifecycle"] == {
        "operation": "ensure_listener", "status": "failed",
    }
    assert prepare_calls == [(15.0, False)]
    assert worker_calls == []


def test_bridge_failure_after_dispatch_is_returned_without_replaying_mutation(monkeypatch):
    error = AdapterError(
        "INTERNAL_ERROR", "Binary URP bridge already disposed", http_status=500
    )
    client, prepare_calls, worker_calls, _ = _client(monkeypatch, worker_error=error)

    response = client.post("/v1/actions", json=_request())

    assert response.status_code == 500
    assert response.get_json()["error"]["message"] == error.message
    assert len(worker_calls) == 1
    assert prepare_calls == [(15.0, False)]
    assert response.get_json()["lifecycle"]["status"] == "ready"
