from __future__ import annotations

import ast
from pathlib import Path

import jsonschema
import pytest

from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS, build_tools
from integrations.openapa_osworld.tool_catalog import action_signature, public_actions
import os_adapter.actions as os_actions
from os_adapter.actions import OSActions
from os_adapter.errors import AdapterError
from os_adapter.schema import ACTIONS, parse_action_request, validate_action_params
from os_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from os_adapter.verifier import verify_specs
from os_adapter.worker import _default_specs


EXPLICIT_TARGET_ACTIONS = {
    "trash.list",
    "trash.restore",
    "desktop.favorites.list",
    "desktop.remove_favorite",
}


class _DesktopStateRunner:
    def __init__(
        self,
        *,
        trash: list[tuple[str, str]] | None = None,
        favorites: list[str] | None = None,
    ) -> None:
        self.trash = list(trash or [])
        self.favorites = list(favorites or [])
        self.calls: list[list[str]] = []

    def run(self, argv, **_kwargs):
        command = list(argv)
        self.calls.append(command)
        if command == ["gio", "trash", "--list"]:
            stdout = "".join(f"{uri}\t{path}\n" for uri, path in self.trash)
            return {"returncode": 0, "stdout": stdout, "stderr": ""}
        if command[:3] == ["gio", "trash", "--restore"]:
            uri = command[3]
            matches = [(item_uri, path) for item_uri, path in self.trash if item_uri == uri]
            if len(matches) != 1:
                raise AssertionError(f"unexpected restore target: {uri}")
            self.trash.remove(matches[0])
            restored = Path(matches[0][1])
            restored.parent.mkdir(parents=True, exist_ok=True)
            restored.write_text("restored", encoding="utf-8")
            return {"returncode": 0, "stdout": "", "stderr": ""}
        if command == ["gsettings", "get", "org.gnome.shell", "favorite-apps"]:
            return {"returncode": 0, "stdout": repr(self.favorites), "stderr": ""}
        if command[:4] == [
            "gsettings",
            "set",
            "org.gnome.shell",
            "favorite-apps",
        ]:
            self.favorites = ast.literal_eval(command[4])
            return {"returncode": 0, "stdout": "", "stderr": ""}
        raise AssertionError(f"unexpected command: {command}")


def _request(action: str, params: dict) -> dict:
    return {"adapter": "os", "action": action, "params": params}


def _exposed_schema(action: str) -> dict:
    return build_tools(
        "os",
        [action],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )[0]["function"]["parameters"]


def test_exact_target_contracts_are_public_and_adapter_owned() -> None:
    assert EXPLICIT_TARGET_ACTIONS.issubset(ACTIONS)
    assert EXPLICIT_TARGET_ACTIONS.issubset(public_actions("os"))
    for action in EXPLICIT_TARGET_ACTIONS:
        manifest = STRICT_ACTION_PARAM_SCHEMAS[action]
        assert DIRECT_ACTION_SCHEMAS["os"][action] == manifest
        jsonschema.Draft202012Validator.check_schema(_exposed_schema(action))

    assert STRICT_ACTION_PARAM_SCHEMAS["trash.restore"]["required"] == [
        "trash_uri",
        "original_path",
    ]
    assert STRICT_ACTION_PARAM_SCHEMAS["desktop.remove_favorite"]["required"] == [
        "desktop_id"
    ]
    assert "trash.list" in action_signature("os", "trash.restore")
    assert "desktop.favorites.list" in action_signature(
        "os", "desktop.remove_favorite"
    )


def test_append_each_line_resolves_relative_output_from_active_terminal(
    tmp_path, monkeypatch
) -> None:
    jsonschema.validate(
        {
            "lines": ["1", "2", "3"],
            "suffix": "<br/>",
            "output_path": "output.txt",
        },
        _exposed_schema("text.append_each_line"),
    )
    monkeypatch.setattr(
        os_actions,
        "_active_terminal_working_directory",
        lambda: tmp_path,
    )

    result = OSActions().append_each_line(
        {"lines": ["1", "2", "3"], "suffix": "<br/>", "output_path": "output.txt"},
        10,
    )

    output = tmp_path / "output.txt"
    assert output.read_text(encoding="utf-8") == "1<br/>\n2<br/>\n3<br/>\n"
    assert result["path"] == str(output.resolve())


