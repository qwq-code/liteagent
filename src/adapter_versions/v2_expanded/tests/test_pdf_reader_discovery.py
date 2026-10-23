import json

import pytest

from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools, search_actions


@pytest.mark.parametrize(
    "query", ["read scientific articles", "extract information from papers"]
)
def test_pdf_reader_is_discoverable_by_document_category(query):
    hits = search_actions("multi_apps", query, strict_generic=True, limit=7)
    assert ("os", "pdf.extract_text_batch") in {
        (hit.get("adapter"), hit.get("downstream_action")) for hit in hits
    }


@pytest.mark.parametrize("forwarded", [False, True])
def test_pdf_reader_usage_explains_existing_window_cursor(forwarded):
    if forwarded:
        tools = constrain_adapter_call_routes(
            build_tools("multi_apps", ["adapter.call"], include_gui=False),
            [("os", "pdf.extract_text_batch")],
        )
    else:
        tools = build_tools("os", ["pdf.extract_text_batch"], include_gui=False)
    description = json.dumps(tools[0]["function"])
    assert "next_start_char" in description
    assert "from start_char" in description
    assert '"start_char"' in description
