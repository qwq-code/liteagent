import copy
from types import SimpleNamespace

import pytest
from integrations.lite_agent.argument_handoff import argument_contract_errors
from integrations.lite_agent.bounded_recovery import repeated_route, recover_tools, recovery_guidance
from integrations.lite_agent.generic_routing import discovered_adapter_routes
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools, search_actions
from integrations.lite_agent.state_model import RuntimeState, ExecutionEvent
from test_repeated_read_recovery import setup_call


def event(step, action, params=None, *, result=None, error=None, catalog=False):
    return ExecutionEvent(step=step, timestamp_utc='', executed=error is None,
        proposed={'kind': 'catalog' if catalog else 'adapter',
                  'tool': 'tools_search' if catalog else 'adapter__adapter_call',
                  'action': 'tools_search' if catalog else 'adapter.call',
                  'arguments': {'query': action} if catalog else {'adapter': 'libreoffice_writer', 'action': action, 'payload': {'params': params or {}}}},
        result=result, error=error)


def test_current_discovery_does_not_resurrect_earlier_application():
    state=RuntimeState(task_id='synthetic',domain='multi_apps',instruction='Transfer observed text.')
    for n, pair in enumerate([('libreoffice_impress','presentation.inspect'),('libreoffice_writer','document.create')],1):
        state.events.append(event(n,'search',catalog=True,result={'matches':[{'action':'adapter.call','adapter':pair[0],'downstream_action':pair[1]}]}))
    assert discovered_adapter_routes(state)==[('libreoffice_writer','document.create')]


def test_search_read_cycle_preserves_other_routes_and_ignores_changed_target():
    state=RuntimeState(task_id='synthetic',domain='multi_apps',instruction='Update the document.')
    for n in range(3):
        state.events.extend([event(2*n+1,'inspect document',catalog=True),event(2*n+2,'document.inspect',result={'context_hint':{'text':'same'}})])
    assert repeated_route(state)==('libreoffice_writer','document.inspect')
    tools=constrain_adapter_call_routes(build_tools('multi_apps',['adapter.call'],include_gui=False,strict_generic=True), [('libreoffice_writer','document.inspect'),('libreoffice_writer','document.append_paragraphs')])
    before=copy.deepcopy(tools)
    result=recover_tools(tools,state)
    wrapper=next(t['function']['parameters'] for t in result if t['function']['name']=='adapter__adapter_call')
    assert len(wrapper['oneOf'])==1
    assert wrapper['oneOf'][0]['properties']['action']['enum']==['document.append_paragraphs']
    assert tools==before
    state.events[-1].proposed['arguments']['payload']['params']={'paragraph_start':10}
    assert repeated_route(state) is None


@pytest.mark.parametrize('forwarded',[False,True])
def test_matrix_rejected_before_dispatch_and_can_be_corrected(forwarded):
    params={'sheet':'Sheet1','range':'B2:D3','values':[[1,2],[3,4]]}
    agent,state,executor,proposal=setup_call('range.write',params,forwarded=forwarded,owning_domain='libreoffice_calc')
    state.instruction='Write the supplied table into the active sheet.'
    result=agent.execute_proposal(state,proposal)
    assert not result.executed and 'RANGE_DIMENSIONS_MISMATCH' in str(result.error)
    assert executor.calls==[]
    assert 'Re-read' in str(result.error)


def test_matrix_valid_flat_and_nested_requests_are_not_rewritten():
    state=SimpleNamespace(domain='libreoffice_calc',events=[])
    for values in [[[1,2],[3,4]],[1,2,3,4]]:
        params={'sheet':'Sheet1','range':'B2:C3','values':values}
        before=copy.deepcopy(params)
        assert argument_contract_errors(state,'range.write',params)==[]
        assert params==before


