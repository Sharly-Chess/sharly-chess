"""What a duplicated event keeps of the rounds already played.

Dropping the pairings has to drop everything that stood on them — the
boards, the team matches those boards sit in, the lineups fielded for
them. A team match left behind is a round that still reports itself as
paired, so the duplicate opens on a round whose matches hold no games
and can never be drawn.
"""

from unittest import TestCase

from contextlib import suppress
import pytest

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


EVENT_ID = 'test-event-clone'
CLONE_ID = 'test-event-clone-copy'
TOURNAMENT_NAME = 'tournament'
N = 2  # boards per match


@pytest.mark.unit
class EventCloneTestCase(TestCase):
    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)
        TestUtils.delete_event(CLONE_ID)

    def _create(self) -> None:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        stored_tournament = TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 3,
                'current_round': 1,
                'team_player_count': N,
                'pairing': 'TEAM_SWISS_STANDARD',
            },
        )
        tournament_id = stored_tournament.id
        assert tournament_id is not None
        with EventDatabase(EVENT_ID, write=True) as database:
            for seed in range(1, 5):
                team_id = database.add_stored_team(
                    StoredTeam(
                        id=None,
                        name=f'Team{seed}',
                        tournament_id=tournament_id,
                        pairing_number=seed,
                        check_in=True,
                    )
                )
                for index in range(N):
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

    def _load(self, uniq_id: str) -> Tournament:
        with suppress(KeyError):
            EventLoader.unload_event(uniq_id)
        # A Tournament holds its event weakly, so the event has to
        # outlive this call.
        self._event = EventLoader().load_event(uniq_id)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    def _play_two_rounds(self) -> None:
        self._create()
        tournament = self._load(EVENT_ID)
        self.assertEqual(tournament.generate_round_pairings(1), '')
        tournament = self._load(EVENT_ID)
        for board in tournament.get_round_boards(1):
            tournament.add_result(board, Result.WIN)
        tournament = self._load(EVENT_ID)
        self.assertEqual(tournament.generate_round_pairings(2), '')
        tournament = self._load(EVENT_ID)
        self.assertEqual(tournament.current_round, 2)
        self.assertTrue(tournament.get_round_team_boards(1))

    def _clone_without_pairings(self, keep_players: bool) -> Tournament:
        """The duplicate the event modal makes with "pairings" unticked."""
        EventLoader.unload_event(EVENT_ID)
        EventDatabase(EVENT_ID).clone(new_uniq_id=CLONE_ID)
        with EventDatabase(CLONE_ID, write=True) as database:
            if not keep_players:
                database.delete_all_stored_players()
            database.delete_all_stored_pairings()
            for stored_tournament in database.load_stored_tournaments():
                tournament_id = stored_tournament.id
                assert tournament_id is not None
                database.set_tournament_pairing_settings(tournament_id, {})
                database.set_tournament_current_round(tournament_id, None)
        return self._load(CLONE_ID)

    def _assert_no_round_is_paired(self, tournament: Tournament) -> None:
        for round_ in range(1, tournament.rounds + 1):
            self.assertFalse(tournament.round_has_pairings(round_))
            self.assertFalse(tournament.get_round_team_boards(round_))
            self.assertFalse(tournament.get_round_boards(round_))

    def test_a_duplicate_keeping_the_players_can_be_drawn_from_round_one(self):
        self._play_two_rounds()
        tournament = self._clone_without_pairings(keep_players=True)
        self.assertEqual(len(tournament.teams), 4)
        self._assert_no_round_is_paired(tournament)
        self.assertEqual(tournament.generate_round_pairings(1), '')

    def test_a_duplicate_without_players_keeps_no_team_matches(self):
        self._play_two_rounds()
        tournament = self._clone_without_pairings(keep_players=False)
        self.assertEqual(len(tournament.teams), 4)
        self.assertEqual(tournament.player_count, 0)
        self._assert_no_round_is_paired(tournament)
