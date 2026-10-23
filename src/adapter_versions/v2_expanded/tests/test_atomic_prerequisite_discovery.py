from integrations.lite_agent.semantic_search_scope import scope_semantic_search_actions
from integrations.lite_agent.tool_catalog import search_actions


def test_filter_scope_keeps_folder_prerequisite_without_unrelated_mutations():
    actions = ["filters.configure", "folders.ensure_local", "accounts.remove", "mail.configure", "messages.query"]
    scoped = scope_semantic_search_actions(actions, ["filters.configure"], strict_generic=True)
    assert {"filters.configure", "folders.ensure_local", "messages.query"}.issubset(scoped)
    assert "accounts.remove" not in scoped
    assert "mail.configure" not in scoped


def test_folder_creation_remains_searchable_in_filter_workflow():
    matches = search_actions(
        "thunderbird", "folders.ensure_local", strict_generic=True,
        semantic_actions=["filters.configure"],
        instruction="Create a local mailbox and route selected mail into it.",
    )
    assert matches[0]["action"] == "folders.ensure_local"
    assert all(item["action"] != "accounts.remove" for item in matches)


def test_filter_prerequisite_is_not_mandatory_or_available_for_other_settings():
    scoped = scope_semantic_search_actions(
        ["mail.configure", "folders.ensure_local", "filters.configure"],
        ["mail.configure"], strict_generic=True,
    )
    assert scoped == ["mail.configure"]


def test_explicit_spaced_route_is_preserved_through_search_and_history():
    from integrations.lite_agent.generic_routing import discovered_adapter_routes
    from integrations.lite_agent.state_model import RuntimeState, ExecutionEvent
    state = RuntimeState(task_id='synthetic', domain='multi_apps', instruction='Read the supplied file.')
    queries = ['os.filesystem.find', 'libreoffice_calc workbook.read_file']
    for step, query in enumerate(queries, 1):
        matches = search_actions('multi_apps', query, strict_generic=True)
        state.events.append(ExecutionEvent(
            step=step, timestamp_utc='', executed=True,
            proposed={'kind': 'catalog', 'tool': 'tools_search', 'arguments': {'query': query}},
            result={'matches': matches},
        ))
    assert [(x['adapter'], x['downstream_action']) for x in matches] == [('libreoffice_calc', 'workbook.read_file')]
    assert discovered_adapter_routes(state) == [('libreoffice_calc', 'workbook.read_file')]


def test_identity_discovery_reads_only_account_bound_public_fields(tmp_path, monkeypatch):
    from thunderbird_adapter.actions import ThunderbirdActions
    from thunderbird_adapter.schema import validate_action_params
    profile = tmp_path / 'profile'
    profile.mkdir()
    prefs = profile / 'prefs.js'
    prefs.write_text('\n'.join([
        'user_pref("mail.accountmanager.accounts", "account7, account8");',
        'user_pref("mail.account.account7.identities", "id4");',
        'user_pref("mail.account.account8.identities", "id9");',
        'user_pref("mail.identity.id4.fullName", "A Person");',
        'user_pref("mail.identity.id4.useremail", "a@example.test");',
        'user_pref("mail.identity.id9.useremail", "b@example.test");',
        'user_pref("mail.identity.id4.password", "secret-synthetic-value");',
        'user_pref("mail.identity.orphan.useremail", "orphan@example.test");',
    ]))
    original = prefs.read_bytes()
    monkeypatch.setattr('thunderbird_adapter.actions.find_profile', lambda: profile)
    validate_action_params('mail.identities.list', {})
    result = ThunderbirdActions().dispatch('mail.identities.list', {}, 1)
    assert [r['identity'] for r in result['identities']] == ['id4', 'id9']
    assert 'secret-synthetic-value' not in str(result)
    assert 'orphan' not in str(result)
    assert prefs.read_bytes() == original
    matches = search_actions('thunderbird', 'find mail identity for signature',
                             semantic_actions=['mail.configure'], strict_generic=True)
    assert any(x['action'] == 'mail.identities.list' for x in matches)
