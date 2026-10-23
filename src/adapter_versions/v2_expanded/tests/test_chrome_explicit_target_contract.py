from __future__ import annotations

from pathlib import Path

import pytest

from chrome_adapter import worker
from chrome_adapter.cdp import CDPClient, ensure_locator_result, locator_expression
from chrome_adapter.errors import AdapterError
from chrome_adapter.schema import TARGET_REQUIRED_ACTIONS, parse_action_request
from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS, build_tools


class FakeTab:
    type = "page"

    def __init__(self, target_id: str, url: str, title: str) -> None:
        self.id = target_id
        self._kwargs = {"type": "page", "url": url, "title": title}


class FakeCDP:
    def evaluate(self, _tab: object, _expression: str) -> dict[str, str]:
        return {
            "url": "https://example.com/",
            "title": "Example Page",
            "ready_state": "complete",
            "body_text": "Example",
        }

    def print_pdf(
        self, _tab: object, landscape: bool, print_background: bool
    ) -> bytes:
        assert landscape is False
        assert print_background is True
        return b"%PDF-" + b"x" * 2000


def _cdp_with_tabs(tabs: list[FakeTab]) -> CDPClient:
    client = object.__new__(CDPClient)
    client.tabs = lambda: tabs
    return client


@pytest.mark.parametrize("action", sorted(TARGET_REQUIRED_ACTIONS))
def test_page_derived_actions_require_an_exact_tab_target(action: str) -> None:
    with pytest.raises(AdapterError) as error:
        parse_action_request({"action": action, "params": {}})

    assert error.value.code == "INVALID_REQUEST"
    assert "exact selector" in error.value.message


def test_target_selector_rejects_unknown_fields() -> None:
    with pytest.raises(AdapterError) as error:
        parse_action_request(
            {
                "action": "page.snapshot",
                "target": {"active": True},
                "params": {},
            }
        )

    assert error.value.code == "INVALID_REQUEST"
    assert error.value.details["unexpected"] == ["active"]


def test_page_verification_requires_its_own_exact_target() -> None:
    with pytest.raises(AdapterError) as error:
        parse_action_request(
            {
                "action": "page.fill",
                "target": {"target_id": "tab-1"},
                "params": {
                    "locator": {"role": "textbox", "name": "Search"},
                    "value": "coffee maker",
                },
                "verify": [
                    {
                        "type": "page_state",
                        "locator": {"label": "Search"},
                        "value": "coffee maker",
                    }
                ],
            }
        )

    assert error.value.code == "INVALID_REQUEST"
    assert "verify[0].target" in error.value.message


def test_print_pdf_requires_and_uses_a_model_selected_output_path(
    tmp_path: Path,
) -> None:
    target = {"target_id": "tab-1"}
    with pytest.raises(AdapterError) as error:
        parse_action_request(
            {"action": "page.print_pdf", "target": target, "params": {}}
        )
    assert error.value.code == "INVALID_REQUEST"

    output = tmp_path / "model-selected.pdf"
    parsed = parse_action_request(
        {
            "action": "page.print_pdf",
            "target": target,
            "params": {"path": str(output)},
        }
    )
    result = worker._print_pdf(FakeCDP(), object(), parsed.params)

    assert result["path"] == str(output)
    assert output.read_bytes().startswith(b"%PDF-")


def test_tab_selection_never_defaults_to_the_first_tab() -> None:
    tabs = [
        FakeTab("tab-1", "https://one.example", "One"),
        FakeTab("tab-2", "https://two.example", "Two"),
    ]
    client = _cdp_with_tabs(tabs)

    with pytest.raises(AdapterError) as error:
        client.select_tab({})
    assert error.value.code == "TAB_SELECTOR_REQUIRED"
    assert [item["target_id"] for item in error.value.details["tabs"]] == [
        "tab-1",
        "tab-2",
    ]


def test_tab_index_must_agree_with_other_selector_fields() -> None:
    tabs = [
        FakeTab("tab-1", "https://one.example", "One"),
        FakeTab("tab-2", "https://two.example", "Two"),
    ]
    client = _cdp_with_tabs(tabs)

    assert client.select_tab({"index": 1, "title": "Two"}) is tabs[1]
    with pytest.raises(AdapterError) as error:
        client.select_tab({"index": 1, "title": "One"})
    assert error.value.code == "TAB_NOT_FOUND"


def test_locator_without_index_rejects_multiple_matches() -> None:
    expression = locator_expression({"css": ".result"}, "click")
    assert "Number.isInteger(spec.locator.index)" in expression
    assert "LOCATOR_AMBIGUOUS" in expression

    with pytest.raises(AdapterError) as error:
        ensure_locator_result(
            {"ok": False, "error": "LOCATOR_AMBIGUOUS", "count": 2}
        )
    assert error.value.code == "LOCATOR_AMBIGUOUS"
    assert error.value.http_status == 409


def test_snapshot_tool_exposes_the_required_exact_target() -> None:
    assert "page.snapshot" not in DIRECT_ACTION_SCHEMAS["chrome"]
    tool = build_tools(
        "chrome",
        ["page.snapshot"],
        include_gui=False,
        include_control_tools=False,
    )[0]["function"]

    assert tool["parameters"]["required"] == ["target"]
    target = tool["parameters"]["properties"]["target"]
    assert target["minProperties"] == 1
    assert target["additionalProperties"] is False
    assert set(target["properties"]) == {"target_id", "url", "title", "index"}
