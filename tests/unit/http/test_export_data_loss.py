"""The warning shown before a tournament is exported to a format that loses
data, over HTTP."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from tests.test_config import TestUtils

EVENT_ID = 'test-export-data-loss-http'


@pytest.fixture
def tournament_id() -> Iterator[int]:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(EVENT_ID, 'tournament')
    with EventDatabase(EVENT_ID) as database:
        stored_id = database.load_stored_tournaments()[0].id
    assert stored_id is not None
    yield stored_id
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_the_sce_export_of_the_warning_opens_the_event_export_options(
    http: TestClient, tournament_id: int
) -> None:
    response = http.get(
        f'/tournament-export/data-loss-modal/{EVENT_ID}/{tournament_id}/trf-26'
    )
    assert response.status_code == 200
    assert f'hx-get="/event-export-modal/{EVENT_ID}"' in response.text
    assert f'data-export-url="/event-export/{EVENT_ID}"' not in response.text

    response = http.get(f'/event-export-modal/{EVENT_ID}')
    assert response.status_code == 200
    assert 'include_players' in response.text
