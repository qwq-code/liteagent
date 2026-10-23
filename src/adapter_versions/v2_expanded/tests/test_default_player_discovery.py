import pytest

from integrations.lite_agent.tool_catalog import search_actions


ASSOCIATION_ROUTES = [
    ("os", "desktop.applications.inspect"),
    ("os", "desktop.mime_associations.set"),
]


@pytest.mark.parametrize("query", [
    "set the default video player",
    "change my default music player",
])
def test_default_player_search_exposes_existing_application_and_mime_tools(query):
    matches = search_actions("multi_apps", query, strict_generic=True)
    routes = [(item.get("adapter"), item.get("downstream_action")) for item in matches]

    assert routes[:2] == ASSOCIATION_ROUTES


def test_current_player_playback_search_does_not_offer_default_association_mutations():
    matches = search_actions(
        "multi_apps", "play this video in the current player", strict_generic=True
    )
    routes = {(item.get("adapter"), item.get("downstream_action")) for item in matches}

    assert routes.isdisjoint(ASSOCIATION_ROUTES)
