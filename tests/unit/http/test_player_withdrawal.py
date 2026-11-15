"""Withdrawing a player from the rest of the tournament and bringing them
back, from the record modal, over HTTP."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.player import TournamentPlayer
from data.tournament import Tournament
from tests.unit.http.events import EventUnderTest
from utils.enum import Result

EVENT_ID = 'test-player-withdrawal-http'
TOURNAMENT_NAME = 'test-player-withdrawal-http-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament(http: TestClient) -> Iterator[Tournament]:
    EVENT.create(json_file='tec-swiss-unpaired')
    tournament = EVENT.tournament()
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/1')
    yield EVENT.tournament()
    EVENT.delete()


def forfeited_player(http: TestClient, tournament: Tournament) -> TournamentPlayer:
    """Gives the white player of the first game of round 1 a forfeit loss."""
    board = next(
        board
        for board in sorted(tournament.get_round_boards(1), key=lambda b: b.index)
        if board.black_player_id is not None
    )
    http.put(
        f'/pairing/set-result/{EVENT_ID}/{tournament.id}/1/{board.identifier}'
        f'/{Result.FORFEIT_LOSS.value}'
    )
    return the_player(board.white_player_id)


def the_player(player_id: int | None) -> TournamentPlayer:
    return next(
        player
        for player in EVENT.tournament().tournament_players
        if player.id == player_id
    )


@pytest.mark.unit
def test_a_player_withdrawn_after_a_forfeit_can_return(
    http: TestClient, tournament: Tournament
):
    player = forfeited_player(http, tournament)

    records = http.patch(f'/records/withdraw-player/{EVENT_ID}/{player.id}')
    assert records.status_code == 200
    player = the_player(player.id)
    assert player.pairings[1].result == Result.FORFEIT_LOSS
    assert all(
        player.pairings[round_].result == Result.ZERO_POINT_BYE
        for round_ in range(2, tournament.rounds + 1)
    )
    assert player.has_withdrawn
    assert 'Return to tournament' in records.text
    assert 'Withdraw from tournament' not in records.text

    records = http.patch(f'/records/return-player/{EVENT_ID}/{player.id}')
    assert records.status_code == 200
    player = the_player(player.id)
    assert player.pairings[1].result == Result.FORFEIT_LOSS
    assert all(
        player.pairings[round_].unpaired for round_ in range(2, tournament.rounds + 1)
    )
    assert not player.has_withdrawn
    assert 'Withdraw from tournament' in records.text
