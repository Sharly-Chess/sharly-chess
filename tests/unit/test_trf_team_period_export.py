"""The TRF of one period of a team tournament reported in periods.

A team file names its teams, their rosters and their matches, so a
report covering part of the tournament windows all three: the teams that
played in it, numbered from 1, the players they fielded there, and the
match points those rounds were worth.

An interclubs season reported one round at a time is the case
<https://ratings.fide.com/tournament_src_report.phtml?code=441469>.
"""

import contextlib
from datetime import datetime, timedelta

import pytest

from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredBoard,
    StoredPairing,
    StoredPlayer,
    StoredTeam,
    StoredTeamBoard,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import EventType, Result

EVENT_ID = 'test-trf-team-period-export'
TOURNAMENT_NAME = 'tournament'

# Rounds 1-2 hold two matches, rounds 3-4 only Alpha against Bravo, and
# Alpha swaps A2 for A3 on board 2 for them.
MATCHES = {
    1: (('Alpha', 'Bravo'), ('Charlie', 'Delta')),
    2: (('Alpha', 'Bravo'), ('Charlie', 'Delta')),
    3: (('Alpha', 'Bravo'),),
    4: (('Alpha', 'Bravo'),),
}
LINEUPS = {
    'Alpha': {1: ('A1', 'A2'), 2: ('A1', 'A2'), 3: ('A1', 'A3'), 4: ('A1', 'A3')},
    'Bravo': dict.fromkeys(range(1, 5), ('B1', 'B2')),
    'Charlie': dict.fromkeys(range(1, 3), ('C1', 'C2')),
    'Delta': dict.fromkeys(range(1, 3), ('D1', 'D2')),
}
ROSTERS = {
    'Alpha': ('A1', 'A2', 'A3'),
    'Bravo': ('B1', 'B2'),
    'Charlie': ('C1', 'C2'),
    'Delta': ('D1', 'D2'),
}


