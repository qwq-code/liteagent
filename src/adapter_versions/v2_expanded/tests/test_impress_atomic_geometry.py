from copy import deepcopy
from types import SimpleNamespace

import jsonschema
import pytest

from impress_adapter import uno_worker
from impress_adapter.errors import AdapterError
from impress_adapter.geometry_contract import ATOMIC_GEOMETRY_FIELDS
from impress_adapter.schema import ACTIONS, parse_action_request
from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.completion_policy import effective_canonical_action
from integrations.lite_agent.model_client import _provider_tools
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools, public_actions, search_actions

DOMAIN = 'libreoffice_impress'
REFERENCE = {'slide': 0, 'selector': {'path': [1]}}
BEFORE = {'x': 1200, 'y': 2300, 'width': 4000, 'height': 5000}


def schema(action):
    tools = build_tools(DOMAIN, [action], include_gui=False, include_control_tools=False, strict_generic=True)
    return tools[0]['function']['parameters']


def native(monkeypatch, shape=None):
    shape = shape or SimpleNamespace(Position=SimpleNamespace(X=1200, Y=2300),
                                     Size=SimpleNamespace(Width=4000, Height=5000))
    page = SimpleNamespace(Width=24000, Height=16000)
    def pick(observed_page, selector):
        assert observed_page is page
        assert selector == {'path': [1]}
        return shape
    session = SimpleNamespace(page=lambda i: page if i == 0 else None, shape=pick)
    monkeypatch.setattr(uno_worker, 'ImpressSession', lambda _: session)
    monkeypatch.setattr(uno_worker, '_shape_summary_at_path', lambda selected, path: {
        'path': list(path), 'x': int(selected.Position.X), 'y': int(selected.Position.Y),
        'width': int(selected.Size.Width), 'height': int(selected.Size.Height)})
    return session, shape


@pytest.mark.parametrize('action,changes,after', [
    ('shape.align_to_slide', {'edge': 'bottom'}, {**BEFORE, 'y': 11000}),
    ('shape.align_to_slide', {'edge': 'right'}, {**BEFORE, 'x': 20000}),
    ('shape.align_to_slide', {'edge': 'left'}, {**BEFORE, 'x': 0}),
    ('shape.align_to_slide', {'edge': 'top'}, {**BEFORE, 'y': 0}),
    ('shape.move', {'x': -300}, {**BEFORE, 'x': -300}),
    ('shape.move', {'x': 900, 'y': 800}, {**BEFORE, 'x': 900, 'y': 800}),
    ('shape.resize', {'height_measurement': {'value': 2.5, 'unit': 'cm'}}, {**BEFORE, 'height': 2500}),
    ('shape.resize', {'width': 2800}, {**BEFORE, 'width': 2800}),
])
def test_each_atomic_operation_changes_only_its_explicit_geometry(monkeypatch, action, changes, after):
    native(monkeypatch)
    params = {**deepcopy(REFERENCE), **changes}
    original = deepcopy(params)
    jsonschema.validate(params, schema(action))
    payload = parse_action_request({'action': action, 'params': params}).to_worker_payload()
    response = uno_worker.execute(payload)
    result = response['result']
    assert {key: result[key] for key in BEFORE} == after
    assert result['verification_passed'] is True
    assert result['before_geometry'] == BEFORE
    assert result['operation'] == action
    assert params == original
    assert response['verification']['passed'] is True


@pytest.mark.parametrize('action,changes', [
    ('shape.align_to_slide', {'edge': 'bottom', 'height': 5000}),
    ('shape.align_to_slide', {'edge': 'bottom', 'height_measurement': {'value': 3173, 'unit': 'mm'}}),
    ('shape.align_to_slide', {'edge': 'diagonal'}),
    ('shape.move', {'x': 200, 'width': 4000}),
    ('shape.move', {'x': True}),
    ('shape.resize', {'height': 2000, 'edge': 'bottom'}),
    ('shape.resize', {'height': 2000, 'height_measurement': {'value': 2, 'unit': 'cm'}}),
    ('shape.resize', {'height_measurement': {'value': 2000, 'unit': 'hundredth-millimeter'}}),
    ('shape.resize', {'height': 0}),
    ('shape.resize', {}),
])
def test_mixed_or_invalid_geometry_is_rejected_before_execution(action, changes):
    params = {**deepcopy(REFERENCE), **changes}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(params, schema(action))
    with pytest.raises(AdapterError):
        parse_action_request({'action': action, 'params': params})


def test_resize_cannot_report_success_when_native_side_effect_moves_shape(monkeypatch):
    class MovesOnResize:
        Position = SimpleNamespace(X=1200, Y=2300)
        _size = SimpleNamespace(Width=4000, Height=5000)
        @property
        def Size(self):
            return self._size
        @Size.setter
        def Size(self, value):
            self._size = value
            self.Position.X = 100
    native(monkeypatch, MovesOnResize())
    payload = parse_action_request({'action': 'shape.resize', 'params': {**REFERENCE, 'width': 7000}}).to_worker_payload()
    with pytest.raises(AdapterError, match='native read-back'):
        uno_worker.execute(payload)


