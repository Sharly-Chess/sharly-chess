from abc import abstractmethod, ABC
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from collections.abc import Callable
from unittest import TestCase
from unittest.mock import PropertyMock, patch

from data.event import Event
from data.loader import EventLoader

import pytest
from data.tie_breaks import tie_breaks, options
from data.tie_breaks.cutters import Cut1TieBreakCutter, Median1TieBreakCutter
from data.tie_breaks.options import (
    ReversedTieBreakOption,
    LegacyMarch2026TieBreakOption,
)
from data.tournament import Tournament
from data.player import TournamentPlayer
from utils.enum import BoardColor, Result
from plugins.ffe import ffe_tie_breaks
from plugins.ffe.ffe_tie_breaks import (
    PapiBuchholzTypeOption,
    StandardPapiBuchholzType,
    CutPapiBuchholzType,
    MedianPapiBuchholzType,
)
from tests.test_config import TestUtils

EVENT_ID = 'test-tiebreaks-event'
TOURNAMENT_ID = 'test-tiebreaks-tournament'


class TieBreakTestCase(TestCase, ABC):
    """Base test class for the tie-breaks tests.
    Those tests are based on the TEC `Exercises in Tie-Breaking` file
    (see https://tec.fide.com/2024/03/18/tie-break-exercise/)."""

    event: Event

    def setUp(self):
        super().setUp()
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID, json_file=self.json_file)
        self.event = EventLoader().load_event(EVENT_ID)

    def tearDown(self):
        TestUtils.delete_event(EVENT_ID)
        super().tearDown()

    @property
    @abstractmethod
    def json_file(self) -> str:
        pass

    @property
    def tournament(self) -> Tournament:
        return self.event.tournaments_by_name[TOURNAMENT_ID]

    def get_player_values(
        self,
        compute_player_value: Callable[[TournamentPlayer], Any],
        exclude_ids: list[int] | None = None,
        only_ids: list[int] | None = None,
    ) -> dict[int, Any]:
        player_values = {}
        for player in self.tournament.tournament_players:
            if not (
                (exclude_ids and player.id in exclude_ids)
                or (only_ids and player.id not in only_ids)
            ):
                player_values[player.id] = compute_player_value(player)
        return player_values

    def get_tie_break_player_values(
        self,
        tie_break_: tie_breaks.TieBreak,
        exclude_ids: list[int] | None = None,
        only_ids: list[int] | None = None,
    ):
        return self.get_player_values(
            lambda p: tie_break_.compute_player_value(
                p, after_round=self.tournament.rounds
            ),
            exclude_ids,
            only_ids,
        )

    def get_direct_encounter_player_values(self):
        self.tournament.compute_tournament_player_ranks()
        tie_break_ = tie_breaks.DirectEncounterTieBreak()
        # Direct encounter resolves the players still tied when it is
        # reached, so it is applied after the points — index 1, the
        # points being the criterion at index 0.
        return tie_break_.compute_all_player_values(
            self.tournament, 1, after_round=self.tournament.rounds
        )


