from types import SimpleNamespace

from impress_adapter import uno_worker
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


def test_summary_text_survives_native_shape_attachment(monkeypatch):
    class Shape:
        String = ''
        ShapeType = 'com.sun.star.drawing.TextShape'

        def getText(self):
            return self

        def getString(self):
            return self.String

    class Page:
        Width, Height = 28000, 21000

        def __init__(self):
            self.shapes = []

        def add(self, shape):
            # Native page attachment initializes the underlying text object.
            shape.String = ''
            self.shapes.append(shape)

        def getCount(self):
            return len(self.shapes)

        def getByIndex(self, index):
            return self.shapes[index]

    class Pages:
        def __init__(self):
            self.items = [Page()]
            title = Shape()
            self.items[0].add(title)
            title.String = 'Example heading'

        def getCount(self):
            return len(self.items)

        def insertNewByIndex(self, index):
            page = Page()
            self.items.insert(index, page)
            return page

        def remove(self, page):
            self.items.remove(page)

    pages = Pages()
    session = SimpleNamespace(pages=pages, page=lambda n: pages.items[n],
                              doc=SimpleNamespace(createInstance=lambda _: Shape()))
    monkeypatch.setattr(uno_worker, '_uno_modules', lambda: (
        SimpleNamespace(createUnoStruct=lambda *args: args), None))
    result = uno_worker._presentation_create_summary_slide(session, {'slides': [0]})
    assert result['verification_passed'] is True
    assert [s.String for s in pages.items[1].shapes] == ['Summary Slide', '1. Example heading']
    assert pages.items[0].shapes[0].String == 'Example heading'


def test_image_composition_does_not_require_duplicate_slide_and_image_creation():
    state = RuntimeState(task_id='synthetic-image-deck', domain='libreoffice_impress',
        instruction='Create two blank slides and insert one image per slide from the Desktop in order.')
    for step, action, arguments in [
        (1, 'slides.create_from_images', {'image_paths': ['/tmp/a.png', '/tmp/b.png'],
                                        'replace_existing_slides': True}),
        (2, 'presentation.save', {}),
        (3, 'presentation.inspect', {}),
    ]:
        state.events.append(ExecutionEvent(step=step, timestamp_utc='2026-10-24T00:00:00Z',
            proposed={'kind': 'adapter', 'action': action, 'tool': 'adapter__'+action.replace('.', '_'),
                      'arguments': arguments}, executed=True,
            result={'context_hint': {'verification_passed': True, 'slide_count': 2}}))
    gate = CompletionMixin._generic_completion_gate(state)
    assert not any('have not succeeded' in item for item in gate['missing']), gate

    state.events = state.events[1:]
    assert not CompletionMixin._generic_completion_gate(state)['passed']
