"""Editing the pairings of a round by hand in FIDE mode, over HTTP: the first
change starts the manual pairing, which is then validated against the
pairing engine or cancelled."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.board import Board
from data.pairings.manual_pairing import round_pairs
from data.pibes import PibeType
from data.tournament import Tournament
from tests.unit.http.events import EventUnderTest
from utils.enum import Result

EVENT_ID = 'test-manual-pairing-http'
TOURNAMENT_NAME = 'test-manual-pairing-http-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament(http: TestClient) -> Iterator[Tournament]:
    EVENT.create(json_file='tec-swiss-unpaired')
    tournament = EVENT.tournament()
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/1')
    yield EVENT.tournament()
    EVENT.delete()


def permute_first_board(
    http: TestClient, tournament: Tournament, skip: int = 0
) -> None:
    board = [
        board
        for board in sorted(tournament.get_round_boards(1), key=lambda b: b.index)
        if board.black_player_id is not None
    ][skip]
    response = http.patch(
        f'/pairing/permute/{EVENT_ID}/{tournament.id}/1/{board.id}?confirmed=1'
    )
    assert response.status_code == 200


@pytest.mark.unit
def test_a_change_starts_a_manual_pairing(http: TestClient, tournament: Tournament):
    permute_first_board(http, tournament)

    assert EVENT.tournament().manual_pairing_round == 1


def untouched_board(tournament: Tournament) -> Board:
    """A game of round 1 the tests leave as it was paired."""
    return [
        board
        for board in sorted(tournament.get_round_boards(1), key=lambda b: b.index)
        if board.black_player_id is not None
    ][-1]


@pytest.mark.unit
def test_results_are_entered_while_the_pairings_are_edited(
    http: TestClient, tournament: Tournament
):
    permute_first_board(http, tournament)
    board = untouched_board(EVENT.tournament())

    http.put(
        f'/pairing/set-result/{EVENT_ID}/{tournament.id}/1/{board.id}'
        f'/{Result.WIN.value}'
    )

    assert EVENT.tournament().boards_by_id[board.id].result == Result.WIN


@pytest.mark.unit
def test_cancelling_keeps_the_results_entered_meanwhile(
    http: TestClient, tournament: Tournament
):
    permute_first_board(http, tournament)
    board = untouched_board(EVENT.tournament())
    pair = (board.white_player_id, board.black_player_id)
    http.put(
        f'/pairing/set-result/{EVENT_ID}/{tournament.id}/1/{board.id}'
        f'/{Result.WIN.value}'
    )

    http.post(f'/pairings/cancel-manual-pairing/{EVENT_ID}/{tournament.id}/1')

    restored = next(
        board
        for board in EVENT.tournament().get_round_boards(1)
        if (board.white_player_id, board.black_player_id) == pair
    )
    assert restored.result == Result.WIN


@pytest.mark.unit
def test_different_pairings_are_confirmed_then_logged(
    http: TestClient, tournament: Tournament
):
    permute_first_board(http, tournament)
    route = f'/pairings/validate-manual-pairing/{EVENT_ID}/{tournament.id}/1'

    response = http.post(route)
    assert 'Validate anyway' in response.text
    assert EVENT.tournament().manual_pairing_round == 1

    http.post(f'{route}?confirmed=1')
    tournament = EVENT.tournament()
    assert tournament.manual_pairing_round is None
    assert [pibe.type for pibe in tournament.pibes] == [PibeType.MPA]


@pytest.mark.unit
def test_pairings_back_to_the_engine_s_validate_without_a_breach(
    http: TestClient, tournament: Tournament
):
    permute_first_board(http, tournament)
    permute_first_board(http, EVENT.tournament())

    http.post(f'/pairings/validate-manual-pairing/{EVENT_ID}/{tournament.id}/1')

    tournament = EVENT.tournament()
    assert tournament.manual_pairing_round is None
    assert tournament.pibes == []


@pytest.mark.unit
def test_cancelling_puts_the_pairings_back(http: TestClient, tournament: Tournament):
    paired = round_pairs(tournament, 1)
    permute_first_board(http, tournament)
    assert round_pairs(EVENT.tournament(), 1) != paired

    response = http.post(
        f'/pairings/cancel-manual-pairing/{EVENT_ID}/{tournament.id}/1'
    )

    assert response.status_code == 200
    tournament = EVENT.tournament()
    assert tournament.manual_pairing_round is None
    assert round_pairs(tournament, 1) == paired
    assert tournament.pibes == []


@pytest.mark.unit
def test_only_the_changes_of_the_manual_pairing_are_checked(
    http: TestClient, tournament: Tournament
):
    route = f'/pairings/validate-manual-pairing/{EVENT_ID}/{tournament.id}/1'
    permute_first_board(http, tournament)
    http.post(f'{route}?confirmed=1')
    permute_first_board(http, EVENT.tournament(), skip=1)

    http.post(f'{route}?confirmed=1')

    tournament = EVENT.tournament()
    second_board = [
        board
        for board in sorted(tournament.get_round_boards(1), key=lambda b: b.index)
        if board.black_player_id is not None
    ][1]
    white = second_board.white_tournament_player
    black = second_board.black_tournament_player
    assert black is not None
    last = tournament.pibes[-1]
    assert last.type == PibeType.MPA
    assert last.description == (
        f'{black.pairing_number}-{white.pairing_number} => '
        f'{white.pairing_number}-{black.pairing_number}'
    )


@pytest.mark.unit
def test_a_forfeit_winner_given_the_bye_is_warned(
    http: TestClient, tournament: Tournament
):
    boards = [
        board
        for board in tournament.get_round_boards(1)
        if board.black_player_id is not None
    ]
    for index, board in enumerate(boards):
        result = Result.FORFEIT_WIN if index == 0 else Result.WIN
        http.put(
            f'/pairing/set-result/{EVENT_ID}/{tournament.id}/1/{board.id}'
            f'/{result.value}'
        )
    winner_id = boards[0].white_player_id
    route = f'/pairings/pair-player/{EVENT_ID}/{tournament.id}/{winner_id}/2'

    response = http.patch(route)

    assert 'Pairing rules broken' in response.text
    assert not EVENT.tournament().round_has_pairings(2)

    http.patch(f'{route}?confirmed=1')

    assert EVENT.tournament().round_has_pairings(2)