@pytest.mark.unit
class SwissTieBreakTestCase(TieBreakTestCase):
    """Class containing all the tie-break tests on the TEC standard Swiss tournament.
    This tournament is defined at page 5 of `Exercises in Tie-Breaking`"""

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
            [options.CutterTieBreakOption(Cut1TieBreakCutter.static_id())]
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

    def test_standard_points(self):
        tie_break_ = tie_breaks.StandardPointsTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
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

    def test_pairing_number(self):
        tie_break_ = tie_breaks.PairingNumberTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {tpn: -tpn for tpn in range(1, 17)}
        self.assertEqual(results, expected)

    def test_pairing_number_reversed(self):
        tie_break_ = tie_breaks.PairingNumberTieBreak([ReversedTieBreakOption(True)])
        results = self.get_tie_break_player_values(tie_break_)
        expected = {tpn: tpn for tpn in range(1, 17)}
        self.assertEqual(results, expected)

    def test_buchholz_legacy_2026(self):
        tie_break_ = tie_breaks.StandardBuchholzTieBreak(
            [LegacyMarch2026TieBreakOption(True)]
        )
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 13.0,
            3: 15.5,
            4: 15.0,
            1: 12.5,
            16: 12.5,
            6: 12.0,
            8: 13.5,
            11: 13.5,
            5: 8.5,
            15: 12.0,
            12: 11.5,
            14: 11.0,
            7: 14.5,
            13: 14.0,
            9: 9.0,
            10: 13.0,
        }
        self.assertEqual(results, expected)

    def test_buchholz(self):
        tie_break_ = tie_breaks.StandardBuchholzTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        # Does not match the exercise due to 03/2026 Handbook update (EV = Exercise value)
        expected = {
            2: 13.0,
            3: 15.5,
            4: 14.0,  # EV 15.0: HPB R2 - dummy capped to rounds/2=2.5 instead of 3.5
            1: 12.5,
            16: 12.5,
            6: 11.5,  # EV 12.0: PAB R3 - dummy capped to rounds/2=2.5 instead of 3
            8: 13.5,
            11: 12.5,  # EV 13.5: Forfeit win R4 - dummy capped to opponent points 1.5 instead of 2.5
            5: 8.5,
            15: 12.0,
            12: 11.5,
            14: 11.0,
            7: 14.5,
            13: 14.0,
            9: 9.0,
            10: 13.0,
        }
        self.assertEqual(results, expected)

    def test_buchholz_cut1_legacy_2026(self):
        tie_break_ = tie_breaks.StandardBuchholzTieBreak(
            [
                options.CutterWithMedianTieBreakOption(Cut1TieBreakCutter().id),
                LegacyMarch2026TieBreakOption(True),
            ]
        )
        results = self.get_tie_break_player_values(
            tie_break_, only_ids=[5, 8, 11, 7, 9, 13, 1, 3, 4, 16, 12, 14, 15]
        )
        expected = {
            5: 7.5,
            8: 12.0,
            11: 12.0,
            7: 12.5,
            9: 7.5,
            13: 12.0,
            1: 11.0,
            3: 13.0,
            4: 11.5,
            16: 11.0,
            12: 9.5,
            14: 9.0,
            15: 11.0,
        }
        self.assertEqual(results, expected)

    def test_buchholz_cut1(self):
        tie_break_ = tie_breaks.StandardBuchholzTieBreak(
            [options.CutterWithMedianTieBreakOption(Cut1TieBreakCutter().id)]
        )
        results = self.get_tie_break_player_values(
            tie_break_, only_ids=[5, 8, 11, 7, 9, 13, 1, 3, 4, 16, 12, 14, 15]
        )
        # Does not match the exercise due to 03/2026 Handbook update (EV = Exercise value)
        expected = {
            5: 7.5,
            8: 12.0,
            11: 11.0,  # EV 12.0: Forfeit win R4 - dummy capped to opponent points 1.5 instead of 2.5
            7: 12.5,
            9: 7.5,
            13: 12.0,
            1: 11.0,
            3: 13.0,
            4: 11.5,
            16: 11.0,
            12: 9.5,
            14: 9.0,
            15: 11.0,
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

    def test_fore_buchholz_legacy_2026(self):
        tie_break_ = tie_breaks.ForeBuchholzTieBreak(
            [LegacyMarch2026TieBreakOption(True)]
        )
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 13.5,
            3: 15.0,
            4: 15.5,
            1: 13.5,
            16: 13.5,
            8: 12.5,
            6: 12.0,
            15: 12.0,
            5: 10.0,
            11: 12.5,
            12: 11.5,
            14: 10.5,
            7: 13.5,
            9: 9.5,
            13: 13.5,
            10: 12.5,
        }
        self.assertEqual(results, expected)

    def test_fore_buchholz(self):
        tie_break_ = tie_breaks.ForeBuchholzTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        # Does not match the exercise due to 03/2026 Handbook update (EV = Exercise value)
        expected = {
            2: 13.5,
            3: 15.0,
            4: 14.5,  # EV 15.5: HPB R2 - dummy capped to rounds/2=2.5 instead of 3.5
            1: 13.5,
            16: 13.5,
            8: 12.5,
            6: 12.0,
            15: 12.0,
            5: 10.0,
            11: 12.0,  # EV 12.5: Forfeit win R4 - dummy capped to opponent adjusted points 1.5 instead of 2
            12: 11.0,  # EV 11.5: Forfeit loss R3 - dummy capped to opponent adjusted points 1.5 instead of 2
            14: 10.5,
            7: 13.5,
            9: 9.5,
            13: 13.5,
            10: 12.5,
        }
        self.assertEqual(results, expected)

    def test_buchholz_papi(self):
        tie_break_ = ffe_tie_breaks.PapiBuchholzTieBreak(
            [PapiBuchholzTypeOption(StandardPapiBuchholzType().id)]
        )
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

    def test_buchholz_cut_papi(self):
        tie_break_ = ffe_tie_breaks.PapiBuchholzTieBreak(
            [PapiBuchholzTypeOption(CutPapiBuchholzType().id)]
        )
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

    def test_buchholz_median_papi(self):
        tie_break_ = ffe_tie_breaks.PapiBuchholzTieBreak(
            [PapiBuchholzTypeOption(MedianPapiBuchholzType().id)]
        )
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

    def test_aob_legacy_2026(self):
        aob = tie_breaks.AverageOfBuchholzTieBreak(
            [LegacyMarch2026TieBreakOption(True)]
        ).compute_player_value
        results = self.get_player_values(
            lambda p: round(aob(p, after_round=self.tournament.rounds), 2)
        )
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

    def test_aob(self):
        aob = tie_breaks.AverageOfBuchholzTieBreak().compute_player_value
        results = self.get_player_values(
            lambda p: round(aob(p, after_round=self.tournament.rounds), 2)
        )
        # Does not match the exercise due to 03/2026 Handbook update (EV = Exercise value)
        # No way to recompute those by hand, as Buchholz test
        # was recomputed it's considered fine by this standard
        expected = {
            1: 12.4,
            2: 13.6,
            3: 12.9,
            4: 13.38,
            5: 13.2,
            6: 13.25,
            7: 11.7,
            8: 12.9,
            9: 12.75,
            10: 10.8,
            11: 12.75,
            12: 14.0,
            13: 11.9,
            14: 13.0,
            15: 12.2,
            16: 13.1,
        }
        self.assertEqual(results, expected)

    def test_sonneborn_berger_swiss_legacy_2026(self):
        tie_break_ = tie_breaks.SonnebornBergerTieBreak(
            [LegacyMarch2026TieBreakOption(True)]
        )
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

    def test_sonneborn_berger_swiss(self):
        tie_break_ = tie_breaks.SonnebornBergerTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        # Does not match the exercise due to 03/2026 Handbook update (EV = Exercise value)
        expected = {
            2: 9.5,
            3: 10.5,
            4: 9.25,  # EV 9.75: HPB R2 - 0.5 * (dummy capped to rounds/2=2.5 instead of 3.5)
            1: 8.0,
            16: 7.25,
            6: 6.0,  # EV 6.5: PAB R3 - 1 * (dummy capped to rounds/2=2.5 instead of 3)
            11: 4.75,  # EV 5.75: Forfeit win R4 - 1 * (dummy capped to opponent score 1.5 instead of 2.5)
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

    def test_sonneborn_berger_swiss_forfeits_played(self):
        """With the played modifier a forfeit counts as a game against the
        scheduled opponent, and a bye still counts as a game against the
        dummy (Art. 16.4): here every bye holder keeps the same value."""
        tie_break_ = tie_breaks.SonnebornBergerTieBreak(
            [options.PlayedModifierTieBreakOption(True)]
        )
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            2: 9.5,
            3: 10.5,
            4: 9.25,  # HPB R2: dummy 2.5 * 0.5
            1: 8.0,
            16: 7.25,
            6: 6.0,  # PAB R3: dummy 2.5 * 1
            11: 4.75,  # Forfeit win R4 against #9: their 1.5 * 1
            8: 5.25,
            5: 4.25,
            14: 4.5,
            12: 4.0,  # PAB R2: dummy 2 * 1
            15: 3.5,
            13: 4.25,
            7: 3.25,
            9: 2.25,  # HPB R3 and PAB R5: dummy 1.5 * 0.5 and 1.5 * 1
            10: 1.5,
        }
        self.assertEqual(results, expected)

    def test_sb_cut1_swiss_legacy_2026(self):
        tie_break_ = tie_breaks.SonnebornBergerTieBreak(
            [
                options.CutterTieBreakOption(Cut1TieBreakCutter.static_id()),
                LegacyMarch2026TieBreakOption(True),
            ]
        )
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

    def test_sb_cut1_swiss(self):
        tie_break_ = tie_breaks.SonnebornBergerTieBreak(
            [options.CutterTieBreakOption(Cut1TieBreakCutter.static_id())]
        )
        results = self.get_tie_break_player_values(tie_break_)
        # Does not match the exercise due to 03/2026 Handbook update (EV = Exercise value)
        expected = {
            2: 8.5,
            3: 9.25,
            4: 7.75,  # EV 8.0: HPB R2
            # 0.5 * (dummy capped to rounds/2=2.5 instead of 3)
            # --> 1.5 General contribution cut instead of 1.75 Involuntary contribution
            1: 7.25,
            16: 5.75,
            6: 5.0,  # EV 5.5: PAB R3 - 1 * (dummy capped to rounds/2=2.5 instead of 3)
            11: 3.25,  # EV 4.25: Forfeit win R4 - 1 * (dummy capped to opponent score 1.5 instead of 2.5)
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
            [options.CutterWithMedianTieBreakOption(Cut1TieBreakCutter().id)]
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

    def test_performance_papi(self):
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

    def test_win_chances_follow_the_fide_conversion_table(self):
        """FIDE B.02 §8.1b: the expected score for a rating difference,
        checked at every step of the table — the first difference each
        percentage covers, and the last."""
        win_chances = tie_breaks.PerfectTournamentPerformanceTieBreak.win_chances
        table = [
            (0, 3, '0.50'),
            (4, 10, '0.51'),
            (11, 17, '0.52'),
            (18, 25, '0.53'),
            (26, 32, '0.54'),
            (33, 39, '0.55'),
            (40, 46, '0.56'),
            (47, 53, '0.57'),
            (54, 61, '0.58'),
            (62, 68, '0.59'),
            (69, 76, '0.60'),
            (77, 83, '0.61'),
            (84, 91, '0.62'),
            (92, 98, '0.63'),
            (99, 106, '0.64'),
            (107, 113, '0.65'),
            (114, 121, '0.66'),
            (122, 129, '0.67'),
            (130, 137, '0.68'),
            (138, 145, '0.69'),
            (146, 153, '0.70'),
            (154, 162, '0.71'),
            (163, 170, '0.72'),
            (171, 179, '0.73'),
            (180, 188, '0.74'),
            (189, 197, '0.75'),
            (198, 206, '0.76'),
            (207, 215, '0.77'),
            (216, 225, '0.78'),
            (226, 235, '0.79'),
            (236, 245, '0.80'),
            (246, 256, '0.81'),
            (257, 267, '0.82'),
            (268, 278, '0.83'),
            (279, 290, '0.84'),
            (291, 302, '0.85'),
            (303, 315, '0.86'),
            (316, 328, '0.87'),
            (329, 344, '0.88'),
            (345, 357, '0.89'),
            (358, 374, '0.90'),
            (375, 391, '0.91'),
            (392, 411, '0.92'),
            (412, 432, '0.93'),
            (433, 456, '0.94'),
            (457, 484, '0.95'),
            (485, 517, '0.96'),
            (518, 559, '0.97'),
            (560, 619, '0.98'),
            (620, 735, '0.99'),
            (736, 1000, '1.00'),
        ]
        for first, last, expected in table:
            for difference in (first, last):
                with self.subTest(difference=difference):
                    high, low = win_chances(2000 + difference, 2000)
                    self.assertEqual(high, Decimal(expected))
                    self.assertEqual(low, 1 - Decimal(expected))
                    # The weaker player's chances are the complement.
                    self.assertEqual(win_chances(2000, 2000 + difference), (low, high))

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

        self.assertEqual(
            self.get_tie_break_player_values(tie_break_, only_ids=[2, 14]),
            {2: 2216, 14: 1942},
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
            {3: 1934, 13: 1909},
        )

    def test_player_rating(self):
        tie_break_ = tie_breaks.PlayerRatingTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            1: 2200,
            2: 2150,
            3: 2100,
            4: 2050,
            5: 2000,
            6: 1950,
            7: 1900,
            8: 1850,
            9: 1800,
            10: 1750,
            11: 1700,
            12: 1650,
            13: 1600,
            14: 1550,
            15: 1500,
            16: 1450,
        }
        self.assertEqual(results, expected)

    def test_player_rating_reversed(self):
        tie_break_ = tie_breaks.PlayerRatingTieBreak([ReversedTieBreakOption(True)])
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            1: -2200,
            2: -2150,
            3: -2100,
            4: -2050,
            5: -2000,
            6: -1950,
            7: -1900,
            8: -1850,
            9: -1800,
            10: -1750,
            11: -1700,
            12: -1650,
            13: -1600,
            14: -1550,
            15: -1500,
            16: -1450,
        }
        self.assertEqual(results, expected)

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

    def test_kashdan_papi(self):
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


