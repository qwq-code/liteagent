"""Generic phase semantics for editing source and persisting its output.

The workflow is derived only from the instruction and model-selected, verified
Adapter events. It never selects a path, command, edit, or output value for the
model.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from .adapter_results import has_passed_verification
from .tool_catalog import build_tools


SOURCE_EDIT = "source_edit"
READ_REFERENCE = "read_reference"
CAPTURE_OUTPUT = "capture_output"
READ_OUTPUT = "read_output"
DONE = "done"

_SOURCE_EXTENSIONS = (
    "c",
    "cc",
    "cpp",
    "cs",
    "go",
    "java",
    "js",
    "jsx",
    "mjs",
    "php",
    "pl",
    "py",
    "rb",
    "rs",
    "sh",
    "ts",
    "tsx",
)
_SOURCE_SUFFIXES = tuple(f".{extension}" for extension in _SOURCE_EXTENSIONS)
_SOURCE_FILENAME = re.compile(
    rf"(?i)(?<![\w./-])([a-z0-9][a-z0-9_.-]*\.(?:{'|'.join(_SOURCE_EXTENSIONS)}))\b"
)
_REFERENCE_DOCUMENT_EXTENSIONS = ("doc", "docx", "odt", "rtf")
_REFERENCE_DOCUMENT_FILENAME = re.compile(
    rf"(?i)(?<![\w./-])([a-z0-9][a-z0-9_.-]*\."
    rf"(?:{'|'.join(_REFERENCE_DOCUMENT_EXTENSIONS)}))\b"
)
_SOURCE_SUBJECT = re.compile(
    rf"(?i)\b(?:code|function|method|program|script|source)\b|"
    rf"\.(?:{'|'.join(_SOURCE_EXTENSIONS)})\b"
)
_SOURCE_EDIT_INTENT = re.compile(
    r"(?i)\b(?:complet(?:e|ed|ing)|correct(?:ed|ing)?|debug(?:ged|ging)?|"
    r"finish(?:ed|ing)?|fix(?:ed|ing)?|implement(?:ed|ing)?|repair(?:ed|ing)?)\b"
)
_PERSISTENT_OUTPUT = re.compile(
    r"(?i)(?:\b(?:save|store|write|capture|record)\b.{0,100}"
    r"\b(?:output|result|stdout|log)\b|"
    r"\b(?:output|result|stdout|log)\b.{0,100}"
    r"\b(?:save|store|write|capture|record)\b)"
)
_PRE_EDIT_EXECUTION_REASON = re.compile(
    r"(?i)\b(?:crash|debug|diagnos|error|fail|reproduc|test)\w*\b"
)
_EXECUTION_VERB = re.compile(r"(?i)\b(?:execute|run|test)\b")

_SOURCE_MUTATIONS = frozenset({"file.replace_literal", "file.write_text"})
_CAPTURE_ACTIONS = frozenset({"command.capture_output", "command.run"})


@dataclass(frozen=True)
class SourceExecutionState:
    active: bool
    phase: str | None
    source_paths: tuple[str, ...] = ()
    reference_paths: tuple[str, ...] = ()
    source_mutation_step: int | None = None
    capture_step: int | None = None
    output_path: str | None = None
    readback_step: int | None = None


def requires_source_edit_output_workflow(instruction: str) -> bool:
    """Recognize a reusable edit-source-then-save-output workflow."""
    return bool(
        _SOURCE_SUBJECT.search(instruction)
        and _SOURCE_EDIT_INTENT.search(instruction)
        and _PERSISTENT_OUTPUT.search(instruction)
    )


def allows_pre_edit_execution(instruction: str) -> bool:
    """Allow a baseline run only when the instruction explicitly orders diagnosis first."""
    edit = _SOURCE_EDIT_INTENT.search(instruction)
    execution = _EXECUTION_VERB.search(instruction)
    return bool(
        edit
        and execution
        and execution.start() < edit.start()
        and _PRE_EDIT_EXECUTION_REASON.search(instruction)
    )


def protocol_guidance(instruction: str) -> str | None:
    """Return short instruction-semantic guidance without materializing arguments."""
    if not requires_source_edit_output_workflow(instruction):
        return None
    baseline = (
        " One bounded pre-edit run is allowed because the instruction explicitly asks to "
        "reproduce or diagnose behavior before editing."
        if allows_pre_edit_execution(instruction)
        else " Do not run the unchanged source before the requested edit."
    )
    reference = (
        " Read the explicitly named supporting document before editing the source."
        if _instruction_reference_names(instruction)
        else ""
    )
    return (
        " For this source-edit workflow, first read the relevant source."
        f"{reference} Then make a model-selected edit on the observed source path."
        " If the source contains a TODO or other incomplete block, implement the missing "
        "operation in its existing control flow; preserve surrounding setup and "
        "finalization statements, then inspect or test the edited source before saving "
        "its output."
        f"{baseline} After the edit, use tools_search for command.run if that action is not exposed. "
        "Call command.run with model-selected argv, "
        "cwd_source, stdout_path, and provenance to persist its standard output. "
        "Omitting stdout_path only returns output; it does not save an output file. "
        "Read the saved stdout_path before propose_done."
    )


def _normalize_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = value.strip()
    if path.startswith("file:"):
        path = unquote(urlparse(path).path)
    if not (path.startswith("/") or path.startswith("~/")):
        return None
    return posixpath.normpath(path)


def _event_action_arguments(event: Any) -> tuple[str, dict[str, Any]]:
    proposed = getattr(event, "proposed", None)
    if not isinstance(proposed, dict):
        return "", {}
    action = str(proposed.get("action", ""))
    arguments = proposed.get("arguments")
    if not isinstance(arguments, dict):
        return action, {}
    if action != "adapter.call":
        return action, arguments
    downstream_action = arguments.get("action")
    payload = arguments.get("payload")
    params = payload.get("params") if isinstance(payload, dict) else None
    return (
        str(downstream_action) if isinstance(downstream_action, str) else "",
        params if isinstance(params, dict) else {},
    )


def _result_mappings(value: Any) -> Iterable[dict[str, Any]]:
    pending = [value]
    for _depth in range(8):
        if not pending:
            return
        next_pending = []
        for item in pending:
            if not isinstance(item, dict):
                continue
            yield item
            for key in (
                "adapter_response",
                "context_hint",
                "downstream_context",
                "identity",
                "response",
                "result",
            ):
                child = item.get(key)
                if isinstance(child, dict):
                    next_pending.append(child)
        pending = next_pending


def _result_confirms_path(event: Any, path: str, *fields: str) -> bool:
    result = getattr(event, "result", None)
    if not has_passed_verification(result):
        return False
    return any(
        _normalize_path(mapping.get(field)) == path
        for mapping in _result_mappings(result)
        for field in fields
    )


def _successful_events(state: Any) -> list[Any]:
    return [
        event
        for event in getattr(state, "events", ())
        if getattr(event, "executed", False)
        and isinstance(getattr(event, "proposed", None), dict)
        and event.proposed.get("kind") == "adapter"
        and not getattr(event, "error", None)
    ]


def _instruction_source_names(instruction: str) -> set[str]:
    return {
        match.group(1).casefold() for match in _SOURCE_FILENAME.finditer(instruction)
    }


def _instruction_reference_names(instruction: str) -> set[str]:
    return {
        match.group(1).casefold()
        for match in _REFERENCE_DOCUMENT_FILENAME.finditer(instruction)
    }


def _relevant_source_path(instruction: str, path: str) -> bool:
    basename = posixpath.basename(path).casefold()
    named_sources = _instruction_source_names(instruction)
    if named_sources:
        return basename in named_sources
    return basename.endswith(_SOURCE_SUFFIXES) and bool(
        _SOURCE_SUBJECT.search(instruction)
    )


def _source_reads(state: Any) -> list[tuple[Any, str]]:
    instruction = str(getattr(state, "instruction", ""))
    reads = []
    for event in _successful_events(state):
        action, arguments = _event_action_arguments(event)
        path = _normalize_path(arguments.get("path"))
        if (
            action == "file.read_text"
            and path is not None
            and _relevant_source_path(instruction, path)
            and _result_confirms_path(event, path, "path")
        ):
            reads.append((event, path))
    return reads


def _reference_reads(state: Any) -> list[tuple[Any, str]]:
    reference_names = _instruction_reference_names(
        str(getattr(state, "instruction", ""))
    )
    if not reference_names:
        return []
    reads = []
    for event in _successful_events(state):
        action, arguments = _event_action_arguments(event)
        path = _normalize_path(arguments.get("path"))
        if (
            action == "document.read_file"
            and path is not None
            and posixpath.basename(path).casefold() in reference_names
            and _result_confirms_path(event, path, "path", "url")
        ):
            reads.append((event, path))
    return reads


def _source_mutations(
    state: Any, source_reads: Iterable[tuple[Any, str]]
) -> list[tuple[Any, str]]:
    reads_by_path: dict[str, int] = {}
    for event, path in source_reads:
        reads_by_path[path] = min(reads_by_path.get(path, event.step), event.step)
    mutations = []
    for event in _successful_events(state):
        action, arguments = _event_action_arguments(event)
        path = _normalize_path(arguments.get("path"))
        if (
            action in _SOURCE_MUTATIONS
            and path in reads_by_path
            and event.step > reads_by_path[path]
            and _result_confirms_path(event, path, "path")
        ):
            mutations.append((event, path))
    return mutations


def _argv_runs_source(arguments: dict[str, Any], source_paths: set[str]) -> bool:
    argv = arguments.get("argv")
    if not isinstance(argv, list):
        return False
    normalized_argv_paths = {
        path for item in argv if (path := _normalize_path(item)) is not None
    }
    if normalized_argv_paths.intersection(source_paths):
        return True
    cwd = _normalize_path(arguments.get("cwd_path"))
    return bool(
        cwd
        and any(
            posixpath.dirname(path) == cwd and posixpath.basename(path) in argv
            for path in source_paths
        )
    )


def _path_mutation_steps(state: Any, path: str) -> list[int]:
    steps = []
    for event in _successful_events(state):
        action, arguments = _event_action_arguments(event)
        if (
            action in _SOURCE_MUTATIONS
            and _normalize_path(arguments.get("path")) == path
        ):
            steps.append(event.step)
    return steps


def _latest_capture(
    state: Any, *, after_step: int, source_paths: set[str]
) -> tuple[Any, str] | None:
    for event in reversed(_successful_events(state)):
        action, arguments = _event_action_arguments(event)
        output_path = _normalize_path(arguments.get("stdout_path"))
        if (
            event.step <= after_step
            or action not in _CAPTURE_ACTIONS
            or output_path is None
            or output_path in source_paths
            or not _argv_runs_source(arguments, source_paths)
            or not _result_confirms_path(event, output_path, "stdout_path")
        ):
            continue
        if any(step > event.step for step in _path_mutation_steps(state, output_path)):
            continue
        return event, output_path
    return None


def _latest_output_readback(
    state: Any, *, after_step: int, output_path: str
) -> Any | None:
    for event in reversed(_successful_events(state)):
        action, arguments = _event_action_arguments(event)
        if event.step <= after_step:
            break
        if (
            action == "file.read_text"
            and _normalize_path(arguments.get("path")) == output_path
            and _result_confirms_path(event, output_path, "path")
        ):
            return event
    return None


def workflow_state(state: Any) -> SourceExecutionState:
    """Derive the current phase from immutable instruction and event evidence."""
    instruction = str(getattr(state, "instruction", ""))
    if getattr(
        state, "domain", None
    ) != "multi_apps" or not requires_source_edit_output_workflow(instruction):
        return SourceExecutionState(active=False, phase=None)

    source_reads = _source_reads(state)
    source_paths = tuple(dict.fromkeys(path for _event, path in source_reads))
    if not source_reads:
        return SourceExecutionState(active=True, phase=None)

    reference_names = _instruction_reference_names(instruction)
    reference_reads = _reference_reads(state)
    reference_paths = tuple(dict.fromkeys(path for _event, path in reference_reads))
    mutations = _source_mutations(state, source_reads)
    # Reference reading guides the initial edit; it must not send a completed
    # edit back to one specific reader instead of checking its actual output.
    if reference_names and not reference_reads and not mutations:
        return SourceExecutionState(
            active=True,
            phase=READ_REFERENCE,
            source_paths=source_paths,
        )

    if not mutations:
        return SourceExecutionState(
            active=True,
            phase=SOURCE_EDIT,
            source_paths=source_paths,
            reference_paths=reference_paths,
        )

    mutation_event, _mutation_path = mutations[-1]
    capture = _latest_capture(
        state,
        after_step=mutation_event.step,
        source_paths=set(source_paths),
    )
    if capture is None:
        return SourceExecutionState(
            active=True,
            phase=CAPTURE_OUTPUT,
            source_paths=source_paths,
            reference_paths=reference_paths,
            source_mutation_step=mutation_event.step,
        )

    capture_event, output_path = capture
    readback = _latest_output_readback(
        state,
        after_step=capture_event.step,
        output_path=output_path,
    )
    if readback is None:
        return SourceExecutionState(
            active=True,
            phase=READ_OUTPUT,
            source_paths=source_paths,
            reference_paths=reference_paths,
            source_mutation_step=mutation_event.step,
            capture_step=capture_event.step,
            output_path=output_path,
        )
    return SourceExecutionState(
        active=True,
        phase=DONE,
        source_paths=source_paths,
        reference_paths=reference_paths,
        source_mutation_step=mutation_event.step,
        capture_step=capture_event.step,
        output_path=output_path,
        readback_step=readback.step,
    )


def phase_actions(state: Any) -> list[str] | None:
    """Return the smallest action surface for an active grounded phase."""
    phase = workflow_state(state).phase
    if phase is None:
        return None
    if phase == READ_REFERENCE:
        return ["document.read_file"]
    if phase == SOURCE_EDIT:
        actions = ["file.replace_literal", "file.write_text", "file.read_text"]
        if allows_pre_edit_execution(str(getattr(state, "instruction", ""))):
            actions.append("command.run")
        return actions
    if phase == CAPTURE_OUTPUT:
        return ["command.run"]
    if phase == READ_OUTPUT:
        return ["file.read_text"]
    return []


def stage_actions(state: Any, actions: Iterable[str]) -> list[str]:
    """Override competing phases only after a relevant source read grounds the workflow."""
    staged = phase_actions(state)
    return list(actions) if staged is None else staged


def build_phase_tools(state: Any) -> list[dict[str, Any]] | None:
    """Build a strict phase surface without adding or constraining model arguments."""
    current = workflow_state(state)
    if current.phase is None:
        return None
    if current.phase == DONE:
        return [
            tool
            for tool in build_tools("multi_apps", [], include_gui=False)
            if tool["function"]["name"] == "propose_done"
        ]

    tools = build_tools(
        "multi_apps",
        phase_actions(state) or [],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )
    fail_tool = next(
        tool
        for tool in build_tools("multi_apps", [], include_gui=False)
        if tool["function"]["name"] == "fail_task"
    )
    guidance = {
        READ_REFERENCE: (
            " The source has been read successfully, but the explicitly named supporting "
            "document has not. Select its path and read it before editing; the Runner will "
            "not supply a path or infer its contents."
        ),
        SOURCE_EDIT: (
            " The source has been read successfully. Select the observed source path and "
            "the exact edit; the Runner will not supply a path or content. If a TODO or "
            "incomplete block is present, fill that operation within the existing control "
            "flow and preserve the surrounding setup/finalization statements. Inspect or "
            "test the edited source before capturing output. Do not execute the unchanged "
            "source."
        ),
        CAPTURE_OUTPUT: (
            " A source edit has succeeded. Select argv, stdout_path, and provenance, then "
            "run the edited source once while persisting its complete standard output."
        ),
        READ_OUTPUT: (
            " The capture succeeded. Read the exact stdout_path shown in the truthful "
            "capture result; do not rewrite the output or repeat the command."
        ),
    }[current.phase]
    for tool in tools:
        tool["function"]["description"] += guidance
    return [*tools, fail_tool]


def completion_errors(state: Any) -> list[str]:
    """Require every public workflow transition before strict completion."""
    current = workflow_state(state)
    if not current.active or current.phase == DONE:
        return []
    if current.phase is None:
        return [
            "read the relevant source through a successful verified file.read_text call "
            "before editing or executing it"
        ]
    if current.phase == READ_REFERENCE:
        return [
            "read the explicitly named supporting document through a successful verified "
            "document.read_file call before editing the source"
        ]
    if current.phase == SOURCE_EDIT:
        return [
            "complete the observed source with a successful model-selected "
            "file.replace_literal or file.write_text call before capturing its output"
        ]
    if current.phase == CAPTURE_OUTPUT:
        return [
            "run the edited source once with a model-selected command.run call and "
            "set stdout_path to save its complete standard output before completion"
        ]
    return [
        "read back the exact model-selected stdout_path with file.read_text after the "
        "successful output capture"
    ]


__all__ = [
    "CAPTURE_OUTPUT",
    "DONE",
    "READ_REFERENCE",
    "READ_OUTPUT",
    "SOURCE_EDIT",
    "SourceExecutionState",
    "allows_pre_edit_execution",
    "build_phase_tools",
    "completion_errors",
    "phase_actions",
    "protocol_guidance",
    "requires_source_edit_output_workflow",
    "stage_actions",
    "workflow_state",
]
