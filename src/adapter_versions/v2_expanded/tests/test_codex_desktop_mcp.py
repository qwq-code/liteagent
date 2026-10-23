from __future__ import annotations

import base64
import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from integrations.codex_agent.desktop_mcp import DesktopMCP


@pytest.fixture(autouse=True)
def ocr(monkeypatch):
    reader = Mock(
        return_value={
            "status": "ok",
            "engine": "tesseract",
            "language": "eng",
            "items": [
                {
                    "text": "Save",
                    "box": [10, 10, 30, 20],
                    "center": [25, 20],
                    "confidence": 95.0,
                }
            ],
            "truncated": False,
        }
    )
    monkeypatch.setattr("integrations.codex_agent.desktop_mcp.read_screenshot", reader)
    return reader


@pytest.fixture
def guest():
    png = io.BytesIO()
    Image.new("RGB", (83, 47), "white").save(png, format="PNG")
    state = SimpleNamespace(
        requests=[],
        png=png.getvalue(),
        screenshot_status=200,
        execute_body={"status": "success", "returncode": 0, "output": "", "error": ""},
        adapter_body={"status": "ok", "result": {"playing": False}},
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            state.requests.append((self.path, None))
            assert self.path == "/screenshot"
            self.send_response(state.screenshot_status)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(state.png)

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.requests.append((self.path, payload))
            body = state.execute_body if self.path == "/execute" else state.adapter_body
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _text(result):
    return json.loads(result["content"][0]["text"])


@pytest.mark.parametrize("tool", ["click", "double_click"])
def test_wrong_arguments_return_schema_then_corrected_call_executes(
    guest, tmp_path, tool
):
    server = DesktopMCP(guest.url, tmp_path)
    invalid = server.call_tool(tool, {"x": 12, "y": 4})
    assert invalid["isError"] is True
    assert "required" in _text(invalid)["detail"]
    schema = _text(invalid)["inputSchema"]
    assert schema["required"] == ["text"]
    assert set(schema["properties"]) == {"text", "occurrence", "seconds"}
    assert schema["properties"]["text"]["minLength"] == 1
    assert schema["properties"]["occurrence"]["minimum"] == 1
    assert guest.requests == []

    server.call_tool("screenshot", {})
    raw = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": {"text": "Save"}},
        }
    )
    corrected = server.dispatch(json.loads(raw), raw_request=raw)["result"]
    assert corrected["isError"] is False
    route, payload = guest.requests[1]
    assert route == "/execute"
    assert payload["shell"] is False
    assert payload["command"][:2] == ["python", "-c"]
    function = "click" if tool == "click" else "doubleClick"
    assert f"pyautogui.{function}(25, 20" in payload["command"][2]
    assert "time.sleep(0.5)" in payload["command"][2]
    compile(payload["command"][2], "<guest-script>", "exec")
    assert [path for path, _ in guest.requests] == [
        "/screenshot",
        "/execute",
        "/screenshot",
    ]
    assert corrected["content"][2]["mimeType"] == "image/png"
    assert base64.b64decode(corrected["content"][2]["data"]) == guest.png
    records = [json.loads(line) for line in server.trace_path.read_text().splitlines()]
    assert records[4]["raw_request"] == raw
    assert records[5]["arguments"] == {"text": "Save"}
    conversion = records[5]["conversion"]
    assert "ocr_text_center.v1" in conversion["contract"]
    assert conversion["gui_arguments"]["x"] == 25
    assert conversion["gui_arguments"]["y"] == 20
    assert conversion["ocr_target"]["target"] == "1:1"
    assert conversion["ocr_target"]["text"] == "Save"
    assert conversion["ocr_target"]["box"] == [10, 10, 30, 20]
    assert conversion["ocr_target"]["center"] == [25, 20]
    assert conversion["ocr_target"]["screenshot"]
    assert (
        records[5]["post_action_observation"]["screenshot"]["file"]
        == "screenshot-0002.png"
    )


