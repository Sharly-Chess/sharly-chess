from unittest import TestCase

import pytest

from data.event import Event
from data.loader import EventLoader
from data.print_documents.documents import BergerGridPrintDocument
from data.print_documents.options import TournamentPrintOption
from data.tie_breaks.team_records import TeamMatchRecord, TeamMatchType, TeamRecord
from data.tie_breaks.team_tie_breaks import TeamTieBreakContext
from data.tie_breaks.tie_breaks import KoyaTieBreak
from tests.test_config import TestUtils
from utils.enum import Result, ScoreType

EVENT_ID = 'test-koya-round-robin-event'
TOURNAMENT_ID = 'test-koya-round-robin-tournament'


@pytest.mark.unit
class KoyaPossibleGamesTestCase(TestCase):
    """The Koya limit is half of what a participant can have scored: in a
    round-robin of an odd number of participants, each cycle gives every
    one of them a free round, which is not a game."""

    def test_any_system_but_a_round_robin_counts_every_round(self):
        self.assertEqual(KoyaTieBreak.possible_games(9, None), 9)

    def test_an_even_field_plays_every_round(self):
        self.assertEqual(KoyaTieBreak.possible_games(9, 10), 9)

    def test_an_odd_field_rests_once_per_cycle(self):
        self.assertEqual(KoyaTieBreak.possible_games(9, 9), 8)
        self.assertEqual(KoyaTieBreak.possible_games(18, 9), 16)

    def test_a_cycle_under_way_counts_its_rounds(self):
        self.assertEqual(KoyaTieBreak.possible_games(7, 9), 7)
        self.assertEqual(KoyaTieBreak.possible_games(12, 9), 11)


def _match(round_: int, opponent_id: int, own_mp: float) -> TeamMatchRecord:
    return TeamMatchRecord(
        round_=round_,
        opponent_id=opponent_id,
        own_mp=own_mp,
        own_gp=own_mp,
        match_type=TeamMatchType.PLAYED,
    )


@pytest.mark.unit
class TeamKoyaOddRoundRobinTestCase(TestCase):
    """Three teams play two matches each over three rounds: the limit is
    half of two matches, 2 match points, which the second team reaches."""

    def test_the_limit_counts_the_matches_a_team_can_play(self):
        records = {
            1: TeamRecord(1, 'A', 3.0, 3.0, [_match(1, 2, 2.0), _match(3, 3, 1.0)]),
            2: TeamRecord(2, 'B', 1.0, 1.0, [_match(1, 1, 0.0), _match(2, 3, 1.0)]),
            3: TeamRecord(3, 'C', 2.0, 2.0, [_match(2, 2, 1.0), _match(3, 1, 1.0)]),
        }
        context = TeamTieBreakContext(
            primary_score=ScoreType.MATCH_POINTS,
            secondary_score=ScoreType.GAME_POINTS,
            rounds=3,
            win_mp=2.0,
            draw_mp=1.0,
            loss_mp=0.0,
            team_player_count=1,
            draw_gp=0.5,
            predetermined_pairings=True,
            round_robin_field=3,
        )
        tie_break = KoyaTieBreak()
        values = {
            team_id: tie_break.compute_team_value(
                record, records, context, after_round=3
            )
            for team_id, record in records.items()
        }
        self.assertEqual(values, {1: 1.0, 2: 1.0, 3: 1.0})


@pytest.mark.unit
class BergerGridRankingRoundTestCase(TestCase):
    """The Berger grid ranks the players as the standings do, after the
    last finished round, though the later rounds are already paired."""

    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID, json_file='manual-koya')
        tournament = self._load()
        for round_ in (6, 7):
            for board in tournament.get_round_boards(round_):
                if board.black_tournament_player is not None:
                    tournament.add_result(board, Result.NO_RESULT)
        tournament.set_published_round(5)

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _load(self):
        # The tournament keeps only a weak reference to its event.
        self._event: Event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_ID]

    def test_the_grid_shows_the_tie_breaks_of_the_standings(self):
        tournament = self._load()
        self.assertEqual(tournament.max_ranking_round, 5)
        standings = {
            player.id: [str(value) for value in player.tie_break_values]
            for player in tournament.compute_tournament_player_ranks().values()
        }

        tournament = self._load()
        document = BergerGridPrintDocument(
            options=[TournamentPrintOption(self._event, tournament.id)]
        )
        document.event = self._event
        context = document.template_context
        grid = {
            player.id: [str(value) for value in player.tie_break_values]
            for player in context['tournament'].tournament_players
        }
        self.assertEqual(tournament.ranking.after_round, 5)
        self.assertEqual(grid, standings)
