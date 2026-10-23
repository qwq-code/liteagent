from __future__ import annotations

import base64
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .errors import AdapterError


VLC_HTTP_URL = "http://127.0.0.1:8080/requests/status.xml"


def _authorization() -> str:
    password = os.environ.get("OSWORLD_VLC_PASSWORD", "password")
    token = base64.b64encode(f":{password}".encode()).decode()
    return f"Basic {token}"


def status_request(
    command: str | None = None,
    params: dict[str, str] | None = None,
    timeout: float = 10,
) -> bytes:
    query = dict(params or {})
    if command:
        query["command"] = command
    url = VLC_HTTP_URL
    if query:
        url += "?" + urllib.parse.urlencode(query)
    return _http_get(url, timeout)


def _http_get(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"Authorization": _authorization()})
    try:
        with urllib.request.urlopen(request, timeout=max(0.1, timeout)) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise AdapterError(
            "VLC_NOT_READY",
            "VLC HTTP interface is unavailable",
            {"url": url, "error": str(exc)},
            503,
        ) from exc


def parse_status(content: bytes) -> dict[str, Any]:
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise AdapterError(
            "VLC_NOT_READY", "VLC returned invalid status XML", str(exc), 503
        ) from exc
    metadata: dict[str, str] = {}
    for element in root.findall('information/category[@name="meta"]/info'):
        if element.get("name") and element.text:
            metadata[element.get("name", "")] = element.text
    return {
        "state": root.findtext("state"),
        "fullscreen": root.findtext("fullscreen"),
        "time": root.findtext("time"),
        "length": root.findtext("length"),
        "position": root.findtext("position"),
        "currentplid": root.findtext("currentplid"),
        "loop": root.findtext("loop"),
        "repeat": root.findtext("repeat"),
        "rate": root.findtext("rate"),
        "metadata": metadata,
    }


def read_status(timeout: float = 10) -> dict[str, Any]:
    return parse_status(status_request(timeout=timeout))


def read_playlist_uri(item_id: str, timeout: float = 10) -> str | None:
    content = _http_get(urllib.parse.urljoin(VLC_HTTP_URL, "playlist.xml"), timeout)
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise AdapterError(
            "VLC_NOT_READY", "VLC returned invalid playlist XML", str(exc), 503
        ) from exc
    for leaf in root.iter("leaf"):
        if leaf.get("id") == item_id:
            return leaf.get("uri") or None
    return None


def wait_http(timeout: float, launch: bool = False) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.1, timeout)
    launched = False
    last_error: AdapterError | None = None
    while time.monotonic() < deadline:
        try:
            return {
                **read_status(timeout=min(3, max(0.1, deadline - time.monotonic()))),
                "launched": launched,
            }
        except AdapterError as exc:
            last_error = exc
        if launch and not launched:
            log_path = Path("/tmp/osworld-vlc-adapter-vlc.log")
            log_stream = log_path.open("ab")
            subprocess.Popen(
                ["vlc", "--no-video-title-show"],
                stdin=subprocess.DEVNULL,
                stdout=log_stream,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
                start_new_session=True,
            )
            log_stream.close()
            launched = True
        time.sleep(0.25)
    raise AdapterError(
        "VLC_NOT_READY",
        "VLC HTTP interface did not become ready",
        {"launched": launched, "last_error": str(last_error) if last_error else None},
        503,
    )
