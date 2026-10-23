from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable


SOURCE_SCOPE_ROOTS = (
    "integrations",
    "scripts",
    "tests",
    "deployment",
    "calc_adapter",
    "chrome_adapter",
    "gimp_adapter",
    "impress_adapter",
    "multi_apps_adapter",
    "os_adapter",
    "thunderbird_adapter",
    "vlc_adapter",
    "vscode_adapter",
    "writer_adapter",
)
EXCLUDED_DIRECTORY_NAMES = frozenset({"__pycache__", ".pytest_cache", ".ruff_cache"})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _excluded(relative: Path) -> bool:
    return (
        any(
            part in EXCLUDED_DIRECTORY_NAMES or part.startswith(".venv")
            for part in relative.parts
        )
        or relative.suffix == ".pyc"
    )


def source_tree_files(v2_root: Path) -> list[Path]:
    root = v2_root.resolve()
    files: set[Path] = set()
    for relative_root in SOURCE_SCOPE_ROOTS:
        scope = root / relative_root
        if not scope.exists():
            continue
        candidates: Iterable[Path] = [scope] if scope.is_file() else scope.rglob("*")
        for candidate in candidates:
            if candidate.is_symlink():
                raise RuntimeError(f"source seal refuses symlink: {candidate}")
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(root)
            if not _excluded(relative):
                files.add(candidate.resolve())
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def build_source_tree_seal(
    v2_root: Path, *, include_files: bool = False
) -> dict[str, Any]:
    root = v2_root.resolve()
    records = []
    digest = hashlib.sha256()
    total_bytes = 0
    for path in source_tree_files(root):
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        file_hash = sha256_file(path)
        digest.update(f"{relative}\0{size}\0{file_hash}\n".encode("utf-8"))
        total_bytes += size
        records.append({"path": relative, "bytes": size, "sha256": file_hash})
    seal: dict[str, Any] = {
        "scope_roots": list(SOURCE_SCOPE_ROOTS),
        "excludes": [
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            ".venv*",
            "*.pyc",
        ],
        "file_count": len(records),
        "total_bytes": total_bytes,
        "algorithm": "sha256 of relative_path\\0size\\0file_sha256\\n records",
        "sha256": digest.hexdigest(),
    }
    if include_files:
        seal["files"] = records
    return seal


def source_tree_seal_matches(expected: Any, current: dict[str, Any]) -> bool:
    if not isinstance(expected, dict):
        return False
    return all(
        expected.get(key) == current.get(key)
        for key in ("scope_roots", "file_count", "total_bytes", "algorithm", "sha256")
    )
