"""The complementary pairings of a round, generated over HTTP."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.journal import JournalAction, load_journal
from data.tournament import Tournament
from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-partial-pairing-http'
TOURNAMENT_NAME = 'test-partial-pairing-http-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament(http: TestClient) -> Iterator[Tournament]:
    """Round 1 paired, then one of its games unpaired."""
    EVENT.create(json_file='tec-swiss-unpaired')
    tournament = EVENT.tournament()
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/1')
    board = next(
        board
        for board in EVENT.tournament().get_round_boards(1)
        if board.black_player_id is not None
    )
    http.delete(f'/pairing/unpair/{EVENT_ID}/{tournament.id}/1/{board.id}?confirmed=1')
    yield EVENT.tournament()
    EVENT.delete()


@pytest.mark.unit
def test_the_complementary_pairings_are_generated_and_journaled(
    http: TestClient, tournament: Tournament
):
    response = http.post(
        f'/pairings/generate-partial/{EVENT_ID}/{tournament.id}/1',
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert not any(
        player.pairings[1].needs_pairing
        for player in EVENT.tournament().tournament_players
    )
    assert [
        entry
        for entry in load_journal(EVENT_ID)
        if entry.action == JournalAction.ROUND_PAIRED
        and entry.stored.data.get('partial')
    ]
