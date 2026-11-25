"""The round-robin pairings document: every round printed as a pairing
table in the style of the per-round pairings, with the table numbers."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.loader import EventLoader
from data.pairings.round_robin_editor import RoundRobinScheduleEditor
from data.pairings.variations import CustomRoundRobinVariation
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredPlayer
from tests.test_config import TestUtils

EVENT_ID = 'test-round-robin-schedule-document-http'
TOURNAMENT_NAME = 'test-round-robin-schedule-document-http-tournament'


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
    yield event.tournaments_by_name[TOURNAMENT_NAME]
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_the_document_prints_every_round_with_its_table_numbers(
    http: TestClient, tournament: Tournament
):
    editor = RoundRobinScheduleEditor(tournament)
    assert editor.fill_from_berger_tables() is None
    assert editor.save() is None
    response = http.get(
        f'/document-view/{EVENT_ID}/round-robin-schedule',
        params={'options': f'tournament={tournament.id}'},
    )
    assert response.status_code == 200
    markup = response.text
    assert markup.count('class="section-title"') == 3
    assert markup.count('<td class="board">1</td>') == 3
    assert markup.count('<td class="board">2</td>') == 3
    assert 'PLAYER1' in markup
    assert '<td class="result">–</td>' in markup
