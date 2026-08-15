"""A player joining a team becomes a player of its tournament at once.

A team tournament stores no ``tournament_player`` rows — the loader
synthesises them from team membership — so a roster change made after the
event was loaded used to be invisible to the tournament until the next
reload. The players tab then showed the new player with a dash where
their tournament should be.
"""

import pytest

from data.event import Event
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredTeam
from tests.test_config import TestUtils
from utils.enum import EventType

EVENT_ID = 'test-team-roster-visibility'
TOURNAMENT_NAME = 'team-tournament'


@pytest.mark.unit
class TestRosterVisibility:
    @pytest.fixture
    def event(self):
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={'team_player_count': 2, 'pairing': 'TEAM_SWISS_STANDARD'},
        )
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = next(
                stored.id
                for stored in database.load_stored_tournaments()
                if stored.name == TOURNAMENT_NAME
            )
            database.add_stored_team(
                StoredTeam(id=None, name='Team A', tournament_id=tournament_id)
            )
        loaded: Event = EventLoader().load_event(EVENT_ID)
        yield loaded
        TestUtils.delete_event(EVENT_ID)

    @staticmethod
    def _tournament(event: Event):
        return event.tournaments_by_name[TOURNAMENT_NAME]

    def _add_player(self, event: Event) -> int:
        return event.add_player(
            StoredPlayer(id=None, last_name='NEWCOMER', first_name='Test'), []
        )

    def test_the_players_tab_sees_the_tournament(self, event):
        """What the row template reads: a dash appears here when this is
        None. Reading it before the team is set must not freeze it."""
        player_id = self._add_player(event)
        player = event.players_by_id[player_id]
        # The tab renders the player as soon as they are created, which
        # is what used to cache "no tournament" for good.
        assert player.optional_single_tournament_player is None

        team = next(iter(event.teams_by_id.values()))
        with EventDatabase(EVENT_ID, write=True) as database:
            team.add_player(player, database)

        assert player.optional_single_tournament is not None
        assert player.optional_single_tournament_player is not None

    def test_joining_a_team_makes_the_player_a_tournament_player(self, event):
        tournament = self._tournament(event)
        assert tournament.player_count == 0

        player_id = self._add_player(event)
        team = next(iter(event.teams_by_id.values()))
        with EventDatabase(EVENT_ID, write=True) as database:
            team.add_player(event.players_by_id[player_id], database)

        # Without reloading the event.
        assert player_id in tournament.tournament_players_by_id
        assert tournament.player_count == 1

    def test_leaving_the_team_removes_them_again(self, event):
        tournament = self._tournament(event)
        player_id = self._add_player(event)
        team = next(iter(event.teams_by_id.values()))
        with EventDatabase(EVENT_ID, write=True) as database:
            team.add_player(event.players_by_id[player_id], database)
            team.remove_player(event.players_by_id[player_id], database)

        assert player_id not in tournament.tournament_players_by_id
        assert tournament.player_count == 0

    def test_a_reload_agrees_with_what_was_shown(self, event):
        """The in-memory answer must match what the loader would build."""
        player_id = self._add_player(event)
        team = next(iter(event.teams_by_id.values()))
        with EventDatabase(EVENT_ID, write=True) as database:
            team.add_player(event.players_by_id[player_id], database)
        live = set(self._tournament(event).tournament_players_by_id)

        EventLoader.unload_event(EVENT_ID)
        reloaded = EventLoader().load_event(EVENT_ID)
        assert set(self._tournament(reloaded).tournament_players_by_id) == live