def test_guest_execution_error_is_visible_and_does_not_end_server(guest, tmp_path):
    server = DesktopMCP(guest.url, tmp_path)
    server.call_tool("screenshot", {})
    guest.execute_body = {
        "status": "success",
        "returncode": 1,
        "error": "No active display",
    }
    failed = server.call_tool("press", {"key": "enter"})
    assert failed["isError"] is True
    assert "No active display" in _text(failed)["detail"]
    assert "key" in _text(failed)["inputSchema"]["properties"]
    assert server.call_tool("click", {"text": "Save"})["isError"] is True

    guest.execute_body = {"status": "success", "returncode": 0}
    assert server.call_tool("press", {"key": "tab"})["isError"] is False
    assert "time.sleep(0.5)" in guest.requests[2][1]["command"][2]
    assert [path for path, _ in guest.requests] == [
        "/screenshot",
        "/execute",
        "/execute",
        "/screenshot",
    ]


def test_screenshot_is_an_image_and_saved_with_original_dimensions(guest, tmp_path):
    server = DesktopMCP(guest.url, tmp_path)
    result = server.call_tool("screenshot", {})
    assert result["isError"] is False
    assert "83 x 47" in result["content"][0]["text"]
    image = result["content"][1]
    assert image["mimeType"] == "image/png"
    assert base64.b64decode(image["data"]) == guest.png
    assert (tmp_path / "screenshot-0001.png").read_bytes() == guest.png


def test_observation_uses_same_pixels_for_ocr_and_separate_image_numbers(
    guest, tmp_path, ocr
):
    server = DesktopMCP(guest.url, tmp_path, ocr_language="eng+chi_sim")
    first = server.call_tool("screenshot", {})
    changed_png = io.BytesIO()
    Image.new("RGB", (83, 47), "blue").save(changed_png, format="PNG")
    guest.png = changed_png.getvalue()
    second = server.call_tool("click", {"text": "Save"})
    third = server.call_tool("screenshot", {})
    assert all(not result["isError"] for result in (first, second, third))
    assert len(list(tmp_path.glob("screenshot-*.png"))) == 3
    assert (tmp_path / "screenshot-0002.png").read_bytes() == guest.png
    assert base64.b64decode(second["content"][2]["data"]) == guest.png
    for result, content_index in (
        (first, 2),
        (second, 3),
        (third, 2),
    ):
        observation = json.loads(
            result["content"][content_index]["text"].split("\n", 1)[1]
        )
        assert observation["items"] == [{"text": "Save", "confidence": 95.0}]
        assert "box" not in json.dumps(observation)
        assert "center" not in json.dumps(observation)
    assert ocr.call_args_list[1].args == (guest.png,)
    assert ocr.call_args.kwargs["language"] == "eng+chi_sim"
    assert 0 < ocr.call_args.kwargs["timeout"] <= 5
    assert server.calls == 3
    records = [json.loads(line) for line in server.trace_path.read_text().splitlines()]
    assert records[1]["ocr"]["items"] == ocr.return_value["items"]


def test_missing_observation_or_text_returns_feedback_without_clicking(
    guest, tmp_path, ocr
):
    server = DesktopMCP(guest.url, tmp_path)
    missing = server.call_tool("click", {"text": "Save"})
    assert missing["isError"] is True
    assert "screenshot" in _text(missing)["detail"].lower()
    assert guest.requests == []
    server.call_tool("screenshot", {})
    ocr.return_value["items"][0]["text"] = "Open"
    server.call_tool("screenshot", {})
    for text in ("Save", "Account Settings"):
        rejected = server.call_tool("click", {"text": text})
        assert rejected["isError"] is True
        assert "screenshot" in _text(rejected)["detail"].lower()
        assert _text(rejected)["inputSchema"]["required"] == ["text"]
    assert [path for path, _ in guest.requests] == ["/screenshot", "/screenshot"]
    assert server.call_tool("click", {"text": "Open"})["isError"] is False
    ocr.return_value["items"] = []
    assert server.call_tool("screenshot", {})["isError"] is False
    assert server.call_tool("click", {"text": "Open"})["isError"] is True
    assert [path for path, _ in guest.requests].count("/execute") == 1


