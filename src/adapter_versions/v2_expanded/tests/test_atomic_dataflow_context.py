import pytest
from integrations.lite_agent.adapter_results import compact_adapter_body
from integrations.lite_agent.completion_policy import requires_terminal_provenance


def test_workbook_context_disambiguates_zero_based_inclusive_endpoints():
    from integrations.lite_agent.adapter_results import workbook_inspect_context
    raw = {'sheets': [{'name': 'Data', 'used_range': {
        'start_column': 26, 'end_column': 28, 'start_row': 4, 'end_row': 19,
    }}]}
    sheet = workbook_inspect_context(raw)['sheets'][0]
    assert sheet['used_range_a1'] == 'AA5:AC20'
    assert sheet['used_range']['end_row'] == 19
    assert 'zero-based inclusive' in sheet['used_range']['coordinate_system']
    assert 'coordinate_system' not in raw['sheets'][0]['used_range']


def test_compacted_transform_result_preserves_input_output_and_operation():
    fields = {'source_sheet': 'Input', 'source_range': 'B2:B40',
              'destination_sheet': 'Output', 'destination_range': 'C2:C40',
              'operation': 'collapse_whitespace'}
    body = {'result': {**fields, 'readback': {'styles': [['verbose'*10000]]}}}
    compact = compact_adapter_body(body, max_chars=300)
    assert all(compact['result'][k] == v for k, v in fields.items())


@pytest.mark.parametrize('instruction', [
    'Quit the stuck application from the command line.',
    'Terminate this process using the shell.',
    'Copy the selected files in the terminal.',
    'Install the package with the command line.',
])
def test_explicit_execution_method_is_recognized_for_generic_operations(instruction):
    assert requires_terminal_provenance(instruction)


@pytest.mark.parametrize('instruction', [
    'Close the window with its close button.',
    'The terminal font is tiny; make it larger.',
    'Read the exported terminal log in the editor.',
])
def test_terminal_mention_alone_does_not_require_command_execution(instruction):
    assert not requires_terminal_provenance(instruction)


def test_forwarded_terminal_contract_requires_explicit_provenance_without_mutating_input():
    import copy
    from jsonschema import Draft202012Validator
    from integrations.lite_agent.tool_catalog import build_tools
    from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
    from integrations.lite_agent.terminal_tool_constraints import constrain_terminal_provenance_tools
    tools = constrain_adapter_call_routes(
        build_tools('multi_apps', ['adapter.call'], include_gui=False, include_control_tools=False, strict_generic=True),
        [('os', 'command.run')],
    )
    before = copy.deepcopy(tools)
    output = constrain_terminal_provenance_tools(tools, 'Stop the process from the command line.')
    validator = Draft202012Validator(output[0]['function']['parameters'])
    params = {'argv': ['kill', '123'], 'cwd_source': 'home', 'provenance': 'none'}
    call = {'adapter': 'os', 'action': 'command.run', 'payload': {'params': params}}
    assert not validator.is_valid(call)
    params['provenance'] = 'shell_history'
    assert validator.is_valid(call)
    assert tools == before


def test_multi_app_public_surface_preserves_execution_method_constraint():
    from jsonschema import Draft202012Validator
    from integrations.lite_agent.state_model import RuntimeState, ExecutionEvent
    from integrations.lite_agent.tool_surface import ToolSurfaceMixin
    from integrations.lite_agent.tool_catalog import build_tools
    state = RuntimeState(task_id='synthetic', domain='multi_apps', instruction='Quit the process from the command line.')
    state.events = [ExecutionEvent(
        step=1, timestamp_utc='', executed=True,
        proposed={'kind': 'catalog', 'tool': 'tools_search', 'arguments': {'query': 'os.command.run'}},
        result={'matches': [{'action': 'adapter.call', 'adapter': 'os', 'downstream_action': 'command.run'}]},
    )]
    tools = ToolSurfaceMixin._apply_common_tool_constraints(
        build_tools('multi_apps', ['adapter.call'], include_gui=False, strict_generic=True), state)
    tool = next(t for t in tools if t['function']['name'] == 'adapter__adapter_call')
    params = {'argv': ['kill', '123'], 'cwd_source': 'home', 'provenance': 'none'}
    call = {'adapter': 'os', 'action': 'command.run', 'payload': {'params': params}}
    validator = Draft202012Validator(tool['function']['parameters'])
    assert not validator.is_valid(call)
    params['provenance'] = 'shell_history'
    assert validator.is_valid(call)


def test_reapplying_route_constraints_does_not_widen_single_route():
    from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
    from integrations.lite_agent.tool_catalog import build_tools
    from jsonschema import Draft202012Validator
    tools = build_tools('multi_apps', ['adapter.call'], include_gui=False, include_control_tools=False, strict_generic=True)
    tools = constrain_adapter_call_routes(tools, [('libreoffice_calc', 'workbook.save')])
    tools = constrain_adapter_call_routes(tools, [('libreoffice_calc', 'workbook.save'), ('os', 'command.run')])
    validator = Draft202012Validator(tools[0]['function']['parameters'])
    assert validator.is_valid({'adapter': 'libreoffice_calc', 'action': 'workbook.save', 'payload': {'params': {}}})
    assert not validator.is_valid({'adapter': 'os', 'action': 'command.run', 'payload': {'params': {'argv': ['pwd'], 'cwd_source': 'home'}}})
