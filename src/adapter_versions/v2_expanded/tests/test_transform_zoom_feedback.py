from types import SimpleNamespace

import pytest

from calc_adapter import uno_worker as worker
from integrations.lite_agent.adapter_results import adapter_context_hint
from integrations.lite_agent.completion_policy import completion_claim_contradictions
from integrations.lite_agent.output_artifact_semantics import requested_output_targets


def test_chained_transforms_keep_effects_and_rewriting_source_reports_loss(monkeypatch):
    class Cell:
        def __init__(self, text):
            self.text = text
        def getString(self):
            return self.text
        def setString(self, text):
            self.text = text
    class Sheet:
        def __init__(self, source, target):
            self.cells = [Cell(source), Cell(target)]
        def getCellByPosition(self, column, row):
            return self.cells[column]
        def getCellRangeByName(self, name):
            column = 0 if name.startswith('A') else 1
            return SimpleNamespace(
                getRangeAddress=lambda: SimpleNamespace(StartRow=0, EndRow=0, StartColumn=column, EndColumn=column),
                getCellByPosition=lambda c, r: self.cells[column+c],
            )
    sheets = {'Raw': Sheet('  nEw   tITLE  ', ''), 'Output': Sheet('', '')}
    session = SimpleNamespace(sheet=sheets.__getitem__, doc=SimpleNamespace(calculateAll=lambda: None))
    monkeypatch.setattr(worker, '_cell_kind', lambda c: 'string' if c.text else 'blank')
    monkeypatch.setattr(worker, '_range_snapshot', lambda r, doc: {'display_text': [[r.getCellByPosition(0, 0).getString()]]})
    params = {'source_sheet': 'Raw', 'source_range': 'A1', 'destination_sheet': 'Output', 'destination': 'B1', 'operation': 'collapse_whitespace'}
    first = worker._text_transform(session, params)
    assert first['text_properties']['satisfied']['collapse_whitespace']
    second = worker._text_transform(session, {**params, 'source_sheet': 'Output', 'source_range': 'B1', 'operation': 'title_case'})
    assert second['readback']['display_text'] == [['New Title']]
    assert second['text_properties']['satisfied']['collapse_whitespace']
    assert second['text_properties']['satisfied']['title_case']
    third = worker._text_transform(session, {**params, 'operation': 'title_case'})
    assert third['readback']['display_text'] == [['  New   Title  ']]
    assert 'collapse_whitespace' in third['lost_text_properties']
    assert sheets['Raw'].cells[0].text == '  nEw   tITLE  '
    hint = adapter_context_hint('libreoffice_calc', 'range.text_transform', {'result': third})
    assert hint['lost_text_properties'] == third['lost_text_properties']
    assert not hint['text_properties']['satisfied']['collapse_whitespace']


def test_empty_output_does_not_count_as_clean_text():
    assert not any(worker._text_properties(['', ''])['satisfied'].values())


@pytest.mark.parametrize('before,requested,actual,direction', [(150, 120, 120, 'out'), (80, 110, 110, 'in'), (100, 100, 100, 'unchanged'), (100, 80, 100, 'unchanged')])
def test_zoom_feedback_uses_actual_controller_value(before, requested, actual, direction):
    class Controller:
        value = before
        @property
        def ZoomValue(self):
            return self.value
        @ZoomValue.setter
        def ZoomValue(self, value):
            self.value = actual
    result = worker._set_zoom(SimpleNamespace(activate_sheet=lambda _: Controller()), {'sheet': 'Data', 'zoom': requested})
    assert result == {'sheet': 'Data', 'zoom': actual, 'previous_zoom': before, 'requested_zoom': requested, 'direction': direction}
    assert adapter_context_hint('libreoffice_calc', 'view.set_zoom', {'result': result})['zoom'] == actual


def test_crop_output_is_distinct_from_input_filename():
    assert requested_output_targets("Crop 'original.png' by 20% as 'cropped.png'.") == ['cropped.png']
    assert requested_output_targets("Crop 'original.png' by 20%.") == []


def test_manual_handoff_is_not_a_finished_operation():
    assert completion_claim_contradictions({'reason': 'GIMP is ready for the user to perform the crop operation manually.'})
    assert not completion_claim_contradictions({'reason': 'The cropped image is ready for the user to view.'})
