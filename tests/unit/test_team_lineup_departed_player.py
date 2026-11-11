"""A player who leaves a team is no longer seated by its lineups."""

import contextlib
from unittest import TestCase

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

EVENT_ID = 'test-team-lineup-departed-player'
TOURNAMENT_NAME = 'tournament'
BOARDS = 4
TEAMS = 4


@pytest.mark.unit
class TeamLineupDepartedPlayerTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        stored_tournament = TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 3,
                'team_player_count': BOARDS,
                'pairing': 'TEAM_SWISS_STANDARD',
            },
        )
        tournament_id = stored_tournament.id
        assert tournament_id is not None
        self.team_ids: list[int] = []
        self.player_ids: list[list[int]] = []
        with EventDatabase(EVENT_ID, write=True) as database:
            for seed in range(1, TEAMS + 1):
                team_id = database.add_stored_team(
                    StoredTeam(
                        id=None,
                        name=f'Team{seed}',
                        tournament_id=tournament_id,
                        pairing_number=seed,
                        check_in=True,
                    )
                )
                self.team_ids.append(team_id)
                # Team1 starts with a substitute, as a team of five.
                size = BOARDS + 1 if seed == 1 else BOARDS
                ids: list[int] = []
                for index in range(size):
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
                            pairing_number=len(self.player_ids) * 10 + index + 1,
                        )
                    )
                    ids.append(player_id)
                self.player_ids.append(ids)

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _load(self) -> Tournament:
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        # A Tournament holds its event weakly, so the event has to
        # outlive this call.
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    def _move_first_player_of_team_1_to_team_4(self) -> int:
        """Team1's round 2 lineup names its first four players; its first
        player then joins Team4."""
        tournament = self._load()
        team_1 = tournament.event.teams_by_id[self.team_ids[0]]
        moved_id = self.player_ids[0][0]
        with EventDatabase(EVENT_ID, write=True) as database:
            team_1.set_round_lineup(2, self.player_ids[0][:BOARDS], database)
        tournament = self._load()
        event = tournament.event
        with EventDatabase(EVENT_ID, write=True) as database:
            event.teams_by_id[self.team_ids[3]].add_player(
                event.players_by_id[moved_id], database
            )
        return moved_id

    def _pair_and_play_round_1(self) -> None:
        tournament = self._load()
        self.assertEqual(tournament.generate_round_pairings(1), '')
        tournament = self._load()
        for board in tournament.get_round_boards(1):
            tournament.add_result(board, Result.WIN)

    def test_the_departed_player_is_not_paired_for_the_team_left(self) -> None:
        self._pair_and_play_round_1()
        moved_id = self._move_first_player_of_team_1_to_team_4()
        tournament = self._load()
        self.assertEqual(tournament.generate_round_pairings(2), '')
        tournament = self._load()
        team_1_match = tournament.team_match_by_team_and_round[(self.team_ids[0], 2)]
        seated = {
            player_id
            for board in team_1_match.boards
            for player_id in (
                board.stored_board.white_player_id,
                board.stored_board.black_player_id,
            )
            if player_id is not None
        }
        # Team4 seats the players of its own round 1 boards, so the player
        # who joined it sits on its bench.
        self.assertNotIn(moved_id, seated)
        # Team1 leaves board 1 empty, and the board still belongs to the
        # two teams of the match.
        stored = team_1_match.stored_team_board
        board_1 = next(board for board in team_1_match.boards if board.index == 0)
        self.assertEqual(
            set(team_1_match.board_team_ids(board_1)),
            {stored.team_a_id, stored.team_b_id},
        )

    def test_the_lineup_left_behind_keeps_a_hole(self) -> None:
        self._pair_and_play_round_1()
        moved_id = self._move_first_player_of_team_1_to_team_4()
        team_1 = self._load().event.teams_by_id[self.team_ids[0]]
        entries = sorted(
            team_1.stored_team.stored_round_lineups[2], key=lambda entry: entry.index
        )
        self.assertEqual(
            [entry.player_id for entry in entries],
            [None, *self.player_ids[0][1:BOARDS]],
        )
        self.assertNotIn(moved_id, [entry.player_id for entry in entries])

    def test_a_player_removed_from_the_team_leaves_a_hole(self) -> None:
        tournament = self._load()
        team_1 = tournament.event.teams_by_id[self.team_ids[0]]
        with EventDatabase(EVENT_ID, write=True) as database:
            team_1.set_round_lineup(1, self.player_ids[0][:BOARDS], database)
        tournament = self._load()
        event = tournament.event
        with EventDatabase(EVENT_ID, write=True) as database:
            event.teams_by_id[self.team_ids[0]].remove_player(
                event.players_by_id[self.player_ids[0][1]], database
            )
        tournament = self._load()
        slots = tournament.event.teams_by_id[self.team_ids[0]].effective_round_slots(1)
        self.assertEqual(
            [player.id if player else None for player in slots],
            [self.player_ids[0][0], None, *self.player_ids[0][2:BOARDS]],
        )

    def test_the_lineup_left_behind_reads_as_a_hole(self) -> None:
        self._pair_and_play_round_1()
        moved_id = self._move_first_player_of_team_1_to_team_4()
        tournament = self._load()
        team_1 = tournament.event.teams_by_id[self.team_ids[0]]
        slots = team_1.effective_round_slots(2)
        self.assertNotIn(moved_id, {p.id for p in slots if p is not None})
