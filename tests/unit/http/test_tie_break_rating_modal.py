"""The tie-breaks modal asks which rating the tie-breaks read.

C.07:10 leaves the choice to the arbiter when a player may hold more
than one rating during the tournament, so the question is put where the
tie-breaks are configured — and only to a tournament that has slices.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils

EVENT_ID = 'test-tie-break-rating-modal'
TOURNAMENT_NAME = 'tournament'


def _create(multi_period: bool) -> int:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(
        EVENT_ID,
        TOURNAMENT_NAME,
        overrides={
            'rounds': 4,
            'multi_period': multi_period,
            'round_datetimes': {
                round_nb: datetime.now() + timedelta(days=14 * (round_nb - 4))
                for round_nb in range(1, 5)
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
        database.set_tournament_periods(tournament_id, [3])
    EventLoader.unload_event(EVENT_ID)
    return tournament_id


@pytest.fixture
def event() -> Iterator[str]:
    yield EVENT_ID
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


def _modal(http: TestClient, tournament_id: int) -> str:
    response = http.get(f'/tournaments/tie-breaks-modal/{EVENT_ID}/{tournament_id}')
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
def test_a_split_tournament_is_asked_which_rating_to_read(http: TestClient, event: str):
    modal = _modal(http, _create(multi_period=True))
    assert 'tie_break_rating' in modal
    assert 'First rating' in modal
    # Each slice on offer by name, plus the per-game choice.
    assert 'value="round"' in modal
    assert 'Rating read by rating-based tie-breaks' in modal
    # Its label keeps its own line, so picking a longer option does not
    # reshape the field.
    assert 'input-block-stacked' in modal
    assert 'Period 1 (R1' in modal and 'Period 2 (R3' in modal


@pytest.mark.unit
def test_a_tournament_rated_in_one_go_is_not_asked(http: TestClient, event: str):
    modal = _modal(http, _create(multi_period=False))
    assert 'tie_break_rating' not in modal
