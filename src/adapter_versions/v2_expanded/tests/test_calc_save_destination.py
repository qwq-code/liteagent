import pytest
from jsonschema import Draft202012Validator
from calc_adapter.errors import AdapterError
from calc_adapter.schema import validate_action_params
from calc_adapter.uno_worker import _save
from integrations.lite_agent.model_client import _provider_tools
from integrations.lite_agent.tool_catalog import build_tools


@pytest.mark.parametrize('params', [{}, {'url': '/tmp/Report.ods'}, {'url': '~/Report.xlsx'}, {'url': 'file:///tmp/Report.XLSX'}])
def test_save_accepts_current_file_or_explicit_supported_destination(params):
    tools = build_tools('libreoffice_calc', ['workbook.save'], include_gui=False, include_control_tools=False, strict_generic=True)
    assert Draft202012Validator(_provider_tools(tools)[0]['function']['parameters']).is_valid(params)
    validate_action_params('workbook.save', params)


@pytest.mark.parametrize('url', ['{}', '', 'null', 'Report.xlsx', '/tmp/', '/tmp/Report.pdf', 'https://example.test/Report.xlsx'])
def test_bad_save_destination_is_rejected_before_accessing_document(url):
    tools = build_tools('libreoffice_calc', ['workbook.save'], include_gui=False, include_control_tools=False, strict_generic=True)
    assert not Draft202012Validator(_provider_tools(tools)[0]['function']['parameters']).is_valid({'url': url})
    with pytest.raises(AdapterError):
        _save(object(), {'url': url})
