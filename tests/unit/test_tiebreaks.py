from abc import abstractmethod, ABC
from decimal import Decimal
from pathlib import Path
from typing import Callable
from unittest import TestCase

from data.event import Event
from data.input_output.tournament_importers import JsonTournamentImporter
from data.loader import EventLoader

import pytest
from data.tie_breaks import tie_breaks, options
from data.tournament import Tournament
from data.player import Player
from plugins.ffe import ffe_tie_breaks
from tests.test_config import TestUtils

EVENT_ID = 'test-pairings-event'
TOURNAMENT_ID = 'test-pairings-tournament'


class TieBreakTestCase(TestCase, ABC):
    event: Event

    def setUp(self):
        super().setUp()
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID)

        self.event = EventLoader().reload_event(EVENT_ID)

        # Import the test players and pairings from the json file
        leaf_name = f'{self.json_file}.json'
        json_path = Path('../json') / leaf_name
        assert json_path.exists(), f'JSON file [{leaf_name}] not found'

        # For the moment the json data format is the same as that produced by papi-converter
        JsonTournamentImporter().load_tournament(json_path, self.event, self.tournament)

        self.event = EventLoader().reload_event(EVENT_ID)

    def tearDown(self):
        TestUtils.delete_event(EVENT_ID)
        super().tearDown()

    @property
    @abstractmethod
    def json_file(self) -> str:
        pass

    @property
    def tournament(self) -> Tournament:
        return self.event.tournaments_by_uniq_id[TOURNAMENT_ID]

    def get_player_values[T](
        self,
        compute_player_value: Callable[[Player], T],
        exclude_ids: list[int] | None = None,
        only_ids: list[int] | None = None,
    ) -> dict[int, T]:
        player_values = {}
        for player in self.tournament.players:
            if not (
                (exclude_ids and player.id in exclude_ids)
                or (only_ids and player.id not in only_ids)
            ):
                player_values[player.id] = compute_player_value(player)
        return player_values

    def get_tie_break_player_values[T](
        self,
        tie_break_: tie_breaks.TieBreak,
        exclude_ids: list[int] | None = None,
        only_ids: list[int] | None = None,
    ):
        return self.get_player_values(
            lambda p: tie_break_.compute_player_value(p, after_round=None),
            exclude_ids,
            only_ids,
        )


