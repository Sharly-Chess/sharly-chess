"""The tournament form's rating periods, driven over HTTP.

The arbiter marks a tournament as lasting more than 30 days and then
ticks the round that starts each slice, in the schedule section. The
section is re-rendered on its own as those boxes change, so both paths
are exercised here.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils
from utils.date_time import format_date_range, format_datetime

EVENT_ID = 'test-periods-http'
TOURNAMENT_NAME = 'test-periods-http-tournament'

# Four rounds spread over three months: too long for one period, and cut
# in two by a boundary at round 3.
ROUND_DATETIMES = {
    1: datetime(2026, 11, 14, 14),
    2: datetime(2026, 11, 28, 14),
    3: datetime(2027, 1, 9, 14),
    4: datetime(2027, 1, 23, 14),
}


def _form_dates() -> dict[str, str]:
    """The tournament's dates and its round schedule, in the format the
    form expects — which the configured date formatter decides."""
    return {
        'date_range': format_date_range(
            datetime(2026, 11, 1).date(), datetime(2027, 2, 1).date()
        )
    } | {
        f'round_{round_nb}_datetime': format_datetime(round_datetime)
        for round_nb, round_datetime in ROUND_DATETIMES.items()
    }


@pytest.fixture
def event() -> Iterator[str]:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(
        EVENT_ID,
        TOURNAMENT_NAME,
        overrides={'rounds': 4, 'round_datetimes': ROUND_DATETIMES},
    )
    yield EVENT_ID
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def _tournament_id(event: str) -> int:
    with EventDatabase(event) as database:
        tournament_id = next(
            stored.id
            for stored in database.load_stored_tournaments()
            if stored.name == TOURNAMENT_NAME
        )
    assert tournament_id is not None
    return tournament_id


def _stored_first_rounds(event: str) -> list[int]:
    with EventDatabase(event) as database:
        return [
            stored.first_round
            for stored in database.load_tournament_stored_periods(_tournament_id(event))
        ]


def _update(http: TestClient, event: str, **fields: str):
    return http.patch(
        f'/tournament-update/{event}/{_tournament_id(event)}',
        data={
            'name': TOURNAMENT_NAME,
            'rounds': '4',
            'pairing_system': 'SWISS',
            'SWISS_pairing_variation': 'SWISS_STANDARD',
        }
        | _form_dates()
        | fields,
    )


def _tie_break_rating(event: str) -> str:
    with EventDatabase(event) as database:
        return next(
            stored.tie_break_rating
            for stored in database.load_stored_tournaments()
            if stored.name == TOURNAMENT_NAME
        )


def _set_tie_break_rating(event: str, period_index: int) -> str:
    """Point the tie-breaks at one of the tournament's slices."""
    with EventDatabase(event, write=True) as database:
        period = database.load_tournament_stored_periods(_tournament_id(event))[
            period_index
        ]
        stored_tournament = next(
            stored
            for stored in database.load_stored_tournaments()
            if stored.name == TOURNAMENT_NAME
        )
        stored_tournament.tie_break_rating = str(period.id)
        database.update_stored_tournament(stored_tournament)
    return str(period.id)


# Rounds ten days apart: the tournament runs past 30 days, and a slice can
# still be merged into its neighbour without the result running past 30
# days itself.
CLOSE_ROUND_DATETIMES = {
    round_nb: datetime(2026, 11, 2, 14) + timedelta(days=10 * (round_nb - 1))
    for round_nb in range(1, 5)
}


def _close_dates() -> dict[str, str]:
    return {
        'date_range': format_date_range(
            datetime(2026, 11, 1).date(), datetime(2026, 12, 15).date()
        )
    } | {
        f'round_{round_nb}_datetime': format_datetime(round_datetime)
        for round_nb, round_datetime in CLOSE_ROUND_DATETIMES.items()
    }


@pytest.mark.unit
def test_a_slice_the_tie_breaks_read_can_lose_its_boundary(
    http: TestClient, event: str
):
    """Merging a slice into its neighbour leaves the tournament with no
    such slice, so the tie-breaks go back to the first rating instead of
    reading one the arbiter never chose."""
    _update(
        http,
        event,
        round_2_period_start='on',
        round_3_period_start='on',
        multi_period='on',
        **_close_dates(),
    )
    assert _stored_first_rounds(event) == [1, 2, 3]
    _set_tie_break_rating(event, 2)

    _update(http, event, round_3_period_start='on', multi_period='on', **_close_dates())
    assert _stored_first_rounds(event) == [1, 3]
    assert _tie_break_rating(event) == ''


@pytest.mark.unit
def test_a_slice_the_tie_breaks_read_survives_its_boundary_moving(
    http: TestClient, event: str
):
    _update(
        http,
        event,
        round_2_period_start='on',
        round_3_period_start='on',
        multi_period='on',
        **_close_dates(),
    )
    period_id = _set_tie_break_rating(event, 1)

    _update(
        http,
        event,
        round_3_period_start='on',
        round_4_period_start='on',
        multi_period='on',
        **_close_dates(),
    )
    assert _stored_first_rounds(event) == [1, 3, 4]
    assert _tie_break_rating(event) == period_id


