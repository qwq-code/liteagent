"""Single-operation contracts and preservation of unrelated state."""

import pytest
from jsonschema import Draft202012Validator

from calc_adapter.schema import validate_action_params as validate_calc
from calc_adapter.errors import AdapterError as CalcError
from calc_adapter.uno_worker import execute as execute_calc
from integrations.lite_agent.tool_catalog import build_tools
from thunderbird_adapter.actions import ThunderbirdActions
from thunderbird_adapter.errors import AdapterError
from thunderbird_adapter.filter_contract import compile_filter_configuration
from thunderbird_adapter.profile import write_filters
from thunderbird_adapter.schema import validate_action_params as validate_mail
from thunderbird_adapter import verifier, worker


def exposed(domain, action):
    return build_tools(domain, [action], include_gui=False, include_control_tools=False,
                       strict_generic=True)[0]['function']['parameters']


@pytest.mark.parametrize('action,good,bad', [
    ('mail.configure', {'dark_mode': True}, {'dark_mode': True, 'unified_inbox': True}),
    ('preferences.update', {'values': {'mail.test': True}}, {'values': {'mail.a': True, 'mail.b': False}}),
    ('preferences.update', {'remove_keys': ['mail.test']}, {'remove_keys': ['mail.a', 'mail.b']}),
    ('preferences.update', {'values': {'mail.test': 1}}, {'values': {'mail.test': 1}, 'remove_keys': ['mail.b']}),
])
def test_mail_contract_accepts_one_change_and_rejects_compound(action, good, bad):
    schema = Draft202012Validator(exposed('thunderbird', action))
    assert schema.is_valid(good)
    validate_mail(action, good)
    assert not schema.is_valid(bad)
    with pytest.raises(AdapterError):
        validate_mail(action, bad)
    with pytest.raises(AdapterError):
        ThunderbirdActions().dispatch(action, bad, 1)


def test_calc_transform_rejects_compound_before_document_connection():
    good = dict(source_sheet='Source', source_range='A1:A2', destination_sheet='Source',
                destination='B1', operation='trim')
    bad = {**good, 'operations': ['trim', 'uppercase']}
    schema = Draft202012Validator(exposed('libreoffice_calc', 'range.text_transform'))
    assert schema.is_valid(good)
    validate_calc('range.text_transform', good)
    assert not schema.is_valid(bad)
    with pytest.raises(CalcError, match='one operation'):
        execute_calc({'action': 'range.text_transform', 'params': bad})


def rule(name='Receipt', destination='Bills'):
    return {'name': name, 'condition_mode': 'all_messages', 'conditions': [],
            'action': 'move_to_local_folder', 'destination': destination}


def test_filter_contract_rejects_batch_and_unnamed_rules():
    schema = Draft202012Validator(exposed('thunderbird', 'filters.configure'))
    good = {'filters': [rule()]}
    assert schema.is_valid(good)
    validate_mail('filters.configure', good)
    unnamed = rule()
    unnamed.pop('name')
    for bad in [{'filters': [rule(), rule('Other')]}, {'filters': [unnamed]}]:
        assert not schema.is_valid(bad)
        with pytest.raises(AdapterError):
            compile_filter_configuration(bad)


def compiled(name='Receipt', destination='Bills'):
    return compile_filter_configuration({'filters': [rule(name, destination)]})['filters']


def test_named_upsert_preserves_other_rules_and_is_idempotent(tmp_path):
    path = tmp_path / 'msgFilterRules.dat'
    write_filters(path, compiled('Other', 'Archive'))
    before = path.read_bytes()
    write_filters(path, compiled())
    assert path.read_bytes().startswith(before)
    write_filters(path, compiled(destination='Paid'))
    updated = path.read_bytes()
    assert updated.startswith(before)
    assert updated.count(b'name="Receipt"') == 1
    assert b'Paid' in updated and b'Bills' not in updated
    write_filters(path, compiled(destination='Paid'))
    assert path.read_bytes() == updated


def test_duplicate_rule_name_does_not_modify_file(tmp_path):
    path = tmp_path / 'msgFilterRules.dat'
    write_filters(path, compiled())
    path.write_text(path.read_text() + path.read_text())
    original = path.read_bytes()
    with pytest.raises(AdapterError, match='Multiple existing'):
        write_filters(path, compiled(destination='Paid'))
    assert path.read_bytes() == original


def test_missing_destination_does_not_create_folder_or_filter(tmp_path, monkeypatch):
    path = tmp_path / 'msgFilterRules.dat'
    monkeypatch.setattr('thunderbird_adapter.actions.resolve_filter_rules_path', lambda _: path)
    actions = ThunderbirdActions()
    monkeypatch.setattr(actions, '_profile_action', lambda operation, timeout: operation(tmp_path))
    with pytest.raises(AdapterError, match='folders.ensure_local'):
        actions.dispatch('filters.configure', {'filters': [rule()]}, 1)
    assert not path.exists()
    assert not (tmp_path / 'Mail').exists()


def test_filter_verification_cannot_join_attributes_from_different_rules(tmp_path, monkeypatch):
    path = tmp_path / 'msgFilterRules.dat'
    write_filters(path, compiled('Receipt', 'Archive'))
    write_filters(path, compiled('Other', 'Bills'))
    monkeypatch.setattr(verifier, 'find_profile', lambda _: tmp_path)
    monkeypatch.setattr(verifier, 'resolve_filter_rules_path', lambda _: path)
    check = {'type': 'filters', 'filters': compiled('Receipt', 'Bills')}
    assert not verifier.verify_check(check)['passed']
    write_filters(path, compiled('Receipt', 'Bills'))
    assert verifier.verify_check(check)['passed']


def test_worker_propagates_failed_verification(monkeypatch):
    monkeypatch.setattr(ThunderbirdActions, 'dispatch', lambda *args: {})
    monkeypatch.setattr(worker, 'verify_specs', lambda specs: {'passed': False})
    with pytest.raises(AdapterError, match='verification failed'):
        worker.execute({'action': 'preferences.update', 'params': {'remove_keys': ['mail.test']}})
