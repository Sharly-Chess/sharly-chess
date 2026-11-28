"""The control that changes the number of columns of a screen, from the
screen itself.

It is offered to the clients that manage the screens on the screens whose
edit form offers the columns (neither the image screens nor the Chess960
ones), and only they may use it: the columns are stored on the screen, or
on its family when the screen is part of one.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from litestar.testing import TestClient

from data.screens.screen import Screen
from data.screens.screen_types import ImageScreenType, RoundRobinGridScreenType
from database.sqlite.event.event_database import EventDatabase
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


def screen_columns(screen_id: int) -> int | None:
    with EventDatabase(EVENT_ID) as database:
        return next(
            stored.columns
            for stored in database.load_stored_screens()
            if stored.id == screen_id
        )


def set_columns(client: TestClient, screen_uniq_id: str, columns: object):
    return client.patch(
        f'/screen-columns/{EVENT_ID}/{screen_uniq_id}',
        data={'columns': str(columns)},
        follow_redirects=False,
    )


def assert_refused(response, status_code: int) -> None:
    """The application answers an error with a redirection to its page."""
    assert response.status_code == 302
    assert response.headers['location'].endswith(f'/error/{status_code}')


@pytest.mark.unit
def test_the_columns_of_a_screen_are_stored_and_shown(
    http: TestClient, event: Fixtures
):
    screen = event.screen
    assert screen.id is not None
    page = http.get(f'/view/screen/{EVENT_ID}/{screen.uniq_id}')
    assert page.status_code == 200
    assert PANEL in page.text
    for icon in ('bi-layout-three-columns', 'bi-dash-circle', 'bi-plus-circle'):
        assert icon in page.text

    assert set_columns(http, screen.uniq_id, 3).status_code == 204
    assert screen_columns(screen.id) == 3
    page = http.get(f'/view/screen/{EVENT_ID}/{screen.uniq_id}')
    assert 'data-columns="3"' in page.text


@pytest.mark.unit
def test_the_columns_of_a_family_screen_are_stored_on_the_family(
    http: TestClient, event: Fixtures
):
    assert set_columns(http, f'{FAMILY_ID}:001', 2).status_code == 204
    assert EVENT.load().families_by_id[event.family_id].columns == 2


@pytest.mark.unit
@pytest.mark.parametrize('columns', [0, Screen.COLUMNS_MAX + 1, 'abc', ''])
def test_a_number_of_columns_out_of_bounds_is_refused(
    http: TestClient, event: Fixtures, columns: object
):
    screen = event.screen
    assert screen.id is not None
    before = screen_columns(screen.id)
    assert_refused(set_columns(http, screen.uniq_id, columns), 400)
    assert screen_columns(screen.id) == before


@pytest.mark.unit
def test_an_image_screen_has_no_columns_control(http: TestClient, event: Fixtures):
    screen = event.image_screen
    assert screen.id is not None
    page = http.get(f'/view/screen/{EVENT_ID}/{screen.uniq_id}')
    assert page.status_code == 200
    assert PANEL not in page.text
    assert_refused(set_columns(http, screen.uniq_id, 2), 400)


@pytest.mark.unit
def test_the_screen_types_without_columns():
    assert not ImageScreenType().columns_adjustable
    assert not Chess960ScreenType().columns_adjustable
    assert not RoundRobinGridScreenType().columns_adjustable


@pytest.mark.unit
def test_a_visitor_is_neither_offered_the_control_nor_allowed_to_use_it(
    lan: TestClient, event: Fixtures
):
    screen = event.screen
    assert screen.id is not None
    page = lan.get(f'/view/screen/{EVENT_ID}/{screen.uniq_id}')
    assert page.status_code == 200
    assert PANEL not in page.text
    before = screen_columns(screen.id)
    assert_refused(set_columns(lan, screen.uniq_id, 4), 403)
    assert screen_columns(screen.id) == before


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
