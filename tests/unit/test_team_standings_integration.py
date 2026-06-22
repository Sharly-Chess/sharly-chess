"""End-to-end check that ``Tournament.team_standings()`` reads team
tie-breaks out of storage, builds team records from team_boards, and
sorts the results.

The fixture is intentionally tiny — two teams, two players each, one
round — engineered so the teams draw on game points but split on
the FFE Berlin coefficient. That's the smallest scenario that
exercises the full integration path:
  StoredTieBreak → Tournament.tie_breaks_by_id → team_tie_breaks
  → team_records → team_tie_break_context → team_standings sort.
"""

from unittest import TestCase

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredBoard,
    StoredPairing,
    StoredPlayer,
    StoredTeam,
    StoredTeamBoard,
    StoredTieBreak,
    StoredTournamentPlayer,
)
from plugins.ffe.ffe_tie_breaks import BerlinTieBreak
from tests.test_config import TestUtils
from utils.enum import EventType, Result


EVENT_ID = 'test-team-standings-integration'
TOURNAMENT_NAME = 'tournament'


@pytest.mark.unit
class TeamStandingsIntegrationTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(
            EVENT_ID,
            overrides={'event_type': EventType.TEAM},
        )
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 1,
                'current_round': 1,
                'team_player_count': 2,
                'pairing': 'TEAM_SWISS_STANDARD',
            },
        )

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _seed_two_team_match_with_berlin(self) -> None:
        """A vs B over two boards: A wins board 1, B wins board 2.

        Game points are even (1-1, a drawn match → 1 MP each), but
        Berlin weights board 1 more heavily so A (1×2 + 0×1 = 2)
        outranks B (0×2 + 1×1 = 1).
        """
        with EventDatabase(EVENT_ID, write=True) as db:
            tournament = next(
                t for t in db.load_stored_tournaments() if t.name == TOURNAMENT_NAME
            )
            tournament_id = tournament.id
            assert tournament_id is not None
            team_a_id = db.add_stored_team(
                StoredTeam(id=None, name='Alpha', tournament_id=tournament_id)
            )
            team_b_id = db.add_stored_team(
                StoredTeam(id=None, name='Bravo', tournament_id=tournament_id)
            )

            def add_player(name: str, team_id: int, team_index: int) -> int:
                player_id = db.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=name,
                        team_id=team_id,
                        team_index=team_index,
                        check_in=True,
                    )
                )
                db.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id,
                        player_id=player_id,
                        pairing_number=team_index,
                    )
                )
                return player_id

            a1 = add_player('A1', team_a_id, 1)
            a2 = add_player('A2', team_a_id, 2)
            b1 = add_player('B1', team_b_id, 1)
            b2 = add_player('B2', team_b_id, 2)

            team_board_id = db.add_stored_team_board(
                StoredTeamBoard(
                    id=None,
                    tournament_id=tournament_id,
                    round_=1,
                    team_a_id=team_a_id,
                    team_b_id=team_b_id,
                    index=1,
                )
            )

            board1_id = db.add_stored_board(
                StoredBoard(
                    id=None,
                    white_player_id=a1,
                    black_player_id=b1,
                    index=1,
                    team_board_id=team_board_id,
                )
            )
            board2_id = db.add_stored_board(
                StoredBoard(
                    id=None,
                    white_player_id=a2,
                    black_player_id=b2,
                    index=2,
                    team_board_id=team_board_id,
                )
            )

            # A1 (white) wins board 1; B1 (black) loses.
            db.add_stored_pairing(
                StoredPairing(
                    tournament_id=tournament_id,
                    player_id=a1,
                    round_=1,
                    result=Result.WIN.value,
                    board_id=board1_id,
                )
            )
            db.add_stored_pairing(
                StoredPairing(
                    tournament_id=tournament_id,
                    player_id=b1,
                    round_=1,
                    result=Result.LOSS.value,
                    board_id=board1_id,
                )
            )
            # A2 (white) loses board 2; B2 (black) wins.
            db.add_stored_pairing(
                StoredPairing(
                    tournament_id=tournament_id,
                    player_id=a2,
                    round_=1,
                    result=Result.LOSS.value,
                    board_id=board2_id,
                )
            )
            db.add_stored_pairing(
                StoredPairing(
                    tournament_id=tournament_id,
                    player_id=b2,
                    round_=1,
                    result=Result.WIN.value,
                    board_id=board2_id,
                )
            )

            db.add_stored_tie_break(
                StoredTieBreak(
                    id=None,
                    tournament_id=tournament_id,
                    type=BerlinTieBreak.static_id(),
                    options={},
                    index=0,
                )
            )

        self.team_a_id = team_a_id
        self.team_b_id = team_b_id

    def _load(self):
        try:
            EventLoader.unload_event(EVENT_ID)
        except KeyError:
            pass
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    def test_berlin_breaks_a_drawn_match(self) -> None:
        self._seed_two_team_match_with_berlin()
        tournament = self._load()

        # Sanity: Berlin shows up among the configured tie-breaks.
        team_tie_breaks = [tb for tb in tournament.tie_breaks if tb.is_team_tiebreak]
        self.assertEqual(len(team_tie_breaks), 1)
        self.assertIsInstance(team_tie_breaks[0], BerlinTieBreak)

        # team_records() yields one TeamRecord per team with board_scores
        # populated, so board-weighted tie-breaks (Berlin) work.
        records = {r.team_id: r for r in tournament.team_records()}
        self.assertEqual(records[self.team_a_id].matches[0].board_scores, (1.0, 0.0))
        self.assertEqual(records[self.team_b_id].matches[0].board_scores, (0.0, 1.0))

        # team_standings sorts by primary/secondary then by tie-break values.
        # MP=1 each, GP=1 each → Berlin (2 vs 1) is the deciding factor.
        standings = tournament.team_standings()
        self.assertEqual(len(standings), 2)
        self.assertEqual(standings[0]['team'].id, self.team_a_id)
        self.assertEqual(standings[1]['team'].id, self.team_b_id)
        self.assertEqual([v.value for v in standings[0]['tie_break_values']], [2.0])
        self.assertEqual([v.value for v in standings[1]['tie_break_values']], [1.0])
        self.assertEqual(standings[0]['rank'], 1)
        self.assertEqual(standings[1]['rank'], 2)

    def test_no_team_tie_breaks_keeps_tie_break_values_empty(self) -> None:
        """When no team tie-breaks are configured, tie_break_values is
        present but empty so consumers can iterate uniformly."""
        with EventDatabase(EVENT_ID, write=True) as db:
            tournament = next(
                t for t in db.load_stored_tournaments() if t.name == TOURNAMENT_NAME
            )
            tournament_id = tournament.id
            assert tournament_id is not None
            db.add_stored_team(
                StoredTeam(id=None, name='Empty', tournament_id=tournament_id)
            )

        tournament = self._load()
        standings = tournament.team_standings()
        self.assertEqual(len(standings), 1)
        self.assertEqual(standings[0]['tie_break_values'], [])
