from __future__ import annotations

import pytest

from integrations.lite_agent.tool_catalog import search_actions


def _os_actions(domain: str, query: str) -> set[str]:
    hits = search_actions(domain, query, strict_generic=True, limit=7)
    return {
        hit["downstream_action"] if domain == "multi_apps" else hit["action"]
        for hit in hits
        if domain != "multi_apps" or hit.get("adapter") == "os"
    }


@pytest.mark.parametrize("domain", ["os", "multi_apps"])
@pytest.mark.parametrize(
    "query",
    [
        "move files and directories into folders",
        "file manager desktop organization",
        "organize files into folders",
    ],
)
def test_move_and_folder_organization_discover_rename(domain: str, query: str) -> None:
    assert "filesystem.rename" in _os_actions(domain, query)


@pytest.mark.parametrize("domain", ["os", "multi_apps"])
def test_explicit_copy_request_keeps_copy_discoverable(domain: str) -> None:
    assert "filesystem.copy" in _os_actions(domain, "copy a file to another folder")

def test_multi_apps_visual_identification_routes_find_open_and_rename() -> None:
    instruction = (
        "Identify the landmarks in several pictures and change each picture's "
        "filename to the landmark name without replacing spaces with underscores."
    )
    routes = search_actions(
        "multi_apps",
        instruction,
        instruction=instruction,
        limit=3,
        strict_generic=True,
    )
    assert [
        (item["adapter"], item["downstream_action"])
        for item in routes
    ] == [
        ("os", "filesystem.find"),
        ("os", "desktop.open_path"),
        ("os", "filesystem.rename"),
    ]