@pytest.mark.unit
class SwissDirectEncounterTieBreakTestCase(TieBreakTestCase):
    """There are no ties to break in the `TEC Swiss` tournament,
    a longer one has to be used (see `Exercises in Tie-Breaking` page 43)."""

    @property
    def json_file(self) -> str:
        return 'tec-swiss-direct-encounter'

    def test_direct_encounter(self):
        results = self.get_direct_encounter_player_values()
        expected = {
            3: 0,
            6: 3,
            1: 1,
            4: 1,
            2: 0,
            7: 0,
            8: 0,
            16: 0,
            5: 0,
            10: 0,
            14: 0,
            15: 0,
            11: 0,
            9: 0,
            12: 0,
            13: 0,
        }
        self.assertEqual(results, expected)


@pytest.mark.unit
class GamesWonUnratedTestCase(TestCase):
    """A game won over the board counts for WON and BWG whether or not it
    is rated (TRF code W)."""

    def _player(self) -> TournamentPlayer:
        def pairing(result: Result, color: BoardColor) -> SimpleNamespace:
            return SimpleNamespace(
                result=result,
                color=color,
                opponent_id=2,
                played=not result.is_unplayed,
                requested_bye=False,
                voluntary_unplayed=False,
            )

        pairings = {
            1: pairing(Result.UNRATED_WIN, BoardColor.BLACK),
            2: pairing(Result.WIN, BoardColor.WHITE),
            3: pairing(Result.FORFEIT_WIN, BoardColor.BLACK),
        }
        return cast(
            TournamentPlayer,
            SimpleNamespace(
                pairings=pairings,
                tournament=SimpleNamespace(point_values=None),
                game_counts_for_tie_breaks=lambda pairing: True,
            ),
        )

    def test_games_won(self):
        value = tie_breaks.GamesWonTieBreak().compute_player_value(
            self._player(), after_round=3
        )
        self.assertEqual(value, 2)

    def test_games_won_with_black(self):
        value = tie_breaks.GamesWonWithBlackTieBreak().compute_player_value(
            self._player(), after_round=3
        )
        self.assertEqual(value, 1)


