"""Small MCP stdio server for an explicitly selected OSWorld guest.

This is a development tool transport, not an evaluator or an episode runner.
All desktop execution happens over HTTP on the configured guest. No local
desktop, task definitions, evaluator, or reference artifacts are accessed.
"""

from __future__ import annotations

import argparse
import base64
import copy
import io
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlsplit

import jsonschema
import requests
from PIL import Image

from integrations.codex_agent.screenshot_ocr import read_screenshot
from integrations.lite_agent.adapter_executor import AdapterExecutor
from integrations.lite_agent.gui_actions import (
    GUI_ACTION_SCHEMA,
    build_gui_command,
    normalize_gui_arguments,
)
from integrations.lite_agent.tool_catalog import (
    DIRECT_ACTION_SCHEMAS,
    FORBIDDEN_DATASET_ACTIONS,
    build_tools,
    public_actions,
)


GUI_DESCRIPTIONS = {
    "click": "Left-click visible text from the latest OCR result. "
    'For example {"text":"Save"}. A unique substring also works. '
    "If several matches exist, specify occurrence (1-based, in OCR list order).",
    "double_click": "Double left-click visible text from the latest OCR result. "
    'For example {"text":"Documents"}. A unique substring also works. '
    "If several matches exist, specify occurrence (1-based, in OCR list order).",
    "type": "Type literal text into the focused field using the guest keyboard. "
    "Supports ASCII keyboard characters; use an Adapter for Unicode text.",
    "press": "Press one key, for example enter, tab, esc, backspace or left.",
    "hotkey": 'Press a key combination in order, for example ["ctrl","s"].',
    "scroll": "Scroll vertically at the current pointer: positive amount goes up, "
    "negative goes down. Amount is wheel clicks.",
    "wait": "Wait the given seconds (0 to 10) for the guest UI to settle.",
}

# Match the pinned OSWorld controller's keyboard representation patch, without
# importing its environment/evaluator package. This fixes shifted punctuation
# on Linux keyboards and changes no model-selected text or coordinates.
_GUI_PREFIX = (
    "import pyautogui, time, platform; pyautogui.FAILSAFE = False; "
    "_shift = '~!@#$%^&*()_+' + chr(123) + chr(125) + '|:\"<>?'; "
    "_linux_shift = '~!@#$%^&*()_+' + chr(123) + chr(125) + '|:\">?'; "
    "pyautogui.isShiftCharacter = lambda c: c.isupper() or "
    "c in (_linux_shift if platform.system() == 'Linux' else _shift); "
)


def _endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Endpoint must be an explicit HTTP(S) URL without credentials or query"
        )
    return value.rstrip("/")


def gui_tools() -> list[dict[str, Any]]:
    tools = [
        {
            "name": "screenshot",
            "description": "Get the current guest desktop as a PNG with its pixel dimensions. "
            "Includes visible OCR text for click and double_click. "
            "Click by text; no coordinates or IDs are needed.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        }
    ]
    for branch in GUI_ACTION_SCHEMA["oneOf"]:
        schema = copy.deepcopy(branch)
        name = schema["properties"].pop("action")["enum"][0]
        if name == "drag":
            continue
        schema["properties"].pop("fallback_reason")
        schema["required"] = [
            field
            for field in schema["required"]
            if field not in {"action", "fallback_reason"}
        ]
        if "seconds" in schema["properties"]:
            schema["properties"]["seconds"]["description"] = (
                "Seconds to wait after this operation, from 0 to 10; default 0.5."
                if name != "wait"
                else "Seconds to wait, from 0 to 10."
            )
        if name in {"click", "double_click"}:
            schema = {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Visible text from the latest OCR result. Case-insensitive exact match or unique substring.",
                    },
                    "occurrence": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Which match to click when text repeats, starting at 1 in OCR list order. Omit for a unique match.",
                    },
                    "seconds": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 10,
                        "default": 0.5,
                        "description": "Seconds to wait after clicking before taking the new screenshot; default 0.5.",
                    },
                },
                "required": ["text"],
                "additionalProperties": False,
            }
        tools.append(
            {
                "name": name,
                "description": GUI_DESCRIPTIONS[name]
                + " Returns a fresh screenshot after success, with OCR when enabled.",
                "inputSchema": schema,
            }
        )
    return tools


def _text_result(value: Any, *, error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
        "isError": error,
    }