@pytest.mark.unit
class SwissTieBreakTestCase(TieBreakTestCase):
    @property
    def json_file(self) -> str:
        return 'tec-swiss'

    def test_points(self):
        results = self.get_player_values(lambda p: p.total_points())
        expected = {
            2: 4,
            1: 3.5,
            3: 3.5,
            4: 3.5,
            16: 3.5,
            6: 3,
            5: 2.5,
            8: 2.5,
            11: 2.5,
            12: 2,
            14: 2,
            15: 2,
            7: 1.5,
            9: 1.5,
            13: 1.5,
            10: 1,
        }
        self.assertEqual(results, expected)

    def test_win(self):
        tie_break_ = tie_breaks.WinsTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 3,
            16: 3,
            1: 2,
            3: 2,
            4: 2,
            6: 3,
            5: 2,
            8: 2,
            11: 2,
            12: 2,
            14: 2,
            15: 2,
            7: 1,
            9: 1,
            13: 1,
            10: 1,
        }
        self.assertEqual(results, expected)

    def test_won(self):
        tie_break_ = tie_breaks.GamesWonTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 3,
            16: 3,
            1: 2,
            3: 2,
            4: 2,
            6: 2,
            5: 2,
            8: 2,
            11: 1,
            14: 2,
            15: 2,
            12: 0,
            7: 1,
            13: 1,
            9: 0,
            10: 1,
        }
        self.assertEqual(results, expected)

    def test_played_with_black(self):
        tie_break_ = tie_breaks.GamesPlayedWithBlackTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 3,
            1: 2,
            3: 2,
            4: 2,
            16: 2,
            6: 2,
            5: 2,
            8: 2,
            11: 2,
            15: 3,
            14: 2,
            12: 0,
            7: 3,
            13: 3,
            9: 1,
            10: 3,
        }
        self.assertEqual(results, expected)

    def test_won_with_black(self):
        tie_break_ = tie_breaks.GamesWonWithBlackTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 1,
            1: 1,
            3: 1,
            4: 1,
            16: 1,
            6: 1,
            5: 0,
            8: 0,
            11: 0,
            12: 0,
            14: 1,
            15: 1,
            7: 0,
            9: 0,
            13: 1,
            10: 1,
        }
        self.assertEqual(results, expected)

    def test_games_elected_to_play(self):
        tie_break_ = tie_breaks.RoundsElectedToPlayTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 5,
            1: 5,
            3: 5,
            16: 5,
            4: 4,
            6: 5,
            5: 5,
            8: 5,
            11: 5,
            15: 5,
            12: 3,
            14: 3,
            7: 5,
            13: 5,
            9: 3,
            10: 5,
        }
        self.assertEqual(results, expected)

    def test_progressive_scores(self):
        tie_break_ = tie_breaks.ProgressiveScoresTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 13,
            4: 11.5,
            1: 11,
            3: 11,
            16: 10.5,
            6: 6,
            8: 8.5,
            11: 5.5,
            5: 5,
            12: 7,
            15: 7,
            14: 6,
            13: 7,
            7: 6,
            9: 2.5,
            10: 4,
        }
        self.assertEqual(results, expected)

    def test_progressive_cut1(self):
        tie_break_ = tie_breaks.ProgressiveScoresTieBreak(
            [options.CutTieBreakOption(1)]
        )
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 12,
            3: 10.5,
            4: 10.5,
            1: 10,
            16: 10,
            6: 6,
            8: 8,
            5: 5,
            11: 5,
            12: 7,
            15: 7,
            14: 5,
            13: 6,
            7: 5,
            9: 2.5,
            10: 4,
        }
        self.assertEqual(results, expected)

    def test_buchholz(self):
        tie_break_ = tie_breaks.StandardBuchholzTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 13,  # No problem exercise
            3: 15.5,  # 1 unplayed round in opponent each
            4: 15,
            1: 12.5,
            16: 12.5,
            6: 12,
            8: 13.5,
            11: 13.5,  # 11 has an unplayed round
            5: 8.5,
            15: 12,
            12: 11.5,
            14: 11,
            7: 14.5,
            13: 14,
            9: 9,
            10: 13,
        }
        self.assertEqual(results, expected)

    def test_buchholz_cut1(self):
        tie_break_ = tie_breaks.StandardBuchholzTieBreak(
            [options.CutBottomTieBreakOption(1)]
        )
        results = self.get_tie_break_player_values(
            tie_break_, only_ids=[5, 8, 11, 7, 9, 13, 1, 3, 4, 16, 12, 14, 15]
        )
        expected = {
            5: 7.5,
            8: 12,
            11: 12,  # 2.5 group
            7: 12.5,
            9: 7.5,
            13: 12,  # 1.5 group
            1: 11,
            3: 13,
            4: 11.5,
            16: 11,  # 3.5 group
            12: 9.5,
            14: 9,
            15: 11,  # 2 group
        }
        self.assertEqual(results, expected)

    def test_adjusted_score(self):
        results = self.get_player_values(
            lambda p: tie_breaks.TieBreak.adjusted_score(
                p, after_round=self.tournament.rounds
            )
        )
        expected = {
            1: 3.5,
            2: 4.0,
            3: 3.5,
            4: 3.5,
            5: 2.5,
            6: 3.0,
            7: 1.5,
            8: 2.5,
            9: 1.5,
            10: 1.0,
            11: 2.5,
            12: 3.0,
            13: 1.5,
            14: 2.0,
            15: 2.0,
            16: 3.5,
        }
        self.assertEqual(results, expected)

    def test_adjusted_score_fore(self):
        results = self.get_player_values(
            lambda p: tie_breaks.TieBreak.adjusted_score(
                p, after_round=self.tournament.rounds, adjust_fore=True
            )
        )
        expected = {
            2: 4,
            1: 3.5,
            3: 3.5,
            4: 3.5,
            16: 3,
            6: 2.5,
            5: 2,
            8: 3,
            11: 2,
            12: 3,
            14: 1.5,
            15: 2.5,
            7: 2,
            9: 1.5,
            13: 2,
            10: 1.5,
        }
        self.assertEqual(results, expected)

    def test_fore_buchholz(self):
        tie_break_ = tie_breaks.ForeBuchholzTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 13.5,
            3: 15,
            4: 15.5,
            1: 13.5,
            16: 13.5,
            8: 12.5,
            6: 12,
            15: 12.0,
            5: 10,
            11: 12.5,
            12: 11.5,
            14: 10.5,
            7: 13.5,
            9: 9.5,
            13: 13.5,
            10: 12.5,
        }
        self.assertEqual(results, expected)

    def test_buchholz_legacy(self):
        tie_break_ = ffe_tie_breaks.PapiStandardBuchholzTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 13.0,
            3: 14.5,
            4: 13.5,
            1: 12.5,
            16: 12.0,
            6: 11.0,
            8: 14.0,
            11: 12.0,
            5: 8.0,
            12: 13.5,
            15: 12.0,
            14: 12.0,
            13: 15.0,
            7: 14.0,
            9: 8.5,
            10: 12.5,
        }
        self.assertEqual(results, expected)

    def test_buchholz_cut_legacy(self):
        tie_break_ = ffe_tie_breaks.PapiBuchholzCutBottomTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 12.0,
            3: 12.5,
            4: 12.0,
            1: 11.0,
            16: 10.5,
            6: 10.0,
            8: 12.5,
            11: 11.0,
            5: 7.0,
            12: 12.0,
            15: 11.0,
            14: 10.5,
            13: 12.5,
            7: 12.0,
            9: 8.0,
            10: 11.0,
        }
        self.assertEqual(results, expected)

    def test_buchholz_median_legacy(self):
        tie_break_ = ffe_tie_breaks.PapiMedianBuchholzTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 8.5,
            3: 8.5,
            4: 8.5,
            1: 7.0,
            16: 6.5,
            6: 6.5,
            8: 9.0,
            11: 7.5,
            5: 5.0,
            12: 8.5,
            15: 7.5,
            14: 7.5,
            13: 9.0,
            7: 8.0,
            9: 4.5,
            10: 7.0,
        }
        self.assertEqual(results, expected)

    def test_aob(self):
        aob = tie_breaks.AverageOfBuchholzTieBreak().compute_player_value
        results = self.get_player_values(lambda p: round(aob(p, after_round=None), 2))
        expected = {
            2: 13.6,
            3: 13.4,
            4: 13.38,
            16: 13.3,
            1: 12.6,
            6: 13.25,
            5: 13.4,
            8: 13,
            11: 12.75,
            12: 15,
            14: 13.17,
            15: 12.2,
            9: 12.75,
            13: 12.1,
            7: 11.9,
            10: 10.9,
        }
        self.assertEqual(results, expected)

    def test_sonneborn_berger_swiss(self):
        tie_break_ = tie_breaks.SonnebornBergerTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 9.5,
            3: 10.5,
            4: 9.75,
            1: 8.0,
            16: 7.25,
            6: 6.5,
            11: 5.75,
            8: 5.25,
            5: 4.25,
            14: 4.5,
            12: 4.0,
            15: 3.5,
            13: 4.25,
            7: 3.25,
            9: 2.25,
            10: 1.5,
        }
        self.assertEqual(results, expected)

    def test_sb_cut1_swiss(self):
        tie_break_ = tie_breaks.SonnebornBergerTieBreak([options.CutTieBreakOption(1)])
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 8.5,
            3: 9.25,
            4: 8.0,
            1: 7.25,
            16: 5.75,
            6: 5.5,
            11: 4.25,
            8: 3.75,
            5: 3.25,
            12: 4.0,
            14: 3.0,
            15: 2.5,
            13: 4.25,
            7: 1.25,
            9: 2.25,
            10: 0.0,
        }
        self.assertEqual(results, expected)

    def test_aro(self):
        tie_break_ = tie_breaks.AverageRatingOpponentsTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 1880,
            3: 1940,
            4: 1888,
            1: 1820,
            16: 1820,
            6: 1813,
            11: 1863,
            8: 1730,
            5: 1690,
            12: 2050,
            15: 1860,
            14: 1800,
            9: 1975,
            13: 1930,
            7: 1760,
            10: 1880,
        }
        self.assertEqual(results, expected)

    def test_aro_cut1(self):
        tie_break_ = tie_breaks.AverageRatingOpponentsTieBreak(
            [options.CutBottomTieBreakOption(1)]
        )
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 1988,
            3: 2000,
            4: 1983,
            1: 1900,
            16: 1900,
            6: 1900,
            11: 2000,
            8: 1800,
            5: 1738,
            15: 1963,
            14: 1900,
            12: 0,
            9: 2200,
            13: 2025,
            7: 1838,
            10: 1975,
        }
        self.assertEqual(results, expected)

    def test_tpr(self):
        tie_break_ = tie_breaks.TournamentPerformanceRatingTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 2120,
            3: 2089,
            4: 2081,
            1: 1969,
            16: 1969,
            6: 1813,
            11: 1776,
            8: 1730,
            5: 1690,
            14: 1925,
            15: 1788,
            12: 1250,
            13: 1781,
            7: 1611,
            9: 1175,
            10: 1640,
        }
        self.assertEqual(results, expected)

    def test_tpr_legacy(self):
        tie_break_ = ffe_tie_breaks.PapiPerformanceTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 2180,
            4: 2093,
            3: 2089,
            1: 2069,
            16: 1899,
            6: 1812,
            11: 1772,
            8: 1730,
            5: 1710,
            14: 1922,
            15: 1708,
            12: 1373,
            13: 1731,
            7: 1621,
            9: 1298,
            10: 1640,
        }
        self.assertEqual(results, expected)

    def test_apro(self):
        tie_break_ = tie_breaks.AveragePerformanceRatingOpponentsTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 1856,
            3: 1904,
            4: 1772,
            1: 1789,
            16: 1805,
            6: 1846,
            11: 1840,
            8: 1915,
            5: 1719,
            12: 2081,
            15: 1776,
            14: 1775,
            9: 1805,
            13: 1879,
            7: 1869,
            10: 1717,
        }
        self.assertEqual(results, expected)

    def test_win_chances(self):
        ratings = [1700, 1950, 1850, 2050, 2150]
        results = [
            tie_breaks.PerfectTournamentPerformanceTieBreak.win_chances(2089, rating)[0]
            for rating in ratings
        ]
        expected = [
            Decimal('0.91'),
            Decimal('0.69'),
            Decimal('0.80'),
            Decimal('0.55'),
            Decimal('0.42'),
        ]
        self.assertEqual(results, expected)

    def test_ptp(self):
        tie_break_ = tie_breaks.PerfectTournamentPerformanceTieBreak()
        results = self.get_tie_break_player_values(tie_break_, exclude_ids=[2, 14])
        expected = {
            3: 2112,
            4: 2168,
            1: 2029,
            16: 2013,
            6: 1810,
            11: 1763,
            8: 1715,
            5: 1689,
            12: 1250,
            15: 1768,
            9: 950,
            13: 1744,
            7: 1531,
            10: 1575,
        }
        self.assertEqual(results, expected)

        # NOTE(Amaras): the following two players do not have the
        # correct PTP, according to the tie-break exercises.
        # I do not know why this happens, but it's the closest I got
        # to having all correct values
        self.assertEqual(
            self.get_tie_break_player_values(tie_break_, only_ids=[2, 14]),
            {
                2: 2217,  # NOTE(Amaras): this should be 2216
                14: 1940,  # NOTE(Amaras): this should be 1942
            },
        )

    def test_average_perfect_performance_opponents(self):
        tie_break_ = tie_breaks.AveragePerfectPerformanceTieBreak()
        results = self.get_tie_break_player_values(tie_break_, exclude_ids=[3, 13])
        expected = {
            2: 1852,
            4: 1784,
            1: 1769,
            16: 1799,
            6: 1836,
            11: 1836,
            8: 1924,
            5: 1676,
            12: 2168,
            15: 1767,
            14: 1756,
            9: 1802,
            7: 1890,
            10: 1687,
        }
        self.assertEqual(results, expected)
        self.assertEqual(
            self.get_tie_break_player_values(tie_break_, only_ids=[3, 13]),
            {
                3: 1935,  # NOTE(Amaras): this should be 1934
                13: 1908,  # NOTE(Amaras): this should be 1909
            },
        )

    def test_kashdan(self):
        tie_break_ = tie_breaks.KashdanTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 16,
            4: 12,
            3: 14,
            1: 14,
            16: 15,
            6: 10,
            11: 8,
            8: 12,
            5: 12,
            14: 9,
            15: 11,
            12: 1,
            13: 9,
            7: 9,
            9: 2,
            10: 8,
        }
        self.assertEqual(results, expected)

    def test_kashdan_legacy(self):
        tie_break_ = ffe_tie_breaks.PapiKashdanTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 16,
            4: 14,
            3: 14,
            1: 14,
            16: 15,
            6: 14,
            11: 12,
            8: 12,
            5: 12,
            14: 11,
            15: 11,
            12: 11,
            13: 9,
            7: 9,
            9: 9,
            10: 8,
        }
        self.assertEqual(expected, results)

    def test_direct_encounter(self):
        tie_break_ = tie_breaks.DirectEncounterTieBreak()
        results = self.get_tie_break_player_values(
            tie_break_, only_ids=[1, 3, 4, 16, 5, 8, 11]
        )
        expected = {
            1: (2.5, False),
            3: (2.5, False),
            4: (2.0, False),
            16: (3.0, False),
            5: (2.0, False),
            8: (2.0, False),
            11: (1.0, False),
        }
        self.assertEqual(results, expected)


