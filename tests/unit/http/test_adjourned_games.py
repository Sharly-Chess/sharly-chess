"""Adjourned games over HTTP, in FIDE mode: they count as draws for the
pairings and the standings, take their result at any time, and a result
other than a draw entered once the next round is paired is logged."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from litestar.testing import TestClient

from data.board import Board
from data.input_output.tournament_exporters import Trf26TournamentExporter
from data.input_output.tournament_importer_options import FileOption
from data.input_output.trf.trf_data import TrfGame, TrfTournament
from data.input_output.trf.trf_importer import TrfTournamentImporter
from data.input_output.trf.trf_serializer import TrfSerializer
from data.pibes import PibeType
from data.tournament import Tournament
from tests.unit.http.events import EventUnderTest
from utils.enum import Result

EVENT_ID = 'test-adjourned-games-http'
TOURNAMENT_NAME = 'test-adjourned-games-http-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


def games(tournament: Tournament, round_: int) -> list[Board]:
    return [
        board
        for board in sorted(tournament.get_round_boards(round_), key=lambda b: b.index)
        if board.black_player_id is not None
    ]


def set_result(
    http: TestClient,
    tournament: Tournament,
    board: Board,
    result: Result,
    round_: int = 1,
    confirmed: bool = False,
) -> str:
    response = http.put(
        f'/pairing/set-result/{EVENT_ID}/{tournament.id}/{round_}'
        f'/{board.id}/{result.value}' + ('?confirmed=1' if confirmed else '')
    )
    assert response.status_code == 200
    return response.text


def pair(http: TestClient, tournament: Tournament, round_: int) -> str:
    response = http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/{round_}')
    assert response.status_code == 200
    return response.text


def finish_round(http: TestClient, tournament: Tournament, round_: int) -> None:
    for board in games(EVENT.tournament(), round_):
        if board.no_result:
            set_result(http, tournament, board, Result.WIN, round_)


def trf_game(trf: TrfTournament, pairing_number: int | None, round_: int) -> TrfGame:
    player = next(player for player in trf.players if player.id == pairing_number)
    return next(game for game in player.games if game.round == round_)


@pytest.fixture
def tournament(http: TestClient) -> Iterator[Tournament]:
    """Round 1 played, its first game adjourned."""
    EVENT.create(json_file='tec-swiss-unpaired')
    tournament = EVENT.tournament()
    pair(http, tournament, 1)
    set_result(http, tournament, games(EVENT.tournament(), 1)[0], Result.ADJOURNED)
    finish_round(http, tournament, 1)
    yield EVENT.tournament()
    EVENT.delete()


@pytest.fixture
def adjourned(tournament: Tournament) -> Board:
    return games(tournament, 1)[0]


@pytest.mark.unit
def test_an_adjourned_game_counts_as_a_draw(tournament: Tournament, adjourned: Board):
    white = adjourned.optional_white_tournament_player
    black = adjourned.black_tournament_player
    assert white is not None and black is not None

    assert adjourned.result == Result.ADJOURNED
    assert white.points_after(1) == 0.5
    assert black.points_after(1) == 0.5
    assert tournament.is_round_finished(1)


@pytest.mark.unit
def test_pairing_with_an_adjourned_game_gives_a_notice(
    http: TestClient, tournament: Tournament
):
    page = pair(http, tournament, 2)

    assert games(EVENT.tournament(), 2)
    assert 'adjourned game counting as a draw' in page


@pytest.mark.unit
def test_the_pairing_engine_reads_a_draw(tournament: Tournament, adjourned: Board):
    white = adjourned.optional_white_tournament_player
    assert white is not None

    trf = tournament.to_trf(after_round=1, for_engine=True)

    assert trf_game(trf, white.pairing_number, 1).result == '='
    assert 'X' not in trf.individuals_point_system


@pytest.mark.unit
def test_the_trf_gives_an_unknown_result(tournament: Tournament, adjourned: Board):
    white = adjourned.optional_white_tournament_player
    assert white is not None

    trf = tournament.to_trf(after_round=1)

    assert trf_game(trf, white.pairing_number, 1).result == '?'
    assert trf.individuals_point_system['X'] == 0.5


@pytest.mark.unit
def test_an_unplayed_game_beside_an_adjourned_one_counts_as_a_draw_in_the_trf(
    http: TestClient, tournament: Tournament
):
    pair(http, tournament, 2)
    tournament = EVENT.tournament()
    unplayed = games(tournament, 2)[-1]
    white = unplayed.optional_white_tournament_player
    assert white is not None

    trf = tournament.to_trf()

    assert trf_game(trf, white.pairing_number, 2).result == '?'
    trf_player = next(p for p in trf.players if p.id == white.pairing_number)
    assert trf_player.points == white.points_after(2) + 0.5


@pytest.mark.unit
def test_a_draw_entered_later_is_not_logged(
    http: TestClient, tournament: Tournament, adjourned: Board
):
    pair(http, tournament, 2)

    set_result(http, tournament, adjourned, Result.DRAW)

    tournament = EVENT.tournament()
    assert tournament.boards_by_id[adjourned.id].result == Result.DRAW
    assert not tournament.pibes


@pytest.mark.unit
def test_a_result_entered_before_the_next_round_is_not_logged(
    http: TestClient, tournament: Tournament, adjourned: Board
):
    set_result(http, tournament, adjourned, Result.WIN)

    tournament = EVENT.tournament()
    assert tournament.boards_by_id[adjourned.id].result == Result.WIN
    assert not tournament.pibes


@pytest.mark.unit
def test_another_result_entered_later_asks_for_confirmation(
    http: TestClient, tournament: Tournament, adjourned: Board
):
    pair(http, tournament, 2)

    page = set_result(http, tournament, adjourned, Result.WIN)

    assert 'breaches the integrity of the pairings' in page
    assert EVENT.tournament().boards_by_id[adjourned.id].result == Result.ADJOURNED


@pytest.mark.unit
def test_another_result_entered_later_is_logged(
    http: TestClient, tournament: Tournament, adjourned: Board
):
    white = adjourned.optional_white_tournament_player
    black = adjourned.black_tournament_player
    assert white is not None and black is not None
    pair(http, tournament, 2)

    set_result(http, tournament, adjourned, Result.WIN, confirmed=True)

    tournament = EVENT.tournament()
    assert tournament.boards_by_id[adjourned.id].result == Result.WIN
    assert [pibe.type for pibe in tournament.pibes] == [PibeType.ADJOURNMENT]
    assert tournament.to_trf().log_comments == [
        f'Adjournment @ Round 1: {white.pairing_number}-{black.pairing_number} 1-0'
    ]


@pytest.mark.unit
def test_the_result_is_entered_rounds_later_in_fide_mode(
    http: TestClient, tournament: Tournament, adjourned: Board
):
    for round_ in (2, 3):
        pair(http, tournament, round_)
        finish_round(http, tournament, round_)
    pair(http, tournament, 4)

    set_result(http, tournament, adjourned, Result.DRAW)

    tournament = EVENT.tournament()
    assert tournament.fide_mode
    assert tournament.boards_by_id[adjourned.id].result == Result.DRAW


@pytest.mark.unit
def test_the_trf_is_partial_until_the_adjourned_games_have_a_result(
    http: TestClient, tournament: Tournament, adjourned: Board
):
    exporter = Trf26TournamentExporter()
    for round_ in range(2, tournament.rounds + 1):
        pair(http, tournament, round_)
        finish_round(http, tournament, round_)

    assert not exporter.is_final(EVENT.tournament())
    assert exporter.label(EVENT.tournament()) == 'TRF26 (ITDX)'

    set_result(http, tournament, adjourned, Result.DRAW)

    assert exporter.is_final(EVENT.tournament())
    assert exporter.label(EVENT.tournament()) == 'TRF26 (final)'


def import_trf(tmp_path: Path, trf: TrfTournament) -> Tournament:
    trf_path = tmp_path / 'adjourned.trf'
    trf_path.write_text(TrfSerializer.dumps(trf), encoding='ascii')
    tournament_id = TrfTournamentImporter([FileOption(trf_path)]).load_tournament(
        EVENT.load()
    )
    return EVENT.load().tournaments_by_id[tournament_id]


@pytest.mark.unit
def test_an_adjourned_game_is_imported(
    tmp_path: Path, tournament: Tournament, adjourned: Board
):
    white = adjourned.optional_white_tournament_player
    assert white is not None

    imported = import_trf(tmp_path, tournament.to_trf(after_round=1))

    assert white.pairing_number is not None
    player = imported.tournament_players_by_pairing_number[white.pairing_number]
    assert player.pairings[1].result == Result.ADJOURNED


@pytest.mark.unit
def test_an_unknown_symbol_is_imported_as_an_adjourned_game(
    tmp_path: Path, tournament: Tournament, adjourned: Board
):
    white = adjourned.optional_white_tournament_player
    black = adjourned.black_tournament_player
    assert white is not None and black is not None
    trf = tournament.to_trf(after_round=1)
    for pairing_number in (white.pairing_number, black.pairing_number):
        trf_game(trf, pairing_number, 1).result = 'c'

    imported = import_trf(tmp_path, trf)

    assert black.pairing_number is not None
    player = imported.tournament_players_by_pairing_number[black.pairing_number]
    assert player.pairings[1].result == Result.ADJOURNED


@pytest.mark.unit
def test_an_unknown_result_worth_nothing_is_a_game_not_played_yet(
    tmp_path: Path, tournament: Tournament, adjourned: Board
):
    white = adjourned.optional_white_tournament_player
    assert white is not None
    trf = tournament.to_trf(after_round=1)
    trf.individuals_point_system['X'] = 0.0

    imported = import_trf(tmp_path, trf)

    assert white.pairing_number is not None
    player = imported.tournament_players_by_pairing_number[white.pairing_number]
    assert player.pairings[1].result == Result.NO_RESULT


@pytest.mark.unit
def test_the_pairing_modal_offers_to_adjourn(http: TestClient, tournament: Tournament):
    board = games(tournament, 1)[1]

    response = http.get(
        f'/event/{EVENT_ID}/pairing/{tournament.id}/1/{board.id}',
        headers={'HX-Request': 'true'},
    )

    assert response.status_code == 200
    assert 'Adjourned' in response.text
