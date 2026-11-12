"""The 310 record lists a team's players in its registration order,
whatever lineups it fields, and the 300 records give the lineup each
round actually fielded."""

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

EVENT_ID = 'test-trf-team-rosters'
TOURNAMENT_NAME = 'tournament'
BOARDS = 4
TEAMS = 4


@pytest.mark.unit
class TrfTeamRostersTestCase(TestCase):
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
                ids: list[int] = []
                for index in range(BOARDS):
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
                            pairing_number=(seed - 1) * BOARDS + index + 1,
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

    def _pair_and_play(self, round_: int) -> None:
        tournament = self._load()
        self.assertEqual(tournament.generate_round_pairings(round_), '')
        tournament = self._load()
        for board in tournament.get_round_boards(round_):
            tournament.add_result(board, Result.WIN)

    def _reverse_lineup(self, round_: int) -> None:
        tournament = self._load()
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament.event.teams_by_id[self.team_ids[0]].set_round_lineup(
                round_, list(reversed(self.player_ids[0])), database
            )

    def test_a_new_lineup_leaves_the_roster_and_the_past_rounds_alone(self) -> None:
        """Team1 fields its players in reverse order from round 2: the
        file the engine pairs round 2 from still lists them in their
        registration order, and says round 1 was played in it."""
        self._pair_and_play(1)
        self._reverse_lineup(2)
        trf = self._load().to_trf(after_round=1, for_engine=True)
        team_1 = next(team for team in trf.teams if team.id == 1)
        self.assertEqual(team_1.player_ids, [1, 2, 3, 4])
        round_1 = next(
            record
            for record in trf.oodo_team_pairings
            if record.round == 1 and record.team_id == 1
        )
        self.assertEqual(round_1.boards, [1, 2, 3, 4])

    def test_the_300_records_give_the_lineup_fielded(self) -> None:
        self._pair_and_play(1)
        self._reverse_lineup(2)
        self._pair_and_play(2)
        trf = self._load().to_trf(after_round=2, for_engine=True)
        team_1 = next(team for team in trf.teams if team.id == 1)
        self.assertEqual(team_1.player_ids, [1, 2, 3, 4])
        round_2 = next(
            record
            for record in trf.oodo_team_pairings
            if record.round == 2 and record.team_id == 1
        )
        self.assertEqual(round_2.boards, [4, 3, 2, 1])
