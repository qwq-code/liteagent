from __future__ import annotations

import base64
import copy
import json
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from openai import OpenAI

from .tools import HOLO_GUI_TOOLS


RequestObserver = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class HoloAgentConfig:
    base_url: str
    model: str
    api_key: str = "EMPTY"
    temperature: float = 0.8
    max_output_tokens: int = 1024
    request_timeout_seconds: float = 180.0
    image_history_limit: int = 3


def select_first_tool_call(calls: list[Any]) -> tuple[Any, int]:
    """Follow Holo's documented native loop by dispatching the first call."""
    if not calls:
        raise ValueError("Holo must return at least one tool call")
    return calls[0], len(calls)


def system_prompt(instruction: str) -> str:
    return (
        "You are a computer-use agent controlling an Ubuntu desktop through screenshots "
        "and GUI input tools. Use exactly one tool per turn. Inspect the newest screenshot "
        "before acting. Coordinates are normalized integers in [0, 1000] with the origin "
        "at the screenshot's top-left. Do not claim success merely because an action was "
        "accepted: call answer only after a later screenshot visually confirms the requested "
        "state. Prefer direct keyboard shortcuts when they are standard and unambiguous. "
        "All interaction must use the provided visible GUI input tools. You may operate a "
        "visible terminal, IDE, or developer interface when the task explicitly requires it, "
        "but you have no hidden shell, filesystem, application API, or evaluator access.\n\n"
        f"<task>\n{instruction}\n</task>"
    )


def trim_to_last_n_images(messages: list[dict[str, Any]], n: int = 3) -> None:
    if n < 1:
        raise ValueError("image history limit must be positive")
    seen = 0
    for message in reversed(messages):
        content = message.get("content")
        if message.get("role") != "user" or not isinstance(content, list):
            continue
        for chunk in reversed(content):
            if chunk.get("type") != "image_url":
                continue
            seen += 1
            if seen > n:
                chunk.clear()
                chunk.update({"type": "text", "text": "[screenshot evicted]"})


class HoloNativeAgent:
    def __init__(
        self,
        config: HoloAgentConfig,
        instruction: str,
        *,
        request_observer: RequestObserver | None = None,
    ) -> None:
        self.config = config
        self.request_observer = request_observer
        self.client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            http_client=httpx.Client(
                timeout=config.request_timeout_seconds,
                trust_env=False,
            ),
        )
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt(instruction)}
        ]

    def observe(self, screenshot: bytes) -> None:
        encoded = base64.b64encode(screenshot).decode("ascii")
        self.messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "<observation>\n"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded}"},
                    },
                    {"type": "text", "text": "\n</observation>"},
                ],
            }
        )
        trim_to_last_n_images(self.messages, self.config.image_history_limit)

    def propose(self) -> dict[str, Any]:
        request = {
            "model": self.config.model,
            "messages": copy.deepcopy(self.messages),
            "tools": copy.deepcopy(HOLO_GUI_TOOLS),
            "tool_choice": "required",
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_effort": "medium",
        }
        if self.request_observer is not None:
            self.request_observer(copy.deepcopy(request))
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=self.messages,
            tools=HOLO_GUI_TOOLS,
            tool_choice="required",
            temperature=self.config.temperature,
            max_tokens=self.config.max_output_tokens,
            extra_body={
                "chat_template_kwargs": {"enable_thinking": True},
                "reasoning_effort": "medium",
            },
        )
        message = response.choices[0].message
        calls = message.tool_calls or []
        call, returned_tool_call_count = select_first_tool_call(calls)
        arguments = json.loads(call.function.arguments)
        if not isinstance(arguments, dict):
            raise ValueError("Holo tool arguments must be a JSON object")
        assistant_message = {
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
            ],
        }
        self.messages.append(assistant_message)
        dumped = message.model_dump(mode="json", exclude_none=True)
        return {
            "model_actual": response.model,
            "call_id": call.id,
            "name": call.function.name,
            "arguments_raw": call.function.arguments,
            "arguments": arguments,
            "returned_tool_call_count": returned_tool_call_count,
            "ignored_tool_call_count": returned_tool_call_count - 1,
            "content": message.content,
            "reasoning": dumped.get("reasoning") or dumped.get("reasoning_content"),
            "response": dumped,
        }

    def record_tool_result(self, call_id: str, result: dict[str, Any]) -> None:
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            }
        )