@pytest.mark.parametrize(
    ("action", "params"),
    [
        ("trash.restore", {"query": "poster.png"}),
        ("trash.restore", {"original_path": "/tmp/poster.png"}),
        ("trash.restore", {"trash_uri": "trash:///poster.png"}),
        (
            "trash.restore",
            {
                "trash_uri": "trash:///poster.png",
                "original_path": "/tmp/poster.png",
                "query": "poster",
            },
        ),
        ("desktop.remove_favorite", {"application": "vim"}),
        ("desktop.remove_favorite", {"desktop_id": "vim"}),
    ],
)
def test_legacy_or_incomplete_implicit_target_arguments_are_rejected(
    action: str, params: dict
) -> None:
    with pytest.raises(AdapterError) as caught:
        parse_action_request(_request(action, params))
    assert caught.value.code == "INVALID_REQUEST"
    assert list(
        jsonschema.Draft202012Validator(_exposed_schema(action)).iter_errors(params)
    )


def test_trash_list_exposes_exact_pairs_and_restore_uses_only_selected_uri(
    tmp_path: Path,
) -> None:
    first = str(tmp_path / "Poster-a.png")
    second = str(tmp_path / "Poster-b.png")
    runner = _DesktopStateRunner(
        trash=[
            ("trash:///Poster-a.png", first),
            ("trash:///Poster-b.png", second),
        ]
    )
    actions = OSActions(runner=runner)

    listing = actions.dispatch("trash.list", {"max_results": 1}, 1)

    assert listing["entries"] == [
        {"trash_uri": "trash:///Poster-a.png", "original_path": first}
    ]
    assert listing["entry_count"] == 2
    assert listing["truncated"] is True
    assert listing["next_offset"] == 1
    assert verify_specs(
        _default_specs("trash.list", {}, listing), listing, runner
    )["passed"]

    with pytest.raises(AdapterError) as mismatch:
        actions.dispatch(
            "trash.restore",
            {
                "trash_uri": "trash:///Poster-a.png",
                "original_path": second,
            },
            1,
        )
    assert mismatch.value.code == "TRASH_TARGET_MISMATCH"
    assert not any(call[:3] == ["gio", "trash", "--restore"] for call in runner.calls)

    params = {
        "trash_uri": "trash:///Poster-a.png",
        "original_path": first,
    }
    validate_action_params("trash.restore", params)
    restored = actions.dispatch("trash.restore", params, 1)

    assert Path(first).read_text(encoding="utf-8") == "restored"
    assert runner.trash == [("trash:///Poster-b.png", second)]
    assert verify_specs(
        _default_specs("trash.restore", params, restored), restored, runner
    )["passed"]


def test_favorites_list_preserves_exact_ids_and_removal_never_resolves_a_name() -> None:
    runner = _DesktopStateRunner(
        favorites=["org.vim.desktop", "vim.desktop", "google-chrome.desktop"]
    )
    actions = OSActions(runner=runner)

    listing = actions.dispatch(
        "desktop.favorites.list", {"offset": 1, "max_results": 1}, 1
    )

    assert listing["favorites"] == ["vim.desktop"]
    assert listing["favorite_count"] == 3
    assert listing["next_offset"] == 2
    assert verify_specs(
        _default_specs("desktop.favorites.list", {}, listing), listing, runner
    )["passed"]

    params = {"desktop_id": "vim.desktop"}
    validate_action_params("desktop.remove_favorite", params)
    removed = actions.dispatch("desktop.remove_favorite", params, 1)

    assert removed["removed"] == "vim.desktop"
    assert runner.favorites == ["org.vim.desktop", "google-chrome.desktop"]
    assert verify_specs(
        _default_specs("desktop.remove_favorite", params, removed), removed, runner
    )["passed"]
