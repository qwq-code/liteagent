from __future__ import annotations

import pytest

from integrations.lite_agent.contact_spreadsheet_semantics import (
    requests_contact_csv_export,
    required_actions,
)
from integrations.lite_agent.instruction_semantics import (
    strict_instruction_required_actions,
)
from integrations.lite_agent.tool_catalog import search_actions


@pytest.mark.parametrize(
    "instruction",
    [
        "Please export my contacts to people.csv.",
        "I need help exporting my contacts to people.csv.",
        "The utility exports my contacts to people.csv.",
        "My contacts are exported to people.csv.",
        "Please save my contacts to people.csv.",
        "I need help saving my contacts to people.csv.",
        "The utility saves my contacts to people.csv.",
        "My contacts are saved to people.csv.",
    ],
)
def test_contact_csv_export_accepts_common_verb_forms(instruction: str) -> None:
    assert requests_contact_csv_export(instruction)
    assert required_actions("multi_apps", instruction) == ["contacts.export_csv"]


@pytest.mark.parametrize(
    "instruction",
    [
        "Please export invoices to people.csv.",
        "Please export my contacts to people.pdf.",
        "Please review my contacts.csv.",
        "The address book contains contacts.csv.",
    ],
)
def test_contact_csv_export_requires_export_intent_and_csv_output(
    instruction: str,
) -> None:
    assert not requests_contact_csv_export(instruction)
    assert required_actions("multi_apps", instruction) == []


def test_gerund_contact_instruction_recalls_export_before_conversion() -> None:
    instruction = (
        "I am exporting my address book contacts to people.csv and then "
        "convert it to roster.xlsx."
    )

    required = required_actions("multi_apps", instruction)
    assert required == ["contacts.export_csv", "document.convert"]
    assert strict_instruction_required_actions("multi_apps", instruction) == []

    matches = search_actions(
        "multi_apps",
        "Thunderbird export contacts CSV",
        instruction=instruction,
        semantic_actions=required,
        strict_generic=True,
        limit=6,
    )
    assert matches
    assert matches[0]["action"] == "adapter.call"
    assert matches[0]["adapter"] == "thunderbird"
    assert matches[0]["downstream_action"] == "contacts.export_csv"
