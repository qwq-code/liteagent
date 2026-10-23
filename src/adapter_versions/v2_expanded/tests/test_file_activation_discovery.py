import pytest

from integrations.lite_agent.tool_catalog import search_actions


@pytest.mark.parametrize(
    ('query', 'instruction'),
    [
        ('open file', 'Read the supplied spreadsheet and insert a table into the document.'),
        ('open workbook', 'Update the bookkeeping sheet with files from the provided folder.'),
        ('open document', 'Read the saved document and export a PDF.'),
        ('open /tmp/example.docx', 'Read document content from the Desktop folder.'),
        ('activate the presentation file', 'Transfer notes from a document into slides.'),
    ],
)
def test_file_activation_is_discoverable_despite_workflow_noun_overlap(query, instruction):
    result = search_actions('multi_apps', query, instruction=instruction, strict_generic=True)
    assert (result[0]['adapter'], result[0]['downstream_action']) == ('os', 'desktop.open_path')


def test_editor_activation_preserves_requested_application():
    result = search_actions('multi_apps', 'open file in VS Code',
                            instruction='Read document content from the supplied folder.', strict_generic=True)
    assert (result[0]['adapter'], result[0]['downstream_action']) == ('vs_code', 'editor.open_file')


def test_background_read_is_not_replaced_with_activation():
    result = search_actions('multi_apps', 'read saved document',
                            instruction='Read a document and export a PDF.', strict_generic=True)
    assert (result[0]['adapter'], result[0]['downstream_action']) == ('libreoffice_writer', 'document.read_file')


def test_excluded_activation_is_not_resurrected():
    result = search_actions('multi_apps', 'open file', strict_generic=True,
                            excluded_routes=[('os', 'desktop.open_path')])
    assert all((item['adapter'], item['downstream_action']) != ('os', 'desktop.open_path')
               for item in result)


@pytest.mark.parametrize('query', ['download attachment', 'thunderbird messages.attachments.download',
                                 'save the docx attachment from the message'])
def test_attachment_download_exposes_save_and_identity_discovery(query):
    result = search_actions('multi_apps', query, strict_generic=True,
                            instruction='Read the attached document from mail and edit its content.')
    routes = [(item['adapter'], item['downstream_action']) for item in result]
    assert routes[0] == ('thunderbird', 'attachments.save')
    assert ('thunderbird', 'messages.query') in routes


def test_reading_an_already_saved_attachment_remains_a_read():
    result = search_actions('multi_apps', 'read the saved docx attachment', strict_generic=True,
                            instruction='Read the attached document from mail and edit its content.')
    assert (result[0]['adapter'], result[0]['downstream_action']) == ('libreoffice_writer', 'document.read_file')
