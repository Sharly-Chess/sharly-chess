"""Recording illegal moves from the board modal, over HTTP.

The pairings row shows how many illegal moves a player has; the count is
changed from the board's modal, which stays open between taps.
"""

import re
from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.board import Board
from data.tournament import Tournament
from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-illegal-moves-http'
TOURNAMENT_NAME = 'test-illegal-moves-http-tournament'
MAXIMUM = 2

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)

STEPPER_COUNT = re.compile(r'bi-flag pe-1"></i><span class="fw-bold">(\d+)</span>')


@pytest.fixture
def tournament() -> Iterator[Tournament]:
    EVENT.create(
        json_file='tec-swiss-unpaired',
        tournament={'record_illegal_moves': MAXIMUM},
    )
    yield EVENT.tournament()
    EVENT.delete()


@pytest.fixture
def board(http: TestClient, tournament: Tournament) -> Board:
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/1')
    return EVENT.tournament().get_round_boards(1)[0]


def white_illegal_moves(board: Board) -> int:
    fresh = next(b for b in EVENT.tournament().get_round_boards(1) if b.id == board.id)
    return fresh.white_pairing.illegal_moves


def add_url(tournament: Tournament, board: Board) -> str:
    return (
        f'/tournament/add-illegal-move/{EVENT_ID}/{tournament.id}/1'
        f'/{board.white_player_id}'
    )


def delete_url(tournament: Tournament, board: Board) -> str:
    return (
        f'/tournament/delete-illegal-move/{EVENT_ID}/{tournament.id}/1'
        f'/{board.white_player_id}'
    )


def stepper_counts(markup: str) -> list[int]:
    return [int(count) for count in STEPPER_COUNT.findall(markup)]


@pytest.mark.unit
def test_an_illegal_move_recorded_from_the_modal_keeps_it_open(
    http: TestClient, tournament: Tournament, board: Board
):
    """Called with the board it was opened for, the route answers with the
    modal again — retargeted at the modal wrapper, showing the new count —
    so the arbiter can tap once more without reopening it."""
    response = http.put(f'{add_url(tournament, board)}?board_id={board.id}')
    assert response.status_code == 200
    assert response.headers['hx-retarget'] == '#modal-wrapper'
    assert stepper_counts(response.text) == [1, 0]
    assert white_illegal_moves(board) == 1


@pytest.mark.unit
def test_the_page_behind_the_modal_is_refreshed_when_it_closes(
    http: TestClient, tournament: Tournament, board: Board
):
    """The row behind the modal shows the count too, and is only re-read once
    the modal closes."""
    response = http.put(f'{add_url(tournament, board)}?board_id={board.id}')
    assert 'requestRefresh()' in response.text


@pytest.mark.unit
def test_an_illegal_move_can_be_removed_from_the_modal(
    http: TestClient, tournament: Tournament, board: Board
):
    http.put(f'{add_url(tournament, board)}?board_id={board.id}')
    http.put(f'{add_url(tournament, board)}?board_id={board.id}')
    response = http.delete(f'{delete_url(tournament, board)}?board_id={board.id}')
    assert response.status_code == 200
    assert response.headers['hx-retarget'] == '#modal-wrapper'
    assert stepper_counts(response.text) == [1, 0]
    assert white_illegal_moves(board) == 1


@pytest.mark.unit
def test_the_count_stops_at_the_tournament_maximum(
    http: TestClient, tournament: Tournament, board: Board
):
    for _ in range(MAXIMUM):
        http.put(f'{add_url(tournament, board)}?board_id={board.id}')
    response = http.put(f'{add_url(tournament, board)}?board_id={board.id}')
    assert stepper_counts(response.text) == [MAXIMUM, 0]
    assert white_illegal_moves(board) == MAXIMUM


@pytest.mark.unit
def test_without_a_board_the_route_answers_with_the_pairings_page(
    http: TestClient, tournament: Tournament, board: Board
):
    """Called from anywhere but the modal, the whole tab is rendered again."""
    response = http.put(add_url(tournament, board))
    assert response.status_code == 200
    assert 'hx-retarget' not in response.headers
    assert 'id="pairings-table"' in response.text
    assert white_illegal_moves(board) == 1


@pytest.mark.unit
def test_the_row_shows_the_count_and_offers_no_control(
    http: TestClient, tournament: Tournament, board: Board
):
    """One flag per recorded move in the pairings row, and nothing to tap:
    the row reports, the modal edits."""
    http.put(add_url(tournament, board))
    http.put(add_url(tournament, board))
    response = http.get(f'/event/{EVENT_ID}/pairings/{tournament.id}/1')
    row = re.search(rf'<tr\s+id="pairing-row-{board.id}".*?</tr>', response.text, re.S)
    assert row is not None
    markup = row.group(0)
    assert markup.count('illegal-move-flag"') == 2
    assert 'add-illegal-move' not in markup
    assert 'delete-illegal-move' not in markup
