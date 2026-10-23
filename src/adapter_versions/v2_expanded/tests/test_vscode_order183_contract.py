from __future__ import annotations

import json

from vscode_adapter.actions import VscodeActions


def test_workspace_add_resolves_observed_active_root(monkeypatch, tmp_path) -> None:
    workspace_root = tmp_path / "project"
    workspace_root.mkdir()
    workspace_file = tmp_path / "project.code-workspace"
    workspace_file.write_text(
        json.dumps({"folders": [{"path": "project"}], "settings": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "vscode_adapter.actions.resolve_active_workspace_file",
        lambda _runner: {
            "workspace_file": str(workspace_file),
            "workspace_roots": [str(workspace_root)],
        },
    )

    result = VscodeActions().workspace_add_folders(
        {
            "path": str(workspace_root),
            "folders": [{"path": str(tmp_path / "data1")}],
        },
        45.0,
    )

    assert result["resolution_source"] == "active_workspace_root"
    assert result["path"] == str(workspace_file)
    assert json.loads(workspace_file.read_text(encoding="utf-8"))["folders"] == [
        {"path": "project"},
        {"path": "data1"},
    ]
