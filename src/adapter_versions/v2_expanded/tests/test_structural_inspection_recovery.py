from copy import deepcopy
from types import SimpleNamespace

import pytest

from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.structural_observation_recovery import recover_structural_tool_surface
from integrations.lite_agent.tool_catalog import build_tools


def make_state():
    state = RuntimeState(task_id='synthetic', domain='libreoffice_impress', instruction='Insert a table.')
    event = ExecutionEvent(step=1, timestamp_utc='', executed=True,
        proposed={'kind': 'adapter', 'action': 'presentation.inspect', 'arguments': {'slides': [2]}},
        result={'context_hint': {'slides': [{'slide_index': 2, 'text_shapes': [
            {'index': 0, 'path': [0], 'lines': ['Overview']}
        ]}]}})
    state.events = [event, deepcopy(event)]
    state.events[-1].step = 2
    return state


def content(state, gui=False):
    agent = AgentProtocolMixin()
    agent.config = SimpleNamespace(include_gui=True)
    tools = [{'type': 'function', 'function': {'name': 'adapter__table_create'}}]
    if gui:
        tools.append({'type': 'function', 'function': {'name': 'gui_action'}})
    return agent._messages(state, b'synthetic-image', available_tools=tools)[-1]['content']


def test_repeated_structural_read_uses_text_recovery_without_changing_ledger():
    state = make_state()
    original = deepcopy(state.events)
    result = content(state)
    assert [item['type'] for item in result] == ['text']
    assert 'Overview' in result[0]['text']
    assert 'same state' in result[0]['text']
    assert state.events == original


@pytest.mark.parametrize('case', ['first_read', 'different_target', 'changed_state', 'failure', 'mutation', 'gui_available'])
def test_visual_context_is_retained_outside_unchanged_structural_cycle(case):
    state = make_state()
    if case == 'first_read':
        state.events = state.events[:1]
    elif case == 'different_target':
        state.events[-1].proposed['arguments'] = {'slides': [3]}
    elif case == 'changed_state':
        state.events[-1].result['context_hint']['slides'][0]['text_shapes'][0]['lines'] = ['Changed']
    elif case == 'failure':
        state.events[-1].executed = False
        state.events[-1].error = {'type': 'NO_DOCUMENT'}
    elif case == 'mutation':
        state.events[-1].proposed['action'] = 'table.create'
    assert any(item['type'] == 'image_url' for item in content(state, gui=case == 'gui_available'))


def test_forwarded_inspection_preserves_same_recovery_boundary():
    state = make_state()
    state.domain = 'multi_apps'
    for event in state.events:
        event.proposed = {'kind': 'adapter', 'action': 'adapter.call', 'arguments': {
            'adapter': 'libreoffice_impress', 'action': 'presentation.inspect',
            'payload': {'params': {'slides': [2]}}}}
    assert [item['type'] for item in content(state)] == ['text']


def test_repeated_inspection_yields_to_edit_or_search_then_recovers():
    state = make_state()
    tools = build_tools(state.domain, ['presentation.inspect', 'table.create', 'presentation.save'],
                        include_gui=False, strict_generic=True)
    original = deepcopy(tools)
    original_events = deepcopy(state.events)
    recovered = recover_structural_tool_surface(tools, state)
    names = {t['function']['name'] for t in recovered}
    assert 'adapter__presentation_inspect' not in names
    assert {'adapter__table_create', 'adapter__presentation_save', 'tools_search'} <= names
    assert tools == original
    assert state.events == original_events
    state.events.append(ExecutionEvent(step=3, timestamp_utc='', executed=True,
        proposed={'kind': 'catalog', 'tool': 'tools_search', 'arguments': {'query': 'inspect another slide'}},
        result={'matches': []}))
    assert recover_structural_tool_surface(tools, state) == original


@pytest.mark.parametrize('case', ['first_read', 'changed_result', 'changed_target', 'failed', 'read_only', 'no_search', 'gui', 'forwarded'])
def test_inspection_remains_available_when_recovery_could_hide_needed_observation(case):
    state = make_state()
    actions = ['presentation.inspect', 'table.create', 'presentation.save']
    if case == 'first_read':
        state.events.pop()
    elif case == 'changed_result':
        state.events[-1].result['context_hint']['slides'][0]['text_shapes'][0]['lines'] = ['New']
    elif case == 'changed_target':
        state.events[-1].proposed['arguments'] = {'slides': [3]}
    elif case == 'failed':
        state.events[-1].error = {'code': 'INSPECTION_FAILED'}
    elif case == 'read_only':
        actions.remove('table.create')
    tools = build_tools(state.domain, actions, include_gui=case == 'gui', strict_generic=True)
    if case == 'no_search':
        tools = [t for t in tools if t['function']['name'] != 'tools_search']
    if case == 'forwarded':
        state.domain = 'multi_apps'
    assert recover_structural_tool_surface(tools, state) == tools