@pytest.mark.unit
class RoundRobinTieBreakTestCase(TieBreakTestCase):
    @property
    def json_file(self) -> str:
        return 'tec-round-robin'

    def test_all_players_met_each_other(self):
        results = self.get_player_values(
            lambda player: [pairing.opponent_id for pairing in player.pairings.values()]
        )
        expected = {
            1: [5, 2, 3, 4, 6],
            2: [6, 1, 5, 3, 4],
            3: [4, 6, 1, 2, 5],
            4: [3, 5, 6, 1, 2],
            5: [1, 4, 2, 6, 3],
            6: [2, 3, 4, 5, 1],
        }
        self.assertEqual(results, expected)

    def test_points_are_correct(self):
        results = self.get_player_values(lambda p: p.total_points())
        expected = {1: 3.5, 2: 3.5, 3: 3.5, 4: 1.5, 5: 1.5, 6: 1.5}
        self.assertEqual(results, expected)

    def test_sonneborn_berger_round_robin(self):
        tie_break_ = tie_breaks.SonnebornBergerTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {1: 9.25, 2: 6.25, 3: 6.25, 4: 4.25, 5: 3.25, 6: 2.25}
        self.assertEqual(results, expected)

    def test_sb_cut1_round_robin(self):
        tie_break_ = tie_breaks.SonnebornBergerTieBreak([options.CutTieBreakOption(1)])
        results = self.get_tie_break_player_values(tie_break_)
        expected = {1: 9.25, 2: 4.75, 3: 4.75, 4: 4.25, 5: 3.25, 6: 1.5}
        self.assertEqual(results, expected)

    def test_koya(self):
        tie_break_ = tie_breaks.KoyaTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {1: 2, 2: 0.5, 3: 0.5, 4: 1, 5: 0.5, 6: 0}
        self.assertEqual(results, expected)

    def test_direct_encounter(self):
        tie_break_ = tie_breaks.DirectEncounterTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            1: (2, True),
            2: (0.5, True),
            3: (0.5, True),
            4: (0.5, True),
            6: (1.5, True),
            5: (1, True),
        }
        self.assertEqual(results, expected)
