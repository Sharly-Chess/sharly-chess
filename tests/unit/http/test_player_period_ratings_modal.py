"""The player modal shows what the earlier slices were played on.

A tournament reported in slices keeps one set of ratings per slice. The
form edits the slice being played; the ones before it are listed below,
since the reports already made of them were built from those values.
"""

from collections.abc import Iterator
from datetime import date, datetime, timedelta

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import TournamentRating

EVENT_ID = 'test-period-ratings-modal'
TOURNAMENT_NAME = 'tournament'
PLAYER_NAME = 'PLAYER'


def _create(multi_period: bool) -> int:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(
        EVENT_ID,
        TOURNAMENT_NAME,
        overrides={
            'rounds': 6,
            'multi_period': multi_period,
            # Under way: the last slice is the one being played, so the
            # ones before it are what the modal has to show.
            'round_datetimes': {
                round_nb: datetime.combine(date.today(), datetime.min.time())
                + timedelta(days=14 * (round_nb - 1) - 70, hours=14)
                for round_nb in range(1, 7)
            },
        },
    )
    with EventDatabase(EVENT_ID, write=True) as database:
        tournament_id = next(
            stored.id
            for stored in database.load_stored_tournaments()
            if stored.name == TOURNAMENT_NAME
        )
        assert tournament_id is not None
        player_id = database.add_stored_player(
            StoredPlayer(
                id=None,
                last_name=PLAYER_NAME,
                ratings={
                    TournamentRating.STANDARD.value: {
                        'fide': 1500,
                        'national': 1480,
                        'estimated': 1450,
                        'k': 20,
                    }
                },
            )
        )
        database.add_stored_tournament_player(
            StoredTournamentPlayer(tournament_id=tournament_id, player_id=player_id)
        )
        database.set_tournament_periods(tournament_id, [3, 5])
    EventLoader.unload_event(EVENT_ID)
    return player_id


@pytest.fixture
def event() -> Iterator[str]:
    yield EVENT_ID
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def _modal(http: TestClient, player_id: int) -> str:
    response = http.get(f'/player-modal/update/{EVENT_ID}/{player_id}')
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
def test_a_split_tournament_lists_the_earlier_periods(http: TestClient, event: str):
    player_id = _create(multi_period=True)
    modal = _modal(http, player_id)
    assert 'Ratings of the earlier periods' in modal
    # Every rating the player holds, as the slice was played on them.
    assert '1500' in modal and '1480' in modal and '1450' in modal
    assert 'K20' in modal


@pytest.mark.unit
def test_a_tournament_rated_in_one_go_says_nothing_of_periods(
    http: TestClient, event: str
):
    player_id = _create(multi_period=False)
    modal = _modal(http, player_id)
    assert 'Ratings of the earlier periods' not in modal
