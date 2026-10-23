from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools
from integrations.lite_agent.tool_surface import ToolSurfaceMixin


def state_with_failed_route():
    return RuntimeState(
        task_id='synthetic-replan', domain='multi_apps',
        instruction='Find the supplied source file and correct its behavior.',
        events=[
            ExecutionEvent(step=1, timestamp_utc='', executed=True,
                proposed={'kind': 'catalog', 'tool': 'tools_search', 'arguments': {'query': 'os.filesystem.find'}},
                result={'matches': [{'action': 'adapter.call', 'adapter': 'os', 'downstream_action': 'filesystem.find'}]}),
            ExecutionEvent(step=2, timestamp_utc='', executed=False,
                proposed={'kind': 'adapter', 'action': 'adapter.call', 'tool': 'adapter__adapter_call',
                    'arguments': {'adapter': 'os', 'action': 'filesystem.find',
                        'payload': {'params': {'roots': ['~/guessed-folder'], 'name_patterns': ['*.py']}}}},
                error={'code': 'PATH_NOT_FOUND', 'message': 'path does not exist: /home/user/guessed-folder'}),
        ],
    )


def test_failed_forwarded_route_reopens_catalog_without_selecting_a_replacement():
    state = state_with_failed_route()
    tools = ToolSurfaceMixin._apply_common_tool_constraints(
        build_tools('multi_apps', ['adapter.call'], include_gui=False, strict_generic=True), state)
    names = {t['function']['name'] for t in tools}
    assert 'tools_search' in names
    assert 'adapter__adapter_call' in names
    assert state.events[-1].proposed['arguments']['payload']['params']['roots'] == ['~/guessed-folder']


def test_full_agent_surface_allows_replanning_after_a_native_route_error():
    agent = LiteAgent(LiteAgentConfig(base_url='http://unused/v1'), object())
    names = {t['function']['name'] for t in agent.tools(state_with_failed_route())}
    assert 'tools_search' in names


def test_untried_catalog_route_still_requires_one_attempt_before_another_search():
    state = state_with_failed_route()
    state.events.pop()
    tools = ToolSurfaceMixin._apply_common_tool_constraints(
        build_tools('multi_apps', ['adapter.call'], include_gui=False, strict_generic=True), state)
    assert 'tools_search' not in {t['function']['name'] for t in tools}
