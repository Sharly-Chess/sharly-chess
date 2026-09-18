"""The checklist bbpPairings writes for the round it is pairing.

The arbiter is shown the engine's own view of a round — score groups,
colour preferences, bye eligibility — so these tests read a real
checklist from the engine rather than a transcribed one.
"""

from collections.abc import Iterator

import pytest

from data.event import Event
from data.loader import EventLoader
from data.pairings.bbp_history import TournamentHistory
from data.pairings.engines import BbpPairings, TeamSwissEngine
from data.pairings.variations import StandardTeamSwissVariation
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import BoardColor, EventType

EVENT_ID = 'test-pairing-history'
TEAM_EVENT_ID = 'test-pairing-history-teams'
TOURNAMENT_NAME = 'test-pairing-history-tournament'
TEAM_COUNT = 4
TEAM_SIZE = 2


@pytest.fixture(scope='module')
def tournament() -> Iterator[Tournament]:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME, json_file='tec-swiss')
    event: Event = EventLoader().load_event(EVENT_ID)
    yield event.tournaments_by_name[TOURNAMENT_NAME]
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.fixture(scope='module')
def team_tournament() -> Iterator[Tournament]:
    TestUtils.create_event(TEAM_EVENT_ID, overrides={'event_type': EventType.TEAM})
    stored_tournament = TestUtils.create_tournament(
        TEAM_EVENT_ID,
        TOURNAMENT_NAME,
        overrides={
            'pairing': StandardTeamSwissVariation.static_id(),
            'team_player_count': TEAM_SIZE,
            'rounds': TEAM_COUNT - 1,
        },
    )
    tournament_id = stored_tournament.id
    assert tournament_id is not None
    with EventDatabase(TEAM_EVENT_ID, write=True) as database:
        for team_index in range(TEAM_COUNT):
            team_id = database.add_stored_team(
                StoredTeam(
                    id=None,
                    name=f'Team {team_index + 1}',
                    tournament_id=tournament_id,
                    pairing_number=team_index + 1,
                    check_in=True,
                )
            )
            for board_index in range(TEAM_SIZE):
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=f'Player {team_index + 1}.{board_index + 1}',
                        team_id=team_id,
                        team_index=board_index,
                        check_in=True,
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id,
                        player_id=player_id,
                        pairing_number=board_index + 1,
                    )
                )
    event: Event = EventLoader().load_event(TEAM_EVENT_ID)
    yield event.tournaments_by_name[TOURNAMENT_NAME]
    EventLoader.unload_event(TEAM_EVENT_ID)
    TestUtils.delete_event(TEAM_EVENT_ID)


@pytest.fixture(scope='module')
def history(tournament: Tournament) -> TournamentHistory:
    parsed, _boards = BbpPairings().get_history(tournament, tournament.current_round)
    return parsed


@pytest.mark.unit
def test_the_checklist_covers_the_rounds_already_played(
    tournament: Tournament, history: TournamentHistory
):
    """The colour history column carries one dash per played round plus
    the one being paired, and that count is what the modal labels its
    columns with."""
    assert history.rounds == tournament.current_round - 1
    assert history.players
    for player in history.players:
        assert len(player.previous_opponents) == history.rounds


@pytest.mark.unit
def test_every_paired_player_appears_once(
    tournament: Tournament, history: TournamentHistory
):
    """Rows are keyed by pairing number, which is what the modal joins
    them to the players by."""
    ids = [player.id for player in history.players]
    assert len(ids) == len(set(ids))
    pairing_numbers = {
        tournament_player.pairing_number
        for tournament_player in tournament.tournament_players
    }
    assert set(ids) <= pairing_numbers


@pytest.mark.unit
def test_the_round_being_paired_reads_the_same_from_both_sides(
    history: TournamentHistory,
):
    """Each side of a board names the other and takes the other colour."""
    by_id = {player.id: player for player in history.players}
    paired = [player for player in history.players if player.current_opponent]
    assert paired
    for player in paired:
        assert player.current_opponent is not None
        opponent = by_id[player.current_opponent]
        assert opponent.current_opponent == player.id
        assert {player.current_color, opponent.current_color} == {
            BoardColor.WHITE,
            BoardColor.BLACK,
        }


@pytest.mark.unit
def test_the_boards_are_the_pairing_the_checklist_describes(tournament: Tournament):
    """The same call returns the round it paired, so the modal shows one
    round rather than two views of different ones."""
    history, boards = BbpPairings().get_history(tournament, tournament.current_round)
    players_by_id = {
        tournament_player.id: tournament_player
        for tournament_player in tournament.tournament_players
    }

    def pairing_number(player_id: int | None) -> int:
        assert player_id is not None
        number = players_by_id[player_id].pairing_number
        assert number is not None
        return number

    played: set[tuple[int, int]] = set()
    byes: set[int] = set()
    for board in boards:
        white = pairing_number(board.white_player_id)
        if board.black_player_id is None:
            byes.add(white)
            continue
        played.add((white, pairing_number(board.black_player_id)))
    assert played == {
        (player.id, player.current_opponent)
        for player in history.players
        if player.current_color == BoardColor.WHITE and player.current_opponent
    }
    assert byes == {
        player.id for player in history.players if player.current_opponent is None
    }


@pytest.mark.unit
def test_the_team_checklist_reads_its_columns_by_name(team_tournament: Tournament):
    """The team checklist carries the team criteria in place of the float
    history, so its columns sit elsewhere than the individual ones."""
    history = TeamSwissEngine().get_team_history(team_tournament, 1)
    assert len(history.teams) == TEAM_COUNT
    assert {team.id for team in history.teams} == set(range(1, TEAM_COUNT + 1))
    for team in history.teams:
        assert team.points == 0.0
        assert team.previous_opponents == []
    by_id = {team.id: team for team in history.teams}
    for team in history.teams:
        assert team.current_opponent is not None
        assert by_id[team.current_opponent].current_opponent == team.id
