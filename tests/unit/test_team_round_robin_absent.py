"""Team round-robin pairs every team from the fixed Berger schedule —
including teams that are not checked in. An absent team must get its
scheduled match, not a zero-point-bye envelope.
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


EVENT_ID = 'test-team-rr-absent'
TOURNAMENT_NAME = 'rr'
N = 2  # players per team
TEAMS = 4  # 4 teams -> 3 Berger rounds


@pytest.mark.unit
class TeamRoundRobinAbsentTestCase(TestCase):
    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _create(self, with_players: bool = True, single_player: bool = False) -> None:
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
                # The 4th team is absent (not checked in).
                team_id = db.add_stored_team(
                    StoredTeam(
                        id=None,
                        name=f'Team{seed}',
                        tournament_id=tid,
                        pairing_number=seed,
                        check_in=seed != TEAMS,
                    )
                )
                self.team_ids.append(team_id)
                if not with_players:
                    continue
                # single_player: give exactly one player to the first
                # team, the rest empty (4 teams, 1 player total).
                team_player_count = (
                    1 if single_player and seed == 1 else 0 if single_player else N
                )
                for p_index in range(team_player_count):
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

    def test_absent_team_is_paired_not_zpb(self):
        self._create()
        tournament = self._load()
        assert (
            tournament.pairing_variation.engine.generate_pairings(tournament, 1) == ''
        )

        team_boards = tournament.get_round_team_boards(1)
        # 4 teams -> 2 real matches, every team on a board, no bye envelope.
        real = [tb for tb in team_boards if tb.stored_team_board.team_b_id is not None]
        byes = [tb for tb in team_boards if tb.stored_team_board.team_b_id is None]
        assert len(real) == 2
        assert byes == []

        absent_team_id = self.team_ids[-1]
        on_board = {
            stb_id
            for tb in real
            for stb_id in (
                tb.stored_team_board.team_a_id,
                tb.stored_team_board.team_b_id,
            )
        }
        assert absent_team_id in on_board

    def test_empty_rosters_still_read_as_paired(self):
        # Teams exist but none have any players. Pairing persists team
        # match envelopes of pure holes and there are no player pairings,
        # yet the round must still read as paired from the envelopes
        # (unpair button shown, not the pair button).
        self._create(with_players=False)
        tournament = self._load()
        assert tournament.player_count == 0
        assert (
            tournament.pairing_variation.engine.generate_pairings(tournament, 1) == ''
        )
        assert tournament.round_has_pairings(1)
        assert tournament.has_pairings

    def test_partial_rosters_read_as_paired(self):
        # 4 teams, a single player across them all. Pairing is allowed
        # (partial rosters leave holes). The round has team matches but
        # the lone player may sit on a board whose opponent is a hole, so
        # no player pairing exists — the round must still read as paired
        # (unpair button shown, not the pair button).
        self._create(single_player=True)
        tournament = self._load()
        assert tournament.player_count == 1
        assert (
            tournament.pairing_variation.engine.generate_pairings(tournament, 1) == ''
        )
        assert tournament.round_has_pairings(1)
        assert tournament.has_pairings
