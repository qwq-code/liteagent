from types import SimpleNamespace

import pytest

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools, select_actions, tool_name


class NoExecutor:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("Tool discovery must not execute application actions")


@pytest.mark.parametrize(
    "instruction",
    [
        "Highlight the selected cells in blue.",
        "Set the cell background to pale green.",
        "Apply amber highlighting to the warning cells.",
    ],
)
def test_cell_highlighting_reaches_the_normal_top_seven_tool_surface(instruction):
    selected = select_actions("libreoffice_calc", instruction, limit=7)
    assert len(selected) <= 7
    assert "range.format" in selected
    tools = build_tools(
        "libreoffice_calc", selected, include_gui=False, strict_generic=True
    )
    assert tool_name("range.format") in {tool["function"]["name"] for tool in tools}

    state = RuntimeState(
        task_id="synthetic-cell-highlighting",
        domain="libreoffice_calc",
        instruction=instruction,
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2032-04-09T12:00:00Z",
                proposed={
                    "kind": "adapter",
                    "tool": tool_name("workbook.inspect"),
                    "action": "workbook.inspect",
                    "arguments": {},
                },
                parsed=True,
                validated=True,
                executed=True,
                result={
                    "status": "ok",
                    "result": {
                        "title": "Inventory.ods",
                        "url": "file:///tmp/Inventory.ods",
                        "sheets": [{"name": "Items", "used_range_a1": "A1:C4"}],
                    },
                },
            )
        ],
    )
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", top_k_actions=7, include_gui=False),
        NoExecutor(),
        model_client=SimpleNamespace(client=object()),
    )
    exposed = {tool["function"]["name"] for tool in agent.tools(state)}
    assert tool_name("range.format") in exposed
    assert "tools_search" in exposed
