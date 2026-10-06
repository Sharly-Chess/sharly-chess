"""What the data-transfer screen offers for a slice.

A tranche is submitted under its own registration, so once that
registration is configured the screen offers to send it from the row
that reports it, as the tournament's own row does.
"""

import contextlib
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils

EVENT_ID = 'test-ffe-period-buttons'
TOURNAMENT_NAME = 'tournament'


def _create(configured: bool) -> int:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(
        EVENT_ID,
        TOURNAMENT_NAME,
        overrides={
            'rounds': 4,
            'multi_period': True,
            'round_datetimes': {
                round_nb: datetime.now() + timedelta(days=14 * (round_nb - 4))
                for round_nb in range(1, 5)
            },
            'plugin_data': {
                'ffe': {'ffe_id': 49943, 'password': 'AAAAAAAAAA'},
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
        second = database.load_tournament_stored_periods(tournament_id)[1]
        assert second.id is not None
        database.set_tournament_period_plugin_data(
            second.id,
            {'ffe': {'ffe_id': 49944, 'password': 'BBBBBBBBBB'} if configured else {}},
        )
    with contextlib.suppress(KeyError):
        EventLoader.unload_event(EVENT_ID)
    return tournament_id


@pytest.fixture
def event() -> Iterator[str]:
    yield EVENT_ID
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_a_configured_slice_offers_to_be_sent(http: TestClient, event: str):
    _create(configured=True)
    response = http.get(f'/ffe/upload-results/{event}')
    assert response.status_code == 200
    assert '/ffe/upload-modal/upload-period/' in response.text


@pytest.mark.unit
def test_a_slice_with_no_registration_offers_nothing(http: TestClient, event: str):
    _create(configured=False)
    response = http.get(f'/ffe/upload-results/{event}')
    assert response.status_code == 200
    assert '/ffe/upload-modal/upload-period/' not in response.text


@pytest.mark.unit
def test_sending_a_slice_answers_with_the_rows(http: TestClient, event: str):
    """The upload runs in a thread of its own and the rows come back at
    once, so the slice's own badge reports it as the tournament's does."""
    tournament_id = _create(configured=True)
    with EventDatabase(EVENT_ID) as database:
        period = database.load_tournament_stored_periods(tournament_id)[1]
    response = http.post(
        f'/ffe/upload-modal/upload-period/{event}/{tournament_id}/{period.id}'
    )
    assert response.status_code == 200
    assert 'id="upload-results"' in response.text
