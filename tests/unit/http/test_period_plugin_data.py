"""A slice carries the identifiers of the registration it is submitted
under.

The FFE gives each "tranche" its own homologation number and password,
so the tournament form asks for one set per slice — under the plugin's
own field names, suffixed with the slice they belong to.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils
from utils.date_time import format_date_range, format_datetime

EVENT_ID = 'test-period-plugin-data'
TOURNAMENT_NAME = 'test-period-plugin-data-tournament'
ROUND_DATETIMES = {
    round_nb: datetime(2026, 11, 2, 14) + timedelta(days=10 * (round_nb - 1))
    for round_nb in range(1, 5)
}


@pytest.fixture
def event() -> Iterator[str]:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME, overrides={'rounds': 4})
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


def _periods(event: str):
    with EventDatabase(event) as database:
        return database.load_tournament_stored_periods(_tournament_id(event))


def _update(http: TestClient, event: str, **fields: str):
    return http.patch(
        f'/tournament-update/{event}/{_tournament_id(event)}',
        data={
            'name': TOURNAMENT_NAME,
            'rounds': '4',
            'pairing_system': 'SWISS',
            'SWISS_pairing_variation': 'SWISS_STANDARD',
            'date_range': format_date_range(
                datetime(2026, 11, 1).date(), datetime(2026, 12, 15).date()
            ),
        }
        | {
            f'round_{round_nb}_datetime': format_datetime(round_datetime)
            for round_nb, round_datetime in ROUND_DATETIMES.items()
        }
        | fields,
    )


@pytest.mark.unit
def test_the_form_asks_for_one_registration_per_slice(http: TestClient, event: str):
    _update(http, event, multi_period='on', round_3_period_start='on')
    second_period = _periods(event)[1]
    assert second_period.id is not None
    modal = http.get(f'/tournament-modal/update/{event}/{_tournament_id(event)}')
    assert modal.status_code == 200
    assert f'ffe_id_period_{second_period.id}' in modal.text
    assert f'ffe_password_period_{second_period.id}' in modal.text


@pytest.mark.unit
def test_a_slice_keeps_its_own_registration(http: TestClient, event: str):
    _update(http, event, multi_period='on', round_3_period_start='on')
    second_period = _periods(event)[1]
    assert second_period.id is not None

    _update(
        http,
        event,
        multi_period='on',
        round_3_period_start='on',
        **{
            f'ffe_id_period_{second_period.id}': '49944',
            f'ffe_password_period_{second_period.id}': 'ABCDEFGHIJ',
        },
    )
    stored = _periods(event)[1]
    assert stored.plugin_data['ffe']['ffe_id'] == 49944
    assert stored.plugin_data['ffe']['password'] == 'ABCDEFGHIJ'


@pytest.mark.unit
def test_the_tournament_keeps_its_own(http: TestClient, event: str):
    """The fields without a slice belong to the tournament, which is the
    first slice's registration — where the FFE publishes the whole
    tournament for the players."""
    _update(
        http,
        event,
        multi_period='on',
        round_3_period_start='on',
        ffe_id='49943',
        ffe_password='JIHGFEDCBA',
    )
    with EventDatabase(event) as database:
        stored_tournament = next(
            stored
            for stored in database.load_stored_tournaments()
            if stored.name == TOURNAMENT_NAME
        )
    assert stored_tournament.plugin_data['ffe']['ffe_id'] == 49943
    assert _periods(event)[1].plugin_data == {}