@pytest.mark.unit
class PLSwissTieBreakTestCase(TieBreakTestCase):
    """Tests provided by Pierre Lapeyre (IA, Arbiter trainer).
    See docs/tie_breaks/Tiebreak_exercises-PL-2026.pptm"""

    @property
    def json_file(self) -> str:
        return 'pl-swiss'

    def test_progressive_score(self):
        tie_break_ = tie_breaks.ProgressiveScoresTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            5: 12.5,
            1: 11,
            2: 12.5,
            6: 10.5,
            4: 9.5,
            3: 9.5,
            11: 8.5,
            14: 6,
            7: 8,
            10: 5.5,
            9: 4.5,
            8: 3,
            13: 2.5,
            12: 1.5,
        }
        self.assertEqual(expected, results)

    def test_buchholz(self):
        tie_break_ = tie_breaks.StandardBuchholzTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            5: 13.5,
            1: 14.5,
            2: 15.0,
            6: 13.5,
            4: 14.5,
            3: 14.0,
            11: 13.0,
            14: 11.0,
            7: 13.5,
            10: 11.0,
            9: 11.5,
            8: 10.5,
            13: 9.0,
            12: 10.0,
        }
        self.assertEqual(expected, results)

    def test_buchholz_cut1(self):
        tie_break_ = tie_breaks.StandardBuchholzTieBreak(
            [options.CutterWithMedianTieBreakOption(Cut1TieBreakCutter.static_id())]
        )
        results = self.get_tie_break_player_values(tie_break_, only_ids=[9, 12])
        expected = {
            9: 10.0,
            12: 9.5,
        }
        self.assertEqual(expected, results)


