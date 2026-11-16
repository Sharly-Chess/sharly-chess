"""Timers and their hours, over HTTP.

A timer counts a venue down to the start of a round, and its hours are
the moments it counts to. Both are edited from modals nothing but a
browser had opened.
"""

import re
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser
from litestar.testing import TestClient

from common.sharly_chess_config import SharlyChessConfig
from database.sqlite.event.event_database import EventDatabase
from utils.date_time import format_datetime

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
    screen_overrides = {'init_set_tournament_ids': [tournament.id]}
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
        {
            'init_set_tournament_ids': [tournament_id],
            'timer_id': timer_ids['Main hall'],
        },
    )
    other = TestUtils.create_screen(
        api,
        EVENT_ID,
        'Annex boards',
        ScreenType.BOARDS,
        {
            'init_set_tournament_ids': [tournament_id],
            'timer_id': timer_ids['Side room'],
        },
    )
    response = http.get(f'/timer-usage-modal/{EVENT_ID}/{timer_ids["Main hall"]}')
    assert response.status_code == 200
    assert response.text.index('Annex boards') < response.text.index('Hall boards')
    assert f'data-testid="screen-{shown.id}-other-timer"' not in response.text
    assert f'data-testid="screen-{other.id}-other-timer"' in response.text
    assert 'Timer: Side room' in response.text


@pytest.mark.unit
def test_the_screens_are_listed_with_the_channels_they_are_designed_for(
    http: TestClient, event: str
):
    api = ApiClient(http)
    timer_ids = timer_ids_by_name(http)
    channel = TestUtils.create_display_controller(api, EVENT_ID, 'Entrance tablets')
    TestUtils.create_screen(
        api,
        EVENT_ID,
        'Hall boards',
        ScreenType.BOARDS,
        {
            'init_set_tournament_ids': [EVENT.tournament().id],
            'display_controller_ids': [channel.id],
        },
    )
    response = http.get(f'/timer-usage-modal/{EVENT_ID}/{timer_ids["Main hall"]}')
    assert response.status_code == 200
    assert response.text.index('Hall boards') < response.text.index('Entrance tablets')


def hour_time(hours: int = 14) -> str:
    """A time of the event's first day, as the hour form writes it."""
    start_date = EVENT.load().start_date
    return format_datetime(datetime.combine(start_date, time(hours)))


def create_hour(http: TestClient, timer_id: int, **fields: str):
    return http.post(
        f'/timer-hour/create/{EVENT_ID}/{timer_id}',
        data={'hour_kind': 'round', 'triggered_at': hour_time()} | fields,
    )


def only_timer_id(http: TestClient) -> int:
    create_timer(http)
    return next(iter(EVENT.load().timers_by_id))


@pytest.mark.unit
def test_a_round_hour_is_worded_from_its_number(http: TestClient, event: str):
    timer_id = only_timer_id(http)
    assert create_hour(http, timer_id, hour_round='3').status_code == 200
    (hour,) = EVENT.load().timers_by_id[timer_id].timer_hours
    assert (hour.round, hour.label) == (3, None)
    assert hour.text_before == 'Round 3 starts in %s'
    assert hour.text_after == 'Round 3 started %s ago'


@pytest.mark.unit
def test_a_round_hour_may_be_labelled(http: TestClient, event: str):
    timer_id = only_timer_id(http)
    create_hour(http, timer_id, hour_round='2', hour_label='Opens A-D')
    (hour,) = EVENT.load().timers_by_id[timer_id].timer_hours
    assert hour.text_before == 'Opens A-D: round 2 starts in %s'


@pytest.mark.unit
def test_another_hour_is_worded_from_its_label(http: TestClient, event: str):
    timer_id = only_timer_id(http)
    create_hour(http, timer_id, hour_kind='other', hour_label='Check-in closes')
    (hour,) = EVENT.load().timers_by_id[timer_id].timer_hours
    assert (hour.round, hour.label) == (None, 'Check-in closes')
    assert hour.text_before == 'Check-in closes in %s'


@pytest.mark.unit
def test_another_hour_needs_a_label(http: TestClient, event: str):
    timer_id = only_timer_id(http)
    response = create_hour(http, timer_id, hour_kind='other')
    assert 'This field is required.' in response.text
    assert not EVENT.load().timers_by_id[timer_id].timer_hours


