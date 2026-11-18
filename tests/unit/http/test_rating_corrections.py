"""Correcting, over HTTP, a game of a round older than the previous one for
the rating report only (C.04.2:4.3): the pairings and the standings keep the
game as recorded, the TRF and Papi exports give it as corrected."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.board import Board
from data.input_output.trf.trf_data import TrfGame, TrfTournament
from data.tournament import Tournament
from plugins.ffe.papi_converter import PapiConverter
from plugins.ffe.papi_mappers import PapiColor, PapiResult
from tests.unit.http.events import EventUnderTest
from utils.enum import Result

EVENT_ID = 'test-rating-corrections-http'
TOURNAMENT_NAME = 'test-rating-corrections-http-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


def play_round(http: TestClient, tournament: Tournament, round_: int) -> None:
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/{round_}')
    for board in EVENT.tournament().get_round_boards(round_):
        if board.black_player_id is not None:
            http.put(
                f'/pairing/set-result/{EVENT_ID}/{tournament.id}/{round_}'
                f'/{board.id}/{Result.WIN.value}'
            )


@pytest.fixture
def tournament(http: TestClient) -> Iterator[Tournament]:
    EVENT.create(json_file='tec-swiss-unpaired')
    tournament = EVENT.tournament()
    for round_ in (1, 2):
        play_round(http, tournament, round_)
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/3')
    yield EVENT.tournament()
    EVENT.delete()


def first_game(tournament: Tournament, round_: int = 1) -> Board:
    return next(
        board
        for board in sorted(tournament.get_round_boards(round_), key=lambda b: b.index)
        if board.black_player_id is not None
    )


def correct(
    http: TestClient,
    tournament: Tournament,
    board: Board,
    white_player_id: int,
    result: Result,
    round_: int = 1,
) -> int:
    return http.put(
        f'/pairing/rating-correction/{EVENT_ID}/{tournament.id}/{round_}'
        f'/{board.id}/{white_player_id}/{result.value}'
    ).status_code


def trf_game(trf: TrfTournament, pairing_number: int | None, round_: int) -> TrfGame:
    player = next(player for player in trf.players if player.id == pairing_number)
    return next(game for game in player.games if game.round == round_)


@pytest.mark.unit
def test_the_rating_report_gives_the_corrected_result(
    http: TestClient, tournament: Tournament
):
    board = first_game(tournament)
    white = board.optional_white_tournament_player
    assert white is not None and board.white_player_id is not None

    assert correct(http, tournament, board, board.white_player_id, Result.DRAW) == 200

    tournament = EVENT.tournament()
    rating_report = tournament.to_trf(rating_report=True)
    assert trf_game(rating_report, white.pairing_number, 1).result == '='
    assert trf_game(tournament.to_trf(), white.pairing_number, 1).result == '1'
    assert tournament.boards_by_id[board.id].result == Result.WIN
    points = next(p for p in rating_report.players if p.id == white.pairing_number)
    assert points.points == white.points_after(3)


@pytest.mark.unit
def test_the_rating_report_gives_the_corrected_colours(
    http: TestClient, tournament: Tournament
):
    board = first_game(tournament)
    white = board.optional_white_tournament_player
    black = board.black_tournament_player
    assert white is not None and black is not None and black.id is not None

    correct(http, tournament, board, black.id, Result.WIN)

    rating_report = EVENT.tournament().to_trf(rating_report=True)
    assert trf_game(rating_report, black.pairing_number, 1).color == 'w'
    assert trf_game(rating_report, black.pairing_number, 1).result == '1'
    assert trf_game(rating_report, white.pairing_number, 1).color == 'b'
    assert trf_game(rating_report, white.pairing_number, 1).result == '0'


@pytest.mark.unit
def test_the_rating_report_says_what_the_pairings_used(
    http: TestClient, tournament: Tournament
):
    board = first_game(tournament)
    white = board.optional_white_tournament_player
    black = board.black_tournament_player
    assert white is not None and black is not None and white.id is not None

    correct(http, tournament, board, white.id, Result.LOSS)

    tournament = EVENT.tournament()
    game = f'{white.pairing_number}-{black.pairing_number}'
    assert tournament.to_trf(rating_report=True).log_comments == [
        f'Rating correction @ Round 1: {game} recorded as 0-1 for rating, '
        '1-0 used for pairings and standings'
    ]
    assert tournament.to_trf().log_comments == []
    assert [entry.round_ for entry in tournament.log_entries] == [1]


@pytest.mark.unit
def test_correcting_back_to_the_recorded_game_removes_the_correction(
    http: TestClient, tournament: Tournament
):
    board = first_game(tournament)
    assert board.white_player_id is not None
    correct(http, tournament, board, board.white_player_id, Result.DRAW)

    correct(http, EVENT.tournament(), board, board.white_player_id, Result.WIN)

    assert EVENT.tournament().rating_corrections == []


@pytest.mark.unit
def test_a_correction_is_removed(http: TestClient, tournament: Tournament):
    board = first_game(tournament)
    assert board.white_player_id is not None
    correct(http, tournament, board, board.white_player_id, Result.DRAW)

    http.delete(f'/pairing/rating-correction/{EVENT_ID}/{tournament.id}/1/{board.id}')

    assert EVENT.tournament().rating_corrections == []


@pytest.mark.unit
def test_the_previous_round_is_not_corrected_for_the_rating_only(
    http: TestClient, tournament: Tournament
):
    board = first_game(tournament, 2)
    assert board.white_player_id is not None

    correct(http, tournament, board, board.white_player_id, Result.DRAW, round_=2)

    assert EVENT.tournament().rating_corrections == []


@pytest.mark.unit
def test_the_papi_export_gives_the_corrected_game(
    http: TestClient, tournament: Tournament
):
    board = first_game(tournament)
    white = board.optional_white_tournament_player
    black = board.black_tournament_player
    assert white is not None and black is not None and black.id is not None

    correct(http, tournament, board, black.id, Result.DRAW)

    papi_data = PapiConverter().tournament_to_papi_data(EVENT.tournament())
    by_name = {player.lastName: player for player in papi_data.players}
    assert by_name[black.last_name].rounds[1].color == PapiColor.WHITE
    assert by_name[black.last_name].rounds[1].result == PapiResult.DRAW_OR_HPB
    assert by_name[white.last_name].rounds[1].color == PapiColor.BLACK


@pytest.mark.unit
def test_the_rating_report_says_which_colours_the_pairings_used(
    http: TestClient, tournament: Tournament
):
    board = first_game(tournament)
    white = board.optional_white_tournament_player
    black = board.black_tournament_player
    assert white is not None and black is not None and black.id is not None

    correct(http, tournament, board, black.id, Result.DRAW)

    assert EVENT.tournament().to_trf(rating_report=True).log_comments == [
        f'Rating correction @ Round 1: {black.pairing_number}-{white.pairing_number} '
        '1/2-1/2 recorded for rating, '
        f'{white.pairing_number}-{black.pairing_number} 1-0 used for pairings '
        'and standings'
    ]
