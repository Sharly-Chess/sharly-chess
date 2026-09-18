"""Pairing a round, entering a result and undoing both, over HTTP."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.tournament import Tournament
from tests.unit.http.events import EventUnderTest
from utils.enum import Result

EVENT_ID = 'test-pairings-http'
TOURNAMENT_NAME = 'test-pairings-http-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament() -> Iterator[Tournament]:
    EVENT.create(json_file='tec-swiss-unpaired')
    yield EVENT.tournament()
    EVENT.delete()


@pytest.mark.unit
def test_pairing_a_round_seats_every_player(http: TestClient, tournament: Tournament):
    assert not tournament.get_round_boards(1)
    response = http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/1')
    assert response.status_code == 200
    boards = EVENT.tournament().get_round_boards(1)
    seated = [
        player_id
        for board in boards
        for player_id in (board.white_player_id, board.black_player_id)
        if player_id
    ]
    # Nobody sits at two boards, and a board seats two players unless the
    # odd player out takes the bye.
    assert len(seated) == len(set(seated))
    assert set(seated) <= {player.id for player in tournament.tournament_players}
    assert len(boards) == (len(seated) + 1) // 2


@pytest.mark.unit
def test_unpairing_the_round_empties_it(http: TestClient, tournament: Tournament):
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/1')
    response = http.post(f'/pairings/unpair/{EVENT_ID}/{tournament.id}/1')
    assert response.status_code == 200
    assert not EVENT.tournament().get_round_boards(1)


@pytest.mark.unit
def test_a_result_is_recorded_for_both_players(
    http: TestClient, tournament: Tournament
):
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/1')
    board = EVENT.tournament().get_round_boards(1)[0]
    response = http.put(
        f'/pairing/set-result/{EVENT_ID}/{tournament.id}/1/{board.id}'
        f'/{Result.WIN.value}'
    )
    assert response.status_code == 200
    played = next(
        board_
        for board_ in EVENT.tournament().get_round_boards(1)
        if board_.id == board.id
    )
    assert played.white_pairing.result == Result.WIN
    assert played.black_pairing.result == Result.LOSS


@pytest.mark.unit
def test_a_board_of_another_round_is_refused(http: TestClient, tournament: Tournament):
    """The board id travels in the URL with the round beside it. A result
    sent for a round that does not hold the board reaches neither: the
    board keeps the result it had, and the other round stays unpaired."""
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/1')
    board = EVENT.tournament().get_round_boards(1)[0]
    response = http.put(
        f'/pairing/set-result/{EVENT_ID}/{tournament.id}/2/{board.id}'
        f'/{Result.WIN.value}'
    )
    assert response.status_code < 500
    played = next(
        board_
        for board_ in EVENT.tournament().get_round_boards(1)
        if board_.id == board.id
    )
    assert played.white_pairing.result == Result.NO_RESULT
    assert not EVENT.tournament().get_round_boards(2)


def board_of_round_one(http: TestClient, tournament: Tournament):
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/1')
    return EVENT.tournament().get_round_boards(1)[0]


@pytest.mark.unit
def test_permuting_a_board_turns_it_round(http: TestClient, tournament: Tournament):
    """The arbiter swaps the colours of a board the engine sat the wrong
    way round for the players in front of them."""
    board = board_of_round_one(http, tournament)
    white, black = board.white_player_id, board.black_player_id
    response = http.patch(f'/pairing/permute/{EVENT_ID}/{tournament.id}/1/{board.id}')
    assert response.status_code == 200
    turned = next(b for b in EVENT.tournament().get_round_boards(1) if b.id == board.id)
    assert (turned.white_player_id, turned.black_player_id) == (black, white)


@pytest.mark.unit
def test_a_hotkey_enters_a_draw(http: TestClient, tournament: Tournament):
    """Results are entered from the keyboard, a digit per outcome."""
    board = board_of_round_one(http, tournament)
    response = http.put(
        f'/pairing/set-result-hotkey/{EVENT_ID}/{tournament.id}/1',
        data={
            'board_id': str(board.id),
            'key': 'Digit3',
            'validate_result': 'false',
        },
    )
    assert response.status_code == 200
    played = next(b for b in EVENT.tournament().get_round_boards(1) if b.id == board.id)
    assert played.white_pairing.result == Result.DRAW
    assert played.black_pairing.result == Result.DRAW


@pytest.mark.unit
def test_a_key_that_means_nothing_enters_nothing(
    http: TestClient, tournament: Tournament
):
    """Every keystroke on the pairings page reaches the handler, not only
    the four that mean something."""
    board = board_of_round_one(http, tournament)
    response = http.put(
        f'/pairing/set-result-hotkey/{EVENT_ID}/{tournament.id}/1',
        data={'board_id': str(board.id), 'key': 'KeyQ', 'validate_result': 'false'},
    )
    assert response.status_code == 200
    untouched = next(
        b for b in EVENT.tournament().get_round_boards(1) if b.id == board.id
    )
    assert untouched.white_pairing.result == Result.NO_RESULT


@pytest.mark.unit
def test_a_player_is_given_bonus_points(http: TestClient, tournament: Tournament):
    board = board_of_round_one(http, tournament)
    player_id = board.white_player_id
    response = http.patch(
        f'/player-point-adjustment/{EVENT_ID}/{tournament.id}/1/{player_id}',
        data={'delta': '0.5', 'reason': 'Arrived to a broken clock'},
    )
    assert response.status_code == 200
    assert EVENT.tournament().player_point_adjustment_total(player_id, 1) == 0.5


@pytest.mark.unit
def test_an_adjustment_the_trf_cannot_carry_is_refused(
    http: TestClient, tournament: Tournament
):
    """The TRF's field holds one figure either side of the point, so the
    adjustment the arbiter types has to fit in it."""
    board = board_of_round_one(http, tournament)
    player_id = board.white_player_id
    response = http.patch(
        f'/player-point-adjustment/{EVENT_ID}/{tournament.id}/1/{player_id}',
        data={'delta': '100', 'reason': ''},
    )
    assert response.status_code == 200
    assert EVENT.tournament().player_point_adjustment_total(player_id, 1) == 0.0


@pytest.mark.unit
def test_an_adjustment_for_a_player_who_is_not_there_is_not_found(
    http: TestClient, tournament: Tournament
):
    response = http.get(
        f'/player-point-adjustment/{EVENT_ID}/{tournament.id}/1/9999',
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers['location'].endswith('/error/404')


@pytest.mark.unit
def test_a_second_entry_that_disagrees_is_not_taken(
    http: TestClient, tournament: Tournament
):
    """Results are entered twice and the second pass checks the first
    rather than overwriting it, so a disagreement is shown rather than
    silently kept."""
    board = board_of_round_one(http, tournament)
    entered = {
        'board_id': str(board.id),
        'key': 'Digit3',
        'validate_result': 'false',
    }
    assert (
        http.put(
            f'/pairing/set-result-hotkey/{EVENT_ID}/{tournament.id}/1', data=entered
        ).status_code
        == 200
    )
    response = http.put(
        f'/pairing/set-result-hotkey/{EVENT_ID}/{tournament.id}/1',
        data=entered | {'key': 'Digit1', 'validate_result': 'true'},
    )
    assert response.status_code == 200
    assert 'highlight-warning' in response.text
    checked = next(
        b for b in EVENT.tournament().get_round_boards(1) if b.id == board.id
    )
    assert checked.white_pairing.result == Result.DRAW


@pytest.mark.unit
@pytest.mark.parametrize(
    'modal',
    [
        'unfinished-round-modal',
        'set-current-round-modal',
        'ratings-warning-modal',
        'absents-modal',
        'settings-modal',
    ],
)
def test_every_pairing_modal_opens(
    http: TestClient, tournament: Tournament, modal: str
):
    """Each one is opened from the pairings tab before a round is
    generated, and each one reads the round it is about."""
    response = http.get(f'/pairings/{modal}/{EVENT_ID}/{tournament.id}/1')
    assert response.status_code == 200


def checked_in(player_id: int) -> bool:
    return next(
        player
        for player in EVENT.tournament().tournament_players
        if player.id == player_id
    ).check_in


@pytest.mark.unit
def test_the_check_in_button_marks_a_player_present_and_absent(
    http: TestClient, tournament: Tournament
):
    """One button, both ways: it reads the player's state rather than
    taking one from the page."""
    player_id = sorted(tournament.tournament_players, key=lambda p: p.id)[0].id
    before = checked_in(player_id)
    url = f'/player-table/check-in-player/{EVENT_ID}/{player_id}'
    assert http.patch(url).status_code == 200
    assert checked_in(player_id) is not before
    assert http.patch(url).status_code == 200
    assert checked_in(player_id) is before


@pytest.mark.unit
def test_marking_everyone_present_leaves_nobody_out(
    http: TestClient, tournament: Tournament
):
    """A player left unchecked is left out of the pairing, so this is the
    button that gets a round paired for the whole entry list."""
    player_id = sorted(tournament.tournament_players, key=lambda p: p.id)[0].id
    if checked_in(player_id):
        http.patch(f'/player-table/check-in-player/{EVENT_ID}/{player_id}')
    assert not checked_in(player_id)

    response = http.post(f'/pairings/set-all-present/{EVENT_ID}/{tournament.id}/1')
    assert response.status_code == 200
    assert all(player.check_in for player in EVENT.tournament().tournament_players)


@pytest.mark.unit
def test_unpairing_the_tournament_empties_every_round(
    http: TestClient, tournament: Tournament
):
    """Undoing one round at a time is the slow way out of a tournament
    paired from the wrong entry list."""
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/1')
    assert EVENT.tournament().get_round_boards(1)
    response = http.post(f'/pairings/unpair-tournament/{EVENT_ID}/{tournament.id}')
    assert response.status_code == 200
    paired = EVENT.tournament()
    assert not any(
        paired.get_round_boards(round_) for round_ in range(1, paired.rounds + 1)
    )
