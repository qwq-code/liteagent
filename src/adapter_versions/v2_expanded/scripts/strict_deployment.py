from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from pathlib import Path

from multi_apps_adapter.route_utils import (
    contains_route,
    decode_text,
    has_unresolved_encoding,
)

STRICT_EXCLUDED_FILES = {
    "gimp_adapter": frozenset({"tasks.py"}),
    "os_adapter": frozenset({"tasks.py"}),
    "thunderbird_adapter": frozenset({"tasks.py"}),
    "vlc_adapter": frozenset(
        {
            "tasks.py",
            "reference_profiles.py",
        }
    ),
    "vscode_adapter": frozenset({"tasks.py"}),
    "writer_adapter": frozenset({"tasks.py"}),
    "multi_apps_adapter": frozenset(
        {
            "task_manifest.json",
            # The legacy assessment implementation reads authoritative answer
            # markers.  It is retained only as historical source, never in a
            # strict-generic guest package.
            "assessment_grading.py",
        }
    ),
}
STRICT_DENIED_FILENAMES = frozenset({"task_manifest.json"})
FORBIDDEN_ACTIONS = (
    "task.execute",
    "task.inspect",
    "artifact.materialize",
    "assessment.grade_multiple_choice_documents",
)
TASK_UUID_PATTERN = re.compile(
    r"(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])",
    re.IGNORECASE,
)


def _literal_denylist_lines(package: Path, relative: str, text: str) -> set[int]:
    """Return the exact source span of the packaged runtime denylist.

    The source scanner must permit the denylist to name forbidden routes, but
    that exception cannot depend on formatter-specific line layout.  Accept
    only one top-level assignment whose value is the complete literal set.
    """
    if package.name != "multi_apps_adapter" or relative != "actions.py":
        return set()
    try:
        module = ast.parse(text)
    except SyntaxError:
        return set()
    for node in module.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != "FORBIDDEN_DATASET_ACTIONS":
            continue
        if not isinstance(node.value, ast.Set):
            return set()
        values = {
            element.value
            for element in node.value.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
        if len(values) != len(node.value.elts) or values != set(FORBIDDEN_ACTIONS):
            return set()
        end_line = getattr(node, "end_lineno", node.lineno)
        return set(range(node.lineno, end_line + 1))
    return set()


def validate_strict_source_files(package: Path, paths: list[Path]) -> None:
    violations: list[str] = []
    for path in paths:
        relative = path.relative_to(package).as_posix()
        if path.name.casefold() in STRICT_DENIED_FILENAMES:
            violations.append(f"{relative}: forbidden dataset manifest")
        if "gold" in path.name.casefold():
            violations.append(f"{relative}: answer-like filename")
        if path.suffix not in {".py", ".json", ".sh", ".service"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        literal_denylist_lines = _literal_denylist_lines(package, relative, text)
        if TASK_UUID_PATTERN.search(decode_text(text)) or has_unresolved_encoding(text):
            violations.append(f"{relative}: UUID constant")
        for line_number, line in enumerate(text.splitlines(), 1):
            actions = [
                action
                for action in FORBIDDEN_ACTIONS
                if contains_route(line, (action,))
            ]
            if not actions:
                continue
            denylist_only = line_number in literal_denylist_lines
            if not denylist_only:
                violations.append(
                    f"{relative}:{line_number}: forbidden route {actions}"
                )
    if violations:
        raise RuntimeError(f"strict deployment source validation failed: {violations}")


def filter_source_files(
    package: Path,
    paths: Iterable[Path],
    *,
    strict_generic: bool = True,
) -> list[Path]:
    candidates = sorted(paths)
    if strict_generic is not True:
        raise RuntimeError("non-strict Adapter deployment is not available")
    denied = [
        path.relative_to(package).as_posix()
        for path in candidates
        if path.name.casefold() in STRICT_DENIED_FILENAMES
    ]
    if denied:
        raise RuntimeError(
            f"strict deployment refuses forbidden dataset manifests: {denied}"
        )
    excluded = STRICT_EXCLUDED_FILES.get(package.name, frozenset())
    selected = [
        path
        for path in candidates
        if path.relative_to(package).as_posix() not in excluded
        and path.name != "README.md"
        and "gold" not in path.name.casefold()
    ]
    validate_strict_source_files(package, selected)
    return selected
