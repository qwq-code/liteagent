"""LiteAgent composition root; orchestration is assembled from focused mixins."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .adapter_executor import AdapterExecutor
from .model_client import StructuredToolModelClient
from .reasoning import SUPPORTED_REASONING_MODES
from .action_selection import ActionSelectionMixin
from .tool_surface import ToolSurfaceMixin
from .agent_protocol import AgentProtocolMixin
from .completion import CompletionMixin
from .execution_engine import ExecutionEngineMixin


@dataclass(frozen=True)
class LiteAgentConfig:
    base_url: str
    model: str = "qwen3.5-4b"
    api_key: str = "EMPTY"
    top_k_actions: int = 7
    include_gui: bool = True
    enable_thinking: bool = False
    reasoning_effort: str | None = None
    max_output_tokens: int = 512
    temperature: float = 0.0
    request_timeout_seconds: float = 180.0
    allow_task_specific_or_golden: bool = False
    # Qwen3.5 exposes a binary control rather than numeric effort tiers.  The
    # legacy effort field remains available for providers that implement tiers.
    reasoning_mode: str | None = None
    presence_penalty: float | None = None
    thinking_token_budget: int | None = None
    tool_call_stop_sequence: str | None = None

    def __post_init__(self) -> None:
        if self.allow_task_specific_or_golden:
            raise ValueError(
                "task-specific or golden-enabled LiteAgent mode is not available"
            )
        if self.reasoning_mode is not None:
            if self.reasoning_mode not in SUPPORTED_REASONING_MODES:
                raise ValueError(f"unsupported reasoning mode: {self.reasoning_mode!r}")
            if self.reasoning_effort is not None:
                raise ValueError(
                    "reasoning_effort and reasoning_mode are mutually exclusive"
                )
            expected_thinking = self.reasoning_mode == "thinking"
            if self.enable_thinking is not expected_thinking:
                raise ValueError(
                    "enable_thinking does not match the requested reasoning mode"
                )


class LiteAgent(
    ActionSelectionMixin,
    ToolSurfaceMixin,
    AgentProtocolMixin,
    CompletionMixin,
    ExecutionEngineMixin,
):
    def __init__(
        self,
        config: LiteAgentConfig,
        adapter_executor: AdapterExecutor,
        gui_executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        model_client: StructuredToolModelClient | None = None,
        *,
        holo_grounder: Callable[[bytes, dict[str, Any]], dict[str, Any]] | None = None,
        holo_gui_gateway: Callable[..., dict[str, Any]] | None = None,
        holo_gateway: Callable[..., dict[str, Any]] | None = None,
    ):
        if holo_gui_gateway is not None and holo_gateway is not None:
            raise ValueError("pass only one Holo GUI gateway")
        self.config = config
        self.adapter_executor = adapter_executor
        self.gui_executor = gui_executor
        self.holo_grounder = holo_grounder
        # ``holo_gateway`` is retained as a concise compatibility alias for
        # callers that provide a combined ground-and-execute implementation.
        self.holo_gui_gateway = holo_gui_gateway or holo_gateway
        self._latest_screenshot: bytes | None = None
        self.model_client = model_client or StructuredToolModelClient(
            base_url=config.base_url,
            api_key=config.api_key,
            request_timeout_seconds=config.request_timeout_seconds,
        )
        self.client = self.model_client.client
