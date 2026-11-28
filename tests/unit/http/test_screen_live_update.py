"""The live update of the layout of a screen.

While it is on, the layout set in the edit modal of a screen, or with the
controls shown on the screen itself, and the alert message set in the modal,
are shown at once by every device that shows the screen, without being
stored. Only the clients that manage the screens turn it on and off, from the
modal; while it is on, any client that sees the screen is shown the controls,
may change the layout with them and save it.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from litestar.testing import TestClient

from data.screens.live_layout import live_key, live_layout
from data.screens.screen import Screen
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredScreen
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-screen-live-update'
EVENT = EventUnderTest(EVENT_ID, 'test-screen-live-update-tournament')
FAMILY_ID = 'test-screen-live-update-family'
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
    timers: dict[str, int]


@pytest.fixture
def event(http: TestClient, api: ApiClient) -> Iterator[Fixtures]:
    EVENT.create(event={'public': True}, json_file='test-screens')
    tournament = EVENT.tournament()
    screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Live screen',
        ScreenType.BOARDS,
        {'init_set_tournament_ids': [tournament.id], 'public': True},
    )
    image_screen = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Live image screen',
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
    for name in ('Round one', 'Round two'):
        assert http.post(f'/timer-create/{EVENT_ID}', data={'name': name}).is_success
    loaded = EVENT.load()
    family_id = next(iter(loaded.families_by_id))
    timers = {timer.name: timer.id for timer in loaded.timers_by_id.values()}
    yield Fixtures(
        screen=screen,
        image_screen=image_screen,
        family_id=family_id,
        timers=timers,
    )
    EVENT.delete()


def live(
    client: TestClient,
    action: str,
    target: str,
    kind: str = 'screen',
    **values: object,
):
    return client.post(
        f'/screen-live/{EVENT_ID}/{kind}/{target}/{action}',
        data={field: str(value) for field, value in values.items()},
        follow_redirects=False,
    )


def assert_refused(response, status_code: int) -> None:
    """The application answers an error with a redirection to its page."""
    assert response.status_code == 302
    assert response.headers['location'].endswith(f'/error/{status_code}')


def stored_screen(screen_id: int | None) -> StoredScreen:
    with EventDatabase(EVENT_ID) as database:
        return next(
            stored
            for stored in database.load_stored_screens()
            if stored.id == screen_id
        )


def screen_page(client: TestClient, uniq_id: str) -> str:
    page = client.get(f'/view/screen/{EVENT_ID}/{uniq_id}')
    assert page.status_code == 200
    return page.text


@pytest.mark.unit
def test_no_controls_while_the_live_update_is_off(
    http: TestClient, lan: TestClient, event: Fixtures
):
    for client in (http, lan):
        assert CONTROLS not in screen_page(client, event.screen.uniq_id)


@pytest.mark.unit
def test_the_live_update_shows_the_layout_without_storing_it(
    http: TestClient, lan: TestClient, event: Fixtures
):
    screen = event.screen
    response = live(http, 'start', screen.uniq_id, font_size=150, columns=3)
    assert response.status_code == 204
    # Every client is shown the layout and the controls.
    for client in (http, lan):
        page = screen_page(client, screen.uniq_id)
        assert '--font-size: 150;' in page
        assert 'data-columns="3"' in page
        assert CONTROLS in page
        for panel in ('screen-columns-panel', 'screen-font-size-panel'):
            assert panel in page
        assert 'screen-timer-panel' in page
        assert 'screen-live-save' in page
    stored = stored_screen(screen.id)
    assert stored.font_size is None
    assert stored.columns != 3


@pytest.mark.unit
def test_a_visitor_changes_and_saves_the_layout_while_it_is_live(
    http: TestClient, lan: TestClient, event: Fixtures
):
    screen = event.screen
    assert live(http, 'start', screen.uniq_id).status_code == 204
    timer_id = event.timers['Round two']
    response = live(lan, 'update', screen.uniq_id, font_size=80, timer_id=timer_id)
    assert response.status_code == 204
    assert '--font-size: 80;' in screen_page(lan, screen.uniq_id)
    assert stored_screen(screen.id).font_size is None

    assert live(lan, 'save', screen.uniq_id).status_code == 204
    stored = stored_screen(screen.id)
    assert stored.font_size == 80
    assert stored.timer_id == timer_id
    assert live_layout(EVENT_ID, live_key('screen', screen.uniq_id)) is None
    assert CONTROLS not in screen_page(lan, screen.uniq_id)


@pytest.mark.unit
def test_only_the_screen_managers_turn_the_live_update_on_and_off(
    http: TestClient, lan: TestClient, event: Fixtures
):
    screen = event.screen
    for action in ('start', 'stop', 'cancel'):
        assert_refused(live(lan, action, screen.uniq_id), 403)
    assert live_layout(EVENT_ID, live_key('screen', screen.uniq_id)) is None


@pytest.mark.unit
@pytest.mark.parametrize('action', ['update', 'save'])
def test_nothing_changes_while_the_live_update_is_off(
    lan: TestClient, event: Fixtures, action: str
):
    screen = event.screen
    assert_refused(live(lan, action, screen.uniq_id, font_size=120), 400)
    assert stored_screen(screen.id).font_size is None


@pytest.mark.unit
def test_turning_the_live_update_off_keeps_the_stored_layout(
    http: TestClient, event: Fixtures
):
    screen = event.screen
    for action in ('stop', 'cancel'):
        assert live(http, 'start', screen.uniq_id, font_size=200).status_code == 204
        assert live(http, action, screen.uniq_id).status_code == 204
        assert live_layout(EVENT_ID, live_key('screen', screen.uniq_id)) is None
        page = screen_page(http, screen.uniq_id)
        assert CONTROLS not in page
        assert '--font-size: 200;' not in page
        assert stored_screen(screen.id).font_size is None


@pytest.mark.unit
@pytest.mark.parametrize(
    'values',
    [
        {'columns': Screen.COLUMNS_MAX + 1},
        {'font_size': Screen.FONT_SIZE_MIN - 1},
        {'font_size': 'abc'},
        {'timer_id': 999999},
    ],
)
def test_a_layout_out_of_bounds_is_refused(
    http: TestClient, event: Fixtures, values: dict
):
    screen = event.screen
    key = live_key('screen', screen.uniq_id)
    assert live(http, 'start', screen.uniq_id).status_code == 204
    before = dict(live_layout(EVENT_ID, key) or {})
    assert_refused(live(http, 'update', screen.uniq_id, **values), 400)
    assert live_layout(EVENT_ID, key) == before


@pytest.mark.unit
def test_the_live_update_of_a_multi_screen_is_that_of_its_family(
    http: TestClient, lan: TestClient, event: Fixtures
):
    assert live(http, 'start', FAMILY_ID, 'family', font_size=90).status_code == 204
    for page_number in ('001', '002'):
        page = screen_page(lan, f'{FAMILY_ID}:{page_number}')
        assert '--font-size: 90;' in page
        assert CONTROLS in page
        assert f'/family/{FAMILY_ID}/' in page
    assert live(lan, 'update', FAMILY_ID, 'family', columns=2).status_code == 204
    assert live(lan, 'save', FAMILY_ID, 'family').status_code == 204
    family = EVENT.load().families_by_id[event.family_id]
    assert (family.stored_family.font_size, family.stored_family.columns) == (90, 2)


@pytest.mark.unit
def test_the_live_update_of_an_image_screen(
    http: TestClient, lan: TestClient, event: Fixtures
):
    screen = event.image_screen
    assert live(http, 'start', screen.uniq_id).status_code == 204
    page = screen_page(lan, screen.uniq_id)
    assert CONTROLS in page
    assert 'screen-font-size-panel' not in page
    assert 'screen-columns-panel' not in page
    # An image screen has no font size: it is not taken.
    response = live(
        lan,
        'update',
        screen.uniq_id,
        background_blurred='on',
        background_color='#123456',
        font_size=150,
    )
    assert response.status_code == 204
    assert 'blurred-image-background' in screen_page(lan, screen.uniq_id)
    assert live(lan, 'save', screen.uniq_id).status_code == 204
    stored = stored_screen(screen.id)
    assert stored.background_blurred
    assert stored.background_color == '#123456'
    assert stored.font_size is None


@pytest.mark.unit
def test_the_live_update_shows_the_alert_message(
    http: TestClient, lan: TestClient, event: Fixtures
):
    screen = event.screen
    response = live(
        http,
        'start',
        screen.uniq_id,
        message_text_checkbox='',
        message_text='Silence please',
    )
    assert response.status_code == 204
    assert 'Silence please' in screen_page(lan, screen.uniq_id)
    stored = stored_screen(screen.id)
    assert stored.message_text is None
    # A modal opened while live shows the message.
    modal = http.get(f'/screen-modal/update/{EVENT_ID}/{screen.id}').text
    message = re.search(r'<input[^>]*name="message_text"[^>]*>', modal)
    assert message is not None and 'value="Silence please"' in message.group(0)
    response = live(http, 'update', screen.uniq_id, message_text='Last round')
    assert response.status_code == 204
    page = screen_page(lan, screen.uniq_id)
    assert 'Last round' in page and 'Silence please' not in page
    # Cancelled, the screen shows the stored message again.
    assert live(http, 'cancel', screen.uniq_id).status_code == 204
    assert 'Last round' not in screen_page(lan, screen.uniq_id)


@pytest.mark.unit
def test_the_alert_message_is_saved_with_the_layout(
    http: TestClient, lan: TestClient, event: Fixtures
):
    screen = event.screen
    response = live(
        http,
        'start',
        screen.uniq_id,
        message_text_checkbox='',
        message_text='Phones off',
    )
    assert response.status_code == 204
    assert live(lan, 'save', screen.uniq_id).status_code == 204
    stored = stored_screen(screen.id)
    assert (stored.message_default, stored.message_text) == (False, 'Phones off')


@pytest.mark.unit
def test_the_alert_message_of_a_multi_screen_is_that_of_its_family(
    http: TestClient, lan: TestClient, event: Fixtures
):
    response = live(
        http,
        'start',
        FAMILY_ID,
        'family',
        message_text_checkbox='',
        message_text='Family message',
    )
    assert response.status_code == 204
    for page_number in ('001', '002'):
        assert 'Family message' in screen_page(lan, f'{FAMILY_ID}:{page_number}')


@pytest.mark.unit
def test_the_edit_modal_offers_the_live_update_on_an_update_only(
    http: TestClient, event: Fixtures
):
    screen = event.screen
    modal = http.get(f'/screen-modal/update/{EVENT_ID}/{screen.id}').text
    assert 'data-testid="screen-live-update"' in modal
    switch = re.search(r'<input[^>]*name="live_update"[^>]*>', modal)
    assert switch is not None and 'checked' not in switch.group(0)
    for url in (
        f'/screen-modal/create/{EVENT_ID}/{ScreenType.BOARDS.value}',
        f'/family-modal/create/{EVENT_ID}/{ScreenType.BOARDS.value}',
    ):
        assert 'data-testid="screen-live-update"' not in http.get(url).text
    family_modal = http.get(f'/family-modal/update/{EVENT_ID}/{event.family_id}').text
    assert 'data-testid="screen-live-update"' in family_modal


@pytest.mark.unit
def test_a_modal_opened_while_live_shows_the_live_layout(
    http: TestClient, event: Fixtures
):
    screen = event.screen
    assert live(http, 'start', screen.uniq_id, font_size=175).status_code == 204
    modal = http.get(f'/screen-modal/update/{EVENT_ID}/{screen.id}').text
    switch = re.search(r'<input[^>]*name="live_update"[^>]*>', modal)
    assert switch is not None and 'checked' in switch.group(0)
    font_size = re.search(r'<input[^>]*name="font_size"[^>]*>', modal)
    assert font_size is not None and 'value="175"' in font_size.group(0)


@pytest.mark.unit
def test_saving_the_modal_ends_the_live_update(http: TestClient, event: Fixtures):
    screen = event.screen
    assert live(http, 'start', screen.uniq_id, font_size=130).status_code == 204
    response = http.patch(
        f'/screen-update/{EVENT_ID}/{screen.id}',
        data={'name': screen.name, 'public': 'on', 'font_size': '130'},
    )
    assert response.status_code == 200
    assert live_layout(EVENT_ID, live_key('screen', screen.uniq_id)) is None
    assert stored_screen(screen.id).font_size == 130


@pytest.mark.unit
def test_the_controls_are_hidden_behind_the_gear_in_order(
    http: TestClient, event: Fixtures
):
    """The gear comes first and shows or hides the controls, hidden at
    first: the columns, the font size, the timer, then the save button."""
    screen = event.screen
    assert live(http, 'start', screen.uniq_id).status_code == 204
    text = screen_page(http, screen.uniq_id)
    assert 'bi-gear' in text
    assert 'class="screen-controls d-none' in text
    positions = [
        text.index(f'id="{panel}"')
        for panel in (
            'screen-controls-toggle',
            'screen-columns-panel',
            'screen-font-size-panel',
            'screen-timer-panel',
            'screen-live-save',
        )
    ]
    assert positions == sorted(positions)


@pytest.mark.unit
def test_no_controls_in_a_preview(http: TestClient, event: Fixtures):
    screen = event.screen
    assert live(http, 'start', screen.uniq_id).status_code == 204
    page = http.get(f'/view/screen/{EVENT_ID}/{screen.uniq_id}?preview=1')
    assert page.status_code == 200
    assert CONTROLS not in page.text
