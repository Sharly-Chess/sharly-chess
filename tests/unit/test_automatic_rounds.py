"""Round-robins work their own round count out from their entrants.

The length of a round-robin follows from how many take part, which is
not known while the tournament is being created — so the field is left
empty (stored as 0) and answered on demand.
"""

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

EVENT_ID = 'test-automatic-rounds'
TOURNAMENT_NAME = 'tournament'


def _tournament_id(database: EventDatabase) -> int:
    tournament_id = next(
        stored.id
        for stored in database.load_stored_tournaments()
        if stored.name == TOURNAMENT_NAME
    )
    assert tournament_id is not None
    return tournament_id


@pytest.mark.unit
class TestAutomaticRounds:
    def teardown_method(self):
        TestUtils.delete_event(EVENT_ID)

    def _load(self):
        try:
            EventLoader.unload_event(EVENT_ID)
        except KeyError:
            pass
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    def _individual(self, rounds: int, pairing: str, players: int):
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(
            EVENT_ID, TOURNAMENT_NAME, overrides={'rounds': rounds, 'pairing': pairing}
        )
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = _tournament_id(database)
            for index in range(players):
                player_id = database.add_stored_player(
                    StoredPlayer(id=None, last_name=f'PLAYER{index:02d}')
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id, player_id=player_id
                    )
                )
        return self._load()

    def _team(self, rounds: int, pairing: str, teams: int):
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={'rounds': rounds, 'pairing': pairing, 'team_player_count': 2},
        )
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = _tournament_id(database)
            for index in range(teams):
                database.add_stored_team(
                    StoredTeam(
                        id=None,
                        name=f'Team {index + 1}',
                        tournament_id=tournament_id,
                        pairing_number=index + 1,
                    )
                )
        return self._load()

    def test_an_odd_field_plays_as_many_rounds_as_players(self):
        tournament = self._individual(0, 'ROUND_ROBIN_BERGER', players=9)
        assert tournament.rounds == 9
        assert tournament.rounds_are_automatic

    def test_an_even_field_plays_one_fewer(self):
        tournament = self._individual(0, 'ROUND_ROBIN_BERGER', players=10)
        assert tournament.rounds == 9

    def test_a_double_round_robin_plays_each_cycle_twice(self):
        tournament = self._individual(0, 'ROUND_ROBIN_DOUBLE_BERGER', players=6)
        assert tournament.rounds == 10

    def test_teams_are_counted_for_a_team_round_robin(self):
        tournament = self._team(0, 'TEAM_ROUND_ROBIN_BERGER', teams=6)
        assert tournament.rounds == 5

    def test_an_empty_tournament_reads_as_one_round(self):
        """Enough to render a form or a schedule without pretending to
        know a count nobody can work out yet."""
        tournament = self._individual(0, 'ROUND_ROBIN_BERGER', players=0)
        assert tournament.automatic_rounds is None
        assert tournament.rounds == 1

    def test_pairing_writes_the_count_down(self):
        """The count is stored as the pairings are generated, so the
        schedule and the exports agree with it — and a tournament that
        was unpaired and re-entered picks up the new figure."""
        tournament = self._individual(5, 'ROUND_ROBIN_BERGER', players=10)
        tournament.persist_automatic_rounds()
        assert tournament.stored_tournament.rounds == 9
        assert self._load().stored_tournament.rounds == 9

    def test_a_swiss_never_computes_its_own(self):
        tournament = self._individual(5, 'SWISS_STANDARD', players=10)
        assert tournament.rounds == 5
        assert tournament.automatic_rounds is None

    def test_a_stale_stored_count_is_ignored(self):
        """A tournament saved before the system worked its own count out
        must not be stuck with the old number — it could not be paired."""
        tournament = self._individual(5, 'ROUND_ROBIN_BERGER', players=10)
        assert tournament.stored_tournament.rounds == 5
        assert tournament.rounds == 9

    def test_the_stored_count_is_the_fallback_while_nobody_is_entered(self):
        tournament = self._individual(5, 'ROUND_ROBIN_BERGER', players=0)
        assert tournament.rounds == 5
