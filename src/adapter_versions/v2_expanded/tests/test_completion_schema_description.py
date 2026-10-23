from __future__ import annotations

import pytest

from integrations.lite_agent.completion_policy import (
    COMPLETION_ARGUMENT_SCHEMA,
    completion_claim_contract_errors,
)
from integrations.lite_agent.tool_catalog import build_tools


def _public_propose_done_schema() -> dict:
    tool = next(
        tool
        for tool in build_tools(
            "os",
            ["filesystem.find"],
            include_gui=False,
            include_control_tools=True,
            strict_generic=True,
        )
        if tool["function"]["name"] == "propose_done"
    )
    return tool["function"]["parameters"]


def test_propose_done_schema_describes_evidence_statement_or_array() -> None:
    schema = _public_propose_done_schema()
    evidence = schema["properties"]["evidence"]

    assert schema["required"] == ["reason", "evidence"]
    assert evidence["type"] == ["string", "array"]
    assert evidence["minLength"] == 1
    assert evidence["minItems"] == 1
    variants = evidence["items"]["oneOf"]
    assert {item["type"] for item in variants} == {"string", "object"}
    assert "native JSON array" in evidence["description"]
    assert "plain text" in evidence["description"]
    assert "plain-text evidence statement" in variants[0]["description"]
    assert "structured evidence record" in variants[1]["description"]


@pytest.mark.parametrize(
    "evidence",
    [
        "verification passed",
        '["verification passed"]',
        '["verification passed",]',
        ["verification passed"],
        [{"status": "ok"}],
    ],
)
def test_schema_accepts_statement_or_native_string_or_object_array(evidence) -> None:
    assert (
        completion_claim_contract_errors(
            {"reason": "Done", "evidence": evidence}
        )
        == []
    )


@pytest.mark.parametrize("evidence", ["", [], None, 7, True, {}, [7]])
def test_schema_rejects_empty_or_invalid_evidence(evidence) -> None:
    assert completion_claim_contract_errors({"reason": "Done", "evidence": evidence})


def test_schema_still_requires_evidence() -> None:
    assert completion_claim_contract_errors({"reason": "Done"})


def test_public_surface_copies_the_shared_completion_schema() -> None:
    schema = _public_propose_done_schema()
    assert schema == COMPLETION_ARGUMENT_SCHEMA
