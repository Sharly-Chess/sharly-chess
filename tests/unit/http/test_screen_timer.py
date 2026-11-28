"""The control that changes the timer a screen shows, from the screen itself.

It is offered to the clients that manage the screens once the event has a
timer, beside the control of the font size, and only they may use it: the
timer is stored on the screen, or on its family when the screen is part of
one.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from litestar.testing import TestClient

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredScreen
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-screen-timer'
EVENT = EventUnderTest(EVENT_ID, 'test-screen-timer-tournament')
FAMILY_ID = 'test-screen-timer-family'
PANEL = 'screen-timer-panel'
CONTROLS = 'screen-control-panel'
ONE_PIXEL_PNG = (
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4'
    '2mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=='
)


@dataclass
class Fixtures:
    screen: StoredScreen
    image_screen: StoredScreen
    family_id: int


@pytest.fixture
def event(api: ApiClient) -> Iterator[Fixtures]:
    EVENT.create(event={'public': True}, json_file='test-screens')
    tournament = EVENT.tournament()
    screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Timer screen',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id], 'public': True},
    )
    image_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Timer image screen',
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


def create_timers(http: TestClient, *names: str) -> dict[str, int]:
    for name in names:
        assert http.post(f'/timer-create/{EVENT_ID}', data={'name': name}).is_success
    return {timer.name: timer.id for timer in EVENT.load().timers_by_id.values()}


def screen_timer_id(screen_id: int) -> int | None:
    with EventDatabase(EVENT_ID) as database:
        return next(
            stored.timer_id
            for stored in database.load_stored_screens()
            if stored.id == screen_id
        )


def set_timer(client: TestClient, screen_uniq_id: str, timer_id: object):
    return client.patch(
        f'/screen-timer/{EVENT_ID}/{screen_uniq_id}',
        data={'timer_id': str(timer_id)},
        follow_redirects=False,
    )


def assert_refused(response, status_code: int) -> None:
    """The application answers an error with a redirection to its page."""
    assert response.status_code == 302
    assert response.headers['location'].endswith(f'/error/{status_code}')


@pytest.mark.unit
def test_no_timer_control_without_timers(http: TestClient, event: Fixtures):
    page = http.get(f'/view/screen/{EVENT_ID}/{event.screen.uniq_id}')
    assert page.status_code == 200
    assert PANEL not in page.text
    # The control of the font size is still there.
    assert 'screen-font-size-panel' in page.text


@pytest.mark.unit
def test_the_timer_control_lists_the_timers(http: TestClient, event: Fixtures):
    create_timers(http, 'Round two', 'Round one')
    page = http.get(f'/view/screen/{EVENT_ID}/{event.screen.uniq_id}')
    assert page.status_code == 200
    assert PANEL in page.text
    assert 'bi-clock' in page.text
    text = page.text
    assert text.index('Round one') < text.index('Round two')


@pytest.mark.unit
def test_the_timer_of_a_screen_is_changed_and_removed(
    http: TestClient, event: Fixtures
):
    timers = create_timers(http, 'Round one', 'Round two')
    screen = event.screen
    assert screen.id is not None
    assert set_timer(http, screen.uniq_id, timers['Round two']).status_code == 204
    assert screen_timer_id(screen.id) == timers['Round two']
    page = http.get(f'/view/screen/{EVENT_ID}/{screen.uniq_id}')
    assert f'value="{timers["Round two"]}" selected' in page.text

    assert set_timer(http, screen.uniq_id, '').status_code == 204
    assert screen_timer_id(screen.id) is None


@pytest.mark.unit
def test_the_timer_of_a_family_screen_is_stored_on_the_family(
    http: TestClient, event: Fixtures
):
    timers = create_timers(http, 'Round one')
    response = set_timer(http, f'{FAMILY_ID}:001', timers['Round one'])
    assert response.status_code == 204
    assert EVENT.load().families_by_id[event.family_id].timer_id == timers['Round one']


@pytest.mark.unit
def test_an_image_screen_has_the_timer_control_only(http: TestClient, event: Fixtures):
    timers = create_timers(http, 'Round one')
    screen = event.image_screen
    assert screen.id is not None
    page = http.get(f'/view/screen/{EVENT_ID}/{screen.uniq_id}')
    assert page.status_code == 200
    assert PANEL in page.text
    assert 'screen-font-size-panel' not in page.text
    assert set_timer(http, screen.uniq_id, timers['Round one']).status_code == 204
    assert screen_timer_id(screen.id) == timers['Round one']


@pytest.mark.unit
@pytest.mark.parametrize('timer_id', ['abc', '0', '999999'])
def test_an_unknown_timer_is_refused(http: TestClient, event: Fixtures, timer_id: str):
    create_timers(http, 'Round one')
    screen = event.screen
    assert screen.id is not None
    assert_refused(set_timer(http, screen.uniq_id, timer_id), 400)
    assert screen_timer_id(screen.id) is None


@pytest.mark.unit
def test_a_visitor_is_neither_offered_the_control_nor_allowed_to_use_it(
    http: TestClient, lan: TestClient, event: Fixtures
):
    timers = create_timers(http, 'Round one')
    screen = event.screen
    assert screen.id is not None
    page = lan.get(f'/view/screen/{EVENT_ID}/{screen.uniq_id}')
    assert page.status_code == 200
    assert CONTROLS not in page.text
    assert_refused(set_timer(lan, screen.uniq_id, timers['Round one']), 403)
    assert screen_timer_id(screen.id) is None


@pytest.mark.unit
def test_no_control_in_a_preview(http: TestClient, event: Fixtures):
    create_timers(http, 'Round one')
    page = http.get(f'/view/screen/{EVENT_ID}/{event.screen.uniq_id}?preview=1')
    assert page.status_code == 200
    assert CONTROLS not in page.text


@pytest.mark.unit
def test_the_controls_are_hidden_behind_the_gear_in_order(
    http: TestClient, event: Fixtures
):
    """The gear comes first and shows or hides the controls, hidden at
    first: the columns, the font size, then the timer."""
    create_timers(http, 'Round one')
    page = http.get(f'/view/screen/{EVENT_ID}/{event.screen.uniq_id}')
    assert page.status_code == 200
    text = page.text
    assert 'bi-gear' in text
    assert 'class="screen-controls d-none' in text
    positions = [
        text.index(f'id="{panel}"')
        for panel in (
            'screen-controls-toggle',
            'screen-columns-panel',
            'screen-font-size-panel',
            'screen-timer-panel',
        )
    ]
    assert positions == sorted(positions)
