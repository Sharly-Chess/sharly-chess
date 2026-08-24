"""Team round-robin table (échiquier) order must match the advance
Berger schedule for every round.

The advance "round-robin schedule" document is built from the raw Berger
table (canonical team order). When rounds are actually paired, the table
order must stay identical to that document — even once standings diverge.
A Swiss-style "strongest match on table 1" re-sort would silently reorder
the tables from round 2 on; this test locks the round-robin order to the
Berger schedule instead.
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
from utils.enum import EventType, Result


EVENT_ID = 'test-team-rr-order'
TOURNAMENT_NAME = 'rr'
N = 2  # players per team
TEAMS = 4  # 4 teams -> 3 Berger rounds


@pytest.mark.unit
class TeamRoundRobinBoardOrderTestCase(TestCase):
    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _create(self) -> None:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': TEAMS - 1,
                'current_round': 1,
                'team_player_count': N,
                'pairing': 'TEAM_ROUND_ROBIN_BERGER',
            },
        )
        self.team_ids: list[int] = []
        with EventDatabase(EVENT_ID, write=True) as db:
            tournament = next(
                t for t in db.load_stored_tournaments() if t.name == TOURNAMENT_NAME
            )
            tid = tournament.id
            assert tid is not None
            for seed in range(1, TEAMS + 1):
                team_id = db.add_stored_team(
                    StoredTeam(
                        id=None,
                        name=f'Team{seed}',
                        tournament_id=tid,
                        pairing_number=seed,
                        check_in=True,
                    )
                )
                self.team_ids.append(team_id)
                for p_index in range(N):
                    pid = db.add_stored_player(
                        StoredPlayer(
                            id=None,
                            last_name=f'T{seed}P{p_index}',
                            team_id=team_id,
                            team_index=p_index,
                            check_in=True,
                        )
                    )
                    db.add_stored_tournament_player(
                        StoredTournamentPlayer(
                            tournament_id=tid, player_id=pid, pairing_number=p_index
                        )
                    )

    def _load(self):
        try:
            EventLoader.unload_event(EVENT_ID)
        except KeyError:
            pass
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    @staticmethod
    def _expected_order(schedule_round):
        """Advance-schedule order: real matches first, PAB (bye) last."""
        real = [p for p in schedule_round if p[1] is not None]
        byes = [p for p in schedule_round if p[1] is None]
        return real + byes

    @staticmethod
    def _actual_order(tournament, round_):
        boards = [
            tb
            for tb in tournament.get_round_team_boards(round_)
            if tb.index is not None
        ]
        boards.sort(key=lambda tb: tb.index)
        return [
            (tb.stored_team_board.team_a_id, tb.stored_team_board.team_b_id)
            for tb in boards
        ]

    @staticmethod
    def _win_for_team_a(tournament, round_) -> None:
        """Give team_a a clean sweep on every match this round so the
        standings diverge before the next round is paired."""
        with EventDatabase(tournament.event.uniq_id, write=True) as db:
            for tb in tournament.get_round_team_boards(round_):
                if tb.stored_team_board.team_b_id is None:
                    continue
                team_a_id = tb.stored_team_board.team_a_id
                for board in tb.boards:
                    for pairing in (
                        board.optional_white_pairing,
                        board.optional_black_pairing,
                    ):
                        if pairing is None:
                            continue
                        won = pairing.tournament_player.team_id == team_a_id
                        pairing.update_result(db, Result.WIN if won else Result.LOSS)

    def test_table_order_follows_advance_schedule_across_rounds(self):
        self._create()
        tournament = self._load()
        engine = tournament.pairing_variation.engine
        schedule = engine.full_schedule(tournament)
        self.assertEqual(sorted(schedule), [1, 2, 3])

        for round_ in (1, 2, 3):
            tournament = self._load()
            engine = tournament.pairing_variation.engine
            self.assertEqual(engine.generate_pairings(tournament, round_), '')
            tournament = self._load()

            self.assertEqual(
                self._actual_order(tournament, round_),
                self._expected_order(schedule[round_]),
                f'round {round_} table order diverged from the Berger schedule',
            )

            # Diverge standings so the next round would be re-sorted by a
            # Swiss-style "strongest match first" rule if one were applied.
            self._win_for_team_a(tournament, round_)
