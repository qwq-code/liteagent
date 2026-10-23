from __future__ import annotations

from integrations.lite_agent.tool_catalog import search_actions


def test_multi_apps_notes_transfer_search_keeps_atomic_workflow_routes_together() -> None:
    instruction = (
        "My PowerPoint slides and speaking notes are saved on the desktop. "
        "Insert the planned remarks from the DOCX into the remaining slide notes."
    )
    matches = search_actions(
        "multi_apps",
        "PowerPoint speaking notes DOCX desktop",
        limit=6,
        instruction=instruction,
        strict_generic=True,
    )
    routes = [(item["adapter"], item["downstream_action"]) for item in matches]

    assert routes[:5] == [
        ("os", "filesystem.find"),
        ("libreoffice_writer", "document.read_file"),
        ("libreoffice_impress", "presentation.inspect"),
        ("libreoffice_impress", "slide.set_notes"),
        ("libreoffice_impress", "presentation.save"),
    ]
    assert all(
        item.get("downstream_action") != "presentation.fill_missing_notes_from_document"
        for item in matches
    )
