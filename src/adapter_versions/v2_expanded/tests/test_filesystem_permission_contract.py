from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from os_adapter.errors import AdapterError
import os_adapter.permissions as permissions
from os_adapter.permissions import set_regular_file_permissions
from os_adapter.verifier import verify_specs


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def test_chmod_tree_skips_a_file_that_disappears_after_enumeration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stable = tmp_path / "stable-2041.txt"
    vanished = tmp_path / "volatile-2041.png"
    stable.write_text("stable", encoding="utf-8")
    vanished.write_text("volatile", encoding="utf-8")
    stable.chmod(0o600)
    vanished.chmod(0o600)

    original_lstat = Path.lstat
    vanished_lstat_calls = 0

    def remove_between_scan_and_chmod(path: Path):
        nonlocal vanished_lstat_calls
        if path == vanished:
            vanished_lstat_calls += 1
            if vanished_lstat_calls == 2:
                vanished.unlink()
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", remove_between_scan_and_chmod)

    result = set_regular_file_permissions(tmp_path, mode="640", recursive=True)

    assert _mode(stable) == 0o640
    assert result["target_count"] == 1
    assert result["changed_count"] == 1
    assert result["vanished_count"] == 1
    assert result["skipped_non_regular_count"] == 0
    assert result["targets"] == [str(stable)]


def test_chmod_tree_keeps_directories_and_symbolic_links_out_of_targets(
    tmp_path: Path,
) -> None:
    regular = tmp_path / "payload-2042.txt"
    directory = tmp_path / "nested"
    link = tmp_path / "payload-link"
    regular.write_text("payload", encoding="utf-8")
    directory.mkdir()
    link.symlink_to(regular)
    regular.chmod(0o600)
    directory.chmod(0o750)

    result = set_regular_file_permissions(tmp_path, mode="644", recursive=True)

    assert _mode(regular) == 0o644
    assert _mode(directory) == 0o750
    assert stat.S_ISLNK(link.lstat().st_mode)
    assert result["target_count"] == 1
    assert result["targets"] == [str(regular)]


def test_chmod_tree_does_not_chmod_a_file_replaced_by_a_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stable = tmp_path / "stable-2043.txt"
    replaced = tmp_path / "replaced-2043"
    stable.write_text("stable", encoding="utf-8")
    replaced.write_text("replace me", encoding="utf-8")
    stable.chmod(0o600)
    replaced.chmod(0o600)
    original_lstat = Path.lstat
    replaced_lstat_calls = 0

    def replace_between_scan_and_chmod(path: Path):
        nonlocal replaced_lstat_calls
        if path == replaced:
            replaced_lstat_calls += 1
            if replaced_lstat_calls == 2:
                replaced.unlink()
                replaced.mkdir(mode=0o750)
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", replace_between_scan_and_chmod)

    result = set_regular_file_permissions(tmp_path, mode="640", recursive=True)

    assert _mode(stable) == 0o640
    assert stat.S_ISDIR(replaced.lstat().st_mode)
    assert _mode(replaced) == 0o750
    assert result["target_count"] == 1
    assert result["vanished_count"] == 0
    assert result["skipped_non_regular_count"] == 1


def test_chmod_tree_does_not_suppress_permission_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "protected-2044.txt"
    target.write_text("protected", encoding="utf-8")
    original_chmod = Path.chmod

    def deny_chmod(path: Path, mode: int, *, follow_symlinks: bool = True) -> None:
        if path == target:
            raise PermissionError("synthetic denial")
        original_chmod(path, mode, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "chmod", deny_chmod)

    with pytest.raises(PermissionError, match="synthetic denial"):
        set_regular_file_permissions(tmp_path, mode="600", recursive=True)


def test_chmod_tree_rejects_a_processed_file_with_the_wrong_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "unchanged-2045.txt"
    target.write_text("unchanged", encoding="utf-8")
    target.chmod(0o600)
    original_chmod = Path.chmod

    def ignore_target(path: Path, mode: int, *, follow_symlinks: bool = True) -> None:
        if path != target:
            original_chmod(path, mode, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "chmod", ignore_target)

    with pytest.raises(AdapterError) as caught:
        set_regular_file_permissions(tmp_path, mode="644", recursive=True)

    assert caught.value.code == "VERIFICATION_FAILED"
    assert _mode(target) == 0o600


def test_mode_tree_verifier_ignores_only_a_disappearing_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stable = tmp_path / "stable-2046.txt"
    vanished = tmp_path / "volatile-2046.txt"
    stable.write_text("stable", encoding="utf-8")
    vanished.write_text("volatile", encoding="utf-8")
    stable.chmod(0o640)
    vanished.chmod(0o640)
    original_lstat = Path.lstat

    def remove_during_verification(path: Path):
        if path == vanished and vanished.exists():
            vanished.unlink()
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", remove_during_verification)

    verification = verify_specs(
        [
            {
                "type": "mode_tree",
                "root": str(tmp_path),
                "mode": 0o640,
                "recursive": True,
            }
        ],
        {},
    )

    assert verification["passed"] is True
    assert verification["checks"][0]["observed"] == {
        "target_count": 1,
        "requested_mode": 0o640,
        "mismatched_count": 0,
        "mismatched_samples": {},
        "sample_modes": {stable.name: 0o640},
        "samples_truncated": False,
    }


def test_chmod_tree_processes_a_new_file_on_the_next_bounded_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initial = tmp_path / "initial-2047.txt"
    late = tmp_path / "late-2047.txt"
    initial.write_text("initial", encoding="utf-8")
    initial.chmod(0o600)
    original_observe = permissions.observe_regular_file_modes
    created_late_file = False

    def observe_after_late_creation(root: Path, *, recursive: bool):
        nonlocal created_late_file
        if not created_late_file:
            late.write_text("late", encoding="utf-8")
            late.chmod(0o600)
            created_late_file = True
        return original_observe(root, recursive=recursive)

    monkeypatch.setattr(
        permissions, "observe_regular_file_modes", observe_after_late_creation
    )

    result = set_regular_file_permissions(tmp_path, mode="640", recursive=True)

    assert _mode(initial) == 0o640
    assert _mode(late) == 0o640
    assert result["target_count"] == 2
    assert result["changed_count"] == 2
    assert result["convergence_passes"] == 2


def test_chmod_tree_large_result_and_verification_are_bounded(tmp_path: Path) -> None:
    file_count = 300
    for index in range(file_count):
        path = tmp_path / f"payload-{index:04d}.txt"
        path.write_text(str(index), encoding="utf-8")
        path.chmod(0o600)

    result = set_regular_file_permissions(tmp_path, mode="640", recursive=True)
    verification = verify_specs(
        [
            {
                "type": "mode_tree",
                "root": result["root"],
                "mode": result["mode_value"],
                "recursive": result["recursive"],
            }
        ],
        result,
    )
    response = json.dumps(
        {"result": result, "verification": verification}, sort_keys=True
    )

    assert result["target_count"] == file_count
    assert len(result["targets"]) == permissions.PERMISSION_TARGET_SAMPLE_LIMIT
    assert result["targets_truncated"] is True
    assert result["targets_omitted"] == (
        file_count - permissions.PERMISSION_TARGET_SAMPLE_LIMIT
    )
    assert verification["passed"] is True
    observed = verification["checks"][0]["observed"]
    assert observed["target_count"] == file_count
    assert len(observed["sample_modes"]) == permissions.PERMISSION_TARGET_SAMPLE_LIMIT
    assert observed["samples_truncated"] is True
    assert len(response) < 20_000
