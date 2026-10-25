from types import SimpleNamespace

import pytest
from jsonschema import validate

from writer_adapter import uno_worker as writer
from writer_adapter.errors import AdapterError
from writer_adapter.schema import validate_action_params
from writer_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from integrations.lite_agent.completion_outcomes import completion_outcome_issues
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools, search_actions
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.semantic_requirements import strict_semantic_requirement_errors


def event(step, action, args=None, payload=None):
    return ExecutionEvent(step=step, timestamp_utc='', parsed=True, validated=True, executed=True,
        proposed={'kind': 'adapter', 'action': action, 'arguments': args or {}},
        result={'adapter_response': {'status': 'ok', 'result': payload or {}}})


@pytest.mark.parametrize('newline', ['\n', '\r\n', '\r'])
def test_source_file_append_preserves_unicode_newlines_existing_text_and_order(tmp_path, newline):
    class Text:
        String = 'Prefix:'
        def getEnd(self): return object()
        def createTextCursorByRange(self, end): return object()
        def insertString(self, cursor, value, absorb): self.String += value
    text = Text()
    session = SimpleNamespace(doc=SimpleNamespace(Text=text))
    source = tmp_path/'part.txt'
    content = f'第一行{newline}second\tline{newline}'
    source.write_bytes(content.encode())
    result = writer._append_text_file(session, {'path': str(source), 'separator': ''})
    assert text.String == 'Prefix:第一行\nsecond\tline\n'
    assert result['content_verified'] is True
    assert result['source_chars'] == len(content)
    writer._append_text_file(session, {'path': str(source), 'separator': '|next|'})
    assert text.String.endswith('|next|第一行\nsecond\tline\n')
    assert source.read_bytes() == content.encode()


@pytest.mark.parametrize('data', [b'\x00ABC', b'\xff\xff'])
def test_binary_or_invalid_text_is_rejected_before_mutation(tmp_path, data):
    path = tmp_path/'bad.txt'
    path.write_bytes(data)
    with pytest.raises(AdapterError):
        writer._append_text_file(SimpleNamespace(), {'path': str(path)})


def test_single_file_append_is_public_and_typed_without_batch_or_shell_fields():
    action = 'document.append_text_file'
    params = {'path': '/tmp/observed.txt', 'separator': ''}
    validate_action_params(action, params)
    validate(params, STRICT_ACTION_PARAM_SCHEMAS[action])
    tools = constrain_adapter_call_routes(build_tools('multi_apps', ['adapter.call'], include_gui=False), [('libreoffice_writer', action)])
    assert tools
    assert any(action in str(hit) for hit in search_actions('multi_apps', 'append text file verbatim Writer'))
    with pytest.raises(AdapterError):
        validate_action_params(action, {'paths': ['/tmp/a', '/tmp/b']})


def calc_state(instruction, events):
    return RuntimeState(task_id='synthetic', domain='libreoffice_calc', instruction=instruction, events=events)


def test_requested_empty_column_is_detected_but_stale_reads_and_zero_are_not():
    data = {'sheet': 'Output', 'range': 'A1:B3', 'display_text': [['Year', 'Change'], ['', '0.1'], ['', '0.2']]}
    state = calc_state('Calculate annual changes in a table with "Year" and "Change".', [event(1, 'range.read', payload=data)])
    assert 'table.empty_requested_column' in {x['code'] for x in completion_outcome_issues(state)}
    data['display_text'][1][0] = '0'
    assert completion_outcome_issues(state) == []
    data['display_text'][1][0] = ''
    state.events.append(event(2, 'range.write', {'sheet': 'Output', 'range': 'A2:A3', 'values': [[2030], [2031]]}))
    assert completion_outcome_issues(state) == []
    state.events.pop()
    state.instruction = 'Create an empty template with "Year" and "Change".'
    assert completion_outcome_issues(state) == []


def test_native_chart_x_axis_is_not_counted_as_a_value_series():
    payload = {'name': 'Trend', 'sheet': 'Data', 'category_axes': [], 'data_series': [{'labels': ['Observed Time']}, {'labels': ['Amount']}]}
    state = calc_state('Create a line chart with "Observed Time" column on the X-axis and amount on Y-axis.', [event(1, 'chart.create', payload=payload)])
    assert 'chart.category_is_value_series' in {x['code'] for x in completion_outcome_issues(state)}
    payload['category_axes'] = [{'labels': ['a', 'b']}]
    assert completion_outcome_issues(state) == []


def test_color_mismatch_reports_instruction_color_and_actual_executed_rgb():
    state = RuntimeState(task_id='synthetic-color', domain='libreoffice_impress',
        instruction='Underline the body text but not title or table. Set the font color to the "blue" color.',
        events=[event(1, 'slide.format_text_roles', {'slide': 0, 'roles': ['all'], 'color': 0xCCCCCD, 'overrides': [{'roles': ['body'], 'underline': True}]})])
    errors = strict_semantic_requirement_errors(state)
    assert any("name='blue'" in error and '#0000FF' in error and '#CCCCCD' in error for error in errors)


def test_reading_all_sources_does_not_count_as_writing_all_sources():
    from integrations.lite_agent.batch_progress import batch_coverage_issues
    from test_full189_shared_repairs import event as forwarded, read
    state = RuntimeState(task_id='files', domain='multi_apps', instruction='Concatenate all .txt files into a Writer document.')
    state.events = [forwarded(1, 'os', 'filesystem.find', {'matches': [
        {'path': '/tmp/first.txt', 'kind': 'file'}, {'path': '/tmp/second.txt', 'kind': 'file'}]}),
        read(2, '/tmp/first.txt', 0, 'First.', 6), read(3, '/tmp/second.txt', 0, 'Second.', 7),
        forwarded(4, 'libreoffice_writer', 'document.append_paragraphs', {'paragraphs': ['Second.']})]
    issues = batch_coverage_issues(state)
    assert issues[0]['code'] == 'unwritten_batch_sources'
    assert issues[0]['remaining'] == ['/tmp/first.txt']
    state.events.append(forwarded(5, 'libreoffice_writer', 'document.append_text_file', {'source_path': '/tmp/first.txt', 'content_verified': True}))
    assert batch_coverage_issues(state) == []


def test_verbatim_transfer_counts_without_model_retyping_source():
    from integrations.lite_agent.batch_progress import batch_coverage_issues
    from test_full189_shared_repairs import event as forwarded
    state = RuntimeState(task_id='files', domain='multi_apps', instruction='Combine all .txt files.')
    state.events = [forwarded(1, 'os', 'filesystem.find', {'matches': [{'path': '/tmp/a.txt', 'kind': 'file'}]}),
        forwarded(2, 'libreoffice_writer', 'document.append_text_file', {'source_path': '/tmp/a.txt', 'content_verified': True})]
    assert batch_coverage_issues(state) == []
    state.events[-1].result['context_hint']['downstream_context']['content_verified'] = False
    assert batch_coverage_issues(state)


def test_sar_dependency_is_selected_only_from_explicit_visible_instruction():
    from scripts.run_lite_agent_pilot import prepare_guest_setup_dependencies
    captured = []
    class Controller:
        def execute_python_command(self, code):
            captured.append(code)
            return {'output': '{"required":["sar"],"prepared":["sar"]}'}
    assert prepare_guest_setup_dependencies(Controller(), {'instruction': 'Use sar to sample resource usage.'})['prepared'] == ['sar']
    assert 'sysstat' in captured[-1]
    captured.clear()
    assert prepare_guest_setup_dependencies(Controller(), {'instruction': 'Write a resource report.'}) == {'required': [], 'prepared': []}
    assert captured == []