@pytest.mark.unit
def test_a_clone_is_cut_like_the_tournament_it_copies(http: TestClient, event: str):
    """The schedule comes with the tournament, so the slices laid over it
    have to come too."""
    _update(http, event, multi_period='on', round_3_period_start='on')
    response = http.post(
        f'/tournament-clone/{event}/{_tournament_id(event)}',
        data={
            'name': 'Clone',
            'rounds': '4',
            'pairing_system': 'SWISS',
            'SWISS_pairing_variation': 'SWISS_STANDARD',
            'multi_period': 'on',
            'round_3_period_start': 'on',
        }
        | _form_dates(),
    )
    assert response.status_code in (200, 302)
    with EventDatabase(event) as database:
        clone_id = next(
            stored.id
            for stored in database.load_stored_tournaments()
            if stored.name == 'Clone'
        )
        assert clone_id is not None
        assert [
            stored.first_round
            for stored in database.load_tournament_stored_periods(clone_id)
        ] == [1, 3]


@pytest.mark.unit
def test_a_tournament_starts_with_the_single_period(http: TestClient, event: str):
    assert _stored_first_rounds(event) == [1]


@pytest.mark.unit
def test_marked_rounds_are_saved_as_period_boundaries(http: TestClient, event: str):
    response = _update(http, event, multi_period='on', round_3_period_start='on')
    assert response.status_code in (200, 302)
    assert _stored_first_rounds(event) == [1, 3]


@pytest.mark.unit
def test_boundaries_are_dropped_when_the_tournament_is_no_longer_long(
    http: TestClient, event: str
):
    _update(http, event, multi_period='on', round_3_period_start='on')
    _update(http, event, round_3_period_start='on')
    assert _stored_first_rounds(event) == [1]


@pytest.mark.unit
def test_a_period_of_more_than_thirty_days_is_rejected(http: TestClient, event: str):
    """Rounds 1 to 4 span more than two months, so leaving them in one
    period comes back marked rather than saved."""
    response = _update(http, event, multi_period='on')
    assert response.status_code == 200
    assert 'round #3' in response.text
    assert _stored_first_rounds(event) == [1]


@pytest.mark.unit
def test_the_schedule_section_lists_the_periods(http: TestClient, event: str):
    response = http.get(
        f'/tournament-schedule-section/{event}',
        params={
            'tournament_id': str(_tournament_id(event)),
            'rounds': '4',
            'multi_period': 'on',
            'round_3_period_start': 'on',
        }
        | _form_dates(),
    )
    assert response.status_code == 200
    assert 'round_3_period_start' in response.text
    assert 'R1' in response.text and 'R3' in response.text
    assert 'Start a new period at this round' in response.text


def _section(http: TestClient, event: str, **params: str) -> str:
    response = http.get(
        f'/tournament-schedule-section/{event}',
        params={
            'tournament_id': str(_tournament_id(event)),
            'rounds': '4',
            'multi_period': 'on',
        }
        | _form_dates()
        | params,
    )
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
def test_a_round_can_be_handed_to_either_neighbouring_period(
    http: TestClient, event: str
):
    """Rounds 1-2, then 3-4: the first period passes its last round on,
    the second hands its first round back."""
    section = _section(http, event, round_3_period_start='on')
    assert 'Move this round to the next period' in section
    assert 'Move this round to the previous period' in section
    assert 'Remove this period' in section


@pytest.mark.unit
def test_the_last_period_has_nothing_to_pass_its_last_round_to(
    http: TestClient, event: str
):
    section = _section(http, event)
    assert 'Move this round to the next period' not in section


@pytest.mark.unit
def test_a_period_of_one_round_still_offers_to_hand_it_over(
    http: TestClient, event: str
):
    """Moving the only round of a period leaves the period empty, which
    is the boundary being dropped — the arbiter should not have to know
    that and reach for the cross instead."""
    section = _section(
        http, event, round_3_period_start='on', round_4_period_start='on'
    )
    assert 'Move this round to the previous period' in section
    assert 'Move this round to the next period' in section


@pytest.mark.unit
def test_the_first_period_cannot_be_removed(http: TestClient, event: str):
    """Round 1 starts a period whatever else is marked, so period 1 has
    nothing to merge into."""
    section = _section(http, event)
    assert 'Remove this period' not in section


@pytest.mark.unit
def test_the_switch_is_offered_only_for_dates_beyond_thirty_days(
    http: TestClient, event: str
):
    """It sits with the dates that make it relevant, and a tournament
    short enough to be rated in one go is not asked about it."""
    long_response = http.get(
        f'/tournament-schedule-section/{event}',
        params={'tournament_id': str(_tournament_id(event)), 'rounds': '4'}
        | _form_dates(),
    )
    short_response = http.get(
        f'/tournament-schedule-section/{event}',
        params={
            'tournament_id': str(_tournament_id(event)),
            'rounds': '4',
            'date_range': format_date_range(
                datetime(2026, 11, 1).date(), datetime(2026, 11, 20).date()
            ),
        },
    )
    assert 'id="multi-period"' in long_response.text
    assert 'id="multi-period"' not in short_response.text


@pytest.mark.unit
def test_an_unticked_switch_leaves_the_period_boxes_hidden(
    http: TestClient, event: str
):
    """A form that comes back marked carries 'off' for the switch, which
    is not the switch being on."""
    response = _update(http, event, round_1_datetime='')
    assert response.status_code == 200
    assert 'round_3_period_start' not in response.text


@pytest.mark.unit
def test_the_schedule_section_hides_the_periods_until_the_switch_is_on(
    http: TestClient, event: str
):
    response = http.get(
        f'/tournament-schedule-section/{event}',
        params={'tournament_id': str(_tournament_id(event)), 'rounds': '4'},
    )
    assert response.status_code == 200
    assert 'round_3_period_start' not in response.text