@pytest.mark.unit
def test_the_wording_of_an_hour_can_be_customised(http: TestClient, event: str):
    timer_id = only_timer_id(http)
    create_hour(http, timer_id, hour_round='4', text_before='Last round ({}) in %s')
    (hour,) = EVENT.load().timers_by_id[timer_id].timer_hours
    assert hour.text_before == 'Last round (4) in %s'
    assert hour.text_after == 'Round 4 started %s ago'


@pytest.mark.unit
def test_two_hours_may_share_a_label(http: TestClient, event: str):
    timer_id = only_timer_id(http)
    for hours in (9, 10):
        create_hour(
            http,
            timer_id,
            hour_kind='other',
            hour_label='Check-in',
            triggered_at=hour_time(hours),
        )
    timer = EVENT.load().timers_by_id[timer_id]
    assert [hour.label for hour in timer.sorted_timer_hours] == ['Check-in'] * 2


def set_schedule(round_hours: dict[int, int]) -> dict[int, datetime]:
    """Schedules the given rounds of the tournament at the given hours of
    the event's first day."""
    tournament = EVENT.tournament()
    start_date = EVENT.load().start_date
    schedule = {
        round_: datetime.combine(start_date, time(hours))
        for round_, hours in round_hours.items()
    }
    with EventDatabase(EVENT_ID, write=True) as database:
        stored_tournament = database.get_stored_tournament(tournament.id)
        assert stored_tournament is not None
        stored_tournament.round_datetimes = dict(schedule)
        database.update_stored_tournament(stored_tournament)
    return schedule


def copy_schedule(http: TestClient, timer_id: int, *rounds: int):
    return http.post(
        f'/timer-hours/copy/{EVENT_ID}/{timer_id}/{EVENT.tournament().id}',
        data={f'round_{round_}': 'on' for round_ in rounds},
    )


def round_hours(timer_id: int) -> list[tuple[int | None, datetime]]:
    timer = EVENT.load().timers_by_id[timer_id]
    return [(hour.round, hour.triggered_at) for hour in timer.sorted_timer_hours]


@pytest.mark.unit
def test_the_checked_rounds_of_a_schedule_are_copied(http: TestClient, event: str):
    timer_id = only_timer_id(http)
    schedule = set_schedule({1: 10, 2: 14, 3: 18})
    modal = http.get(f'/timer-hours-copy-modal/{EVENT_ID}/{timer_id}')
    assert modal.status_code == 200
    assert modal.text.count('data-status="new"') == 3
    response = copy_schedule(http, timer_id, 1, 2)
    assert '2 hours added.' in response.text
    assert round_hours(timer_id) == [(1, schedule[1]), (2, schedule[2])]


@pytest.mark.unit
def test_copying_a_changed_schedule_again_moves_the_rounds(
    http: TestClient, event: str
):
    """A round hour keeps its label and its wording when the schedule
    moves it."""
    timer_id = only_timer_id(http)
    set_schedule({1: 10, 2: 14})
    create_hour(
        http,
        timer_id,
        hour_round='2',
        hour_label='Opens A-D',
        triggered_at=hour_time(15),
    )
    schedule = set_schedule({1: 10, 2: 16})
    modal = http.get(f'/timer-hours-copy-modal/{EVENT_ID}/{timer_id}')
    assert 'data-status="changed"' in modal.text
    response = copy_schedule(http, timer_id, 1, 2)
    assert '1 hour added. 1 hour moved.' in response.text
    assert round_hours(timer_id) == [(1, schedule[1]), (2, schedule[2])]
    (moved,) = [
        hour
        for hour in EVENT.load().timers_by_id[timer_id].timer_hours
        if hour.round == 2
    ]
    assert moved.label == 'Opens A-D'


@pytest.mark.unit
def test_a_round_is_not_copied_over_another_hour(http: TestClient, event: str):
    timer_id = only_timer_id(http)
    set_schedule({1: 14})
    create_hour(
        http,
        timer_id,
        hour_kind='other',
        hour_label='Prize-giving',
        triggered_at=hour_time(14),
    )
    modal = http.get(f'/timer-hours-copy-modal/{EVENT_ID}/{timer_id}')
    assert 'Taken by [Prize-giving]' in modal.text
    copy_schedule(http, timer_id, 1)
    assert round_hours(timer_id) == [
        (None, datetime.combine(EVENT.load().start_date, time(14)))
    ]