@pytest.mark.unit
class RoundRobinTieBreakTestCase(TieBreakTestCase):
    """Class containing all the tie-break tests on the TEC Round-Robin tournament.
    This tournament is defined at page 6 of `Exercises in Tie-Breaking`"""

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

    def test_tpr_rounds_the_percentage_half_up(self):
        """C.07 Art. 10.2 reads the conversion table on the fractional
        score to two decimals; a half rounds up, as every rounding in the
        FIDE regulations does (Art. 10.1, B.02 Art. 8.3.4). Helene (id 6)
        scored 0.5 in 4 played games: 12.5% reads as 13%, RD -322."""
        tie_break_ = tie_breaks.TournamentPerformanceRatingTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {1: 2199, 2: 2209, 3: 2219, 4: 1931, 5: 2038, 6: 1803}
        self.assertEqual(results, expected)

    def test_apro_round_robin(self):
        tie_break_ = tie_breaks.AveragePerformanceRatingOpponentsTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {1: 2040, 2: 2038, 3: 2036, 4: 2094, 5: 2140, 6: 2140}
        self.assertEqual(results, expected)

    def test_sb_cut1_round_robin(self):
        tie_break_ = tie_breaks.SonnebornBergerTieBreak(
            [options.CutterTieBreakOption(Cut1TieBreakCutter.static_id())]
        )
        results = self.get_tie_break_player_values(tie_break_)
        expected = {1: 9.25, 2: 4.75, 3: 4.75, 4: 4.25, 5: 3.25, 6: 1.5}
        self.assertEqual(results, expected)

    def test_koya(self):
        tie_break_ = tie_breaks.KoyaTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {1: 2, 2: 0.5, 3: 0.5, 4: 1, 5: 0.5, 6: 0}
        self.assertEqual(results, expected)

    def test_direct_encounter(self):
        results = self.get_direct_encounter_player_values()
        expected = {
            1: 2,
            2: 0,
            3: 0,
            5: 1,
            6: 2,
            4: 0,
        }
        self.assertEqual(results, expected)


