from types import SimpleNamespace

import pytest

from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.state_model import RuntimeState
from integrations.lite_agent.tool_catalog import build_tools


@pytest.mark.parametrize("domain,action", [
    ("libreoffice_writer", "document.append_paragraphs"),
    ("libreoffice_writer", "table.insert_after_text"),
    ("libreoffice_calc", "workbook.create_new"),
    ("libreoffice_impress", "slide.set_notes"),
    ("vs_code", "file.replace_literal"),
])
@pytest.mark.parametrize("discovered", [False, True])
def test_content_write_has_same_budget_on_direct_and_discovered_routes(domain, action, discovered):
    state = RuntimeState(task_id="synthetic", domain="multi_apps" if discovered else domain,
                         instruction="Write the supplied content.")
    tools = build_tools(state.domain, ["adapter.call" if discovered else action],
                        include_gui=False, include_control_tools=False, strict_generic=True)
    if discovered:
        tools = constrain_adapter_call_routes(tools, [(domain, action)])

    class Probe(AgentProtocolMixin):
        config = SimpleNamespace(max_output_tokens=512)

        def tools(self, state):
            return tools

    assert Probe().output_token_budget(state) == 4096


def test_inspection_does_not_inflate_generation_budget():
    state = RuntimeState(task_id="synthetic", domain="libreoffice_writer", instruction="Inspect.")

    class Probe(AgentProtocolMixin):
        config = SimpleNamespace(max_output_tokens=512)

        def tools(self, state):
            return build_tools(state.domain, ["document.inspect"], include_gui=False,
                               include_control_tools=False, strict_generic=True)

    assert Probe().output_token_budget(state) == 512