@pytest.mark.unit
def test_a_timer_is_created_from_a_schedule(http: TestClient, event: str):
    schedule = set_schedule({1: 10, 2: 14})
    tournament = EVENT.tournament()
    response = http.post(f'/timer-create-from-schedule/{EVENT_ID}/{tournament.id}')
    assert response.status_code == 200
    (timer,) = EVENT.load().timers
    assert timer.name == tournament.name
    assert round_hours(timer.id) == [(1, schedule[1]), (2, schedule[2])]


@pytest.mark.unit
def test_the_hour_form_opens_for_every_action(http: TestClient, event: str):
    timer_id = only_timer_id(http)
    create_hour(http, timer_id, hour_round='1')
    (hour,) = EVENT.load().timers_by_id[timer_id].timer_hours
    assert (
        http.get(f'/timer-hour-modal/create/{EVENT_ID}/{timer_id}').status_code == 200
    )
    for action in ('update', 'clone'):
        response = http.get(
            f'/timer-hour-modal/{action}/{EVENT_ID}/{timer_id}/{hour.id}'
        )
        assert response.status_code == 200


@pytest.mark.unit
def test_a_timer_may_stop_showing_at_the_hour(http: TestClient, event: str):
    """A delay of 0 is kept rather than replaced by the event's delay."""
    response = create_timer(http, delay_1='', delay_2='0', delay_3='0')
    assert response.status_code == 200
    (timer,) = EVENT.load().timers
    assert timer.delays == {1: 15, 2: 0, 3: 0}


@pytest.mark.unit
def test_the_event_delays_may_be_0(http: TestClient, event: str):
    response = http.patch(
        f'/default-timers-update/{EVENT_ID}',
        data={'delay_1': '10', 'delay_2': '0', 'delay_3': '0'},
    )
    assert response.status_code == 200
    assert EVENT.load().timer_delays == {1: 10, 2: 0, 3: 0}
    assert SharlyChessConfig.default_timer_delays == {1: 15, 2: 5, 3: 10}


@pytest.mark.unit
def test_a_negative_delay_is_refused(http: TestClient, event: str):
    response = create_timer(http, delay_3='-1')
    assert 'Invalid delay [-1]' in response.text
    assert timer_names() == []


def quick_countdown(http: TestClient, **fields: str):
    return http.post(
        f'/timer-quick/{EVENT_ID}',
        data={'label': 'Next round', 'minutes': '10'} | fields,
    )


@pytest.mark.unit
def test_a_quick_countdown_ends_minutes_from_now(http: TestClient, event: str):
    timer_id = only_timer_id(http)
    before = datetime.now()
    response = quick_countdown(http, **{f'timer_{timer_id}': 'on'})
    assert response.status_code == 200
    (hour,) = EVENT.load().timers_by_id[timer_id].timer_hours
    assert hour.label == 'Next round'
    assert hour.text_before == 'Next round in %s'
    assert timedelta(minutes=10) <= hour.triggered_at - before <= timedelta(minutes=11)


@pytest.mark.unit
def test_a_quick_countdown_may_end_at_a_given_time(http: TestClient, event: str):
    timer_id = only_timer_id(http)
    at = (datetime.now() + timedelta(minutes=30)).replace(second=0, microsecond=0)
    if at.date() != datetime.now().date():
        pytest.skip('the test runs too close to midnight')
    quick_countdown(http, at=at.strftime('%H:%M'), **{f'timer_{timer_id}': 'on'})
    (hour,) = EVENT.load().timers_by_id[timer_id].timer_hours
    assert hour.triggered_at == at


@pytest.mark.unit
def test_a_quick_countdown_goes_to_the_chosen_timers_only(http: TestClient, event: str):
    timer_ids = timer_ids_by_name(http)
    quick_countdown(http, **{f'timer_{timer_ids["Main hall"]}': 'on'})
    timers = EVENT.load().timers_by_id
    assert len(timers[timer_ids['Main hall']].timer_hours) == 1
    assert not timers[timer_ids['Side room']].timer_hours


@pytest.mark.unit
def test_a_quick_countdown_needs_a_timer_to_be_chosen(http: TestClient, event: str):
    only_timer_id(http)
    response = quick_countdown(http)
    assert 'Choose at least one timer.' in response.text


