from __future__ import annotations

import importlib.util
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import requests


MODULE_PATH = (
    Path(__file__).parents[1] / "deployment" / "qwen38-vllm" / "context_gateway.py"
)
SPEC = importlib.util.spec_from_file_location("context_gateway", MODULE_PATH)
assert SPEC and SPEC.loader
gateway = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gateway)


class FakeBackendHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    active = 0
    lock = threading.Lock()
    entered = threading.Event()
    release = threading.Event()

    def do_POST(self) -> None:  # noqa: N802
        with self.lock:
            self.active += 1
        self.entered.set()
        self.release.wait(timeout=5)
        with self.lock:
            self.active -= 1
        payload = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        payload = b"healthy"
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture
def gateway_pair():
    FakeBackendHandler.entered.clear()
    FakeBackendHandler.release.clear()
    backend = ThreadingHTTPServer(("127.0.0.1", 0), FakeBackendHandler)
    backend_thread = threading.Thread(target=backend.serve_forever, daemon=True)
    backend_thread.start()
    admission = gateway.AdmissionController()
    short = gateway.GatewayServer(
        ("127.0.0.1", 0),
        gateway.ProxyHandler,
        backend=f"http://127.0.0.1:{backend.server_port}",
        endpoint_kind="short",
        admission=admission,
        connect_timeout=2,
        read_timeout=5,
        max_body_bytes=1024,
    )
    long = gateway.GatewayServer(
        ("127.0.0.1", 0),
        gateway.ProxyHandler,
        backend=f"http://127.0.0.1:{backend.server_port}",
        endpoint_kind="long",
        admission=admission,
        connect_timeout=2,
        read_timeout=5,
        max_body_bytes=1024,
    )
    threads = [
        threading.Thread(target=short.serve_forever, daemon=True),
        threading.Thread(target=long.serve_forever, daemon=True),
    ]
    for thread in threads:
        thread.start()
    yield short, long, admission
    FakeBackendHandler.release.set()
    short.shutdown()
    long.shutdown()
    backend.shutdown()
    short.server_close()
    long.server_close()
    backend.server_close()


def test_long_request_gets_exclusive_slot_and_short_waits(gateway_pair) -> None:
    short, long, admission = gateway_pair
    short_url = f"http://127.0.0.1:{short.server_port}/v1/chat/completions"
    long_url = f"http://127.0.0.1:{long.server_port}/v1/chat/completions"
    first_done = threading.Event()

    def first_short() -> None:
        requests.post(short_url, data=b"{}", timeout=5)
        first_done.set()

    first = threading.Thread(target=first_short)
    first.start()
    assert FakeBackendHandler.entered.wait(timeout=2)

    long_result: list[requests.Response] = []
    long_thread = threading.Thread(
        target=lambda: long_result.append(
            requests.post(long_url, data=b"{}", timeout=5)
        )
    )
    long_thread.start()
    time.sleep(0.1)
    assert admission.snapshot()["waiting_long"] == 1

    second_result: list[requests.Response] = []
    second = threading.Thread(
        target=lambda: second_result.append(
            requests.post(short_url, data=b"{}", timeout=5)
        )
    )
    second.start()
    time.sleep(0.1)
    assert not second_result

    FakeBackendHandler.release.set()
    first.join(timeout=3)
    long_thread.join(timeout=3)
    second.join(timeout=3)
    assert first_done.is_set()
    assert long_result and long_result[0].status_code == 200
    assert second_result and second_result[0].status_code == 200
    assert admission.snapshot() == {
        "active_short": 0,
        "active_long": False,
        "waiting_long": 0,
    }


def test_control_status_does_not_wait(gateway_pair) -> None:
    short, _long, admission = gateway_pair
    with admission.slot("long"):
        response = requests.get(
            f"http://127.0.0.1:{short.server_port}/queue/status", timeout=2
        )
    assert response.status_code == 200
    assert response.json()["active_long"] is True


def test_body_limit_is_enforced(gateway_pair) -> None:
    short, _long, _admission = gateway_pair
    response = requests.post(
        f"http://127.0.0.1:{short.server_port}/v1/chat/completions",
        data=b"x" * 1025,
        timeout=2,
    )
    assert response.status_code == 413
