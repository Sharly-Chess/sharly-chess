"""What deleting a tournament takes with it.

Teams belong to their tournament and go with it (the `team` foreign key
cascades). Players belong to the *event*, so only those no other
tournament holds are removed — and a team tournament holds them through
its teams, storing no ``tournament_player`` row of its own.
"""

from unittest import TestCase

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import EventType

EVENT_ID = 'test-tournament-delete'
DOOMED = 'doomed'
SURVIVOR = 'survivor'


@pytest.mark.unit
class TournamentDeleteTestCase(TestCase):
    """A team event with two tournaments: one is deleted, the other must
    come through untouched."""

    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        for name in (DOOMED, SURVIVOR):
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

    def _tournament_ids(self, database: EventDatabase) -> dict[str, int]:
        return {
            tournament.name: tournament.id
            for tournament in database.load_stored_tournaments()
            if tournament.id is not None
        }

    def _add_team(
        self, database: EventDatabase, name: str, tournament_id: int | None
    ) -> int:
        return database.add_stored_team(
            StoredTeam(id=None, name=name, tournament_id=tournament_id)
        )

    def _add_player(
        self, database: EventDatabase, last_name: str, team_id: int | None
    ) -> int:
        return database.add_stored_player(
            StoredPlayer(id=None, last_name=last_name, team_id=team_id, team_index=0)
        )

    def _build(self) -> dict[str, int]:
        """Two tournaments, each with a team and a player, plus a team
        that has not been assigned to a tournament yet."""
        with EventDatabase(EVENT_ID, write=True) as database:
            ids = self._tournament_ids(database)
            doomed_team = self._add_team(database, 'Doomed team', ids[DOOMED])
            survivor_team = self._add_team(database, 'Survivor team', ids[SURVIVOR])
            unassigned_team = self._add_team(database, 'Not yet assigned', None)
            return {
                'doomed_tournament': ids[DOOMED],
                'survivor_tournament': ids[SURVIVOR],
                'doomed_team': doomed_team,
                'survivor_team': survivor_team,
                'unassigned_team': unassigned_team,
                'doomed_player': self._add_player(database, 'Doomed', doomed_team),
                'survivor_player': self._add_player(
                    database, 'Survivor', survivor_team
                ),
                'unassigned_player': self._add_player(
                    database, 'Unassigned', unassigned_team
                ),
            }

    def _delete_doomed(self, ids: dict[str, int]) -> None:
        with EventDatabase(EVENT_ID, write=True) as database:
            database.delete_stored_tournament(ids['doomed_tournament'])

    def test_teams_of_the_deleted_tournament_go(self):
        ids = self._build()
        self._delete_doomed(ids)
        event = self._load_event()
        assert ids['doomed_team'] not in event.teams_by_id

    def test_teams_of_other_tournaments_stay(self):
        ids = self._build()
        self._delete_doomed(ids)
        event = self._load_event()
        assert ids['survivor_team'] in event.teams_by_id

    def test_unassigned_teams_stay(self):
        # A team is created before being assigned to a tournament, so a
        # NULL tournament_id must survive any tournament being deleted.
        ids = self._build()
        self._delete_doomed(ids)
        event = self._load_event()
        assert ids['unassigned_team'] in event.teams_by_id

    def test_players_of_the_deleted_tournament_go(self):
        ids = self._build()
        self._delete_doomed(ids)
        event = self._load_event()
        assert ids['doomed_player'] not in event.players_by_id

    def test_players_of_other_tournaments_stay(self):
        ids = self._build()
        self._delete_doomed(ids)
        event = self._load_event()
        assert ids['survivor_player'] in event.players_by_id

    def test_players_in_no_tournament_stay(self):
        ids = self._build()
        self._delete_doomed(ids)
        event = self._load_event()
        assert ids['unassigned_player'] in event.players_by_id

    def test_player_entered_in_both_tournaments_stays(self):
        # Held by the doomed tournament through its team, and by the
        # survivor through a tournament_player row: the survivor keeps it.
        ids = self._build()
        with EventDatabase(EVENT_ID, write=True) as database:
            database.add_stored_tournament_player(
                StoredTournamentPlayer(
                    tournament_id=ids['survivor_tournament'],
                    player_id=ids['doomed_player'],
                )
            )
        self._delete_doomed(ids)
        event = self._load_event()
        assert ids['doomed_player'] in event.players_by_id

    def test_the_modal_counts_what_is_deleted(self):
        # The delete dialog warns using `exclusive_player_ids`; it has to
        # match what actually goes.
        ids = self._build()
        event = self._load_event()
        tournament = event.tournaments_by_id[ids['doomed_tournament']]
        announced = set(tournament.exclusive_player_ids)
        announced_teams = {team.id for team in tournament.teams}
        assert announced == {ids['doomed_player']}
        assert announced_teams == {ids['doomed_team']}

        self._delete_doomed(ids)
        remaining = set(self._load_event().players_by_id)
        assert not announced & remaining


@pytest.mark.unit
class ClearTournamentPlayersTestCase(TestCase):
    """Importing players "and delete the existing ones" empties the
    tournament but keeps its teams, ready to be filled again."""

    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        for name in (DOOMED, SURVIVOR):
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

    def _build(self) -> dict[str, int]:
        with EventDatabase(EVENT_ID, write=True) as database:
            ids = {
                tournament.name: tournament.id
                for tournament in database.load_stored_tournaments()
                if tournament.id is not None
            }
            cleared_team = database.add_stored_team(
                StoredTeam(id=None, name='Cleared', tournament_id=ids[DOOMED])
            )
            other_team = database.add_stored_team(
                StoredTeam(id=None, name='Other', tournament_id=ids[SURVIVOR])
            )
            return {
                'tournament': ids[DOOMED],
                'other_tournament': ids[SURVIVOR],
                'cleared_team': cleared_team,
                'other_team': other_team,
                'cleared_player': database.add_stored_player(
                    StoredPlayer(
                        id=None, last_name='Cleared', team_id=cleared_team, team_index=0
                    )
                ),
                'other_player': database.add_stored_player(
                    StoredPlayer(
                        id=None, last_name='Other', team_id=other_team, team_index=0
                    )
                ),
            }

    def test_team_players_are_deleted(self):
        ids = self._build()
        with EventDatabase(EVENT_ID, write=True) as database:
            database.delete_players_in_tournament(ids['tournament'])
        event = self._load_event()
        assert ids['cleared_player'] not in event.players_by_id

    def test_the_teams_themselves_are_kept(self):
        # The import re-attaches the new players to them by name.
        ids = self._build()
        with EventDatabase(EVENT_ID, write=True) as database:
            database.delete_players_in_tournament(ids['tournament'])
        event = self._load_event()
        assert ids['cleared_team'] in event.teams_by_id

    def test_other_tournaments_are_untouched(self):
        ids = self._build()
        with EventDatabase(EVENT_ID, write=True) as database:
            database.delete_players_in_tournament(ids['tournament'])
        event = self._load_event()
        assert ids['other_player'] in event.players_by_id
        assert ids['other_team'] in event.teams_by_id

    def test_a_player_of_two_tournaments_only_loses_this_one(self):
        ids = self._build()
        with EventDatabase(EVENT_ID, write=True) as database:
            database.add_stored_tournament_player(
                StoredTournamentPlayer(
                    tournament_id=ids['other_tournament'],
                    player_id=ids['cleared_player'],
                )
            )
            database.delete_players_in_tournament(ids['tournament'])
        event = self._load_event()
        assert ids['cleared_player'] in event.players_by_id
