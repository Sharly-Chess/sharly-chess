"""Timers and their hours, over HTTP.

A timer counts a venue down to the start of a round, and its hours are
the moments it counts to. Both are edited from modals nothing but a
browser had opened.
"""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-timers-http'
EVENT = EventUnderTest(EVENT_ID, 'test-timers-http-tournament')


@pytest.fixture
def event() -> Iterator[str]:
    EVENT.create()
    yield EVENT_ID
    EVENT.delete()


def timer_names() -> list[str]:
    return [timer.name for timer in EVENT.load().timers_by_id.values()]


def create_timer(http: TestClient, **fields: str):
    return http.post(f'/timer-create/{EVENT_ID}', data={'name': 'Round one'} | fields)


@pytest.mark.unit
def test_a_timer_is_created_renamed_and_deleted(http: TestClient, event: str):
    assert create_timer(http).status_code == 200
    assert timer_names() == ['Round one']
    timer_id = next(iter(EVENT.load().timers_by_id))
    renamed = http.patch(
        f'/timer-update/{EVENT_ID}/{timer_id}', data={'name': 'Round two'}
    )
    assert renamed.status_code == 200
    assert timer_names() == ['Round two']
    deleted = http.delete(f'/timer-delete/{EVENT_ID}/{timer_id}')
    assert deleted.status_code == 200
    assert timer_names() == []


@pytest.mark.unit
def test_a_new_timer_opens_its_hours(http: TestClient, event: str):
    """A new timer has no hours yet, so its creation leads to the list of
    hours, from which they can be added one by one or from a tournament."""
    response = create_timer(http)
    assert 'Timer [Round one] has been created.' in response.text
    assert 'No hours.' in response.text


@pytest.mark.unit
def test_a_timer_needs_a_name(http: TestClient, event: str):
    response = create_timer(http, name='')
    assert response.status_code == 200
    assert 'This field is required.' in response.text
    assert timer_names() == []


@pytest.mark.unit
def test_two_timers_cannot_share_a_name(http: TestClient, event: str):
    assert create_timer(http).status_code == 200
    response = create_timer(http)
    assert response.status_code == 200
    assert 'This name is already used.' in response.text
    assert timer_names() == ['Round one']


@pytest.mark.unit
def test_a_cloned_timer_stands_beside_the_first(http: TestClient, event: str):
    create_timer(http)
    timer_id = next(iter(EVENT.load().timers_by_id))
    response = http.post(
        f'/timer-clone/{EVENT_ID}/{timer_id}', data={'name': 'Round one (copy)'}
    )
    assert response.status_code == 200
    assert 'Timer [Round one (copy)] has been created.' in response.text
    assert sorted(timer_names()) == ['Round one', 'Round one (copy)']


@pytest.mark.unit
@pytest.mark.parametrize('action', ['update', 'clone', 'delete'])
def test_the_timer_modal_opens_for_every_action(
    http: TestClient, event: str, action: str
):
    create_timer(http)
    timer_id = next(iter(EVENT.load().timers_by_id))
    response = http.get(f'/timer-modal/{action}/{EVENT_ID}/{timer_id}')
    assert response.status_code == 200


@pytest.mark.unit
def test_the_default_colours_modal_opens(http: TestClient, event: str):
    """The delays and colours a new timer starts from belong to the
    event, not to any one timer."""
    response = http.get(f'/default-timers-modal/{EVENT_ID}')
    assert response.status_code == 200


@pytest.mark.unit
def test_the_hours_of_a_timer_are_listed(http: TestClient, event: str):
    create_timer(http)
    timer_id = next(iter(EVENT.load().timers_by_id))
    response = http.get(f'/timer-hours-modal/{EVENT_ID}/{timer_id}')
    assert response.status_code == 200


def timer_ids_by_name(http: TestClient) -> dict[str, int]:
    create_timer(http, name='Main hall')
    create_timer(http, name='Side room')
    return {timer.name: timer.id for timer in EVENT.load().timers}


@pytest.mark.unit
def test_the_checked_screens_display_the_timer(http: TestClient, event: str):
    """The checked screens, multi-screens and rotators display the timer, even
    when they showed another timer; the unchecked ones that displayed it are
    left without a timer, and the screens of the other timer keep it."""
    api = ApiClient(http)
    timer_ids = timer_ids_by_name(http)
    main_hall, side_room = timer_ids['Main hall'], timer_ids['Side room']
    tournament = EVENT.tournament()
    screen_overrides = {'init_set_tournament_id': tournament.id}
    boards = TestUtils.create_screen(
        api, EVENT_ID, 'Boards', ScreenType.BOARDS, screen_overrides
    )
    players = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Players',
        ScreenType.PLAYERS,
        screen_overrides | {'timer_id': side_room},
    )
    kept = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Kept',
        ScreenType.BOARDS,
        screen_overrides | {'timer_id': side_room},
    )
    family = TestUtils.create_family(
        api,
        EVENT_ID,
        tournament.stored_tournament,
        'hall-family',
        ScreenType.BOARDS,
        {'parts': 2},
    )
    rotator_id = TestUtils.create_rotator(api, EVENT_ID, 'Entrance')

    response = http.patch(
        f'/timer-usage-update/{EVENT_ID}/{main_hall}',
        data={
            f'screen_{boards.id}': 'on',
            f'screen_{players.id}': 'on',
            f'family_{family.id}': 'on',
            f'rotator_{rotator_id}': 'on',
        },
    )
    assert response.status_code == 200
    loaded = EVENT.load()
    timer = loaded.timers_by_id[main_hall]
    assert [screen.name for screen in timer.screens] == ['Boards', 'Players']
    assert [item.id for item in timer.families] == [family.id]
    assert [item.id for item in timer.rotators] == [rotator_id]
    assert [screen.id for screen in loaded.timers_by_id[side_room].screens] == [kept.id]

    response = http.patch(
        f'/timer-usage-update/{EVENT_ID}/{main_hall}',
        data={f'screen_{players.id}': 'on'},
    )
    assert response.status_code == 200
    loaded = EVENT.load()
    assert loaded.basic_screens_by_id[boards.id].timer is None
    assert loaded.families_by_id[family.id].timer is None
    assert loaded.rotators_by_id[rotator_id].timer is None
    assert [screen.name for screen in loaded.timers_by_id[main_hall].screens] == [
        'Players'
    ]
    assert [screen.id for screen in loaded.timers_by_id[side_room].screens] == [kept.id]


@pytest.mark.unit
def test_the_screens_are_listed_with_their_timer(http: TestClient, event: str):
    api = ApiClient(http)
    timer_ids = timer_ids_by_name(http)
    tournament_id = EVENT.tournament().id
    shown = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Hall boards',
        ScreenType.BOARDS,
        {'init_set_tournament_id': tournament_id, 'timer_id': timer_ids['Main hall']},
    )
    other = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Annex boards',
        ScreenType.BOARDS,
        {'init_set_tournament_id': tournament_id, 'timer_id': timer_ids['Side room']},
    )
    response = http.get(f'/timer-usage-modal/{EVENT_ID}/{timer_ids["Main hall"]}')
    assert response.status_code == 200
    assert response.text.index('Annex boards') < response.text.index('Hall boards')
    assert f'data-testid="screen-{shown.id}-other-timer"' not in response.text
    assert f'data-testid="screen-{other.id}-other-timer"' in response.text
    assert 'Timer: Side room' in response.text