@pytest.mark.unit
class TestTeamPeriodTrf:
    def teardown_method(self):
        TestUtils.delete_event(EVENT_ID)

    def _setup(self):
        """Four teams over four rounds, cut after round 2, the home team
        winning every board."""
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 4,
                'team_player_count': 2,
                'pairing': 'TEAM_SWISS_STANDARD',
                'multi_period': True,
                'round_datetimes': {
                    round_nb: datetime.now() + timedelta(days=14 * (round_nb - 4))
                    for round_nb in range(1, 5)
                },
            },
        )
        with EventDatabase(EVENT_ID, write=True) as database:
            tournament_id = next(
                stored.id
                for stored in database.load_stored_tournaments()
                if stored.name == TOURNAMENT_NAME
            )
            assert tournament_id is not None
            database.set_tournament_periods(tournament_id, [3])
            team_ids: dict[str, int] = {}
            player_ids: dict[str, int] = {}
            for number, (team_name, roster) in enumerate(ROSTERS.items(), start=1):
                team_ids[team_name] = database.add_stored_team(
                    StoredTeam(
                        id=None,
                        name=team_name,
                        tournament_id=tournament_id,
                        pairing_number=number,
                    )
                )
                for index, player_name in enumerate(roster, start=1):
                    player_ids[player_name] = database.add_stored_player(
                        StoredPlayer(
                            id=None,
                            last_name=player_name,
                            team_id=team_ids[team_name],
                            team_index=index,
                            check_in=True,
                        )
                    )
                    database.add_stored_tournament_player(
                        StoredTournamentPlayer(
                            tournament_id=tournament_id,
                            player_id=player_ids[player_name],
                            pairing_number=len(player_ids),
                        )
                    )
            for round_nb, matches in MATCHES.items():
                for index, (home, away) in enumerate(matches):
                    team_board_id = database.add_stored_team_board(
                        StoredTeamBoard(
                            id=None,
                            tournament_id=tournament_id,
                            round_=round_nb,
                            team_a_id=team_ids[home],
                            team_b_id=team_ids[away],
                            index=index,
                        )
                    )
                    for board, (white, black) in enumerate(
                        zip(
                            LINEUPS[home][round_nb],
                            LINEUPS[away][round_nb],
                            strict=True,
                        )
                    ):
                        board_id = database.add_stored_board(
                            StoredBoard(
                                id=None,
                                white_player_id=player_ids[white],
                                black_player_id=player_ids[black],
                                index=board,
                                team_board_id=team_board_id,
                            )
                        )
                        for name, result in ((white, Result.WIN), (black, Result.LOSS)):
                            database.add_stored_pairing(
                                StoredPairing(
                                    tournament_id=tournament_id,
                                    player_id=player_ids[name],
                                    round_=round_nb,
                                    result=result.value,
                                    board_id=board_id,
                                )
                            )
        return self._load()

    def _load(self):
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    @staticmethod
    def _roster_names(trf, team):
        names = {player.id: player.name for player in trf.players}
        return [names[player_id] for player_id in team.player_ids]

    def test_the_file_holds_the_whole_field(self):
        """Charlie and Delta sat rounds 3 and 4 out, and are in the file
        all the same: it describes the tournament, and says of those two
        only that they played nothing in the period."""
        tournament = self._setup()
        trf = tournament.to_trf(period=tournament.periods[1])
        assert trf.num_teams == 4
        assert sorted(team.name for team in trf.teams) == [
            'Alpha',
            'Bravo',
            'Charlie',
            'Delta',
        ]
        charlie = next(team for team in trf.teams if team.name == 'Charlie')
        assert (charlie.match_points, charlie.game_points) == (0.0, 0.0)

    def test_the_teams_keep_the_numbers_the_tournament_gave_them(self):
        tournament = self._setup()
        trf = tournament.to_trf(period=tournament.periods[1])
        assert sorted(team.id for team in trf.teams) == [1, 2, 3, 4]

    def test_a_roster_lists_the_whole_roster(self):
        """A2 played rounds 1 and 2 and A3 rounds 3 and 4; the roster the
        file carries is the team's, substitutes included."""
        tournament = self._setup()
        trf = tournament.to_trf(period=tournament.periods[1])
        alpha = next(team for team in trf.teams if team.name == 'Alpha')
        assert sorted(self._roster_names(trf, alpha)) == ['A1', 'A2', 'A3']

    def test_the_match_points_are_the_period_s_own(self):
        """Alpha won all four boards of the period: two match wins, not
        the four it holds over the tournament."""
        tournament = self._setup()
        trf = tournament.to_trf(period=tournament.periods[1])
        alpha = next(team for team in trf.teams if team.name == 'Alpha')
        bravo = next(team for team in trf.teams if team.name == 'Bravo')
        assert (alpha.match_points, alpha.game_points) == (4.0, 4.0)
        assert (bravo.match_points, bravo.game_points) == (0.0, 0.0)
        assert (alpha.rank, bravo.rank) == (1, 2)

    def test_the_matches_keep_the_rounds_they_were_played_at(self):
        tournament = self._setup()
        trf = tournament.to_trf(period=tournament.periods[1])
        assert trf.num_rounds == 4
        assert {record.round for record in trf.oodo_team_pairings} == {3, 4}

    def test_every_team_answers_for_the_period(self):
        """801 and 802 carry one row per team of the tournament, the
        rounds outside the period left blank."""
        tournament = self._setup()
        trf = tournament.to_trf(period=tournament.periods[1])
        assert len(trf.informative_team_pairings_records) == 4
        assert len(trf.informative_team_results_records) == 4

    def test_the_whole_tournament_is_still_exported_in_full(self):
        tournament = self._setup()
        trf = tournament.to_trf()
        assert trf.num_teams == 4
        assert trf.num_rounds == 4
        alpha = next(team for team in trf.teams if team.name == 'Alpha')
        assert (alpha.match_points, alpha.game_points) == (8.0, 8.0)
