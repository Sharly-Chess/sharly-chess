"""Regression tests for moving teams after their boards are unpaired."""

from unittest import TestCase

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPairing,
    StoredPlayer,
    StoredTeam,
    StoredTeamBoard,
)
from tests.test_config import TestUtils
from utils.enum import EventType, Result, TeamByeType


EVENT_ID = 'test-team-tournament-move'
SOURCE_NAME = 'source'
DESTINATION_NAME = 'destination'


@pytest.mark.unit
class TeamTournamentMoveTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        for name in (SOURCE_NAME, DESTINATION_NAME):
            TestUtils.create_tournament(
                EVENT_ID,
                name,
                overrides={
                    'rounds': 3,
                    'team_player_count': 1,
                    'pairing': 'TEAM_SWISS_STANDARD',
                },
            )

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _load_event(self):
        try:
            EventLoader.unload_event(EVENT_ID)
        except KeyError:
            pass
        return EventLoader().load_event(EVENT_ID)

    def test_boardless_bye_does_not_lock_team_and_is_removed_on_move(self):
        with EventDatabase(EVENT_ID, write=True) as database:
            tournaments = {
                tournament.name: tournament
                for tournament in database.load_stored_tournaments()
            }
            source_id = tournaments[SOURCE_NAME].id
            destination_id = tournaments[DESTINATION_NAME].id
            assert source_id is not None
            assert destination_id is not None
            team_id = database.add_stored_team(
                StoredTeam(
                    id=None,
                    name='Movable',
                    tournament_id=source_id,
                    pairing_number=1,
                )
            )
            player_id = database.add_stored_player(
                StoredPlayer(
                    id=None,
                    last_name='Player',
                    team_id=team_id,
                    team_index=0,
                )
            )
            for round_ in (1, 2):
                database.add_stored_team_board(
                    StoredTeamBoard(
                        id=None,
                        tournament_id=source_id,
                        round_=round_,
                        team_a_id=team_id,
                        team_b_id=None,
                        index=None,
                        bye_type=TeamByeType.ZPB,
                    )
                )
                database.add_stored_pairing(
                    StoredPairing(
                        tournament_id=source_id,
                        player_id=player_id,
                        round_=round_,
                        result=Result.ZERO_POINT_BYE.value,
                        board_id=None,
                    )
                )

        event = self._load_event()
        team = event.teams_by_id[team_id]
        with EventDatabase(EVENT_ID, write=True) as database:
            team.set_round_bye(1, None, database)

        assert team.round_bye_type(1) is None
        assert team.round_bye_type(2) == TeamByeType.ZPB
        assert not team.has_been_paired
        with EventDatabase(EVENT_ID) as database:
            source_pairings = database.load_tournament_stored_pairings_by_player(
                source_id
            )
        # Cancelling the team-level round-1 bye must not assume the imported
        # player records are mirrors of it.
        assert [pairing.round_ for pairing in source_pairings[player_id]] == [1, 2]

        with EventDatabase(EVENT_ID, write=True) as database:
            team.set_tournament(destination_id, database)

        event = self._load_event()
        moved_team = event.teams_by_id[team_id]
        assert moved_team.tournament_id == destination_id
        assert moved_team.pairing_number is None
        assert event.tournaments_by_id[source_id].get_round_team_boards(2) == []
        with EventDatabase(EVENT_ID) as database:
            pairings = database.load_tournament_stored_pairings_by_player(source_id)
        assert player_id not in pairings

    def test_real_team_board_still_locks_team(self):
        with EventDatabase(EVENT_ID, write=True) as database:
            source = next(
                tournament
                for tournament in database.load_stored_tournaments()
                if tournament.name == SOURCE_NAME
            )
            assert source.id is not None
            team_a_id = database.add_stored_team(
                StoredTeam(id=None, name='Alpha', tournament_id=source.id)
            )
            team_b_id = database.add_stored_team(
                StoredTeam(id=None, name='Bravo', tournament_id=source.id)
            )
            database.add_stored_team_board(
                StoredTeamBoard(
                    id=None,
                    tournament_id=source.id,
                    round_=1,
                    team_a_id=team_a_id,
                    team_b_id=team_b_id,
                    index=0,
                )
            )

        event = self._load_event()
        assert event.teams_by_id[team_a_id].has_been_paired
        assert event.teams_by_id[team_b_id].has_been_paired