@pytest.mark.unit
class MedianBuchholzWithByesTestCase(TieBreakTestCase):
    """Alpha (#1) has a half-point bye and a zero-point bye, both
    voluntarily unplayed rounds whose dummy is worth 2.5 (own score 3.5
    capped at half the rounds, Art. 16.4.2), or 3.5 before March 2026.
    Cut 1 takes the lower of them (Art. 16.5); the median then takes the
    highest contribution of all, the other dummy, not the highest
    opponent score."""

    @property
    def json_file(self) -> str:
        return 'median-buchholz-byes'

    def _alpha(self, tie_break_):
        return self.get_tie_break_player_values(tie_break_, only_ids=[1])[1]

    def test_buchholz(self):
        self.assertEqual(self._alpha(tie_breaks.StandardBuchholzTieBreak()), 8.0)
        self.assertEqual(
            self._alpha(
                tie_breaks.StandardBuchholzTieBreak(
                    [LegacyMarch2026TieBreakOption(True)]
                )
            ),
            10.0,
        )

    def test_buchholz_cut1(self):
        cut1 = options.CutterWithMedianTieBreakOption(Cut1TieBreakCutter.static_id())
        self.assertEqual(self._alpha(tie_breaks.StandardBuchholzTieBreak([cut1])), 5.5)
        self.assertEqual(
            self._alpha(
                tie_breaks.StandardBuchholzTieBreak(
                    [cut1, LegacyMarch2026TieBreakOption(True)]
                )
            ),
            6.5,
        )

    def test_buchholz_median1(self):
        median1 = options.CutterWithMedianTieBreakOption(
            Median1TieBreakCutter.static_id()
        )
        self.assertEqual(
            self._alpha(tie_breaks.StandardBuchholzTieBreak([median1])), 3.0
        )
        self.assertEqual(
            self._alpha(
                tie_breaks.StandardBuchholzTieBreak(
                    [median1, LegacyMarch2026TieBreakOption(True)]
                )
            ),
            3.0,
        )


