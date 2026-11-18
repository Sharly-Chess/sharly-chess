"""A team board the other team left empty takes a result from the
pairings page: a forfeit win for the present player, or F-F when they did
not show up either."""

import contextlib
from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.board import Board
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import EventType, Result

EVENT_ID = 'test-team-forfeit-hole-result'
TOURNAMENT_NAME = 'tournament'
BOARDS = 2
TEAMS = 2

_loaded: list[Event] = []


def load() -> Tournament:
    with contextlib.suppress(KeyError):
        EventLoader.unload_event(EVENT_ID)
    event = EventLoader().load_event(EVENT_ID)
    _loaded[:] = [event]
    return event.tournaments_by_name[TOURNAMENT_NAME]


def hole_board(tournament: Tournament) -> Board:
    return next(
        board
        for board in tournament.get_round_boards(1)
        if board.team_forfeit_hole_pairing is not None
    )


def white_result(board: Board, player_result: Result) -> Result:
    if board.optional_white_tournament_player is not None:
        return player_result
    return player_result.opposite_result


@pytest.fixture(
    params=[('TEAM_SWISS_STANDARD', TEAMS), ('MOLTER_STANDARD', 3)],
    ids=['team-match', 'molter'],
)
def tournament(request: pytest.FixtureRequest) -> Iterator[Tournament]:
    """Team1 leaves its second board empty in round 1, in a team match or
    in a Molter round paired board by board."""
    pairing, teams = request.param
    TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
    stored_tournament = TestUtils.create_tournament(
        EVENT_ID,
        TOURNAMENT_NAME,
        overrides={
            'rounds': 1,
            'team_player_count': BOARDS,
            'pairing': pairing,
        },
    )
    tournament_id = stored_tournament.id
    assert tournament_id is not None
    first_team_players: list[int | None] = []
    with EventDatabase(EVENT_ID, write=True) as database:
        for seed in range(1, teams + 1):
            team_id = database.add_stored_team(
                StoredTeam(
                    id=None,
                    name=f'Team{seed}',
                    tournament_id=tournament_id,
                    pairing_number=seed,
                    check_in=True,
                )
            )
            for index in range(BOARDS):
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=f'T{seed}P{index}',
                        team_id=team_id,
                        team_index=index,
                        check_in=True,
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id,
                        player_id=player_id,
                        pairing_number=index + 1,
                    )
                )
                if seed == 1:
                    first_team_players.append(player_id)
    first_team_players[1] = None
    tournament = load()
    team = next(team for team in tournament.teams if team.name == 'Team1')
    with EventDatabase(EVENT_ID, write=True) as database:
        team.set_round_lineup(1, first_team_players, database)
    assert load().generate_round_pairings(1) == ''
    yield load()
    _loaded.clear()
    with contextlib.suppress(KeyError):
        EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.mark.unit
def test_the_pairings_page_opens_the_result_of_a_hole(
    http: TestClient, tournament: Tournament
):
    board = hole_board(tournament)
    response = http.get(f'/event/{EVENT_ID}/pairings/{tournament.id}/1')
    assert response.status_code == 200
    assert f'/event/{EVENT_ID}/pairing/{tournament.id}/1/{board.identifier}' in (
        response.text
    )


@pytest.mark.unit
def test_the_result_dialog_of_a_hole_offers_only_forfeits(
    http: TestClient, tournament: Tournament
):
    board = hole_board(tournament)
    response = http.get(
        f'/event/{EVENT_ID}/pairing/{tournament.id}/1/{board.identifier}'
    )
    assert response.status_code == 200
    assert 'F – F' in response.text
    assert '½ – ½' not in response.text


@pytest.mark.unit
def test_the_result_dialog_of_a_hole_names_both_teams(
    http: TestClient, tournament: Tournament
):
    board = hole_board(tournament)
    present = board.team_forfeit_hole_pairing
    assert present is not None
    present_team = present.tournament_player.team
    assert present_team is not None
    response = http.get(
        f'/event/{EVENT_ID}/pairing/{tournament.id}/1/{board.identifier}'
    )
    assert response.status_code == 200
    assert 'Team1' in response.text
    assert present_team.name in response.text


@pytest.mark.unit
def test_an_absent_present_player_is_recorded_as_a_double_forfeit(
    http: TestClient, tournament: Tournament
):
    board = hole_board(tournament)
    http.put(
        f'/pairing/set-result/{EVENT_ID}/{tournament.id}/1/{board.identifier}'
        f'/{white_result(board, Result.DOUBLE_FORFEIT).value}'
    )
    board = load().boards_by_id[board.identifier]
    pairing = board.team_forfeit_hole_pairing
    assert pairing is not None
    assert pairing.result == Result.DOUBLE_FORFEIT


@pytest.mark.unit
def test_a_played_result_is_refused_on_a_hole(http: TestClient, tournament: Tournament):
    board = hole_board(tournament)
    http.put(
        f'/pairing/set-result/{EVENT_ID}/{tournament.id}/1/{board.identifier}'
        f'/{Result.DRAW.value}'
    )
    pairing = load().boards_by_id[board.identifier].team_forfeit_hole_pairing
    assert pairing is not None
    assert pairing.result == Result.FORFEIT_WIN