def test_duplicate_ocr_text_needs_explicit_occurrence(guest, tmp_path, ocr):
    ocr.return_value["items"].append(
        {
            "text": "Save",
            "box": [60, 10, 20, 20],
            "center": [70, 20],
            "confidence": 90.0,
        }
    )
    server = DesktopMCP(guest.url, tmp_path)
    server.call_tool("screenshot", {})
    ambiguous = server.call_tool("click", {"text": "Save"})
    assert ambiguous["isError"] is True
    detail = _text(ambiguous)["detail"]
    assert all(value in detail for value in ("occurrence", "Save", "1", "2"))
    assert [path for path, _ in guest.requests] == ["/screenshot"]
    selected = server.call_tool("click", {"text": "Save", "occurrence": 2})
    assert selected["isError"] is False
    assert "pyautogui.click(70, 20)" in guest.requests[1][1]["command"][2]


def test_ocr_text_matches_normalized_exact_before_unique_substring(
    guest, tmp_path, ocr
):
    ocr.return_value["items"].extend(
        [
            {
                "text": "Save As",
                "box": [50, 10, 30, 20],
                "center": [65, 20],
                "confidence": 91.0,
            },
            {
                "text": "Account  Settings",
                "box": [5, 30, 70, 15],
                "center": [40, 37],
                "confidence": 92.0,
            },
        ]
    )
    server = DesktopMCP(guest.url, tmp_path)
    server.call_tool("screenshot", {})
    exact = server.call_tool("click", {"text": "  sAvE  "})
    assert exact["isError"] is False
    assert "pyautogui.click(25, 20)" in guest.requests[1][1]["command"][2]
    partial = server.call_tool("click", {"text": "account settings", "seconds": 0})
    assert partial["isError"] is False
    assert "pyautogui.click(40, 37)" in guest.requests[3][1]["command"][2]
    assert "time.sleep(0)" in guest.requests[3][1]["command"][2]
    substring = server.call_tool("click", {"text": "Settings"})
    assert substring["isError"] is False
    assert "pyautogui.click(40, 37)" in guest.requests[5][1]["command"][2]


def test_post_action_screenshot_failure_preserves_executed_result(guest, tmp_path, ocr):
    server = DesktopMCP(guest.url, tmp_path)
    server.call_tool("screenshot", {})
    guest.screenshot_status = 503
    result = server.call_tool("click", {"text": "Save"})
    assert result["isError"] is False
    assert _text(result)["executed"] is True
    assert "503" in result["content"][1]["text"]
    assert [path for path, _ in guest.requests] == [
        "/screenshot",
        "/execute",
        "/screenshot",
    ]
    assert ocr.call_count == 1
    record = json.loads(server.trace_path.read_text().splitlines()[-1])
    assert record["http_status"] == 200
    assert record["post_action_observation"]["http_status"] == 503
    assert server.call_tool("click", {"text": "Save"})["isError"] is True
    assert [path for path, _ in guest.requests].count("/execute") == 1


def test_failed_screenshot_request_invalidates_previous_targets(guest, tmp_path):
    server = DesktopMCP(guest.url, tmp_path)
    server.call_tool("screenshot", {})
    guest.screenshot_status = 503
    assert server.call_tool("screenshot", {})["isError"] is True
    assert server.call_tool("click", {"text": "Save"})["isError"] is True
    assert [path for path, _ in guest.requests] == ["/screenshot", "/screenshot"]


@pytest.mark.parametrize("unexpected_error", [False, True])
def test_ocr_failure_keeps_action_result_and_image(
    guest, tmp_path, ocr, unexpected_error
):
    server = DesktopMCP(guest.url, tmp_path)
    server.call_tool("screenshot", {})
    if unexpected_error:
        ocr.side_effect = TimeoutError("OCR timeout")
    else:
        ocr.return_value = {"status": "error", "detail": "OCR timeout"}
    result = server.call_tool("press", {"key": "tab"})
    assert result["isError"] is False
    assert _text(result)["executed"] is True
    assert base64.b64decode(result["content"][2]["data"]) == guest.png
    assert "OCR timeout" in result["content"][3]["text"]
    assert server.call_tool("click", {"text": "Save"})["isError"] is True
    assert [path for path, _ in guest.requests] == [
        "/screenshot",
        "/execute",
        "/screenshot",
    ]