@pytest.mark.unit
class ForeBuchholzFinalRoundTestCase(TieBreakTestCase):
    """Fore Buchholz has the paired games of the final round end in draws
    (Art. 8.3), forfeits included, so that round counts as played.

    Delta (#4) forfeits the final round to Echo (#5): the round contributes
    Echo's score and is not a voluntary unplayed round, so Cut 1 takes the
    lowest contribution (Art. 16.5.1). Alpha (#1) has a zero-point bye in
    round 2 and forfeits the final round to Charlie (#3): the bye is no
    longer at the end of the tournament and keeps its zero (Art. 16.3.2),
    which Charlie's Fore Buchholz reads."""

    @property
    def json_file(self) -> str:
        return 'fore-buchholz-final-round'

    def test_adjusted_score_fore(self):
        results = self.get_player_values(
            lambda p: tie_breaks.TieBreak.adjusted_score(
                p, after_round=self.tournament.rounds, adjust_fore=True
            ),
            only_ids=[1, 3, 4, 5],
        )
        self.assertEqual(results, {1: 0.5, 3: 1.5, 4: 0.5, 5: 2.5})

    def test_fore_buchholz(self):
        tie_break_ = tie_breaks.ForeBuchholzTieBreak()
        results = self.get_tie_break_player_values(tie_break_, only_ids=[3, 4])
        self.assertEqual(results, {3: 3.5, 4: 6.5})

    def test_fore_buchholz_cut1(self):
        tie_break_ = tie_breaks.ForeBuchholzTieBreak(
            [options.CutterWithMedianTieBreakOption(Cut1TieBreakCutter.static_id())]
        )
        results = self.get_tie_break_player_values(tie_break_, only_ids=[4])
        self.assertEqual(results, {4: 5.0})


class ForeBuchholzPredeterminedPairingsTestCase(TieBreakTestCase):
    """With pre-determined pairings a forfeit is a regular game (Art. 15.2),
    so Fore Buchholz counts it against the scheduled opponent, as the /P
    modifier does.

    Delta (#4) forfeits round 2 to Echo (#5) and loses to Echo in round 3."""

    @property
    def json_file(self) -> str:
        return 'fore-buchholz-predetermined'

    def _delta(self, tie_break_: tie_breaks.TieBreak) -> float:
        return self.get_tie_break_player_values(tie_break_, only_ids=[4])[4]

    def test_a_forfeit_counts_as_played(self):
        played = self._delta(
            tie_breaks.ForeBuchholzTieBreak(
                [options.PlayedModifierTieBreakOption(True)]
            )
        )
        swiss = self._delta(tie_breaks.ForeBuchholzTieBreak())
        with patch.object(
            type(self.tournament.pairing_system),
            'predetermined_pairings',
            new_callable=PropertyMock,
            return_value=True,
        ):
            predetermined = self._delta(tie_breaks.ForeBuchholzTieBreak())
        self.assertEqual(predetermined, played)
        self.assertNotEqual(predetermined, swiss)


class KoyaTieBreakTestCase(TieBreakTestCase):
    """Test on a stricter koya, the TEC exercise is too laxist
    (0 on last round + no opponent score matching the limit)"""

    @property
    def json_file(self) -> str:
        return 'manual-koya'

    def test_koya(self):
        tie_break_ = tie_breaks.KoyaTieBreak()
        results = self.get_tie_break_player_values(tie_break_)
        expected = {
            1: 0.5,
            2: 2.0,
            3: 0.0,
            4: 2.0,
            5: 1.5,
            6: 0.5,
            7: 2.0,
            8: 0.0,
        }
        self.assertEqual(results, expected)


@pytest.mark.unit
class KoyaAcronymTestCase(TestCase):
    """The Koya limit is written ``/L±n``, the sign carried once (TEC,
    *Mandatory Tie-Breaks*, Modifiers: "/L±n Used for Koya, Set the Limit
    to ± n half points above / below 50%. (L+1 , L-2, …)"). A reader that
    takes ``L--1`` for an unknown modifier computes an unlimited Koya."""

    def test_the_limit_carries_one_sign(self):
        for value, expected in ((1, 'KS/L+1'), (-1, 'KS/L-1'), (-2, 'KS/L-2')):
            tie_break_ = tie_breaks.KoyaTieBreak(
                [options.KoyaLimitTieBreakOption(value)]
            )
            self.assertEqual(tie_break_.trf_acronym, expected)

    def test_no_limit_leaves_the_acronym_bare(self):
        self.assertEqual(tie_breaks.KoyaTieBreak().trf_acronym, 'KS')