@pytest.mark.unit
def test_a_quick_countdown_creates_a_new_timer(http: TestClient, event: str):
    """A new timer is created on demand, and the screens that show it are
    chosen next."""
    response = quick_countdown(http, new_timer='on')
    assert response.status_code == 200
    (timer,) = EVENT.load().timers
    assert [hour.label for hour in timer.timer_hours] == ['Next round']
    assert f'/timer-usage-update/{EVENT_ID}/{timer.id}' in response.text


@pytest.mark.unit
def test_the_quick_countdown_modal_opens(http: TestClient, event: str):
    only_timer_id(http)
    response = http.get(f'/timer-quick-modal/{EVENT_ID}')
    assert response.status_code == 200
    assert 'Quick countdown' in response.text


def free_time(timer_id: int, now: datetime) -> datetime:
    return EVENT.load().timers_by_id[timer_id].free_hour_time(now)


@pytest.mark.unit
def test_a_new_hour_starts_at_the_next_quarter_during_the_event(
    http: TestClient, event: str
):
    timer_id = only_timer_id(http)
    day = EVENT.load().start_date
    now = datetime.combine(day, time(10, 7, 30))
    assert free_time(timer_id, now) == datetime.combine(day, time(10, 15))
    create_hour(
        http,
        timer_id,
        hour_round='1',
        triggered_at=format_datetime(datetime.combine(day, time(10, 15))),
    )
    assert free_time(timer_id, now) == datetime.combine(day, time(10, 30))


@pytest.mark.unit
def test_a_new_hour_follows_the_last_one_before_the_event(http: TestClient, event: str):
    timer_id = only_timer_id(http)
    day = EVENT.load().start_date
    before = datetime.combine(day - timedelta(days=3), time(12))
    assert free_time(timer_id, before) == datetime.combine(day, time(9))
    create_hour(http, timer_id, hour_round='1', triggered_at=hour_time(14))
    assert free_time(timer_id, before) == datetime.combine(day, time(15))


def postpone(http: TestClient, timer_id: int, hour_id: int, **fields: str):
    return http.patch(
        f'/timer-hour/postpone/{EVENT_ID}/{timer_id}/{hour_id}', data=fields
    )


def hour_times(timer_id: int) -> list[tuple[int | None, str]]:
    timer = EVENT.load().timers_by_id[timer_id]
    return [
        (hour.round, hour.triggered_at.strftime('%H:%M'))
        for hour in timer.sorted_timer_hours
    ]


def hour_id_of_round(timer_id: int, round_: int) -> int:
    timer = EVENT.load().timers_by_id[timer_id]
    return next(hour.id for hour in timer.timer_hours if hour.round == round_)


@pytest.mark.unit
def test_an_hour_and_the_later_ones_of_its_day_are_postponed(
    http: TestClient, event: str
):
    timer_id = only_timer_id(http)
    for round_, hours in ((1, 9), (2, 14), (3, 18)):
        create_hour(
            http, timer_id, hour_round=str(round_), triggered_at=hour_time(hours)
        )
    modal = http.get(
        f'/timer-hour-postpone-modal/{EVENT_ID}/{timer_id}/{hour_id_of_round(timer_id, 2)}'
    )
    assert modal.status_code == 200
    response = postpone(
        http, timer_id, hour_id_of_round(timer_id, 2), minutes='15', later_hours='on'
    )
    assert '2 hours postponed by 15 min.' in response.text
    assert hour_times(timer_id) == [(1, '09:00'), (2, '14:15'), (3, '18:15')]


@pytest.mark.unit
def test_an_hour_is_postponed_alone(http: TestClient, event: str):
    timer_id = only_timer_id(http)
    for round_, hours in ((1, 9), (2, 14)):
        create_hour(
            http, timer_id, hour_round=str(round_), triggered_at=hour_time(hours)
        )
    postpone(http, timer_id, hour_id_of_round(timer_id, 1), other_minutes='40')
    assert hour_times(timer_id) == [(1, '09:40'), (2, '14:00')]


@pytest.mark.unit
def test_an_hour_is_not_postponed_onto_another(http: TestClient, event: str):
    timer_id = only_timer_id(http)
    for round_, hours in ((1, 9), (2, 10)):
        create_hour(
            http, timer_id, hour_round=str(round_), triggered_at=hour_time(hours)
        )
    response = postpone(
        http, timer_id, hour_id_of_round(timer_id, 1), other_minutes='60'
    )
    assert 'already takes that time.' in response.text
    assert hour_times(timer_id) == [(1, '09:00'), (2, '10:00')]


