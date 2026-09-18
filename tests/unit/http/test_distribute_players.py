"""Spreading the players of an event over its tournaments, over HTTP.

The action is offered from the tournaments tab and from the players tab,
and comes back to whichever one it was started from.
"""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.event import Event
from tests.test_config import TestUtils
from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-distribute-http'
FIRST_TOURNAMENT = 'test-distribute-http-first'
SECOND_TOURNAMENT = 'test-distribute-http-second'

EVENT = EventUnderTest(EVENT_ID, FIRST_TOURNAMENT)


@pytest.fixture
def event() -> Iterator[Event]:
    EVENT.create(json_file='tec-swiss-unpaired')
    TestUtils.create_tournament(EVENT_ID, SECOND_TOURNAMENT)
    yield EVENT.load()
    EVENT.delete()


def player_count_by_tournament_id(event: Event) -> dict[int, int]:
    return {
        tournament.id: len(tournament.tournament_players_by_id)
        for tournament in event.sorted_tournaments
    }


def distribute(http: TestClient, event: Event, tab: str | None) -> str:
    """Send every player of the event to its second tournament, and answer
    with the address the arbiter is sent back to."""
    counts = {tournament.id: 0 for tournament in event.sorted_tournaments}
    counts[event.sorted_tournaments[1].id] = event.player_count
    response = http.post(
        f'/distribute-players/{EVENT_ID}',
        data={'distribution_type': 'rating'}
        | ({'tab': tab} if tab is not None else {})
        | {
            f'player_count_{tournament_id}': str(count)
            for tournament_id, count in counts.items()
        },
    )
    assert response.status_code == 201
    return response.headers['HX-Redirect']


@pytest.mark.unit
@pytest.mark.parametrize('tab', ['tournaments', 'players'])
def test_both_tabs_offer_the_distribution(http: TestClient, event: Event, tab: str):
    response = http.get(f'/event/{EVENT_ID}/{tab}')
    assert response.status_code == 200
    assert f'/distribute-players-modal/{EVENT_ID}' in response.text


@pytest.mark.unit
def test_the_modal_reminds_the_arbiter_to_update_the_players(
    http: TestClient, event: Event
):
    response = http.get(f'/distribute-players-modal/{EVENT_ID}')
    assert response.status_code == 200
    assert 'before distributing them among the tournaments' in response.text


@pytest.mark.unit
@pytest.mark.parametrize(
    ('opened_from', 'carried'),
    [('players', 'players'), ('tournaments', 'tournaments'), (None, 'tournaments')],
)
def test_the_modal_carries_the_tab_it_was_opened_from(
    http: TestClient, event: Event, opened_from: str | None, carried: str
):
    response = http.get(
        f'/distribute-players-modal/{EVENT_ID}',
        params={'tab': opened_from} if opened_from is not None else {},
    )
    assert response.status_code == 200
    assert f'name="tab" value="{carried}"' in response.text


@pytest.mark.unit
def test_the_players_are_distributed_and_the_first_tab_comes_back(
    http: TestClient, event: Event
):
    before = player_count_by_tournament_id(event)
    assert before[event.sorted_tournaments[0].id]

    assert distribute(http, event, 'players') == f'/event/{EVENT_ID}/players'

    after = player_count_by_tournament_id(EVENT.load())
    assert after[event.sorted_tournaments[0].id] == 0
    assert after[event.sorted_tournaments[1].id] == sum(before.values())


@pytest.mark.unit
def test_a_tab_naming_no_page_falls_back_to_the_tournaments(
    http: TestClient, event: Event
):
    """The tab names the page to come back to, and the players have been
    moved by the time it is read: a value no page answers to would fail
    the request after the fact."""
    assert distribute(http, event, 'no-such-tab') == f'/event/{EVENT_ID}/tournaments'