def test_mail_index_cannot_be_substituted_for_message_id():
    state=RuntimeState(task_id='synthetic',domain='multi_apps',instruction='Save a selected attachment.')
    e=event(1,'messages.query',result={'context_hint':{'downstream_context':{'folder':'Invoices','messages':[{'mailbox_index':0}]}}})
    e.proposed['arguments']['adapter']='thunderbird';state.events=[e]
    params={'folder_name':'Invoices','message_id':'0','output_path':'/tmp/a.pdf'}
    args={'adapter':'thunderbird','action':'attachments.save','payload':{'params':params}}
    original=copy.deepcopy(args)
    assert 'MESSAGE_SELECTOR_MISMATCH' in argument_contract_errors(state,'adapter.call',args)[0]
    assert args==original
    params.pop('message_id');params['mailbox_index']=0
    assert argument_contract_errors(state,'adapter.call',args)==[]
    params['message_id']='0';e.result['context_hint']['downstream_context']['messages'][0]['message_id']='0'
    assert argument_contract_errors(state,'adapter.call',args)==[]


def test_failed_parameter_variant_does_not_remove_route():
    agent,state,executor,proposal=setup_call('document.read_file',{'path':'/tmp/missing.docx'},forwarded=True)
    executor.response={'executed':False,'error':{'code':'FILE_NOT_FOUND','message':'missing'}}
    agent.execute_proposal(state,proposal);agent.execute_proposal(state,proposal)
    assert state.active_request_blocks()
    assert ('libreoffice_writer','document.read_file') not in state.blocked_routes()
    assert state.active_request_block('adapter.call',{'adapter':'libreoffice_writer','action':'document.read_file','payload':{'params':{'path':'/tmp/other.docx'}}}) is None


def test_error_guidance_survives_catalog_turn():
    state=RuntimeState(task_id='synthetic',domain='multi_apps',instruction='Update document.')
    state.events=[event(1,'document.read_file',error={'code':'FILE_NOT_FOUND'}),event(2,'locate source',catalog=True)]
    assert 'Discover the actual source' in recovery_guidance(state)
    state.events.append(event(3,'document.inspect',result={'context_hint':{'text':'new'}}))
    assert 'Discover the actual source' not in recovery_guidance(state)


def test_repeated_rejected_route_pauses_until_new_observation():
    state = RuntimeState(task_id='synthetic', domain='multi_apps', instruction='Update document.')
    for n in range(3):
        state.events.extend([
            event(2*n+1, 'read document', catalog=True),
            event(2*n+2, 'document.read_file', {'path': '/tmp/missing.docx'},
                  error={'type': 'RepeatedActionBlocked', 'previous_error': {'code': 'FILE_NOT_FOUND'}}),
        ])
    tools = constrain_adapter_call_routes(
        build_tools('multi_apps', ['adapter.call'], include_gui=False, strict_generic=True),
        [('libreoffice_writer', 'document.read_file'), ('libreoffice_writer', 'document.inspect')])
    filtered = recover_tools(tools, state)
    schema = next(t['function']['parameters'] for t in filtered if t['function']['name'] == 'adapter__adapter_call')
    assert [b['properties']['action']['enum'] for b in schema['oneOf']] == [['document.inspect']]
    state.events.append(event(7, 'document.inspect', result={'context_hint': {'text': 'new'}}))
    assert recover_tools(tools, state) == tools


def test_changing_rejected_arguments_keeps_route_available():
    state = RuntimeState(task_id='synthetic', domain='multi_apps', instruction='Update document.')
    state.events = [event(n, 'document.read_file', {'path': f'/tmp/{n}.docx'},
                          error={'type': 'RepeatedActionBlocked'}) for n in range(3)]
    tools = build_tools('multi_apps', ['adapter.call'], include_gui=False, strict_generic=True)
    assert repeated_route(state) is None
    assert recover_tools(tools, state) == tools


def test_command_search_does_not_return_native_converter():
    found=search_actions('multi_apps','convert doc to pdf command line',instruction='Convert document files to PDF.',strict_generic=True)
    assert [(r['adapter'],r['downstream_action']) for r in found]==[('os','command.run')]


def test_current_application_search_beats_previous_workflow_nouns():
    found=search_actions('multi_apps','libreoffice writer create document',instruction='Extract all text from presentation slides into a document.',strict_generic=True,completed_routes=[('libreoffice_impress','presentation.inspect')])
    assert (found[0]['adapter'],found[0]['downstream_action'])==('libreoffice_writer','document.create')