class DesktopMCP:
    def __init__(
        self,
        guest_url: str,
        trace_dir: Path,
        *,
        max_calls: int = 100,
        deadline_seconds: float = 1800,
        adapter_urls: dict[str, str] | None = None,
        ocr_language: str | None = "eng",
    ) -> None:
        self.guest_url = _endpoint(guest_url)
        if (
            max_calls < 1
            or not math.isfinite(deadline_seconds)
            or deadline_seconds <= 0
        ):
            raise ValueError(
                "max_calls and deadline_seconds must be positive and finite"
            )
        self.max_calls = max_calls
        self.calls = 0
        self.screenshot_count = 0
        self.ocr_targets: dict[str, dict[str, Any]] = {}
        self.ocr_language = ocr_language
        self.deadline = time.monotonic() + deadline_seconds
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.trace_path = self.trace_dir / "desktop_calls.jsonl"
        # A new trace per process preserves previous attempts rather than appending
        # a fresh episode to old evidence or overwriting its screenshot files.
        self.trace_path.touch(mode=0o600, exist_ok=False)
        self.tools = {tool["name"]: tool for tool in gui_tools()}
        self.adapter_routes: dict[str, tuple[str, str]] = {}
        urls = {domain: _endpoint(url) for domain, url in (adapter_urls or {}).items()}
        for domain in urls:
            if domain not in DIRECT_ACTION_SCHEMAS:
                raise ValueError(f"No direct Adapter schemas for {domain!r}")
            actions = sorted(
                set(public_actions(domain)).intersection(DIRECT_ACTION_SCHEMAS[domain])
                - FORBIDDEN_DATASET_ACTIONS
                - {"adapter.call"}
            )
            for action, tool in zip(
                actions,
                build_tools(
                    domain,
                    actions,
                    include_gui=False,
                    include_control_tools=False,
                    strict_generic=True,
                ),
                strict=True,
            ):
                function = tool["function"]
                name = f"{domain}__{function['name']}"
                if name in self.tools:
                    raise ValueError(f"Duplicate tool name: {name}")
                self.tools[name] = {
                    "name": name,
                    "description": function["description"],
                    "inputSchema": function["parameters"],
                }
                self.adapter_routes[name] = (domain, action)
        self.adapters = AdapterExecutor(
            urls,
            trace_path=self.trace_dir / "adapter_calls.jsonl",
            deadline_monotonic=self.deadline,
        )

    def _trace(self, event: dict[str, Any]) -> None:
        with self.trace_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")

    def _remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Episode deadline exhausted; stop this episode.")
        return remaining

    def _screenshot(self, trace: dict[str, Any]) -> dict[str, Any]:
        self.ocr_targets.clear()
        response = requests.get(
            self.guest_url + "/screenshot", timeout=min(30, self._remaining())
        )
        trace["http_status"] = response.status_code
        if not response.ok:
            raise RuntimeError(
                f"Screenshot HTTP {response.status_code}: {response.text}"
            )
        data = response.content
        with Image.open(io.BytesIO(data)) as screenshot:
            if screenshot.format != "PNG":
                raise ValueError(
                    f"Expected PNG screenshot, received {screenshot.format}"
                )
            width, height = screenshot.size
            screenshot.verify()
        self.screenshot_count += 1
        filename = f"screenshot-{self.screenshot_count:04d}.png"
        with (self.trace_dir / filename).open("xb") as output:
            output.write(data)
        trace["screenshot"] = {"file": filename, "width": width, "height": height}
        result = {
            "content": [
                {
                    "type": "text",
                    "text": f"Guest screenshot: {width} x {height} pixels. "
                    "Click by OCR text below, or use keyboard tools for other controls.",
                },
                {
                    "type": "image",
                    "data": base64.b64encode(data).decode("ascii"),
                    "mimeType": "image/png",
                },
            ],
            "isError": False,
        }
        if self.ocr_language is not None:
            started = time.monotonic()
            try:
                ocr = read_screenshot(
                    data,
                    language=self.ocr_language,
                    timeout=min(5.0, self._remaining()),
                )
            except Exception as exc:
                # OCR is additional evidence; the original PNG remains usable.
                ocr = {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}
            trace["ocr"] = ocr
            trace["ocr_seconds"] = round(time.monotonic() - started, 3)
            targets = []
            if ocr.get("status") == "ok":
                for index, item in enumerate(ocr["items"], 1):
                    target = f"{self.screenshot_count}:{index}"
                    self.ocr_targets[target] = {
                        "target": target,
                        **item,
                        "screenshot": filename,
                    }
                    targets.append(
                        {
                            "text": item["text"],
                            "confidence": item["confidence"],
                        }
                    )
            visible_ocr = {**ocr, "items": targets}
            result["content"].append(
                {
                    "type": "text",
                    "text": "OCR text in this screenshot (may misread text), in reading order. "
                    'Use click with text, for example {"text":"Save"}. '
                    "No coordinates or IDs. Text may be a label rather "
                    "than a clickable control; use keyboard navigation if needed.\n"
                    + json.dumps(
                        visible_ocr, ensure_ascii=False, separators=(",", ":")
                    ),
                }
            )
        return result

    def _gui(
        self, name: str, arguments: dict[str, Any], trace: dict[str, Any]
    ) -> dict[str, Any]:
        ocr_target = None
        if name in {"click", "double_click"}:
            query = " ".join(arguments["text"].casefold().split())
            items = list(self.ocr_targets.values())
            if not query:
                raise ValueError("Provide non-empty visible OCR text to click.")
            matches = [
                item
                for item in items
                if query == " ".join(item["text"].casefold().split())
            ]
            if not matches:
                matches = [
                    item
                    for item in items
                    if query in " ".join(item["text"].casefold().split())
                ]
            if not matches:
                raise ValueError(
                    f"No current OCR text matches {arguments['text']!r}. "
                    "Call screenshot and use visible text from its OCR items; "
                    "if the control has no OCR text, use keyboard navigation."
                )
            occurrence = arguments.get("occurrence")
            if (len(matches) > 1 and occurrence is None) or (
                occurrence is not None and occurrence > len(matches)
            ):
                raise ValueError(
                    "Specify occurrence to select one of these OCR matches: "
                    + json.dumps(
                        [
                            {"occurrence": index, "text": item["text"]}
                            for index, item in enumerate(matches, 1)
                        ],
                        ensure_ascii=False,
                    )
                )
            ocr_target = matches[(occurrence or 1) - 1]
            arguments = {
                "x": ocr_target["center"][0],
                "y": ocr_target["center"][1],
                "seconds": arguments.get("seconds", 0.5),
            }
        envelope = {
            "action": name,
            "fallback_reason": "Direct Codex desktop tool",
            "seconds": 0.5,
            **arguments,
        }
        normalized = normalize_gui_arguments(envelope)
        trace["conversion"] = {
            "contract": "GUI tool name supplies action; fallback_reason is wrapper metadata; "
            "decimal strings use the existing GUI numeric conversion.",
            "gui_arguments": normalized,
        }
        if ocr_target is not None:
            trace["conversion"]["contract"] = (
                "ocr_text_center.v1: match model-selected text against the latest OCR, "
                "case/whitespace-insensitive exact match first, else literal substring; "
                "use model-selected occurrence for duplicates, and execute the matched box center."
            )
            trace["conversion"]["ocr_target"] = copy.deepcopy(ocr_target)
        command = build_gui_command(normalized)
        seconds = normalized["seconds"]
        if command == "WAIT":
            script = f"import time; time.sleep({seconds!r})"
        else:
            script = _GUI_PREFIX + command + f"; time.sleep({seconds!r})"
        payload = {"command": ["python", "-c", script], "shell": False}
        trace["request"] = payload
        self.ocr_targets.clear()
        response = requests.post(
            self.guest_url + "/execute",
            json=payload,
            timeout=min(120, self._remaining()),
        )
        trace["http_status"] = response.status_code
        try:
            body = response.json()
        except ValueError:
            body = {"raw_text": response.text}
        trace["guest_response"] = body
        succeeded = (
            response.ok
            and isinstance(body, dict)
            and body.get("status") == "success"
            and body.get("returncode") == 0
        )
        if not succeeded:
            raise RuntimeError(
                f"Guest rejected {name}; HTTP {response.status_code}: "
                + json.dumps(body, ensure_ascii=False)
            )
        result = _text_result(
            {"status": "ok", "executed": True, "guest_response": body}
        )
        observation_trace: dict[str, Any] = {}
        trace["post_action_observation"] = observation_trace
        try:
            observation = self._screenshot(observation_trace)
        except Exception as exc:
            observation_trace["error"] = f"{type(exc).__name__}: {exc}"
            result["content"].append(
                {
                    "type": "text",
                    "text": "The action executed, but its screenshot is unavailable: "
                    + observation_trace["error"]
                    + ". Call screenshot to inspect the current state before deciding "
                    "the next action.",
                }
            )
        else:
            result["content"].extend(observation["content"])
        return result

    def call_tool(
        self, name: str, arguments: Any, *, raw_request: Any = None
    ) -> dict[str, Any]:
        self.calls += 1
        trace = {
            "call": self.calls,
            "tool": name,
            "arguments": copy.deepcopy(arguments),
        }
        self._trace({"event": "call", **trace, "raw_request": raw_request})
        tool = self.tools.get(name)
        try:
            self._remaining()
            if self.calls > self.max_calls:
                raise RuntimeError(
                    f"Tool-call limit of {self.max_calls} exhausted; stop this episode."
                )
            if tool is None:
                raise ValueError(
                    f"Unknown tool {name!r}; use tools/list for available tools."
                )
            jsonschema.validate(arguments, tool["inputSchema"])
            if name == "screenshot":
                result = self._screenshot(trace)
            elif name in self.adapter_routes:
                self.ocr_targets.clear()
                domain, action = self.adapter_routes[name]
                trace["conversion"] = {
                    "domain": domain,
                    "action": action,
                    "arguments": arguments,
                }
                body = self.adapters.execute(
                    domain, action, arguments, {"codex_call": self.calls}
                )
                result = _text_result(body, error=body.get("status") != "ok")
                if result["isError"]:
                    result["content"].append(
                        {
                            "type": "text",
                            "text": "Tool parameter schema: "
                            + json.dumps(tool["inputSchema"], ensure_ascii=False),
                        }
                    )
            else:
                result = self._gui(name, arguments, trace)
        except Exception as exc:
            detail = (
                exc.message if isinstance(exc, jsonschema.ValidationError) else str(exc)
            )
            result = _text_result(
                {
                    "status": "error",
                    "type": type(exc).__name__,
                    "detail": detail,
                    "budget_exhausted": self.calls > self.max_calls
                    or time.monotonic() >= self.deadline,
                    "inputSchema": tool["inputSchema"] if tool else None,
                },
                error=True,
            )
        self._trace({"event": "result", **trace, "result": result})
        return result

    def dispatch(
        self, request: Any, *, raw_request: str | None = None
    ) -> dict[str, Any] | None:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid JSON-RPC request"},
            }
        if "id" not in request:
            return None
        response = {"jsonrpc": "2.0", "id": request["id"]}
        method = request.get("method")
        params = request.get("params", {})
        if not isinstance(params, dict):
            return {
                **response,
                "error": {"code": -32602, "message": "params must be an object"},
            }
        if method == "initialize":
            version = params.get("protocolVersion")
            result = {
                "protocolVersion": version
                if version in {"2024-11-05", "2025-03-26", "2025-06-18"}
                else "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "codex-osworld-desktop", "version": "0.1.0"},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": list(self.tools.values())}
        elif method == "resources/list":
            result = {"resources": []}
        elif method == "resources/templates/list":
            result = {"resourceTemplates": []}
        elif method == "tools/call":
            name = params.get("name")
            if not isinstance(name, str):
                return {
                    **response,
                    "error": {"code": -32602, "message": "Tool name must be a string"},
                }
            result = self.call_tool(
                name, params.get("arguments", {}), raw_request=raw_request or request
            )
        else:
            return {
                **response,
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            }
        return {**response, "result": result}

    def serve(self, source: TextIO = sys.stdin, sink: TextIO = sys.stdout) -> None:
        pid_path = self.trace_dir / "server.json"
        with pid_path.open("x", encoding="utf-8") as output:
            json.dump({"pid": os.getpid()}, output)
        try:
            for line in source:
                try:
                    request = json.loads(line)
                except ValueError as exc:
                    response = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": str(exc)},
                    }
                else:
                    response = self.dispatch(request, raw_request=line.rstrip("\n"))
                if response is not None:
                    sink.write(
                        json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n"
                    )
                    sink.flush()
        finally:
            pid_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--guest-url",
        required=True,
        help="Explicit URL of an existing OSWorld guest HTTP server",
    )
    parser.add_argument(
        "--trace-dir",
        required=True,
        type=Path,
        help="New local trace directory (contains private screenshots)",
    )
    parser.add_argument(
        "--max-steps", "--max-calls", dest="max_calls", type=int, default=100
    )
    parser.add_argument(
        "--timeout-seconds",
        "--deadline-seconds",
        dest="deadline_seconds",
        type=float,
        default=1800,
    )
    parser.add_argument(
        "--adapter-urls-json",
        type=Path,
        help="Optional JSON object mapping Adapter domains to deployed base URLs",
    )
    parser.add_argument(
        "--ocr-language", default="eng", help="Installed Tesseract language(s)"
    )
    parser.add_argument(
        "--no-ocr", action="store_true", help="Return screenshots without OCR"
    )
    args = parser.parse_args()
    urls = (
        json.loads(args.adapter_urls_json.read_text()) if args.adapter_urls_json else {}
    )
    if not isinstance(urls, dict) or any(
        not isinstance(value, str) for value in urls.values()
    ):
        parser.error(
            "--adapter-urls-json must contain an object mapping domain names to URLs"
        )
    DesktopMCP(
        args.guest_url,
        args.trace_dir,
        max_calls=args.max_calls,
        deadline_seconds=args.deadline_seconds,
        adapter_urls=urls,
        ocr_language=None if args.no_ocr else args.ocr_language,
    ).serve()


if __name__ == "__main__":
    main()
