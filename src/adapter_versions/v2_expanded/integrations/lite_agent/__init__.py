"""Lightweight structured-tool runtime for OSWorld v2 Adapter experiments."""

from .runtime import AdapterExecutor, LiteAgent, LiteAgentConfig, RuntimeState
from .model_client import StructuredToolModelClient, StructuredToolProtocolError
from .safety import assert_agent_surface_safe, sanitize_agent_visible_result
from .tool_catalog import build_tools, select_actions
from .reasoning import SUPPORTED_REASONING_EFFORTS, SUPPORTED_REASONING_MODES
from .episode_control import (
    CONTROL_TOOL_NAMES,
    SoftRestartDecision,
    advance_local_step,
    begin_same_vm_soft_restart,
    consume_terminal_audit,
    finalize_deferred_terminal,
    mark_tool_result_for_audit,
    record_model_audit,
    resolve_terminal_audit,
    recovery_summary,
)

__all__ = [
    "AdapterExecutor",
    "LiteAgent",
    "LiteAgentConfig",
    "RuntimeState",
    "StructuredToolModelClient",
    "StructuredToolProtocolError",
    "assert_agent_surface_safe",
    "build_tools",
    "sanitize_agent_visible_result",
    "select_actions",
    "SUPPORTED_REASONING_EFFORTS",
    "SUPPORTED_REASONING_MODES",
    "CONTROL_TOOL_NAMES",
    "SoftRestartDecision",
    "advance_local_step",
    "begin_same_vm_soft_restart",
    "consume_terminal_audit",
    "finalize_deferred_terminal",
    "mark_tool_result_for_audit",
    "record_model_audit",
    "resolve_terminal_audit",
    "recovery_summary",
]
