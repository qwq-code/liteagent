#!/usr/bin/env python3
"""Small queueing gateway for one shared Qwen3.8 vLLM process.

The gateway deliberately keeps the model process unaware of endpoint classes.  A
short endpoint and a long endpoint share one backend, while a fair admission
controller prevents a queued long request from being starved by new short
requests.  It is intended for a trusted private network, not public exposure.
"""

from __future__ import annotations

import argparse
import http.client
import json
import logging
import signal
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator
from urllib.parse import urlsplit


HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)
CONTROL_PATHS = frozenset(
    {
        "/health",
        "/version",
        "/v1/models",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/metrics",
        "/queue/status",
    }
)
MAX_BODY_BYTES = 128 * 1024 * 1024


class AdmissionController:
    """Fair two-class admission: short work drains before one long request."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._active_short = 0
        self._active_long = False
        self._waiting_long = 0

    @contextmanager
    def slot(self, kind: str) -> Iterator[float]:
        if kind not in {"short", "long"}:
            raise ValueError(f"unsupported endpoint kind: {kind}")
        started = time.monotonic()
        with self._condition:
            if kind == "long":
                self._waiting_long += 1
                try:
                    self._condition.wait_for(
                        lambda: not self._active_long and self._active_short == 0
                    )
                finally:
                    self._waiting_long -= 1
                self._active_long = True
            else:
                self._condition.wait_for(
                    lambda: not self._active_long and self._waiting_long == 0
                )
                self._active_short += 1
        try:
            yield time.monotonic() - started
        finally:
            with self._condition:
                if kind == "long":
                    self._active_long = False
                else:
                    self._active_short -= 1
                self._condition.notify_all()

    def snapshot(self) -> dict[str, int | bool]:
        with self._condition:
            return {
                "active_short": self._active_short,
                "active_long": self._active_long,
                "waiting_long": self._waiting_long,
            }


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        backend: str,
        endpoint_kind: str,
        admission: AdmissionController,
        connect_timeout: float,
        read_timeout: float,
        max_body_bytes: int,
    ) -> None:
        super().__init__(address, handler_class)
        parsed = urlsplit(backend)
        if parsed.scheme != "http" or not parsed.hostname:
            raise ValueError("backend must be an http:// URL")
        self.backend_host = parsed.hostname
        self.backend_port = parsed.port or 80
        self.backend_prefix = parsed.path.rstrip("/")
        self.endpoint_kind = endpoint_kind
        self.admission = admission
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.max_body_bytes = max_body_bytes


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "QwenContextGateway/1.0"

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch()

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._dispatch()

    def _dispatch(self) -> None:
        path = urlsplit(self.path).path
        if path == "/queue/status":
            self._send_json(200, self.server.admission.snapshot())
            return

        if path in CONTROL_PATHS:
            self._proxy(wait_seconds=0.0)
            return

        kind = self.server.endpoint_kind
        with self.server.admission.slot(kind) as wait_seconds:
            self._proxy(wait_seconds=wait_seconds)

    def _read_body(self) -> bytes | None:
        transfer_encoding = self.headers.get("Transfer-Encoding", "").lower()
        if transfer_encoding:
            self._send_json(411, {"error": "chunked requests are not supported"})
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "invalid content length"})
            return None
        if length < 0 or length > self.server.max_body_bytes:
            self._send_json(413, {"error": "request body exceeds gateway limit"})
            return None
        return self.rfile.read(length) if length else b""

    def _proxy(self, *, wait_seconds: float) -> None:
        body = self._read_body()
        if body is None:
            return

        path = f"{self.server.backend_prefix}{self.path}"
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
        }
        headers["X-Context-Gateway-Endpoint"] = self.server.endpoint_kind
        headers["Content-Length"] = str(len(body))
        connection = http.client.HTTPConnection(
            self.server.backend_host,
            self.server.backend_port,
            timeout=self.server.connect_timeout,
        )
        response: http.client.HTTPResponse | None = None
        try:
            connection.connect()
            if connection.sock is not None:
                connection.sock.settimeout(self.server.read_timeout)
            connection.request(self.command, path, body=body, headers=headers)
            response = connection.getresponse()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() in HOP_BY_HOP_HEADERS:
                    continue
                self.send_header(key, value)
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
            logging.info(
                "endpoint=%s method=%s path=%s status=%s wait_ms=%.1f",
                self.server.endpoint_kind,
                self.command,
                urlsplit(self.path).path,
                response.status,
                wait_seconds * 1000,
            )
        except (BrokenPipeError, ConnectionResetError):
            logging.info("client disconnected endpoint=%s", self.server.endpoint_kind)
        except Exception as exc:  # pragma: no cover - exercised by deployment smoke
            logging.error("backend proxy error: %s", type(exc).__name__)
            if not self.wfile.closed:
                self._send_json(502, {"error": "backend unavailable"})
        finally:
            if response is not None:
                response.close()
            connection.close()

    def _send_json(self, status: int, payload: object) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format_string: str, *args: object) -> None:
        logging.info("%s - %s", self.address_string(), format_string % args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="http://127.0.0.1:8101")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--short-port", type=int, default=8001)
    parser.add_argument("--long-port", type=int, default=8003)
    parser.add_argument("--connect-timeout", type=float, default=15.0)
    parser.add_argument("--read-timeout", type=float, default=1800.0)
    parser.add_argument("--max-body-bytes", type=int, default=MAX_BODY_BYTES)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    admission = AdmissionController()
    servers = [
        GatewayServer(
            (args.bind, args.short_port),
            ProxyHandler,
            backend=args.backend,
            endpoint_kind="short",
            admission=admission,
            connect_timeout=args.connect_timeout,
            read_timeout=args.read_timeout,
            max_body_bytes=args.max_body_bytes,
        ),
        GatewayServer(
            (args.bind, args.long_port),
            ProxyHandler,
            backend=args.backend,
            endpoint_kind="long",
            admission=admission,
            connect_timeout=args.connect_timeout,
            read_timeout=args.read_timeout,
            max_body_bytes=args.max_body_bytes,
        ),
    ]
    threads = [
        threading.Thread(
            target=server.serve_forever, name=f"gateway-{server.endpoint_kind}"
        )
        for server in servers
    ]
    for thread in threads:
        thread.start()
    logging.info(
        "gateway ready short=%s:%s long=%s:%s backend=%s",
        args.bind,
        args.short_port,
        args.bind,
        args.long_port,
        args.backend,
    )

    stop_event = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()
        for server in servers:
            server.shutdown()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    stop_event.wait()
    for server in servers:
        server.server_close()
    for thread in threads:
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
