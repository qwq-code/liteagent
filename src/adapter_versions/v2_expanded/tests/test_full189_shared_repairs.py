from copy import deepcopy
from types import SimpleNamespace

import pytest
from jsonschema import ValidationError, validate

from calc_adapter import uno_worker
from integrations.lite_agent.adapter_results import adapter_context_hint
from integrations.lite_agent.batch_progress import batch_coverage_issues
from integrations.lite_agent.completion_policy import completion_claim_contradictions
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools
from os_adapter.errors import AdapterError
from os_adapter.schema import parse_action_request


def test_case_variant_reuses_existing_native_date_format_without_insertion(monkeypatch):
    class Formats:
        def queryKey(self, code, locale, scan):
            return 49 if code == 'YYYY-MM-DD' else -1
        def addNew(self, code, locale):
            raise AssertionError('duplicate built-in must not be inserted')
    monkeypatch.setattr(uno_worker, '_locale', lambda _: object())
    target = SimpleNamespace()
    assert uno_worker._apply_number_format(SimpleNamespace(getNumberFormats=Formats), target, 'yyyy-mm-dd') == 49
    assert target.NumberFormat == 49


def test_number_format_preserves_literal_units_and_escaped_characters(monkeypatch):
    seen = []
    class Formats:
        def queryKey(self, code, locale, scan):
            seen.append(code)
            return -1
        def addNew(self, code, locale):
            seen.append(code)
            return 77
    monkeypatch.setattr(uno_worker, '_locale', lambda _: object())
    code = 'yyyy "days" \\m _d *s [h]'
    uno_worker._apply_number_format(SimpleNamespace(getNumberFormats=Formats), SimpleNamespace(), code)
    assert seen == [code, 'YYYY "days" \\m _d *s [h]', code]


def test_misplaced_command_output_path_is_rejected_in_both_public_contracts():
    params = {'argv': ['echo', 'example'], 'cwd_source': 'explicit', 'cwd_path': '/tmp', 'provenance': 'none'}
    payload = {'params': params, 'target': {'stdout_path': '/tmp/out.txt'}}
    with pytest.raises(AdapterError, match='inside params'):
        parse_action_request({'action': 'command.run', **payload})
    tool = constrain_adapter_call_routes(build_tools('multi_apps', ['adapter.call'], include_gui=False), [('os', 'command.run')])[0]
    schema = tool['function']['parameters']
    with pytest.raises(ValidationError):
        validate({'payload': payload}, schema)
    fixed = {'params': {**params, 'stdout_path': '/tmp/out.txt'}}
    validate({'payload': fixed}, schema)
    assert parse_action_request({'action': 'command.run', **fixed}).params['stdout_path'] == '/tmp/out.txt'


def test_formula_looking_text_feedback_keeps_literal_contract():
    body = {'result': {'sheet': 'Data', 'range': 'D2:D3', 'written_cells': 2,
        'values': [['=A2+B2'], [5]], 'display_text': [['=A2+B2'], ['5']],
        'kinds': [['string'], ['formula']], 'formulas': [[''], ['=2+3']]}}
    before = deepcopy(body)
    hint = adapter_context_hint('libreoffice_calc', 'range.write', body)
    assert hint['literal_formula_cells'] == ['D2']
    assert hint['formulas'][1] == ['=2+3']
    assert 'TEXT, not calculated' in hint['guidance']
    assert body == before


@pytest.mark.parametrize('claim', [
    'The user can proceed to crop the picture and save it.',
    'The remaining sections can be extracted similarly.',
    'Remaining documents should be converted using the same method.',
])
def test_delegating_unfinished_work_is_not_completion(claim):
    assert completion_claim_contradictions({'reason': claim, 'evidence': 'some operations succeeded'})


@pytest.mark.parametrize('claim', [
    'All documents were converted; the user can open them.',
    'There are no remaining sections. All files were saved.',
])
def test_legitimate_followup_use_does_not_invalidate_completion(claim):
    assert not completion_claim_contradictions({'reason': claim, 'evidence': 'files verified'})


def event(step, adapter, action, hint):
    return ExecutionEvent(step=step, timestamp_utc='', executed=True,
        proposed={'kind': 'adapter', 'action': 'adapter.call', 'arguments': {
            'adapter': adapter, 'action': action, 'payload': {'params': {}}}},
        result={'context_hint': {'downstream_context': hint}})


def read(step, path, start, text, total):
    return event(step, 'vs_code', 'file.read_text', {'files': [{'path': path,
        'source_total_chars': total, 'chunks': [{'start_char': start, 'end_char': start+len(text),
            'text': text, 'offset_basis': 'unicode_characters'}]}]})


def test_all_text_sources_need_actual_content_and_paginated_reads_accumulate():
    state = RuntimeState(task_id='unrelated', domain='multi_apps', instruction='Combine all .txt files into a document.')
    state.events = [event(1, 'vs_code', 'workspace.find_files', {'matches': [
        {'path': '/tmp/a.txt', 'kind': 'file'}, {'path': '/tmp/b.txt', 'kind': 'file'}]}),
        read(2, '/tmp/a.txt', 0, 'alpha', 5), read(3, '/tmp/b.txt', 0, 'bet', 4)]
    assert batch_coverage_issues(state)[0]['remaining'] == ['/tmp/b.txt']
    state.events.append(read(4, '/tmp/b.txt', 3, 'a', 4))
    assert batch_coverage_issues(state) == []
    state.instruction = 'Summarize one .txt file.'
    state.events.pop()
    assert batch_coverage_issues(state) == []


def test_pdf_receipts_cannot_count_overwritten_path_twice():
    state = RuntimeState(task_id='another', domain='multi_apps', instruction='Split this book into PDFs, each containing a chapter.')
    state.events = [event(1, 'os', 'pdf.outline.inspect', {'input_path': '/tmp/book.pdf', 'section_count': 2,
        'sections': [{'title': 'Start', 'start_page': 2, 'end_page': 7}, {'title': 'End', 'start_page': 8, 'end_page': 14}]})]
    for step, start, end in [(2, 2, 7), (3, 8, 14)]:
        state.events.append(event(step, 'os', 'pdf.pages.extract', {'input_path': '/tmp/book.pdf',
            'output_path': '/tmp/one.pdf', 'start_page': start, 'end_page': end, 'verification_passed': True}))
    issue = batch_coverage_issues(state)[0]
    assert issue['remaining_count'] == 1 and issue['remaining'][0]['start_page'] == 2
    assert issue['advisory'] is True  # Does not falsely reject pre-existing chapter files.
    state.events.append(event(4, 'os', 'pdf.pages.extract', {'input_path': '/tmp/book.pdf',
        'output_path': '/tmp/two.pdf', 'start_page': 2, 'end_page': 7, 'verification_passed': True}))
    assert batch_coverage_issues(state) == []