@pytest.mark.parametrize('action', list(ATOMIC_GEOMETRY_FIELDS))
def test_owned_schema_provider_schema_and_dispatch_cover_every_atomic_action(action):
    assert action in ACTIONS and action in uno_worker.ACTIONS and action in public_actions(DOMAIN)
    tools = build_tools(DOMAIN, [action], include_gui=False, include_control_tools=False, strict_generic=True)
    provider = _provider_tools(tools)[0]['function']['parameters']
    assert set(provider['properties']) == {'slide', 'slide_number', 'selector', *ATOMIC_GEOMETRY_FIELDS[action]}
    assert provider['additionalProperties'] is False
    event = ExecutionEvent(step=1, timestamp_utc='', executed=True,
        proposed={'kind': 'adapter', 'action': action, 'arguments': deepcopy(REFERENCE)}, result={})
    assert effective_canonical_action(event, DOMAIN) == (DOMAIN, 'shape.set_geometry', REFERENCE)
    state = RuntimeState(task_id='synthetic', domain=DOMAIN, instruction='Move the shape.', events=[event])
    assert state.successful_action_events('shape.set_geometry') == [event]
    assert event.proposed['action'] == action


def test_agent_exposes_atomic_geometry_tools_and_retains_legacy_api_compatibility():
    agent = LiteAgent(LiteAgentConfig(base_url='http://unused/v1', include_gui=False), object())
    try:
        tools = agent._build_tools(DOMAIN, ['presentation.inspect', 'shape.set_geometry'], include_gui=False)
        names = {t['function']['name'] for t in tools}
        assert {'adapter__shape_align_to_slide', 'adapter__shape_move', 'adapter__shape_resize'} <= names
        assert 'adapter__shape_set_geometry' not in names
        assert 'adapter__presentation_inspect' in names
        legacy = {**REFERENCE, 'x': 300, 'height': 6000}
        jsonschema.validate(legacy, schema('shape.set_geometry'))
        assert parse_action_request({'action': 'shape.set_geometry', 'params': legacy}).action == 'shape.set_geometry'
    finally:
        agent.client.close()


def test_geometry_search_finds_the_responsible_atomic_operation():
    for query, expected in [('align picture bottom edge', 'shape.align_to_slide'), ('resize picture height cm', 'shape.resize')]:
        matches = search_actions(DOMAIN, query, limit=3, strict_generic=True)
        assert expected in [m['action'] for m in matches]


def test_discovered_compatibility_route_remains_callable(monkeypatch):
    agent = LiteAgent(LiteAgentConfig(base_url='http://unused/v1', include_gui=False), object())
    try:
        state = RuntimeState(task_id='synthetic-discovery', domain=DOMAIN, instruction='Move the picture.')
        atoms = agent._build_tools(DOMAIN, ['shape.set_geometry'], include_gui=False)
        monkeypatch.setattr(agent, '_tools_for_state', lambda _: atoms)
        assert 'adapter__shape_set_geometry' not in {t['function']['name'] for t in agent.tools(state)}
        state.expanded_actions = ['shape.set_geometry']
        assert 'adapter__shape_set_geometry' in {t['function']['name'] for t in agent.tools(state)}
        assert atoms == agent._tools_for_state(state)
    finally:
        agent.client.close()


def test_full_execution_preserves_model_selected_atomic_action_and_arguments(monkeypatch):
    import json
    native(monkeypatch)
    calls = []
    def execute(domain, action, arguments, metadata):
        calls.append((domain, action, deepcopy(arguments)))
        response = uno_worker.execute(parse_action_request({'action': action, 'params': arguments}).to_worker_payload())
        return {'executed': True, 'result': response}
    agent = LiteAgent(LiteAgentConfig(base_url='http://unused/v1', include_gui=False), SimpleNamespace(execute=execute))
    try:
        state = RuntimeState(task_id='synthetic-atomic-execution', domain=DOMAIN,
                             instruction='Move the picture to the bottom edge of slide 1.')
        params = {**deepcopy(REFERENCE), 'edge': 'bottom'}
        tools = agent._build_tools(DOMAIN, ['shape.set_geometry'], include_gui=False)
        event = agent.execute_proposal(state, {'tool': 'adapter__shape_align_to_slide',
            'arguments_raw': json.dumps(params), '_model_visible_tools': tools})
        assert event.executed, event.error
        assert calls == [(DOMAIN, 'shape.align_to_slide', params)]
        assert event.proposed['arguments'] == params
        assert event.proposed['action'] == 'shape.align_to_slide'
        assert 'arguments_source' not in event.proposed
        assert effective_canonical_action(event, DOMAIN) == (DOMAIN, 'shape.set_geometry', params)
    finally:
        agent.client.close()
