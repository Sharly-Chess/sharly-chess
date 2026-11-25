"""A team can be pinned to a table number, as a player can be in an
individual tournament.

The pinned match keeps that table every round it is paired, whatever its
opponent or its standing. The number is written onto the team board when the
round is paired, so changing a team's fixed table renumbers only the rounds
paired afterwards — never the ones already played.
"""

import contextlib
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


EVENT_ID = 'test-team-fixed-table'
TOURNAMENT_NAME = 'swiss'
N = 2  # players per team
TEAMS = 4


@pytest.mark.unit
class TeamFixedTableTestCase(TestCase):
    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _create(self) -> None:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 3,
                'team_player_count': N,
                'pairing': 'TEAM_SWISS_STANDARD',
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
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    @staticmethod
    def _table_of_team(tournament, round_, team_id) -> int | None:
        """The displayed table number of the match ``team_id`` plays this
        round, or ``None`` when it has no numbered match."""
        for tb in tournament.get_round_team_boards(round_):
            if tb.index is None:
                continue
            stb = tb.stored_team_board
            if team_id in (stb.team_a_id, stb.team_b_id):
                return tb.display_number
        return None

    @staticmethod
    def _set_fixed(tournament, team_id, value) -> None:
        with EventDatabase(tournament.event.uniq_id, write=True) as db:
            team = tournament.event.teams_by_id[team_id]
            team.stored_team.fixed = value
            team.update(db)

    @staticmethod
    def _finish_round(tournament, round_) -> None:
        """Enter a result on every board so the next Swiss round can pair."""
        with EventDatabase(tournament.event.uniq_id, write=True) as db:
            for tb in tournament.get_round_team_boards(round_):
                for board in tb.boards:
                    for pairing in (
                        board.optional_white_pairing,
                        board.optional_black_pairing,
                    ):
                        if pairing is not None:
                            pairing.update_result(db, Result.DRAW)

    def test_fixed_table_held_and_change_does_not_renumber_past_round(self):
        self._create()

        # Pin the fourth seed to table 1. Swiss orders the strongest match
        # onto table 1, so without the pin seed 4 would not land there.
        tournament = self._load()
        pinned = self.team_ids[3]
        self._set_fixed(tournament, pinned, 1)

        tournament = self._load()
        engine = tournament.pairing_variation.engine
        self.assertEqual(engine.generate_pairings(tournament, 1), '')
        tournament = self._load()
        self.assertEqual(
            self._table_of_team(tournament, 1, pinned),
            1,
            'the pinned team should play at its fixed table in round 1',
        )
        # Every table number is still present exactly once (no hole, no
        # duplicate): four teams make two matches, numbered 1 and 2.
        self.assertEqual(
            sorted(
                tb.display_number
                for tb in tournament.get_round_team_boards(1)
                if tb.index is not None
            ),
            [1, 2],
        )

        # Move the pin to table 2 before pairing round 2.
        self._finish_round(tournament, 1)
        tournament = self._load()
        self._set_fixed(tournament, pinned, 2)
        tournament = self._load()
        engine = tournament.pairing_variation.engine
        self.assertEqual(engine.generate_pairings(tournament, 2), '')
        tournament = self._load()

        # Round 2 honours the new table…
        self.assertEqual(self._table_of_team(tournament, 2, pinned), 2)
        # …while round 1, already paired, keeps the old one.
        self.assertEqual(self._table_of_team(tournament, 1, pinned), 1)

    def test_both_teams_fixed_takes_the_higher_table(self):
        self._create()
        tournament = self._load()
        engine = tournament.pairing_variation.engine
        team_a, team_b = self.team_ids[0], self.team_ids[1]
        self._set_fixed(tournament, team_a, 2)
        self._set_fixed(tournament, team_b, 5)
        tournament = self._load()
        engine = tournament.pairing_variation.engine
        self.assertEqual(engine._match_fixed_table(tournament, (team_a, team_b)), 5)
        # A bye envelope (no opponent) is never pinned.
        self.assertIsNone(engine._match_fixed_table(tournament, (team_a, None)))
