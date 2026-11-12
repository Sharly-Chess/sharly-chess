"""Results and illegal moves entered from an input screen, over HTTP.

Each write carries the value the screen showed when it was tapped: a write
built from what the screen no longer shows, or sent twice, does not apply.
"""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.board import Board
from data.tournament import Tournament
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.events import EventUnderTest
from utils.enum import Result

EVENT_ID = 'test-input-screen-writes-http'
TOURNAMENT_NAME = 'test-input-screen-writes-http-tournament'
SCREEN_ID = 'test-input-screen-writes-http-screen'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament(api: ApiClient, http: TestClient) -> Iterator[Tournament]:
    EVENT.create(
        json_file='tec-swiss-unpaired',
        tournament={'record_illegal_moves': 2},
    )
    tournament = EVENT.tournament()
    TestUtils.create_screen(
        api,
        EVENT_ID,
        SCREEN_ID,
        ScreenType.INPUT,
        {'init_set_tournament_id': tournament.id},
    )
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/1')
    http.put(f'/pairings/publish/{EVENT_ID}/{tournament.id}/1')
    yield EVENT.tournament()
    EVENT.delete()


@pytest.fixture
def board(tournament: Tournament) -> Board:
    return tournament.get_round_boards(1)[0]


def fresh(board: Board) -> Board:
    return next(b for b in EVENT.tournament().get_round_boards(1) if b.id == board.id)


def put_result(
    http: TestClient,
    tournament: Tournament,
    board: Board,
    result: Result,
    shown: Result,
) -> str:
    response = http.put(
        f'/view/update-result/1/{EVENT_ID}/{SCREEN_ID}/{tournament.id}/1'
        f'/{board.identifier}/{result.value}?shown={shown.value}'
    )
    assert response.status_code == 200
    return response.text


def illegal_move_url(action: str, tournament: Tournament, board: Board) -> str:
    return (
        f'/view/{action}-illegal-move/1/{EVENT_ID}/{SCREEN_ID}/{tournament.id}'
        f'/{board.white_player_id}'
    )


@pytest.mark.unit
def test_the_result_window_sends_the_result_it_shows(
    http: TestClient, tournament: Tournament, board: Board
):
    put_result(http, tournament, board, Result.WIN, Result.NO_RESULT)
    response = http.get(
        f'/view/result-modal/1/{EVENT_ID}/{SCREEN_ID}/{tournament.id}/{board.identifier}'
    )
    assert f'?shown={Result.WIN.value}' in response.text


@pytest.mark.unit
def test_a_result_is_recorded_over_the_one_shown(
    http: TestClient, tournament: Tournament, board: Board
):
    put_result(http, tournament, board, Result.WIN, Result.NO_RESULT)
    put_result(http, tournament, board, Result.LOSS, Result.WIN)
    assert fresh(board).result == Result.LOSS


@pytest.mark.unit
def test_a_result_changed_since_the_window_opened_is_kept(
    http: TestClient, tournament: Tournament, board: Board
):
    """Another device entered 1-0 after this one opened its window on an empty
    board: this one's 0-1 is refused and its user told why."""
    put_result(http, tournament, board, Result.WIN, Result.NO_RESULT)
    markup = put_result(http, tournament, board, Result.LOSS, Result.NO_RESULT)
    assert fresh(board).result == Result.WIN
    assert 'hx-swap-oob' in markup
    assert 'nothing was recorded' in markup


@pytest.mark.unit
def test_a_result_sent_twice_is_recorded_once_without_a_warning(
    http: TestClient, tournament: Tournament, board: Board
):
    put_result(http, tournament, board, Result.DRAW, Result.NO_RESULT)
    markup = put_result(http, tournament, board, Result.DRAW, Result.NO_RESULT)
    assert fresh(board).result == Result.DRAW
    assert 'nothing was recorded' not in markup


@pytest.mark.unit
def test_an_illegal_move_sent_twice_is_counted_once(
    http: TestClient, tournament: Tournament, board: Board
):
    url = f'{illegal_move_url("add", tournament, board)}?shown=0'
    assert http.put(url).status_code == 200
    assert http.put(url).status_code == 200
    assert fresh(board).white_pairing.illegal_moves == 1


@pytest.mark.unit
def test_an_illegal_move_removal_sent_twice_removes_one(
    http: TestClient, tournament: Tournament, board: Board
):
    http.put(f'{illegal_move_url("add", tournament, board)}?shown=0')
    http.put(f'{illegal_move_url("add", tournament, board)}?shown=1')
    url = f'{illegal_move_url("delete", tournament, board)}?shown=2'
    assert http.delete(url).status_code == 200
    assert http.delete(url).status_code == 200
    assert fresh(board).white_pairing.illegal_moves == 1


@pytest.mark.unit
def test_the_illegal_move_flags_send_the_count_they_show(
    http: TestClient, tournament: Tournament, board: Board
):
    http.put(f'{illegal_move_url("add", tournament, board)}?shown=0')
    markup = http.get(f'/view/screen/{EVENT_ID}/{SCREEN_ID}').text
    assert f'{illegal_move_url("add", tournament, board)}?shown=1' in markup
    assert f'{illegal_move_url("delete", tournament, board)}?shown=1' in markup
