"""In FIDE mode, taking games apart in the previous round is a manual
pairing too, and the pairings of only one round are edited at a time; a
pairing engine that cannot pair the round still lets the pairings be
validated, showing the ones changed by hand."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from common.exception import PairingEngineError
from data.board import Board
from data.pairings.engines import PairingEngine
from data.tournament import Tournament
from tests.unit.http.events import EventUnderTest
from utils.enum import Result

EVENT_ID = 'test-manual-pairing-rounds'
EVENT = EventUnderTest(EVENT_ID, 'test-manual-pairing-rounds-tournament')


def games(tournament: Tournament, round_: int) -> list[Board]:
    return [
        board
        for board in sorted(tournament.get_round_boards(round_), key=lambda b: b.index)
        if board.black_player_id is not None
    ]


@pytest.fixture
def tournament(http: TestClient) -> Iterator[Tournament]:
    """Rounds 1 and 2 played, round 3 paired."""
    EVENT.create(json_file='tec-swiss-unpaired')
    tournament_id = EVENT.tournament().id
    for round_ in (1, 2):
        http.post(f'/pairings/generate/{EVENT_ID}/{tournament_id}/{round_}')
        for board in games(EVENT.tournament(), round_):
            http.put(
                f'/pairing/set-result/{EVENT_ID}/{tournament_id}/{round_}'
                f'/{board.identifier}/{Result.WIN.value}'
            )
    http.post(f'/pairings/generate/{EVENT_ID}/{tournament_id}/3')
    yield EVENT.tournament()
    EVENT.delete()


def unpair(http: TestClient, tournament: Tournament, round_: int) -> None:
    board = games(EVENT.tournament(), round_)[0]
    route = f'/{EVENT_ID}/{tournament.id}/{round_}/{board.identifier}'
    http.put(f'/pairing/set-result{route}/{Result.NO_RESULT.value}')
    http.delete(f'/pairing/unpair{route}')


@pytest.mark.unit
def test_unpairing_in_the_previous_round_starts_a_manual_pairing(
    http: TestClient, tournament: Tournament
):
    unpair(http, tournament, 2)

    assert EVENT.tournament().manual_pairing_round == 2


@pytest.mark.unit
def test_the_pairings_of_another_round_wait_for_the_validation(
    http: TestClient, tournament: Tournament
):
    unpair(http, tournament, 2)
    board = games(EVENT.tournament(), 3)[0]
    route = f'/pairing/unpair/{EVENT_ID}/{tournament.id}/3/{board.identifier}'

    response = http.get(
        f'/pairings/warning-modal/{EVENT_ID}/{tournament.id}/3'
        f'/MANUAL_UNPAIRING/DELETE/{route}'
    )

    assert 'are being edited: validate or cancel them' in response.text
    assert EVENT.tournament().manual_pairing_round == 2
    assert board.identifier in EVENT.tournament().boards_by_id


@pytest.mark.unit
def test_pairings_the_engine_cannot_check_are_listed(
    http: TestClient, tournament: Tournament, monkeypatch: pytest.MonkeyPatch
):
    def fail(*_args, **_kwargs):
        raise PairingEngineError('internal context', detail='no valid pairing exists')

    monkeypatch.setattr(PairingEngine, 'expected_round_pairs', fail)
    http.patch(
        f'/pairing/permute/{EVENT_ID}/{tournament.id}/3'
        f'/{games(tournament, 3)[0].identifier}?confirmed=1'
    )

    response = http.post(
        f'/pairings/validate-manual-pairing/{EVENT_ID}/{tournament.id}/3'
    )

    assert 'no valid pairing exists' in response.text
    assert 'internal context' not in response.text
    assert 'Pairings changed by hand' in response.text
