from __future__ import annotations

import stat
from pathlib import Path

import pytest

from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS, public_actions
from multi_apps_adapter.actions import MultiAppsActions
from multi_apps_adapter.errors import AdapterError as MultiAppsAdapterError
from multi_apps_adapter.schema import ACTIONS as MULTI_APPS_ACTIONS
from multi_apps_adapter.schema import parse_action_request as parse_multi_apps_request
from multi_apps_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as MULTI_APPS_SCHEMAS,
)
from os_adapter.actions import OSActions
import os_adapter.actions as os_actions
from os_adapter.errors import AdapterError as OSAdapterError
from os_adapter.schema import ACTIONS as OS_ACTIONS
from os_adapter.schema import parse_action_request as parse_os_request
from os_adapter.schema import validate_action_params
from os_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS as OS_SCHEMAS


RETIRED_OS_MACROS = {
    "filesystem.copy_matching_tree",
    "filesystem.chmod_tree",
    "document.convert_batch",
    "terminal.configure_size",
    "text.concatenate_columns",
}
ATOMIC_OS_REPLACEMENTS = {
    "filesystem.find",
    "filesystem.create_directory",
    "filesystem.copy",
    "filesystem.copy_to_directories",
    "filesystem.set_permissions",
    "document.convert",
    "command.run",
    "terminal.launch",
}


class _ConversionRunner:
    def run(self, argv, *, timeout=None, check=True, cwd=None):
        output_directory = Path(argv[argv.index("--outdir") + 1])
        output_format = argv[argv.index("--convert-to") + 1]
        source = Path(argv[-1])
        (output_directory / f"{source.stem}.{output_format}").write_bytes(
            b"synthetic converted document"
        )
        return {"returncode": 0, "stdout": "", "stderr": "", "duration_ms": 1}


class _TrashRunner:
    def __init__(self) -> None:
        self.restored: list[str] = []

    def run(self, argv, **_kwargs):
        if argv == ["gio", "trash", "--list"]:
            return {
                "returncode": 0,
                "stdout": (
                    "trash:///first\t/home/user/Desktop/Quarterly Report.txt\n"
                    "trash:///second\t/home/user/Documents/quarterly-notes.txt\n"
                ),
                "stderr": "",
                "duration_ms": 1,
            }
        if argv[:3] == ["gio", "trash", "--restore"]:
            self.restored.append(argv[3])
            return {"returncode": 0, "stdout": "", "stderr": "", "duration_ms": 1}
        raise AssertionError(argv)


class _FavoriteRunner:
    def __init__(self) -> None:
        self.favorites = ["vim.desktop", "org.gnome.Nautilus.desktop"]
        self.set_calls = 0

    def run(self, argv, **_kwargs):
        if argv[:2] == ["gsettings", "get"]:
            return {
                "returncode": 0,
                "stdout": repr(self.favorites),
                "stderr": "",
                "duration_ms": 1,
            }
        if argv[:2] == ["gsettings", "set"]:
            self.set_calls += 1
            self.favorites = ["org.gnome.Nautilus.desktop"]
            return {"returncode": 0, "stdout": "", "stderr": "", "duration_ms": 1}
        raise AssertionError(argv)


def test_os_macros_are_unreachable_and_atomic_actions_remain_public() -> None:
    surfaces = (
        set(OS_ACTIONS),
        set(OS_SCHEMAS),
        set(DIRECT_ACTION_SCHEMAS["os"]),
        set(public_actions("os")),
    )

    assert all(RETIRED_OS_MACROS.isdisjoint(surface) for surface in surfaces)
    assert all(ATOMIC_OS_REPLACEMENTS.issubset(surface) for surface in surfaces)


def test_multi_apps_does_not_restore_the_os_batch_conversion_facade() -> None:
    action = "document.convert_batch"

    assert action not in MULTI_APPS_ACTIONS
    assert action not in MULTI_APPS_SCHEMAS
    assert action not in DIRECT_ACTION_SCHEMAS["multi_apps"]
    assert action not in public_actions("multi_apps")

    with pytest.raises(MultiAppsAdapterError) as parsed_error:
        parse_multi_apps_request({"action": action, "params": {}})
    assert parsed_error.value.code == "UNSUPPORTED_ACTION"

    with pytest.raises(MultiAppsAdapterError) as dispatch_error:
        MultiAppsActions().dispatch(action, {}, 0.1)
    assert dispatch_error.value.code == "UNSUPPORTED_ACTION"


@pytest.mark.parametrize("action", sorted(RETIRED_OS_MACROS))
def test_os_rejects_retired_macro_requests_before_execution(action: str) -> None:
    with pytest.raises(OSAdapterError) as parsed_error:
        parse_os_request({"action": action, "params": {}})
    assert parsed_error.value.code == "UNSUPPORTED_ACTION"

    with pytest.raises(OSAdapterError) as dispatch_error:
        OSActions().dispatch(action, {}, 0.1)
    assert dispatch_error.value.code == "UNSUPPORTED_ACTION"


def test_set_permissions_changes_only_one_explicit_regular_file(tmp_path: Path) -> None:
    target = tmp_path / "selected.txt"
    sibling = tmp_path / "sibling.txt"
    target.write_text("selected", encoding="utf-8")
    sibling.write_text("sibling", encoding="utf-8")
    target.chmod(0o600)
    sibling.chmod(0o600)
    params = {"path": str(target), "mode": "0640"}

    validate_action_params("filesystem.set_permissions", params)
    result = OSActions().dispatch("filesystem.set_permissions", params, 1)

    assert result["path"] == str(target)
    assert result["mode"] == "0640"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert stat.S_IMODE(sibling.stat().st_mode) == 0o600


def test_document_convert_targets_one_explicit_source_and_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "selected.odt"
    destination = tmp_path / "selected.pdf"
    source.write_bytes(b"synthetic source")
    params = {"source": str(source), "destination": str(destination)}
    monkeypatch.setattr(os_actions.shutil, "which", lambda _name: "/usr/bin/soffice")

    validate_action_params("document.convert", params)
    result = OSActions(runner=_ConversionRunner()).dispatch(
        "document.convert", params, 2
    )

    assert result["source"] == str(source)
    assert result["destination"] == str(destination)
    assert result["output_format"] == "pdf"
    assert destination.read_bytes() == b"synthetic converted document"


def test_atomic_schemas_require_exact_single_file_paths() -> None:
    assert OS_SCHEMAS["filesystem.set_permissions"]["required"] == ["path", "mode"]
    assert OS_SCHEMAS["document.convert"]["required"] == [
        "source",
        "destination",
    ]
    assert "input_pattern" not in OS_SCHEMAS["document.convert"]["properties"]


def test_trash_restore_rejects_all_filename_queries() -> None:
    runner = _TrashRunner()

    for query in ("quarterly", "quarterly report.TXT"):
        with pytest.raises(OSAdapterError) as error:
            OSActions(runner=runner).restore_trash({"query": query}, 1)
        assert error.value.code == "INVALID_ARGUMENT"
    assert runner.restored == []


def test_remove_favorite_rejects_all_application_name_queries() -> None:
    runner = _FavoriteRunner()

    for application in ("vim editor", "VIM"):
        with pytest.raises(OSAdapterError) as error:
            OSActions(runner=runner).remove_favorite(
                {"application": application}, 1
            )
        assert error.value.code == "INVALID_ARGUMENT"
    assert runner.set_calls == 0
