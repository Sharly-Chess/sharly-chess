"""Players marked as not eligible for byes (FIDE C.05:6.7.4), over HTTP."""

import re
from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.input_output.trf.trf_export import TrfExport
from data.input_output.trf.trf_serializer import TrfSerializer
from data.player import TournamentPlayer
from data.tournament import Tournament
from plugins.ffe.print_documents.ffe_types import FFET2Type
from tests.unit.http.events import EventUnderTest
from utils.enum import Result

EVENT_ID = 'test-player-byes-http'
TOURNAMENT_NAME = 'test-player-byes-http-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament() -> Iterator[Tournament]:
    EVENT.create(tournament={'rounds': 5})
    yield EVENT.tournament()
    EVENT.delete()


def player_form(tournament: Tournament, **fields: str) -> dict[str, str]:
    return {
        'federation': 'FRA',
        'gender': '',
        'title': '',
        'tournament_id': str(tournament.id),
        'last_name': 'Doe',
    } | fields


def the_player() -> TournamentPlayer:
    return next(
        player
        for player in EVENT.tournament().tournament_players
        if player.last_name == 'DOE'
    )


def create_player(http: TestClient, tournament: Tournament, **fields: str) -> None:
    response = http.post(
        f'/player-create/{EVENT_ID}', data=player_form(tournament, **fields)
    )
    assert response.status_code == 200


def set_bye(http: TestClient, player: TournamentPlayer, result: Result) -> Result:
    http.patch(
        f'/player-set-bye/{EVENT_ID}/{player.id}/1',
        params={'result': result.value},
    )
    return the_player().pairings[1].result


@pytest.mark.unit
def test_a_new_player_is_eligible_for_byes_by_default(
    http: TestClient, tournament: Tournament
):
    response = http.get(f'/player-modal/create/{EVENT_ID}')
    assert response.status_code == 200
    switch = re.search(r'<input[^>]*name="byes_allowed"[^>]*>', response.text)
    assert switch is not None
    assert 'checked' in switch.group()


@pytest.mark.unit
def test_the_eligibility_is_stored_from_the_switch(
    http: TestClient, tournament: Tournament
):
    create_player(http, tournament, byes_allowed='on')
    assert the_player().byes_allowed
    response = http.patch(
        f'/player-update/{EVENT_ID}/{the_player().id}',
        data=player_form(tournament),
    )
    assert response.status_code == 200
    assert not the_player().byes_allowed


@pytest.mark.unit
def test_a_player_not_eligible_for_byes_gets_no_half_point_bye(
    http: TestClient, tournament: Tournament
):
    """A Zero-Point Bye is still possible, it is no request for points."""
    create_player(http, tournament)
    player = the_player()
    records = http.get(f'/record-modal/{EVENT_ID}/{player.id}')
    assert records.status_code == 200
    assert 'The player is not eligible for byes.' in records.text

    assert set_bye(http, player, Result.HALF_POINT_BYE) == Result.NO_RESULT
    assert set_bye(http, player, Result.FULL_POINT_BYE) == Result.NO_RESULT
    assert set_bye(http, player, Result.ZERO_POINT_BYE) == Result.ZERO_POINT_BYE


@pytest.mark.unit
def test_a_player_with_a_bye_stays_eligible(http: TestClient, tournament: Tournament):
    """The switch is greyed out, so the form sends nothing for it."""
    create_player(http, tournament, byes_allowed='on')
    player = the_player()
    assert set_bye(http, player, Result.HALF_POINT_BYE) == Result.HALF_POINT_BYE

    modal = http.get(f'/player-modal/update/{EVENT_ID}/{player.id}')
    assert 'The player has already been assigned a bye.' in modal.text
    response = http.patch(
        f'/player-update/{EVENT_ID}/{player.id}', data=player_form(tournament)
    )
    assert response.status_code == 200
    assert the_player().byes_allowed


@pytest.mark.unit
def test_a_full_point_bye_is_logged(http: TestClient, tournament: Tournament):
    """Full-point byes are deprecated, so the log points each one out: in
    the TRF and in the minutes of the arbiter."""
    create_player(http, tournament, byes_allowed='on')
    assert EVENT.tournament().log_entries == []

    set_bye(http, the_player(), Result.FULL_POINT_BYE)
    tournament = EVENT.tournament()
    (pairing_number, player), *_ = (
        tournament.tournament_players_by_pairing_number.items()
    )
    trf = TrfSerializer.dumps(TrfExport(tournament).build(after_round=1))
    assert f'### Full-point bye @ Round 1: player {pairing_number}\n' in trf
    assert (
        f'- Ronde 1 : Bye point entier attribué à {player.full_name}.'
        in FFET2Type.report_text_for([tournament])
    )
