"""The settings of a started FIDE-mode tournament, over HTTP: the points are
fixed unless it leaves FIDE mode, and changing the number of rounds or the
tie-breaks takes a double warning and is logged."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.pibes import Pibe, PibeType
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTieBreak
from tests.unit.http.events import EventUnderTest
from utils.enum import Result

EVENT_ID = 'test-fide-mode-settings'
TOURNAMENT_NAME = 'test-fide-mode-settings-tournament'

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)

FIELDS = {
    'name': TOURNAMENT_NAME,
    'rounds': '5',
    'rating': '1',
    'pairing_system': 'SWISS',
    'SWISS_pairing_variation': 'SWISS_STANDARD',
    'fide_mode': 'on',
}


@pytest.fixture
def tournament() -> Iterator[Tournament]:
    EVENT.create(json_file='tec-swiss')
    yield EVENT.tournament()
    EVENT.delete()


GP_FIELDS = {
    Result.WIN: 'gp_win',
    Result.DRAW: 'gp_draw',
    Result.LOSS: 'gp_loss',
    Result.ZERO_POINT_BYE: 'gp_zpb',
    Result.PAIRING_ALLOCATED_BYE: 'gp_pab',
}


def form(tournament: Tournament, **fields: str) -> dict[str, str]:
    """The form as the modal sends it, with the points already set."""
    game_points = tournament.stored_tournament.game_points or {}
    return (
        FIELDS
        | {
            field: str(game_points[result.value])
            for result, field in GP_FIELDS.items()
            if result.value in game_points
        }
        | fields
    )


def update(http: TestClient, tournament: Tournament, **fields: str) -> str:
    response = http.patch(
        f'/tournament-update/{EVENT_ID}/{tournament.id}',
        data=form(tournament, **fields),
    )
    assert response.status_code == 200
    return response.text


@pytest.mark.unit
def test_the_points_are_fixed_in_fide_mode(http: TestClient, tournament: Tournament):
    game_points = tournament.stored_tournament.game_points

    text = update(http, tournament, gp_win='3')

    assert 'Leave FIDE mode to change them.' in text
    assert EVENT.tournament().stored_tournament.game_points == game_points


@pytest.mark.unit
def test_the_points_change_when_leaving_fide_mode(
    http: TestClient, tournament: Tournament
):
    data = form(tournament, gp_win='3', fide_mode_exit_confirmed='on')
    del data['fide_mode']
    http.patch(f'/tournament-update/{EVENT_ID}/{tournament.id}', data=data)

    tournament = EVENT.tournament()
    assert not tournament.fide_mode
    assert (tournament.stored_tournament.game_points or {})[Result.WIN.value] == 3


@pytest.mark.unit
def test_changing_the_rounds_is_confirmed_then_logged(
    http: TestClient, tournament: Tournament
):
    text = update(http, tournament, rounds='6')

    assert 'Change the number of rounds' in text
    assert EVENT.tournament().rounds == 5

    update(http, tournament, rounds='6', rounds_change_confirmed='on')

    tournament = EVENT.tournament()
    assert tournament.rounds == 6
    assert PibeType.ROUNDS in [pibe.type for pibe in tournament.pibes]


@pytest.mark.unit
def test_the_tie_breaks_are_fixed_until_unlocked(
    http: TestClient, tournament: Tournament
):
    assert tournament.id is not None
    with EventDatabase(EVENT_ID, write=True) as database:
        tie_break_id = database.add_stored_tie_break(
            StoredTieBreak(
                id=None,
                tournament_id=tournament.id,
                type='WINS',
                options={},
                index=len(tournament.tie_breaks_by_id),
            )
        )
    route = f'/tournaments/tie-break/delete/{EVENT_ID}/{tournament.id}/{tie_break_id}'

    http.get(f'/tournaments/tie-breaks-modal/{EVENT_ID}/{tournament.id}')
    http.delete(route)
    assert tie_break_id in EVENT.tournament().tie_breaks_by_id

    http.post(f'/tournaments/tie-breaks-unlock/{EVENT_ID}/{tournament.id}')
    http.delete(route)

    tournament = EVENT.tournament()
    assert tie_break_id not in tournament.tie_breaks_by_id
    assert [pibe.type for pibe in tournament.pibes] == [PibeType.TIE_BREAKS]


@pytest.mark.unit
def test_more_byes_than_fide_allows_are_set_without_confirmation(
    http: TestClient, tournament: Tournament
):
    update(http, tournament, max_byes='2')

    assert EVENT.tournament().max_byes == 2


@pytest.mark.unit
def test_a_second_half_point_bye_is_confirmed(http: TestClient, tournament: Tournament):
    with EventDatabase(EVENT_ID, write=True) as database:
        tournament.stored_tournament.max_byes = 2
        tournament.stored_tournament.rounds = 7
        database.update_stored_tournament(tournament.stored_tournament)
    tournament = EVENT.tournament()
    player = next(iter(tournament.tournament_players))
    round_ = tournament.current_round + 1
    route = f'/event/{EVENT_ID}/unpaired-modal/{tournament.id}/{round_ + 1}/{player.id}'

    assert not player.half_point_bye_needs_confirmation(round_ + 1)
    assert 'already has one' not in http.get(route).text

    tournament.set_player_byes(player, {round_: Result.HALF_POINT_BYE})
    player = EVENT.tournament().tournament_players_by_id[player.id]

    assert not player.half_point_bye_needs_confirmation(round_)
    assert player.half_point_bye_needs_confirmation(round_ + 1)
    assert 'already has one' in http.get(route).text
    assert 'already has one' in http.get(f'/record-modal/{EVENT_ID}/{player.id}').text


@pytest.mark.unit
def test_the_prohibited_pairings_are_fixed_once_paired(
    http: TestClient, tournament: Tournament
):
    with EventDatabase(EVENT_ID, write=True) as database:
        tournament.stored_tournament.rounds = 6
        database.update_stored_tournament(tournament.stored_tournament)
    member_ids = ','.join(
        str(player.id) for player in list(tournament.tournament_players)[:2]
    )
    route = f'/pairings/prohibited/manual-save/{EVENT_ID}/{tournament.id}/6'

    http.post(route, data={'member_ids': member_ids})

    assert not EVENT.tournament().prohibited_pairings.manual_groups()

    http.post(f'/pairings/prohibited/leave-fide-mode/{EVENT_ID}/{tournament.id}/6')
    http.post(route, data={'member_ids': member_ids})

    tournament = EVENT.tournament()
    assert not tournament.fide_mode
    assert tournament.prohibited_pairings.manual_groups()


@pytest.mark.unit
def test_the_log_lists_what_was_recorded(http: TestClient, tournament: Tournament):
    tournament.log_pibe(Pibe(PibeType.CORRECTION, 4, '6-17: 1-0 => 0-1'))

    response = http.get(f'/pairings/fide-log-modal/{EVENT_ID}/{tournament.id}/5')

    assert response.status_code == 200
    assert 'result of 6-17 changed from 1-0 to 0-1' in response.text
