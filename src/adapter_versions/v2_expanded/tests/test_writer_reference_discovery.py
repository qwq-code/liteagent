from types import SimpleNamespace

import pytest

from integrations.lite_agent.agent import LiteAgent
from integrations.lite_agent.state_model import RuntimeState
from integrations.lite_agent.tool_catalog import build_tools, search_actions


@pytest.mark.parametrize("instruction", [
    "Append this citation to my references and add a cross reference using its number at the marked text.",
    "Append the supplied bibliography citation and insert a cross-reference using its native list number at the marked placeholder.",
    "Add a numbered cross reference to this new list entry at the marker.",
])
def test_numbered_reference_source_operations_reach_initial_tools(instruction):
    agent = object.__new__(LiteAgent)
    agent.config = SimpleNamespace(top_k_actions=7)
    state = RuntimeState(
        task_id="synthetic-reference-discovery", domain="libreoffice_writer",
        instruction=instruction,
    )
    actions = agent.selected_actions(state)
    tools = build_tools("libreoffice_writer", actions, include_gui=True)
    names = {tool["function"]["name"] for tool in tools}
    assert {
        "adapter__document_inspect", "adapter__document_save",
        "adapter__text_find", "adapter__document_append_paragraphs",
        "adapter__bookmark_create", "adapter__paragraph_apply_numbering",
        "adapter__cross_reference_insert",
    } <= names
    assert state.events == []


@pytest.mark.parametrize("instruction", [
    "Make this paragraph bold.",
    "Convert comma separated text into a table.",
])
def test_unrelated_writer_requests_do_not_gain_reference_source_tools(instruction):
    agent = object.__new__(LiteAgent)
    agent.config = SimpleNamespace(top_k_actions=7)
    state = RuntimeState(
        task_id="synthetic-unrelated-discovery", domain="libreoffice_writer",
        instruction=instruction,
    )
    assert {"bookmark.create", "paragraph.apply_numbering"}.isdisjoint(
        agent.selected_actions(state)
    )


@pytest.mark.parametrize("domain", ["libreoffice_writer", "multi_apps"])
@pytest.mark.parametrize(("query", "action"), [
    ("Writer bookmark for a cross reference source", "bookmark.create"),
    ("Writer continue numbered reference list", "paragraph.apply_numbering"),
])
def test_reference_source_operations_are_searchable_by_usage(domain, query, action):
    matches = search_actions(domain, query, strict_generic=True)
    assert action in {item.get("downstream_action", item["action"]) for item in matches}
