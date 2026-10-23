"""Target binding for explicit VS Code workspace-open instructions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterator

from .adapter_results import has_passed_verification
from .completion_policy import canonical_action_request, effective_canonical_action
from .result_envelopes import iter_result_mappings


ACTION = "workspace.open"
_WORKSPACE_KIND = r"(?:folder|directory|project|workspace)"
_OPEN_VERB = r"(?:open|load)"
_QUOTED_OPEN_RE = re.compile(
    rf"(?is)\b{_OPEN_VERB}\b\s+"
    rf"(?P<prefix>(?:(?:the|an?)\s+)?(?:(?:{_WORKSPACE_KIND})\s+)?"
    r"(?:(?:named|called)\s+)?)"
    r"(?P<quote>[\"'`])(?P<target>[^\"'`\r\n]+)(?P=quote)"
)
_BARE_KIND_OPEN_RE = re.compile(
    rf"(?is)\b{_OPEN_VERB}\b\s+(?:the\s+|an?\s+)?"
    rf"(?P<kind>project\s+folder|workspace\s+folder|{_WORKSPACE_KIND})\s+"
    r"(?:named|called)\s+(?P<target>[A-Za-z0-9][A-Za-z0-9_.-]*)"
)
_KIND_RE = re.compile(rf"(?i)\b{_WORKSPACE_KIND}\b")
_FILE_KIND_RE = re.compile(r"(?i)\b(?:document|editor|file|tab)\b")
_TRAILING_KIND_RE = re.compile(
    rf"(?is)^\s*(?:(?:as|as\s+an?)\s+)?(?:an?\s+|the\s+)?{_WORKSPACE_KIND}\b"
)
_TRAILING_NON_WORKSPACE_RE = re.compile(
    r"(?is)^\s*(?:(?:as|as\s+an?)\s+)?(?:an?\s+|the\s+)?"
    r"(?:command|document|file|menu|panel|setting|settings|tab|view)\b"
)
_TARGET_KIND_TERMINAL_RE = re.compile(r"(?is)^\s*(?:$|[.,;!?])")
_VSCODE_CONTEXT_RE = re.compile(r"(?is)^\s*(?:in|using|with)\s+(?:vs\s*code|vscode)\b")
_CONJOINED_TARGET_TAIL_RE = re.compile(
    rf"(?is)^\s*(?:(?:as\s+(?:an?\s+)?|the\s+)?"
    rf"(?:project\s+folder|workspace\s+folder|{_WORKSPACE_KIND})\s+)?"
    r"(?:along\s+with|and|or|together\s+with|,)\s+"
    rf"(?:the\s+|an?\s+)?(?:(?:project\s+folder|workspace\s+folder|{_WORKSPACE_KIND})"
    r"\s+(?:(?:named|called)\s+)?)?"
    r"(?:"
    r"(?P<quote>[\"'`])[^\"'`\r\n]+(?P=quote)"
    r"|"
    r"[A-Za-z0-9][A-Za-z0-9_.-]*"
    rf"(?=\s*(?:$|[.,;!?]|{_WORKSPACE_KIND}\b|along\s+with\b|and\b|or\b|"
    r"together\s+with\b|in\b|inside\b|under\b|using\b|with\b|within\b))"
    r")"
)
_PARENT_RELATION_RE = re.compile(
    r"(?is)\b(?:in|inside|within|under)\b\s+(?:the\s+)?"
    r"(?:"
    r"(?P<quote>[\"'`])(?P<quoted>[^\"'`\r\n]+)(?P=quote)"
    r"(?:\s+(?:folder|directory))?"
    r"|"
    r"(?P<bare>[A-Za-z0-9][A-Za-z0-9_.-]*)\s+(?:folder|directory)"
    r")"
)
_BARE_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "at",
        "directory",
        "folder",
        "from",
        "in",
        "into",
        "on",
        "called",
        "named",
        "project",
        "the",
        "to",
        "under",
        "using",
        "with",
        "workspace",
    }
)


@dataclass(frozen=True)
class WorkspaceOpenIntent:
    """Instruction-derived target and only the explicitly named ancestors."""

    target: str
    ancestors: tuple[str, ...] = ()
    allow_code_workspace: bool = False


def _path_parts(value: Any) -> tuple[str, ...]:
    """Return lexical path components without resolving a host path."""
    if not isinstance(value, str) or not value.strip():
        return ()
    raw = value.strip().rstrip("/")
    if not raw:
        return ()
    return tuple(
        part for part in PurePosixPath(raw).parts if part not in {"", "/", "."}
    )


def _target_matches_component(
    component: str, target: str, *, allow_code_workspace: bool
) -> bool:
    if component == target:
        return True
    return bool(
        allow_code_workspace
        and component.endswith(".code-workspace")
        and component.removesuffix(".code-workspace") == target
    )


def path_binds_target(
    path: Any, target: str, *, allow_code_workspace: bool = False
) -> bool:
    """Return whether a path leaf exactly names the requested workspace."""
    parts = _path_parts(path)
    return bool(
        parts
        and _target_matches_component(
            parts[-1], target, allow_code_workspace=allow_code_workspace
        )
    )


def path_binds_intent(
    path: Any, intent: WorkspaceOpenIntent, *, allow_tilde: bool = True
) -> bool:
    """Bind the leaf and every instruction-explicit ancestor in order."""
    if not isinstance(path, str):
        return False
    raw = path.strip()
    if not (raw.startswith("/") or (allow_tilde and raw.startswith("~/"))):
        return False
    parts = _path_parts(path)
    if not parts or not _target_matches_component(
        parts[-1],
        intent.target,
        allow_code_workspace=intent.allow_code_workspace,
    ):
        return False
    hierarchy = intent.ancestors
    if not hierarchy:
        return True
    return len(parts) > len(hierarchy) and parts[-len(hierarchy) - 1 : -1] == hierarchy


def _candidate_label(value: str) -> str | None:
    stripped = value.strip().rstrip("/.,;:!?")
    if not stripped or "/" in stripped or "\\" in stripped:
        return None
    return stripped if stripped not in {".", "..", "~"} else None


def _ordered_ancestors(text: str) -> tuple[str, ...]:
    """Parse a contiguous inner-to-outer location phrase after the target."""
    inner_to_outer: list[str] = []
    cursor = 0
    for _ in range(6):
        match = _PARENT_RELATION_RE.search(text, cursor)
        if match is None:
            break
        between = text[cursor : match.start()]
        if len(between) > 28 or re.search(
            r"[.;!?\n]|\b(?:and|then|via|using|with)\b", between, re.I
        ):
            break
        value = match.group("quoted") or match.group("bare")
        label = _candidate_label(value)
        if label is None:
            break
        inner_to_outer.append(label)
        cursor = match.end()
    return tuple(reversed(inner_to_outer))


def _is_negated_open(text: str, start: int) -> bool:
    prefix = text[max(0, start - 24) : start]
    return bool(
        re.search(
            r"(?i)(?:\bavoid\s+|\bdo\s+not\s+|\bdon't\s+|\bexcept\s+|"
            r"\bnever\s+|\bnot\s+to\s+)$",
            prefix,
        )
    )


def requested_workspace_open_intent(
    instruction: str,
) -> WorkspaceOpenIntent | None:
    """Extract one explicit open target and any instruction-named hierarchy."""
    text = str(instruction).translate(
        str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})
    )
    candidates: list[WorkspaceOpenIntent] = []

    for match in _QUOTED_OPEN_RE.finditer(text):
        if _is_negated_open(text, match.start()):
            continue
        prefix = match.group("prefix")
        if _FILE_KIND_RE.search(prefix):
            continue
        target = _candidate_label(match.group("target"))
        if target is None:
            continue
        tail = text[match.end() : match.end() + 180]
        if _CONJOINED_TARGET_TAIL_RE.search(tail):
            return None
        suffix = tail[:56]
        if _TRAILING_NON_WORKSPACE_RE.search(suffix):
            continue
        target_is_kind = target.casefold() in {
            "folder",
            "directory",
            "project",
            "workspace",
        }
        prefix_kind = _KIND_RE.search(prefix)
        suffix_kind = _TRAILING_KIND_RE.search(suffix)
        ancestors = _ordered_ancestors(tail)
        target_kind_context = bool(
            _TARGET_KIND_TERMINAL_RE.search(suffix)
            or _VSCODE_CONTEXT_RE.search(suffix)
            or ancestors
        )
        if (
            (target_is_kind and target_kind_context)
            or prefix_kind is not None
            or suffix_kind is not None
        ):
            kind_text = " ".join(
                match.group(0)
                for match in (prefix_kind, suffix_kind)
                if match is not None
            )
            candidates.append(
                WorkspaceOpenIntent(
                    target=target,
                    ancestors=ancestors,
                    allow_code_workspace=(
                        "workspace" in kind_text.casefold()
                        or target.casefold().endswith(".code-workspace")
                    ),
                )
            )

    for match in _BARE_KIND_OPEN_RE.finditer(text):
        if _is_negated_open(text, match.start()):
            continue
        target = _candidate_label(match.group("target"))
        if target is None or target.casefold() in _BARE_STOP_WORDS:
            continue
        tail = text[match.end() : match.end() + 180]
        if _CONJOINED_TARGET_TAIL_RE.search(tail):
            return None
        candidates.append(
            WorkspaceOpenIntent(
                target=target,
                ancestors=_ordered_ancestors(tail),
                allow_code_workspace=(
                    "workspace" in match.group("kind").casefold()
                    or target.casefold().endswith(".code-workspace")
                ),
            )
        )

    by_target: dict[str, list[WorkspaceOpenIntent]] = {}
    for candidate in candidates:
        by_target.setdefault(candidate.target, []).append(candidate)
    if len(by_target) != 1:
        return None
    same_target = next(iter(by_target.values()))
    explicit_hierarchies = {
        candidate.ancestors for candidate in same_target if candidate.ancestors
    }
    if len(explicit_hierarchies) > 1:
        return None
    selected = max(same_target, key=lambda candidate: len(candidate.ancestors))
    return WorkspaceOpenIntent(
        target=selected.target,
        ancestors=selected.ancestors,
        allow_code_workspace=any(
            candidate.allow_code_workspace for candidate in same_target
        ),
    )


def requested_workspace_open_target(instruction: str) -> str | None:
    intent = requested_workspace_open_intent(instruction)
    return intent.target if intent is not None else None


def required_actions(domain: str, instruction: str) -> list[str]:
    if domain != "vs_code" or requested_workspace_open_intent(instruction) is None:
        return []
    return [ACTION]


def workflow_intent(state: Any) -> WorkspaceOpenIntent | None:
    if str(getattr(state, "domain", "")) != "vs_code":
        return None
    return requested_workspace_open_intent(str(getattr(state, "instruction", "")))


def workflow_target(state: Any) -> str | None:
    intent = workflow_intent(state)
    return intent.target if intent is not None else None


def _selected_workspace_open_arguments(
    default_domain: str, action: str, arguments: dict[str, Any]
) -> dict[str, Any] | None:
    domain, canonical_action, selected = canonical_action_request(
        default_domain, action, arguments
    )
    if (domain, canonical_action) != ("vs_code", ACTION):
        return None
    return selected


def argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    """Reject paths that drop an explicit target name or ancestor hierarchy."""
    intent = workflow_intent(state)
    selected = _selected_workspace_open_arguments(
        str(getattr(state, "domain", "")), action, arguments
    )
    if intent is None or selected is None:
        return []
    path = selected.get("path")
    if path_binds_intent(path, intent):
        return []
    hierarchy = "/".join((*intent.ancestors, intent.target))
    return [
        f"workspace.open path must bind the explicit instruction hierarchy {hierarchy!r} "
        "with an exact target basename (or a .code-workspace stem only for a workspace); "
        "choose the complete model-authored target path rather than an ancestor or a "
        "same-named target elsewhere. The Runner does not choose or rewrite the path"
    ]


def _executed_workspace_open_events(
    state: Any,
) -> Iterator[tuple[Any, dict[str, Any]]]:
    for event in getattr(state, "events", ()):
        domain, action, arguments = effective_canonical_action(
            event, str(getattr(state, "domain", ""))
        )
        if (domain, action) == ("vs_code", ACTION) and getattr(
            event, "executed", False
        ):
            yield event, arguments


def _observed_workspace_results(event: Any) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for mapping in iter_result_mappings(getattr(event, "result", None)):
        path = mapping.get("path")
        expected_name = mapping.get("expected_name")
        has_window_identity = isinstance(mapping.get("window"), dict) or isinstance(
            mapping.get("window_id"), str
        )
        if (
            isinstance(path, str)
            and path.strip()
            and isinstance(expected_name, str)
            and expected_name
            and has_window_identity
        ):
            results.append((path, expected_name))
    return results


def observed_workspace_paths(event: Any) -> set[str]:
    """Return resolved paths from structured workspace Adapter results."""
    return {path for path, _expected_name in _observed_workspace_results(event)}


def _expected_name_binds_intent(
    expected_name: str, intent: WorkspaceOpenIntent
) -> bool:
    if expected_name == intent.target:
        return True
    return bool(
        intent.allow_code_workspace
        and intent.target.endswith(".code-workspace")
        and expected_name == intent.target.removesuffix(".code-workspace")
    )


def completion_errors(state: Any) -> list[str]:
    """Require final verified model and Adapter paths to name the target workspace."""
    intent = workflow_intent(state)
    if intent is None:
        return []
    events = list(_executed_workspace_open_events(state))
    if not events:
        return [
            f"no executed workspace.open call opened the instruction-selected {intent.target!r} "
            "folder/project/workspace"
        ]
    event, arguments = max(events, key=lambda item: getattr(item[0], "step", 0))
    if getattr(event, "error", None) or not has_passed_verification(
        getattr(event, "result", None)
    ):
        return [
            "the last executed workspace.open lacks passed Adapter verification, so "
            "the final workspace state is not provable"
        ]
    model_path = arguments.get("path")
    observed_results = _observed_workspace_results(event)
    observed_paths = {path for path, _expected_name in observed_results}
    if not path_binds_intent(model_path, intent):
        return [
            f"the last verified workspace.open used model-selected path {model_path!r}, "
            f"which does not bind the requested hierarchy "
            f"{'/'.join((*intent.ancestors, intent.target))!r}"
        ]
    if not observed_paths:
        return [
            "the last verified workspace.open result does not expose an Adapter-observed "
            "resolved path, so the requested workspace cannot be confirmed"
        ]
    if not any(
        path_binds_intent(path, intent, allow_tilde=False)
        and _expected_name_binds_intent(expected_name, intent)
        for path, expected_name in observed_results
    ):
        return [
            "the last verified workspace.open Adapter result does not bind both its "
            f"resolved path {sorted(observed_paths)!r} and expected workspace name to "
            f"the requested {'/'.join((*intent.ancestors, intent.target))!r} workspace"
        ]
    return []


__all__ = [
    "ACTION",
    "WorkspaceOpenIntent",
    "argument_contract_errors",
    "completion_errors",
    "observed_workspace_paths",
    "path_binds_intent",
    "path_binds_target",
    "requested_workspace_open_intent",
    "requested_workspace_open_target",
    "required_actions",
    "workflow_target",
]