def test_ocr_can_be_disabled_without_disabling_screenshots(guest, tmp_path, ocr):
    server = DesktopMCP(guest.url, tmp_path, ocr_language=None)
    result = server.call_tool("wait", {"seconds": 0})
    assert result["isError"] is False
    assert len(result["content"]) == 3
    assert result["content"][2]["type"] == "image"
    assert not ocr.called
    assert server.call_tool("click", {"text": "Save"})["isError"] is True
    assert [path for path, _ in guest.requests].count("/execute") == 1


def test_stdio_initialize_discovery_and_protocol_errors_do_not_execute(guest, tmp_path):
    server = DesktopMCP(guest.url, tmp_path)
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "resources/list"},
        {"jsonrpc": "2.0", "id": 4, "method": "resources/templates/list"},
        {"jsonrpc": "2.0", "id": 5, "method": "resources/read"},
        {"jsonrpc": "2.0", "id": 6, "method": "ping"},
    ]
    source = io.StringIO(
        "malformed\n" + "\n".join(json.dumps(request) for request in requests)
    )
    sink = io.StringIO()
    server.serve(source, sink)
    responses = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert responses[0]["error"]["code"] == -32700
    assert responses[1]["result"]["protocolVersion"] == "2025-06-18"
    assert {tool["name"] for tool in responses[2]["result"]["tools"]} == {
        "screenshot",
        "click",
        "double_click",
        "type",
        "press",
        "hotkey",
        "scroll",
        "wait",
    }
    assert responses[3]["result"] == {"resources": []}
    assert responses[4]["result"] == {"resourceTemplates": []}
    assert responses[5]["error"]["code"] == -32601
    assert responses[6]["result"] == {}
    assert guest.requests == []


def test_call_and_time_budgets_stop_dispatch_without_retry(guest, tmp_path):
    server = DesktopMCP(guest.url, tmp_path, max_calls=1)
    assert server.call_tool("wait", {"seconds": 0})["isError"] is False
    exhausted = server.call_tool("click", {"text": "Save"})
    assert exhausted["isError"] is True
    assert _text(exhausted)["budget_exhausted"] is True
    assert len(guest.requests) == 2

    server = DesktopMCP(guest.url, tmp_path / "expired")
    server.deadline = 0
    exhausted = server.call_tool("screenshot", {})
    assert exhausted["isError"] is True
    assert _text(exhausted)["budget_exhausted"] is True
    assert len(guest.requests) == 2


def test_server_pid_is_available_while_serving_and_removed_at_eof(tmp_path):
    server = DesktopMCP("http://guest.invalid:5000", tmp_path)

    class Input(io.StringIO):
        def __iter__(self):
            assert json.loads((tmp_path / "server.json").read_text()) == {
                "pid": os.getpid()
            }
            return super().__iter__()

    server.serve(Input(), io.StringIO())
    assert not (tmp_path / "server.json").exists()


def test_optional_adapter_uses_specific_schema_and_preserves_errors(guest, tmp_path):
    server = DesktopMCP(guest.url, tmp_path, adapter_urls={"vlc": guest.url})
    name = next(
        name
        for name, route in server.adapter_routes.items()
        if route == ("vlc", "playback.status")
    )
    assert all(route[1] != "adapter.call" for route in server.adapter_routes.values())
    result = server.call_tool(name, {})
    assert result["isError"] is False
    path, payload = guest.requests[0]
    assert path == "/v1/actions"
    assert payload["adapter"] == "vlc"
    assert payload["action"] == "playback.status"
    assert payload["params"] == {}

    guest.adapter_body = {
        "status": "error",
        "error": {"detail": "Player is not running"},
    }
    failed = server.call_tool(name, {})
    assert failed["isError"] is True
    assert "Player is not running" in json.dumps(failed)
    assert "Tool parameter schema" in failed["content"][1]["text"]
