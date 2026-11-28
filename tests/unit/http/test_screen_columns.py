"""The columns and the font size of the edit forms of the screens, and the
screen types whose columns cannot be set (neither the image screens nor
the Chess960 ones).
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from litestar.testing import TestClient

from data.screens.screen import Screen
from data.screens.screen_types import ImageScreenType, RoundRobinGridScreenType
from database.sqlite.event.event_store import StoredScreen
from plugins.chess960.screen_type import Chess960ScreenType
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-screen-columns'
EVENT = EventUnderTest(EVENT_ID, 'test-screen-columns-tournament')
FAMILY_ID = 'test-screen-columns-family'
PANEL = 'screen-columns-panel'
ONE_PIXEL_PNG = (
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4'
    '2mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=='
)


@dataclass
class Fixtures:
    screen: StoredScreen
    image_screen: StoredScreen
    family_id: int


@pytest.fixture(scope='module')
def event(api: ApiClient) -> Iterator[Fixtures]:
    EVENT.create(event={'public': True}, json_file='test-screens')
    tournament = EVENT.tournament()
    screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Columns screen',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id], 'public': True},
    )
    image_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Columns image screen',
        ScreenType.IMAGE,
        {'public': True, 'background_image_upload': ONE_PIXEL_PNG},
    )
    TestUtils.create_family(
        api,
        EVENT_ID,
        tournament.stored_tournament,
        FAMILY_ID,
        ScreenType.BOARDS,
        {'parts': 2, 'public': True},
    )
    family_id = next(iter(EVENT.load().families_by_id))
    yield Fixtures(screen=screen, image_screen=image_screen, family_id=family_id)
    EVENT.delete()


@pytest.mark.unit
def test_the_screen_types_without_columns():
    assert not ImageScreenType().columns_adjustable
    assert not Chess960ScreenType().columns_adjustable
    assert not RoundRobinGridScreenType().columns_adjustable


def field_error(page: str, field_id: str) -> str | None:
    """The message shown under a field of the form."""
    match = re.search(rf'id="{field_id}-error"[^>]*>\s*([^<]*)', page)
    return match.group(1).strip() if match else None


@pytest.mark.unit
def test_the_edit_form_bounds_the_columns_and_the_font_size(
    http: TestClient, event: Fixtures
):
    screen = event.screen
    assert screen.id is not None
    modal = http.get(f'/screen-modal/update/{EVENT_ID}/{screen.id}')
    assert modal.status_code == 200
    for name, minimum, maximum, step in (
        ('columns', Screen.COLUMNS_MIN, Screen.COLUMNS_MAX, 1),
        (
            'font_size',
            Screen.FONT_SIZE_MIN,
            Screen.FONT_SIZE_MAX,
            Screen.FONT_SIZE_STEP,
        ),
    ):
        tag = re.search(rf'<input[^>]*name="{name}"[^>]*>', modal.text)
        assert tag is not None, name
        assert f'min="{minimum}"' in tag.group(0)
        assert f'max="{maximum}"' in tag.group(0)
        assert f'step="{step}"' in tag.group(0)


@pytest.mark.unit
@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('columns', Screen.COLUMNS_MAX + 1),
        ('font_size', Screen.FONT_SIZE_MIN - 1),
        ('font_size', Screen.FONT_SIZE_MAX + 1),
    ],
)
def test_the_edit_form_refuses_values_out_of_bounds(
    http: TestClient, event: Fixtures, field: str, value: int
):
    screen = event.screen
    assert screen.id is not None
    response = http.patch(
        f'/screen-update/{EVENT_ID}/{screen.id}',
        data={'name': screen.name, 'public': 'on', field: str(value)},
    )
    assert response.status_code == 200
    error = field_error(response.text, field.replace('_', '-'))
    assert error is not None and 'between' in error


@pytest.mark.unit
def test_the_image_fields_have_a_section_of_their_own(
    http: TestClient, event: Fixtures
):
    """The fields of an image screen, from the URL of its background image
    on, are in a section after the properties of the screen."""
    screen = event.image_screen
    assert screen.id is not None
    modal = http.get(f'/screen-modal/update/{EVENT_ID}/{screen.id}')
    assert modal.status_code == 200
    headings = [
        (match.start(), match.group(1).strip())
        for match in re.finditer(
            r'<h3 class="sc-section-heading[^"]*">([^<]*)</h3>', modal.text
        )
    ]
    assert [text for _, text in headings] == ['Properties', 'Layout']
    assert headings[1][0] < modal.text.index('name="background_image"')


@pytest.mark.unit
@pytest.mark.parametrize('modal', ['screen', 'family'])
def test_the_edit_forms_use_the_controls_of_the_screens(
    http: TestClient, event: Fixtures, modal: str
):
    """The columns are set with - and + buttons and the font size with a
    slider and its reset button, as on the screens themselves."""
    screen = event.screen
    item_id = screen.id if modal == 'screen' else event.family_id
    page = http.get(f'/{modal}-modal/update/{EVENT_ID}/{item_id}')
    assert page.status_code == 200
    columns = re.search(r'<input[^>]*name="columns"[^>]*>', page.text)
    font_size = re.search(r'<input[^>]*name="font_size"[^>]*>', page.text)
    assert columns is not None and 'readonly' in columns.group(0)
    assert font_size is not None and 'type="range"' in font_size.group(0)
    for marker in (
        'bi-dash-circle',
        'bi-plus-circle',
        'bi-arrow-counterclockwise',
        'data-font-size-reset',
    ):
        assert marker in page.text, marker
    assert 'Font size:' in page.text
    assert 'Font size adjustment' not in page.text