def test_agent_surface_and_messages_share_structural_recovery():
    from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
    agent = LiteAgent(LiteAgentConfig(base_url='http://unused/v1'), object())
    state = make_state()
    state.instruction = 'Make the titles on slides 2 and 3 blue and bold.'
    names = {t['function']['name'] for t in agent.tools(state)}
    assert 'adapter__slides_format_text_roles' in names
    assert 'tools_search' in names
    assert 'adapter__presentation_inspect' not in names
    state.events.pop()
    assert 'adapter__presentation_inspect' in {t['function']['name'] for t in agent.tools(state)}


def test_saved_edit_and_duplicate_observations_offer_review_not_another_undo():
    state = make_state()
    edit = ExecutionEvent(step=1, timestamp_utc='', executed=True,
        proposed={'kind': 'adapter', 'action': 'presentation.set_page_size',
                  'arguments': {'width': 19000, 'height': 27000}},
        result={'context_hint': {'verification_passed': True}})
    save = ExecutionEvent(step=2, timestamp_utc='', executed=True,
        proposed={'kind': 'adapter', 'action': 'presentation.save', 'arguments': {}},
        result={'context_hint': {'saved': True}})
    for i, e in enumerate(state.events, 3):
        e.step = i
    state.events = [edit, save, *state.events]
    tools = build_tools(state.domain, ['presentation.inspect', 'presentation.set_page_size', 'presentation.save'],
                        include_gui=True, strict_generic=True)
    before = deepcopy(state.events)
    reviewed = recover_structural_tool_surface(tools, state)
    assert {t['function']['name'] for t in reviewed} == {'tools_search', 'propose_done', 'fail_task'}
    assert state.events == before
    # An unfinished requirement can be pursued through search; no automatic
    # completion or mutation is inserted, and ordinary tools return immediately.
    state.events.append(ExecutionEvent(step=5, timestamp_utc='', executed=True,
        proposed={'kind': 'catalog', 'tool': 'tools_search', 'arguments': {'query': 'resize slides'}},
        result={'matches': []}))
    assert recover_structural_tool_surface(tools, state) == tools


def test_unsaved_edit_retains_edit_and_save_choices():
    state = make_state()
    state.events.insert(0, ExecutionEvent(step=0, timestamp_utc='', executed=True,
        proposed={'kind': 'adapter', 'action': 'table.create', 'arguments': {}}, result={}))
    tools = build_tools(state.domain, ['presentation.inspect', 'table.create', 'presentation.save'],
                        include_gui=False, strict_generic=True)
    names = {t['function']['name'] for t in recover_structural_tool_surface(tools, state)}
    assert {'adapter__table_create', 'adapter__presentation_save', 'tools_search'} <= names


def test_repeated_observation_after_save_without_edit_keeps_mutation_available():
    state = make_state()
    state.events.insert(0, ExecutionEvent(step=0, timestamp_utc='', executed=True,
        proposed={'kind': 'adapter', 'action': 'presentation.save', 'arguments': {}}, result={}))
    tools = build_tools(state.domain, ['presentation.inspect', 'table.create', 'presentation.save'],
                        include_gui=False, strict_generic=True)
    names = {t['function']['name'] for t in recover_structural_tool_surface(tools, state)}
    assert 'adapter__table_create' in names
    assert 'adapter__presentation_save' not in names


@pytest.mark.parametrize('kind', ['gui', 'dispatched_failure'])
def test_intervening_possible_mutation_invalidates_saved_review(kind):
    state = make_state()
    edit = ExecutionEvent(step=0, timestamp_utc='', executed=True,
        proposed={'kind': 'adapter', 'action': 'table.create', 'arguments': {}}, result={})
    save = ExecutionEvent(step=1, timestamp_utc='', executed=True,
        proposed={'kind': 'adapter', 'action': 'presentation.save', 'arguments': {}}, result={})
    change = ExecutionEvent(step=2, timestamp_utc='', executed=kind == 'gui', validated=True,
        proposed={'kind': 'gui' if kind == 'gui' else 'adapter',
                  'action': 'table.create', 'arguments': {}},
        error=None if kind == 'gui' else {'type': 'partial_execution_failure'})
    state.events = [edit, save, change, *state.events]
    tools = build_tools(state.domain, ['presentation.inspect', 'table.create', 'presentation.save'],
                        include_gui=False, strict_generic=True)
    names = {t['function']['name'] for t in recover_structural_tool_surface(tools, state)}
    assert {'adapter__table_create', 'adapter__presentation_save'} <= names
