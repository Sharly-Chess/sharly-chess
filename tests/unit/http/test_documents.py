"""The print documents, rendered in this process.

A document opens in a tab of its own, carrying the modal's choices in one
query parameter, and what those choices put in the markup is read here.
"""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-documents-http'
TOURNAMENT_NAME = 'test-documents-http-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament_id() -> Iterator[int]:
    EVENT.create(json_file='tec-swiss')
    tournament = EVENT.tournament()
    assert tournament.id is not None
    yield tournament.id
    EVENT.delete()


def crosstable(http: TestClient, tournament_id: int, **options: str) -> str:
    query = '|'.join(
        f'{key}={value}'
        for key, value in ({'tournament': str(tournament_id)} | options).items()
    )
    response = http.get(
        f'/document-view/{EVENT_ID}/crosstable', params={'options': query}
    )
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
def test_the_crosstable_names_its_players(http: TestClient, tournament_id: int):
    assert 'ALYX' in crosstable(http, tournament_id)


@pytest.mark.unit
@pytest.mark.parametrize(
    ('option', 'included'), [({}, False), ({'player-history': 'on'}, True)]
)
def test_the_crosstable_carries_a_history_per_player_on_request(
    http: TestClient, tournament_id: int, option: dict[str, str], included: bool
):
    markup = crosstable(http, tournament_id, **option)
    assert ('class="player-history"' in markup) is included
