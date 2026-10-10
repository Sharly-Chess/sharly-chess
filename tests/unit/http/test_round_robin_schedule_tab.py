"""The schedule of a round-robin, edited from the pairings tab: a custom
round-robin opens on it, and changing the variation of a tournament not
paired yet starts from the new variation's schedule."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.event import Event
from data.loader import EventLoader
from data.pairings.variations import (
    BergerRoundRobinVariation,
    CustomRoundRobinVariation,
)
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredPlayer
from tests.test_config import TestUtils

EVENT_ID = 'test-round-robin-schedule-http'
TOURNAMENT_NAME = 'test-round-robin-schedule-http-tournament'


_loaded_events: list[Event] = []


def load_tournament() -> Tournament:
    EventLoader.unload_event(EVENT_ID)
    event = EventLoader().load_event(EVENT_ID)
    # The tournament keeps only a weak reference to its event.
    _loaded_events[:] = [event]
    return event.tournaments_by_name[TOURNAMENT_NAME]


@pytest.fixture
def tournament() -> Iterator[Tournament]:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(
        EVENT_ID,
        TOURNAMENT_NAME,
        overrides={'pairing': CustomRoundRobinVariation.static_id()},
    )
    event = EventLoader().load_event(EVENT_ID)
    for index in range(4):
        event.add_player(
            StoredPlayer(id=None, last_name=f'Player{index + 1}'),
            [event.tournaments_by_name[TOURNAMENT_NAME]],
        )
    yield load_tournament()
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def pairings_tab(http: TestClient, tournament: Tournament) -> str:
    response = http.get(f'/event/{EVENT_ID}/pairings/{tournament.id}/1')
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
def test_a_custom_round_robin_opens_on_its_schedule(
    http: TestClient, tournament: Tournament
):
    page = pairings_tab(http, tournament)
    assert 'id="schedule-banner"' in page
    assert 'Pair tournament' not in page


@pytest.mark.unit
def test_changing_to_berger_leaves_the_schedule_being_edited(
    http: TestClient, tournament: Tournament
):
    player_id = sorted(player.id for player in tournament.tournament_players)[0]
    response = http.post(
        f'/pairings/schedule/place/{EVENT_ID}/{tournament.id}/1',
        data={'table': '0', 'side': '0', 'member': str(player_id)},
    )
    assert response.status_code == 200
    assert load_tournament().round_robin_schedule_draft is not None

    response = http.patch(
        f'/tournament-update/{EVENT_ID}/{tournament.id}',
        data={
            'name': TOURNAMENT_NAME,
            'rating': '1',
            'pairing_system': 'ROUND_ROBIN',
            'ROUND_ROBIN_pairing_variation': BergerRoundRobinVariation.static_id(),
            'fide_mode': 'on',
        },
    )
    assert response.status_code == 200
    updated = load_tournament()
    assert updated.pairing_variation.id == BergerRoundRobinVariation.static_id()
    assert updated.round_robin_schedule_draft is None
    assert updated.round_robin_schedule is None

    page = pairings_tab(http, updated)
    assert 'id="schedule-banner"' not in page
    assert 'Pair tournament' in page
