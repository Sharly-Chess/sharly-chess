"""The slider that sets the font size of a screen from the screen itself.

Only the clients that manage the screens are offered the slider, and only
they may store the size it sets: on the screen, or on its family when the
screen is part of one.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from litestar.testing import TestClient

from data.access_levels.access_levels import (
    AccessLevel,
    ResultsEntryAccessLevel,
    ScreenManagementAccessLevel,
    SpectatorAccessLevel,
)
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredScreen
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient

EVENT_ID = 'test-screen-font-size'
TOURNAMENT_NAME = 'test-screen-font-size-tournament'
FAMILY_ID = 'test-screen-font-size-family'
PASSWORD = 'test-password'
PANEL = 'screen-font-size-panel'
ONE_PIXEL_PNG = (
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4'
    '2mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=='
)


@dataclass
class Fixtures:
    screen: StoredScreen
    family_id: int
    image_screen: StoredScreen


@pytest.fixture(scope='module')
def event(api: ApiClient) -> Iterator[Fixtures]:
    TestUtils.create_event(EVENT_ID, overrides={'public': True})
    tournament = TestUtils.create_tournament(
        EVENT_ID, TOURNAMENT_NAME, json_file='test-screens'
    )
    screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Font size screen',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id], 'public': True},
    )
    TestUtils.create_family(
        api,
        EVENT_ID,
        tournament,
        FAMILY_ID,
        ScreenType.BOARDS,
        {'parts': 2, 'public': True},
    )
    with EventDatabase(EVENT_ID) as database:
        family_id = next(
            stored.id
            for stored in database.load_stored_families()
            if stored.uniq_id == FAMILY_ID
        )
    assert family_id is not None
    image_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Font size image screen',
        ScreenType.IMAGE,
        {'public': True, 'background_image_upload': ONE_PIXEL_PNG},
    )
    yield Fixtures(screen=screen, family_id=family_id, image_screen=image_screen)
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def screen_font_size(screen_id: int) -> int | None:
    with EventDatabase(EVENT_ID) as database:
        return next(
            stored.font_size
            for stored in database.load_stored_screens()
            if stored.id == screen_id
        )


def family_font_size(family_id: int) -> int | None:
    with EventDatabase(EVENT_ID) as database:
        return next(
            stored.font_size
            for stored in database.load_stored_families()
            if stored.id == family_id
        )


def set_font_size(client: TestClient, screen_uniq_id: str, font_size: object):
    return client.patch(
        f'/screen-font-size/{EVENT_ID}/{screen_uniq_id}',
        data={'font_size': str(font_size)},
        follow_redirects=False,
    )


def assert_refused(response, status_code: int) -> None:
    """The application answers an error with a redirection to its page."""
    assert response.status_code == 302
    assert response.headers['location'].endswith(f'/error/{status_code}')


def sign_in(http: TestClient, lan: TestClient, access_level: type[AccessLevel]) -> None:
    """Create an account holding only *access_level* and sign the network
    client in as it."""
    name = access_level.static_id()
    created = http.post(
        f'/account-create/{EVENT_ID}',
        data={
            'first_name': 'Test',
            'last_name': name,
            'password': PASSWORD,
            'active': 'on',
        },
    )
    assert created.status_code == 200
    with EventDatabase(EVENT_ID) as database:
        account = next(
            stored
            for stored in database.load_stored_accounts()
            if stored.last_name == name
        )
    # A new account inherits the anonymous account's permissions.
    with EventDatabase(EVENT_ID, write=True) as database:
        for permission in account.stored_permissions:
            database.delete_stored_permission(permission)
    granted = http.post(
        f'/account-permission-create/{EVENT_ID}/{account.id}',
        data={'access_level': name},
    )
    assert granted.status_code == 200
    signed_in = lan.post(
        f'/profile-login/{EVENT_ID}',
        data={'account_id': str(account.id), 'password': PASSWORD},
    )
    assert signed_in.is_success, signed_in.text


@pytest.mark.unit
def test_the_font_size_of_a_screen_is_stored_and_shown(
    http: TestClient, event: Fixtures
):
    screen = event.screen
    assert screen.id is not None
    response = set_font_size(http, screen.uniq_id, 150)
    assert response.status_code == 204
    assert screen_font_size(screen.id) == 150

    page = http.get(f'/view/screen/{EVENT_ID}/{screen.uniq_id}')
    assert page.status_code == 200
    assert '--font-size: 150;' in page.text
    assert PANEL in page.text
    assert 'value="150"' in page.text


@pytest.mark.unit
def test_the_font_size_of_a_family_screen_is_stored_on_the_family(
    http: TestClient, event: Fixtures
):
    response = set_font_size(http, f'{FAMILY_ID}:001', 80)
    assert response.status_code == 204
    assert family_font_size(event.family_id) == 80
    # Every screen of the family follows.
    page = http.get(f'/view/screen/{EVENT_ID}/{FAMILY_ID}:002')
    assert page.status_code == 200
    assert '--font-size: 80;' in page.text


@pytest.mark.unit
@pytest.mark.parametrize('font_size', [0, 49, 301, 'abc', ''])
def test_a_font_size_out_of_bounds_is_refused(
    http: TestClient, event: Fixtures, font_size: object
):
    screen = event.screen
    assert screen.id is not None
    before = screen_font_size(screen.id)
    assert_refused(set_font_size(http, screen.uniq_id, font_size), 400)
    assert screen_font_size(screen.id) == before


@pytest.mark.unit
def test_the_font_size_of_an_unknown_screen_is_refused(
    http: TestClient, event: Fixtures
):
    assert_refused(set_font_size(http, 'no-such-screen', 120), 404)


@pytest.mark.unit
def test_a_screen_manager_is_offered_the_slider_and_may_use_it(
    http: TestClient, lan: TestClient, event: Fixtures
):
    sign_in(http, lan, ScreenManagementAccessLevel)
    screen = event.screen
    assert screen.id is not None
    page = lan.get(f'/view/screen/{EVENT_ID}/{screen.uniq_id}')
    assert page.status_code == 200
    assert PANEL in page.text
    assert set_font_size(lan, screen.uniq_id, 175).status_code == 204
    assert screen_font_size(screen.id) == 175


@pytest.mark.unit
@pytest.mark.parametrize(
    'access_level',
    [None, SpectatorAccessLevel, ResultsEntryAccessLevel],
    ids=['anonymous', 'spectator', 'results-entry'],
)
def test_other_clients_are_neither_offered_the_slider_nor_allowed_to_use_it(
    http: TestClient,
    lan: TestClient,
    event: Fixtures,
    access_level: type[AccessLevel] | None,
):
    if access_level:
        sign_in(http, lan, access_level)
    screen = event.screen
    assert screen.id is not None
    page = lan.get(f'/view/screen/{EVENT_ID}/{screen.uniq_id}')
    assert page.status_code == 200
    assert PANEL not in page.text
    before = screen_font_size(screen.id)
    assert_refused(set_font_size(lan, screen.uniq_id, 220), 403)
    assert screen_font_size(screen.id) == before


@pytest.mark.unit
def test_the_slider_is_not_offered_in_a_preview(http: TestClient, event: Fixtures):
    page = http.get(f'/view/screen/{EVENT_ID}/{event.screen.uniq_id}?preview=1')
    assert page.status_code == 200
    assert PANEL not in page.text


@pytest.mark.unit
def test_an_image_screen_has_no_slider(http: TestClient, event: Fixtures):
    screen = event.image_screen
    assert screen.id is not None
    page = http.get(f'/view/screen/{EVENT_ID}/{screen.uniq_id}')
    assert page.status_code == 200
    assert PANEL not in page.text
    before = screen_font_size(screen.id)
    assert_refused(set_font_size(http, screen.uniq_id, 150), 400)
    assert screen_font_size(screen.id) == before