@pytest.mark.unit
def test_the_screens_of_a_timer_are_chosen_with_it(http: TestClient, event: str):
    """The screens checked in the timer's own form show it; an edit that
    unchecks one takes the timer off it."""
    api = ApiClient(http)
    overrides = {'init_set_tournament_ids': [EVENT.tournament().id]}
    boards = TestUtils.create_screen(
        api, EVENT_ID, 'Boards', ScreenType.BOARDS, overrides
    )
    players = TestUtils.create_screen(
        api, EVENT_ID, 'Players', ScreenType.PLAYERS, overrides
    )
    form = http.get(f'/timer-modal/create/{EVENT_ID}')
    assert f'name="screen_{boards.id}"' in form.text
    create_timer(http, **{f'screen_{boards.id}': 'on', f'screen_{players.id}': 'on'})
    (timer,) = EVENT.load().timers
    assert [screen.name for screen in timer.screens] == ['Boards', 'Players']
    http.patch(
        f'/timer-update/{EVENT_ID}/{timer.id}',
        data={'name': 'Round one', f'screen_{players.id}': 'on'},
    )
    (timer,) = EVENT.load().timers
    assert [screen.name for screen in timer.screens] == ['Players']


def move_event(days: int) -> None:
    """Moves the event's tournament to start the given number of days from
    today."""
    tournament = EVENT.tournament()
    with EventDatabase(EVENT_ID, write=True) as database:
        stored_tournament = database.get_stored_tournament(tournament.id)
        assert stored_tournament is not None
        stored_tournament.start_date = date.today() + timedelta(days=days)
        stored_tournament.stop_date = date.today() + timedelta(days=days + 1)
        database.update_stored_tournament(stored_tournament)


@pytest.mark.unit
def test_an_hour_may_be_set_today_before_the_event(http: TestClient, event: str):
    """A countdown can run while the event is being set up, before its first
    day; a day between today and the event is accepted too."""
    move_event(10)
    timer_id = only_timer_id(http)
    today_late = format_datetime(datetime.combine(date.today(), time(23, 59)))
    response = create_hour(http, timer_id, hour_round='1', triggered_at=today_late)
    assert 'Choose a date' not in response.text
    assert len(EVENT.load().timers_by_id[timer_id].timer_hours) == 1


@pytest.mark.unit
def test_an_hour_after_the_event_is_refused(http: TestClient, event: str):
    move_event(10)
    timer_id = only_timer_id(http)
    late = datetime.combine(date.today() + timedelta(days=20), time(14))
    response = create_hour(
        http, timer_id, hour_round='1', triggered_at=format_datetime(late)
    )
    assert 'Choose a date from' in response.text
    assert not EVENT.load().timers_by_id[timer_id].timer_hours


@pytest.mark.unit
def test_a_quick_countdown_goes_to_a_new_timer_beside_the_others(
    http: TestClient, event: str
):
    timer_id = only_timer_id(http)
    quick_countdown(http, new_timer='on', **{f'timer_{timer_id}': 'on'})
    timers = EVENT.load().timers
    assert len(timers) == 2
    assert all(len(timer.timer_hours) == 1 for timer in timers)


@pytest.mark.unit
def test_a_new_timer_is_offered_ticked_when_the_event_has_none(
    http: TestClient, event: str
):
    response = http.get(f'/timer-quick-modal/{EVENT_ID}')
    assert 'name="new_timer"' in response.text
    assert re.search(
        r'data-testid="quick-new-timer"\s+value="on"\s+checked', response.text
    )


def proposed_timer_name(http: TestClient) -> str:
    parser = AdvancedHTMLParser()
    parser.parseStr(http.get(f'/timer-modal/create/{EVENT_ID}').text)
    return next(
        field.getAttribute('value')
        for field in parser.getElementsByTagName('input')
        if field.getAttribute('name') == 'name'
    )


@pytest.mark.unit
def test_a_new_timer_is_named_timer_then_numbered(http: TestClient, event: str):
    assert proposed_timer_name(http) == 'Timer'
    create_timer(http, name='Timer')
    assert proposed_timer_name(http) == 'Timer (2)'


@pytest.mark.unit
def test_a_quick_countdown_names_its_new_timer_as_a_new_timer_is(
    http: TestClient, event: str
):
    create_timer(http, name='Timer')
    quick_countdown(http, new_timer='on')
    assert sorted(timer_names()) == ['Timer', 'Timer (2)']
