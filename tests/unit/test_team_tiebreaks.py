"""Team tie-break tests reproducing the TEC-2023 published exercises
(Exercises 34-41), running against pure ``TeamRecord`` inputs so the
math is verified independently of the storage layer.

Source crosstable: TEC-2023 ``Exercises in Tie-Breaking``, §2.3 (14
teams, 4 players each, 7 Swiss rounds). Unplayed-match scoring per
the tournament regulations on PDF page 9:

  PAB / HPB → 1 match point, 2 game points (a draw against a dummy)
  ZPB / -F  → 0 / 0
  +F        → 2 match points, 4 game points
"""

from unittest import TestCase

import pytest

from data.tie_breaks.team_records import TeamMatchRecord, TeamMatchType, TeamRecord
from data.tie_breaks.team_tie_breaks import (
    ESBVariant,
    ESBVariantTieBreakOption,
    ExtendedDirectEncounterTieBreak,
    ExtendedSonnebornBergerTeamTieBreak,
    MatchPointsVsGamePointsTieBreak,
    ScoresAndScheduleStrengthCombinationTieBreak,
    TeamTieBreakContext,
)
from data.tie_breaks.tie_breaks import StandardBuchholzTieBreak
from data.tie_breaks.options import (
    CutterTieBreakOption,
    CutterWithMedianTieBreakOption,
    TeamScoreTieBreakOption,
)
from data.tie_breaks.cutters import Cut1TieBreakCutter
from utils.enum import ScoreType


# ---------------------------------------------------------------------------
# Raw crosstable data (TEC-2023 §2.3, p. 6). Each tuple is one round's
# match for that team: (opponent_team_id, own_gp, match_type). own_mp
# is derived from own_gp vs opponent_gp (computed once below).
# ---------------------------------------------------------------------------

PLAYED = TeamMatchType.PLAYED
PAB = TeamMatchType.PAB
HPB = TeamMatchType.HPB
ZPB = TeamMatchType.ZPB
F_WIN = TeamMatchType.FORFEIT_WIN
F_LOSS = TeamMatchType.FORFEIT_LOSS

# Raw rounds: team_id -> list of (opponent_or_None, own_gp, match_type)
_RAW: dict[int, list[tuple[int | None, float, TeamMatchType]]] = {
    1: [  # Antelopes
        (8, 2.5, PLAYED),
        (4, 1.5, PLAYED),
        (7, 3.0, PLAYED),
        (2, 2.5, PLAYED),
        (5, 1.5, PLAYED),
        (None, 4.0, F_WIN),
        (3, 2.5, PLAYED),
    ],
    2: [  # Bonobos
        (9, 3.0, PLAYED),
        (3, 4.0, PLAYED),
        (5, 0.0, PLAYED),
        (1, 1.5, PLAYED),
        (13, 3.0, PLAYED),
        (4, 2.5, PLAYED),
        (10, 3.0, PLAYED),
    ],
    3: [  # Cougars
        (10, 2.5, PLAYED),
        (2, 0.0, PLAYED),
        (9, 3.0, PLAYED),
        (6, 2.5, PLAYED),
        (4, 3.0, PLAYED),
        (5, 3.5, PLAYED),
        (1, 1.5, PLAYED),
    ],
    4: [  # Deer
        (11, 3.0, PLAYED),
        (1, 2.5, PLAYED),
        (13, 3.0, PLAYED),
        (5, 3.5, PLAYED),
        (3, 1.0, PLAYED),
        (2, 1.5, PLAYED),
        (9, 2.5, PLAYED),
    ],
    5: [  # Elephants
        (12, 4.0, PLAYED),
        (6, 3.0, PLAYED),
        (2, 4.0, PLAYED),
        (4, 0.5, PLAYED),
        (1, 2.5, PLAYED),
        (3, 0.5, PLAYED),
        (13, 3.5, PLAYED),
    ],
    6: [  # Falcons
        (13, 2.0, PLAYED),
        (5, 1.0, PLAYED),
        (8, 3.0, PLAYED),
        (3, 1.5, PLAYED),
        (11, 2.5, PLAYED),
        (None, 0.0, F_LOSS),
        (12, 2.5, PLAYED),
    ],
    7: [  # Giraffes
        (14, 2.0, PLAYED),
        (8, 2.0, PLAYED),
        (1, 1.0, PLAYED),
        (10, 2.5, PLAYED),
        (9, 2.0, PLAYED),
        (13, 2.0, PLAYED),
        (None, 0.0, ZPB),
    ],
    8: [  # Hippopotami
        (1, 1.5, PLAYED),
        (7, 2.0, PLAYED),
        (6, 1.0, PLAYED),
        (12, 3.5, PLAYED),
        (10, 2.0, PLAYED),
        (9, 2.0, PLAYED),
        (11, 3.0, PLAYED),
    ],
    9: [  # Iguanas
        (2, 1.0, PLAYED),
        (12, 4.0, PLAYED),
        (3, 1.0, PLAYED),
        (14, 3.0, PLAYED),
        (7, 2.0, PLAYED),
        (8, 2.0, PLAYED),
        (4, 1.5, PLAYED),
    ],
    10: [  # Jackals
        (3, 1.5, PLAYED),
        (11, 1.5, PLAYED),
        (12, 2.5, PLAYED),
        (7, 1.5, PLAYED),
        (8, 2.0, PLAYED),
        (14, 3.0, PLAYED),
        (2, 1.0, PLAYED),
    ],
    11: [  # Koalas
        (4, 1.0, PLAYED),
        (10, 2.5, PLAYED),
        (14, 2.0, PLAYED),
        (13, 1.5, PLAYED),
        (6, 1.5, PLAYED),
        (12, 2.0, PLAYED),
        (8, 1.0, PLAYED),
    ],
    12: [  # Lynxes
        (5, 0.0, PLAYED),
        (9, 0.0, PLAYED),
        (10, 1.5, PLAYED),
        (8, 0.5, PLAYED),
        (None, 2.0, PAB),
        (11, 2.0, PLAYED),
        (6, 1.5, PLAYED),
    ],
    13: [  # Moose
        (6, 2.0, PLAYED),
        (14, 2.5, PLAYED),
        (4, 1.0, PLAYED),
        (11, 2.5, PLAYED),
        (2, 1.0, PLAYED),
        (7, 2.0, PLAYED),
        (5, 0.5, PLAYED),
    ],
    14: [  # Narwhals
        (7, 2.0, PLAYED),
        (13, 1.5, PLAYED),
        (11, 2.0, PLAYED),
        (9, 1.0, PLAYED),
        (None, 2.0, HPB),
        (10, 1.0, PLAYED),
        (None, 2.0, PAB),
    ],
}

_NAMES = {
    1: 'Antelopes',
    2: 'Bonobos',
    3: 'Cougars',
    4: 'Deer',
    5: 'Elephants',
    6: 'Falcons',
    7: 'Giraffes',
    8: 'Hippopotami',
    9: 'Iguanas',
    10: 'Jackals',
    11: 'Koalas',
    12: 'Lynxes',
    13: 'Moose',
    14: 'Narwhals',
}


def _build_records() -> dict[int, TeamRecord]:
    """Convert ``_RAW`` into ``TeamRecord`` instances, deriving each
    match's own_mp from the played-match GP comparison and the
    tournament's unplayed-match rules (PAB / HPB → 1 MP, +F → 2 MP,
    everything else → 0 MP). own_gp comes straight from the raw data.
    """
    # First pass: collect own_gp per (team, round) so we can look up the
    # opponent's own_gp for played-match MP derivation.
    own_gp_lookup: dict[tuple[int, int], float] = {}
    for team_id, rounds in _RAW.items():
        for round_index, (_opp, own_gp, _kind) in enumerate(rounds, start=1):
            own_gp_lookup[(team_id, round_index)] = own_gp

    records: dict[int, TeamRecord] = {}
    for team_id, rounds in _RAW.items():
        matches: list[TeamMatchRecord] = []
        total_mp = 0.0
        total_gp = 0.0
        for round_index, (opp_id, own_gp, kind) in enumerate(rounds, start=1):
            if kind == PLAYED:
                assert opp_id is not None
                opp_gp = own_gp_lookup[(opp_id, round_index)]
                if own_gp > opp_gp:
                    own_mp = 2.0
                elif own_gp < opp_gp:
                    own_mp = 0.0
                else:
                    own_mp = 1.0
            elif kind in (PAB, HPB):
                own_mp = 1.0
            elif kind == F_WIN:
                own_mp = 2.0
            else:  # ZPB, F_LOSS
                own_mp = 0.0
            matches.append(
                TeamMatchRecord(
                    round_=round_index,
                    opponent_id=opp_id,
                    own_mp=own_mp,
                    own_gp=own_gp,
                    match_type=kind,
                )
            )
            total_mp += own_mp
            total_gp += own_gp
        records[team_id] = TeamRecord(
            team_id=team_id,
            name=_NAMES[team_id],
            total_mp=total_mp,
            total_gp=total_gp,
            matches=matches,
        )
    return records


_CONTEXT = TeamTieBreakContext(
    primary_score=ScoreType.MATCH_POINTS,
    secondary_score=ScoreType.GAME_POINTS,
    rounds=7,
    win_mp=2.0,
    draw_mp=1.0,
    loss_mp=0.0,
    team_player_count=4,
    # 4-player teams, 1-½-0 game scoring → a half match = 4 × ½ = 2 GP.
    draw_gp=2.0,
)


# Sanity-check expected totals from the published crosstable (§2.3 p.6).
_EXPECTED_TOTALS: dict[int, tuple[float, float]] = {
    1: (10, 17.5),
    2: (10, 17.0),
    3: (10, 16.0),
    4: (10, 17.0),
    5: (10, 18.0),
    6: (7, 12.5),
    7: (6, 11.5),
    8: (7, 15.0),
    9: (6, 14.5),
    10: (5, 13.0),
    11: (4, 11.5),
    12: (2, 7.5),
    13: (6, 11.5),
    14: (4, 11.5),
}


def _cut1_option() -> CutterTieBreakOption:
    return CutterTieBreakOption(Cut1TieBreakCutter.static_id())


def _bh(team_score: str, cut1: bool = False) -> StandardBuchholzTieBreak:
    """FIDE MTB26 BH:<team_score> [/C1] for the TEC fixture."""
    opts: list = [TeamScoreTieBreakOption(team_score)]
    if cut1:
        opts.append(CutterWithMedianTieBreakOption(Cut1TieBreakCutter.static_id()))
    return StandardBuchholzTieBreak(opts)


@pytest.mark.unit
class TecTeamTieBreakTestCase(TestCase):
    """Reproduces TEC-2023 Exercises 34-41 using pure TeamRecord input."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.records = _build_records()

    def test_team_totals_match_published_crosstable(self):
        """Sanity check: the derived totals match the §2.3 crosstable."""
        for team_id, (mp, gp) in _EXPECTED_TOTALS.items():
            rec = self.records[team_id]
            self.assertEqual(rec.total_mp, mp, f'MP for team {team_id}')
            self.assertEqual(rec.total_gp, gp, f'GP for team {team_id}')

    # ----- Exercise 34: MPvGP -----------------------------------------------

    def test_ex34_mpvgp_with_mp_primary_returns_gp(self):
        """When MP is primary, MPvGP returns the GP total."""
        tb = MatchPointsVsGamePointsTieBreak([])
        for team_id, (_mp, gp) in _EXPECTED_TOTALS.items():
            value = tb.compute_team_value(
                self.records[team_id],
                self.records,
                _CONTEXT,
                after_round=7,
            )
            self.assertEqual(value, gp, f'MPvGP for team {team_id}')

    def test_ex34_mpvgp_with_gp_primary_returns_mp(self):
        """And vice versa when GP is the primary score."""
        gp_context = TeamTieBreakContext(
            primary_score=ScoreType.GAME_POINTS,
            secondary_score=ScoreType.MATCH_POINTS,
            rounds=7,
            win_mp=2.0,
            draw_mp=1.0,
            loss_mp=0.0,
            team_player_count=4,
            draw_gp=2.0,
        )
        tb = MatchPointsVsGamePointsTieBreak([])
        for team_id, (mp, _gp) in _EXPECTED_TOTALS.items():
            value = tb.compute_team_value(
                self.records[team_id],
                self.records,
                gp_context,
                after_round=7,
            )
            self.assertEqual(value, mp, f'MPvGP for team {team_id}')

    # ----- Exercise 35: Sistema Buchholz (BH) with MP primary --------------

    # PDF Ex 35 p.55 final table (BH values, MP primary).
    EX35_BH_MP = {
        1: 64,
        2: 57,
        3: 58,
        4: 56,
        5: 55,
        6: 46,
        7: 44,
        8: 41,
        9: 50,
        10: 44,
        11: 41,
        12: 41,
        13: 52,
        14: 36,
    }

    def test_ex35_buchholz_total_mp_primary(self):
        tb = _bh(TeamScoreTieBreakOption.VALUE_MP)
        for team_id, expected in self.EX35_BH_MP.items():
            value = tb.compute_team_value(
                self.records[team_id],
                self.records,
                _CONTEXT,
                after_round=7,
            )
            self.assertEqual(value, expected, f'BH for team {team_id}')

    # ----- Exercise 36: BH-C1 with MP primary -------------------------------

    EX36_BH_C1_MP = {
        1: 57,
        2: 52,
        3: 53,
        4: 52,
        5: 53,
        6: 39,
        7: 38,
        8: 39,
        9: 48,
        10: 42,
        11: 39,
        12: 39,
        13: 48,
        14: 32,
    }

    def test_ex36_buchholz_cut1_mp_primary(self):
        tb = _bh(TeamScoreTieBreakOption.VALUE_MP, cut1=True)
        for team_id, expected in self.EX36_BH_C1_MP.items():
            value = tb.compute_team_value(
                self.records[team_id],
                self.records,
                _CONTEXT,
                after_round=7,
            )
            self.assertEqual(value, expected, f'BH-C1 for team {team_id}')

    # ----- Exercise 37: BH-C1 with GP primary -------------------------------

    # From the PDF Ex 37 table (BH-C1 with GP-primary scoring).
    EX37_BH_C1_GP = {
        1: 100.5,
        2: 96.0,
        3: 97.0,
        4: 94.5,
        5: 91.5,
        6: 79.5,
        7: 83.0,
        8: 82.5,
        9: 90.0,
        10: 84.5,
        11: 80.5,
        12: 84.5,
        13: 89.5,
        14: 75.5,
    }

    def test_ex37_buchholz_cut1_gp_primary(self):
        gp_context = TeamTieBreakContext(
            primary_score=ScoreType.GAME_POINTS,
            secondary_score=ScoreType.MATCH_POINTS,
            rounds=7,
            win_mp=2.0,
            draw_mp=1.0,
            loss_mp=0.0,
            team_player_count=4,
            draw_gp=2.0,
        )
        tb = _bh(TeamScoreTieBreakOption.VALUE_GP, cut1=True)
        for team_id, expected in self.EX37_BH_C1_GP.items():
            value = tb.compute_team_value(
                self.records[team_id],
                self.records,
                gp_context,
                after_round=7,
            )
            self.assertAlmostEqual(
                value, expected, places=1, msg=f'BH-C1 GP for team {team_id}'
            )

    # ----- Exercise 38: EMMSB-C1 for 10-MP teams ----------------------------

    EX38_EMMSB_TOTAL = {1: 88, 2: 74, 3: 76, 4: 72, 5: 70}
    EX38_EMMSB_C1 = {1: 74, 2: 64, 3: 66, 4: 64, 5: 66}

    def _esb(self, variant: ESBVariant, cut1: bool = False):
        opts: list = [ESBVariantTieBreakOption(variant.value)]
        if cut1:
            from data.tie_breaks.team_tie_breaks import ESBCutterTieBreakOption

            opts.append(ESBCutterTieBreakOption(Cut1TieBreakCutter.static_id()))
        return ExtendedSonnebornBergerTeamTieBreak(opts)

    def test_ex38_emmsb_total_for_tied_teams(self):
        tb = self._esb(ESBVariant.EMMSB)
        for team_id, expected in self.EX38_EMMSB_TOTAL.items():
            value = tb.compute_team_value(
                self.records[team_id],
                self.records,
                _CONTEXT,
                after_round=7,
            )
            self.assertEqual(value, expected, f'EMMSB for team {team_id}')

    def test_ex38_emmsb_cut1_for_tied_teams(self):
        tb = self._esb(ESBVariant.EMMSB, cut1=True)
        for team_id, expected in self.EX38_EMMSB_C1.items():
            value = tb.compute_team_value(
                self.records[team_id],
                self.records,
                _CONTEXT,
                after_round=7,
            )
            self.assertEqual(value, expected, f'EMMSB-C1 for team {team_id}')

    # ----- Exercise 39: EGMSB (no cut) --------------------------------------

    # PDF Ex 39 p.59 — opponent GP × own MP.
    EX39_EGMSB = {1: 158.0, 2: 144.0, 3: 150.0, 4: 146.0, 5: 132.0}

    def test_ex39_egmsb_for_tied_teams(self):
        tb = self._esb(ESBVariant.EGMSB)
        for team_id, expected in self.EX39_EGMSB.items():
            value = tb.compute_team_value(
                self.records[team_id],
                self.records,
                _CONTEXT,
                after_round=7,
            )
            self.assertAlmostEqual(
                value, expected, places=1, msg=f'EGMSB for team {team_id}'
            )

    # ----- Exercise 40: EMGSB for 6-MP teams --------------------------------

    # PDF Ex 40 p.60 — opponent MP × own GP. Worked examples for #7, #9, #13.
    EX40_EMGSB = {7: 68.5, 9: 83.0, 13: 73.0}

    def test_ex40_emgsb_for_six_mp_teams(self):
        tb = self._esb(ESBVariant.EMGSB)
        for team_id, expected in self.EX40_EMGSB.items():
            value = tb.compute_team_value(
                self.records[team_id],
                self.records,
                _CONTEXT,
                after_round=7,
            )
            self.assertAlmostEqual(
                value, expected, places=1, msg=f'EMGSB for team {team_id}'
            )

    # ----- Exercise 41: EGGSB for 7-MP teams --------------------------------

    # PDF Ex 41 p.60 — opponent GP × own GP. Worked examples for #6 and #8.
    EX41_EGGSB = {6: 157.5, 8: 181.5}

    def test_ex41_eggsb_for_seven_mp_teams(self):
        tb = self._esb(ESBVariant.EGGSB)
        for team_id, expected in self.EX41_EGGSB.items():
            value = tb.compute_team_value(
                self.records[team_id],
                self.records,
                _CONTEXT,
                after_round=7,
            )
            self.assertAlmostEqual(
                value, expected, places=2, msg=f'EGGSB for team {team_id}'
            )

    # ----- Summary table (page 61) sanity-checks for the rest of the field -

    # Per-team EMMSB / EGMSB / EMGSB / EGGSB from the page 61 wrap-up
    # table. Falcons (#6) EMMSB is **32** here, not the 33 the PDF
    # summary prints — the PDF itself states on page 60 that
    # "forfeit losses... [their] contribution is always null" (the
    # rule confirmed by every other team and by Falcons' EGM/EMG/EGG
    # values, which all match the summary), so the printed 33 is a
    # transcription error in that single cell.
    EX_SUMMARY = {
        # team_id: (EMMSB, EGMSB, EMGSB, EGGSB)
        1: (88, 158.0, 158.5, 283.0),
        2: (74, 144.0, 131.0, 249.75),
        3: (76, 150.0, 128.0, 247.5),
        4: (72, 146.0, 130.0, 253.5),
        5: (70, 132.0, 125.0, 236.0),
        6: (32, 79.5, 73.0, 157.5),  # PDF prints EMMSB 33 — typo, correct value 32
        7: (33, 78.5, 68.5, 155.0),
        8: (30, 79.0, 77.0, 181.5),
        9: (26, 66.5, 83.0, 180.0),
        10: (19, 53.0, 72.5, 161.75),
        11: (16, 45.0, 61.0, 138.5),
        12: (6, 19.0, 33.5, 83.75),
        13: (30, 72.0, 73.0, 152.5),
        14: (19, 48.0, 58.0, 140.75),
    }

    def test_summary_table_emm_egm_emg_egg(self):
        for team_id, (emm, egm, emg, egg) in self.EX_SUMMARY.items():
            self._check_variant(team_id, ESBVariant.EMMSB, emm)
            self._check_variant(team_id, ESBVariant.EGMSB, egm)
            self._check_variant(team_id, ESBVariant.EMGSB, emg)
            self._check_variant(team_id, ESBVariant.EGGSB, egg)

    def _check_variant(
        self, team_id: int, variant: ESBVariant, expected: float
    ) -> None:
        tb = self._esb(variant)
        value = tb.compute_team_value(
            self.records[team_id],
            self.records,
            _CONTEXT,
            after_round=7,
        )
        self.assertAlmostEqual(
            value,
            expected,
            places=2,
            msg=f'{variant.value} for team {team_id}',
        )

    # ----- Exercise 42: EDE on 4-MP tied {Koalas, Narwhals} -----------------

    def test_ex42_ede_two_teams_drew(self):
        """Koalas (11) and Narwhals (14) drew their direct match; sub-MP
        and sub-GP both yield identical sub-scores → EDE cannot split."""
        ede = ExtendedDirectEncounterTieBreak([])
        group = [self.records[11], self.records[14]]
        values = ede.compute_all_team_values(
            [group], self.records, _CONTEXT, after_round=7
        )
        # Same rank delta = still tied.
        self.assertEqual(values[11], values[14])

    # ----- Exercise 43: EDE on 7-MP tied {Falcons, Hippopotami} -------------

    def test_ex43_ede_two_teams_one_won(self):
        """Falcons beat Hippopotami 3-1 in R3 → Falcons ranks ahead."""
        ede = ExtendedDirectEncounterTieBreak([])
        group = [self.records[6], self.records[8]]
        values = ede.compute_all_team_values(
            [group], self.records, _CONTEXT, after_round=7
        )
        # Higher delta = better. Falcons should outrank Hippopotami.
        self.assertGreater(values[6], values[8])
        self.assertEqual({values[6], values[8]}, {0.0, 1.0})

    # ----- Exercise 44: EDE on 6-MP tied {Giraffes, Iguanas, Moose} --------

    def test_ex44_ede_three_teams_unresolved(self):
        """Iguanas and Moose never played each other; even after the
        secondary-score retry, min/max ranges of the missing match keep
        all three in one bracket → EDE leaves the group tied."""
        ede = ExtendedDirectEncounterTieBreak([])
        group = [self.records[7], self.records[9], self.records[13]]
        values = ede.compute_all_team_values(
            [group], self.records, _CONTEXT, after_round=7
        )
        self.assertEqual(values[7], values[9])
        self.assertEqual(values[9], values[13])

    # ----- Exercise 45: EDE on 10-MP tied {1..5} ---------------------------

    EX45_EDE_RANK = {  # final rank, 0 = best
        4: 0,
        2: 1,
        1: 2,
        3: 3,
        5: 4,
    }

    def test_ex45_ede_five_teams_resolved_via_secondary(self):
        """All five played each other; sub-MP is tied 4-4-4-4-4 so the
        algorithm falls back to GP and produces the published order
        #4, #2, #1, #3, #5."""
        ede = ExtendedDirectEncounterTieBreak([])
        group = [self.records[i] for i in (1, 2, 3, 4, 5)]
        values = ede.compute_all_team_values(
            [group], self.records, _CONTEXT, after_round=7
        )
        # Higher delta = better; convert to final standings.
        order = sorted(values.items(), key=lambda kv: -kv[1])
        ranks = {team_id: rank for rank, (team_id, _v) in enumerate(order)}
        self.assertEqual(ranks, self.EX45_EDE_RANK)

    # ----- Exercise 49: SSSC values for every team -------------------------

    EX49_SSSC = {
        1: 38.83,
        2: 36.00,
        3: 35.33,
        4: 35.67,
        5: 36.33,
        6: 27.83,
        7: 26.17,
        8: 28.67,
        9: 31.17,
        10: 27.67,
        11: 25.17,
        12: 21.17,
        13: 28.83,
        14: 23.50,
    }

    def test_ex49_sssc_normalisation_factor(self):
        """7 rounds × 2 MP-per-win = 14 max primary; 4 GP-per-match max
        secondary; F_N = floor(14/4) = 3."""
        factor = ScoresAndScheduleStrengthCombinationTieBreak.normalization_factor(
            _CONTEXT
        )
        self.assertEqual(factor, 3)

    def test_ex49_sssc_all_teams(self):
        tb = ScoresAndScheduleStrengthCombinationTieBreak([])
        for team_id, expected in self.EX49_SSSC.items():
            value = tb.compute_team_value(
                self.records[team_id],
                self.records,
                _CONTEXT,
                after_round=7,
            )
            self.assertAlmostEqual(
                value, expected, places=2, msg=f'SSSC for team {team_id}'
            )

    def test_ex49_sssc_normalization_factor_gp_primary_example(self):
        """PDF Ex 49 second example: 9 rounds, 4-player teams, GP
        primary → F_N = floor(36/2) = 18."""
        ctx = TeamTieBreakContext(
            primary_score=ScoreType.GAME_POINTS,
            secondary_score=ScoreType.MATCH_POINTS,
            rounds=9,
            win_mp=2.0,
            draw_mp=1.0,
            loss_mp=0.0,
            team_player_count=4,
            draw_gp=2.0,
        )
        factor = ScoresAndScheduleStrengthCombinationTieBreak.normalization_factor(ctx)
        self.assertEqual(factor, 18)


@pytest.mark.unit
class BerlinTieBreakTestCase(TestCase):
    """FFE Berlin / Coefficient d'échiquier (FFE rules §11.1).

    Reproduces the worked example from the FFE rulebook: 8-board match,
    Team A scores 1-0-0-½-1-0-½-1 → Berlin 16.5;
    Team B scores 0-1-1-½-0-1-½-0 → Berlin 19.5
    (so Team B wins on Berlin despite a 4-4 game-point draw)."""

    def test_ffe_rulebook_eight_board_example(self):
        from plugins.ffe.ffe_tie_breaks import BerlinTieBreak

        team_a_boards = (1.0, 0.0, 0.0, 0.5, 1.0, 0.0, 0.5, 1.0)
        team_b_boards = (0.0, 1.0, 1.0, 0.5, 0.0, 1.0, 0.5, 0.0)
        team_a = TeamRecord(
            team_id=1,
            name='A',
            total_mp=1.0,
            total_gp=4.0,
            matches=[
                TeamMatchRecord(
                    round_=1,
                    opponent_id=2,
                    own_mp=1.0,
                    own_gp=4.0,
                    match_type=TeamMatchType.PLAYED,
                    board_scores=team_a_boards,
                ),
            ],
        )
        team_b = TeamRecord(
            team_id=2,
            name='B',
            total_mp=1.0,
            total_gp=4.0,
            matches=[
                TeamMatchRecord(
                    round_=1,
                    opponent_id=1,
                    own_mp=1.0,
                    own_gp=4.0,
                    match_type=TeamMatchType.PLAYED,
                    board_scores=team_b_boards,
                ),
            ],
        )
        records = {1: team_a, 2: team_b}
        context = TeamTieBreakContext(
            primary_score=ScoreType.MATCH_POINTS,
            secondary_score=ScoreType.GAME_POINTS,
            rounds=1,
            win_mp=2.0,
            draw_mp=1.0,
            loss_mp=0.0,
            team_player_count=8,
            draw_gp=4.0,
        )
        tb = BerlinTieBreak([])
        self.assertEqual(
            tb.compute_team_value(team_a, records, context, after_round=1),
            16.5,
        )
        self.assertEqual(
            tb.compute_team_value(team_b, records, context, after_round=1),
            19.5,
        )

    def test_berlin_ignores_unplayed_matches_with_no_board_data(self):
        """Forfeits / byes record no board_scores → Berlin contribution
        is zero for that round, matching the FFE convention that only
        actually-played boards carry a coefficient."""
        from plugins.ffe.ffe_tie_breaks import BerlinTieBreak

        team = TeamRecord(
            team_id=1,
            name='A',
            total_mp=2.0,
            total_gp=4.0,
            matches=[
                TeamMatchRecord(
                    round_=1,
                    opponent_id=2,
                    own_mp=2.0,
                    own_gp=4.0,
                    match_type=TeamMatchType.PLAYED,
                    board_scores=(1.0, 1.0, 1.0, 1.0),
                ),
                TeamMatchRecord(
                    round_=2,
                    opponent_id=None,
                    own_mp=0.0,
                    own_gp=0.0,
                    match_type=TeamMatchType.FORFEIT_LOSS,
                    board_scores=(),
                ),
            ],
        )
        records = {1: team}
        context = TeamTieBreakContext(
            primary_score=ScoreType.MATCH_POINTS,
            secondary_score=ScoreType.GAME_POINTS,
            rounds=2,
            win_mp=2.0,
            draw_mp=1.0,
            loss_mp=0.0,
            team_player_count=4,
            draw_gp=2.0,
        )
        tb = BerlinTieBreak([])
        # 4 + 3 + 2 + 1 = 10 from R1 only; R2 forfeit contributes 0.
        self.assertEqual(
            tb.compute_team_value(team, records, context, after_round=2),
            10.0,
        )


@pytest.mark.unit
class GamePointsDifferentialTieBreakTestCase(TestCase):
    """FFE *Différentiel des points de parties* — Σ (own_gp - opp_gp)
    across rounds. Coupe Loubatière §4.4.a."""

    @staticmethod
    def _context() -> TeamTieBreakContext:
        return TeamTieBreakContext(
            primary_score=ScoreType.MATCH_POINTS,
            secondary_score=ScoreType.GAME_POINTS,
            rounds=3,
            win_mp=3.0,
            draw_mp=2.0,
            loss_mp=1.0,
            team_player_count=4,
            draw_gp=0.0,
        )

    def test_two_team_played_match_subtracts_opponent_gp(self):
        from plugins.ffe.ffe_tie_breaks import GamePointsDifferentialTieBreak

        team_a = TeamRecord(
            team_id=1,
            name='A',
            total_mp=0.0,
            total_gp=3.0,
            matches=[
                TeamMatchRecord(
                    round_=1,
                    opponent_id=2,
                    own_mp=3.0,
                    own_gp=3.0,
                    match_type=TeamMatchType.PLAYED,
                ),
            ],
        )
        team_b = TeamRecord(
            team_id=2,
            name='B',
            total_mp=0.0,
            total_gp=1.0,
            matches=[
                TeamMatchRecord(
                    round_=1,
                    opponent_id=1,
                    own_mp=1.0,
                    own_gp=1.0,
                    match_type=TeamMatchType.PLAYED,
                ),
            ],
        )
        records = {1: team_a, 2: team_b}
        tb = GamePointsDifferentialTieBreak([])
        self.assertEqual(
            tb.compute_team_value(team_a, records, self._context(), after_round=1),
            2.0,
        )
        self.assertEqual(
            tb.compute_team_value(team_b, records, self._context(), after_round=1),
            -2.0,
        )

    def test_pab_counts_full_own_gp_with_no_subtraction(self):
        """No opponent → no opp_gp → differential = own_gp."""
        from plugins.ffe.ffe_tie_breaks import GamePointsDifferentialTieBreak

        team = TeamRecord(
            team_id=1,
            name='A',
            total_mp=3.0,
            total_gp=4.0,
            matches=[
                TeamMatchRecord(
                    round_=1,
                    opponent_id=None,
                    own_mp=3.0,
                    own_gp=4.0,
                    match_type=TeamMatchType.PAB,
                ),
            ],
        )
        tb = GamePointsDifferentialTieBreak([])
        self.assertEqual(
            tb.compute_team_value(team, {1: team}, self._context(), after_round=1),
            4.0,
        )

    def test_forfeit_loss_contributes_zero(self):
        from plugins.ffe.ffe_tie_breaks import GamePointsDifferentialTieBreak

        team = TeamRecord(
            team_id=1,
            name='A',
            total_mp=0.0,
            total_gp=0.0,
            matches=[
                TeamMatchRecord(
                    round_=1,
                    opponent_id=2,
                    own_mp=0.0,
                    own_gp=0.0,
                    match_type=TeamMatchType.FORFEIT_LOSS,
                ),
            ],
        )
        tb = GamePointsDifferentialTieBreak([])
        self.assertEqual(
            tb.compute_team_value(team, {1: team}, self._context(), after_round=1),
            0.0,
        )

    def test_sums_across_rounds_and_respects_after_round(self):
        from plugins.ffe.ffe_tie_breaks import GamePointsDifferentialTieBreak

        team_a = TeamRecord(
            team_id=1,
            name='A',
            total_mp=0.0,
            total_gp=0.0,
            matches=[
                TeamMatchRecord(
                    round_=1,
                    opponent_id=2,
                    own_mp=3.0,
                    own_gp=3.0,
                    match_type=TeamMatchType.PLAYED,
                ),
                TeamMatchRecord(
                    round_=2,
                    opponent_id=2,
                    own_mp=1.0,
                    own_gp=1.0,
                    match_type=TeamMatchType.PLAYED,
                ),
            ],
        )
        team_b = TeamRecord(
            team_id=2,
            name='B',
            total_mp=0.0,
            total_gp=0.0,
            matches=[
                TeamMatchRecord(
                    round_=1,
                    opponent_id=1,
                    own_mp=1.0,
                    own_gp=1.0,
                    match_type=TeamMatchType.PLAYED,
                ),
                TeamMatchRecord(
                    round_=2,
                    opponent_id=1,
                    own_mp=1.0,
                    own_gp=2.0,
                    match_type=TeamMatchType.PLAYED,
                ),
            ],
        )
        records = {1: team_a, 2: team_b}
        tb = GamePointsDifferentialTieBreak([])
        # After R1 only: A = 3-1 = +2
        self.assertEqual(
            tb.compute_team_value(team_a, records, self._context(), after_round=1),
            2.0,
        )
        # After R2: A = (3-1) + (1-2) = +1
        self.assertEqual(
            tb.compute_team_value(team_a, records, self._context(), after_round=2),
            1.0,
        )

    def test_negative_match_total_clamps_before_subtracting(self):
        from plugins.ffe.ffe_tie_breaks import GamePointsDifferentialTieBreak

        # Raw match: A=2, B=-1 → adjusted A=2, B=0.
        team_a = TeamRecord(
            team_id=1,
            name='A',
            total_mp=0.0,
            total_gp=2.0,
            matches=[
                TeamMatchRecord(
                    round_=1,
                    opponent_id=2,
                    own_mp=3.0,
                    own_gp=2.0,
                    match_type=TeamMatchType.PLAYED,
                )
            ],
        )
        team_b = TeamRecord(
            team_id=2,
            name='B',
            total_mp=0.0,
            total_gp=-1.0,
            matches=[
                TeamMatchRecord(
                    round_=1,
                    opponent_id=1,
                    own_mp=1.0,
                    own_gp=-1.0,
                    match_type=TeamMatchType.PLAYED,
                )
            ],
        )
        records = {1: team_a, 2: team_b}
        tb = GamePointsDifferentialTieBreak([])
        # A: 2 - 0 = +2 ; B: 0 - 2 = -2
        self.assertEqual(
            tb.compute_team_value(team_a, records, self._context(), after_round=1),
            2.0,
        )
        self.assertEqual(
            tb.compute_team_value(team_b, records, self._context(), after_round=1),
            -2.0,
        )


@pytest.mark.unit
class GamePointsForTieBreakTestCase(TestCase):
    """FFE *Points de parties « pour »* — Σ of each match's own score
    floored at 0."""

    @staticmethod
    def _context() -> TeamTieBreakContext:
        return TeamTieBreakContext(
            primary_score=ScoreType.MATCH_POINTS,
            secondary_score=ScoreType.GAME_POINTS,
            rounds=3,
            win_mp=3.0,
            draw_mp=2.0,
            loss_mp=1.0,
            team_player_count=4,
            draw_gp=0.0,
        )

    def test_sums_clamped_match_scores(self):
        from plugins.ffe.ffe_tie_breaks import GamePointsForTieBreak

        team = TeamRecord(
            team_id=1,
            name='A',
            total_mp=0.0,
            total_gp=0.0,
            matches=[
                TeamMatchRecord(
                    round_=1,
                    opponent_id=2,
                    own_mp=3.0,
                    own_gp=2.5,
                    match_type=TeamMatchType.PLAYED,
                ),
                # Negative raw match score clamps to 0 (not -1).
                TeamMatchRecord(
                    round_=2,
                    opponent_id=3,
                    own_mp=0.0,
                    own_gp=-1.0,
                    match_type=TeamMatchType.PLAYED,
                ),
                TeamMatchRecord(
                    round_=3,
                    opponent_id=None,
                    own_mp=3.0,
                    own_gp=4.0,
                    match_type=TeamMatchType.PAB,
                ),
            ],
        )
        tb = GamePointsForTieBreak([])
        # 2.5 + max(0,-1) + 4 = 6.5 ; respects after_round.
        self.assertEqual(
            tb.compute_team_value(team, {1: team}, self._context(), after_round=3),
            6.5,
        )
        self.assertEqual(
            tb.compute_team_value(team, {1: team}, self._context(), after_round=1),
            2.5,
        )


@pytest.mark.unit
class LowestOwnAverageRatingTieBreakTestCase(TestCase):
    """FFE *Moyenne des derniers Elo diffusés, la plus basse*. The
    tie-break reads ``TeamRecord.own_avg_rating`` and returns its
    negation so the lowest team wins the descending sort."""

    @staticmethod
    def _context() -> TeamTieBreakContext:
        return TeamTieBreakContext(
            primary_score=ScoreType.MATCH_POINTS,
            secondary_score=ScoreType.GAME_POINTS,
            rounds=3,
            win_mp=3.0,
            draw_mp=2.0,
            loss_mp=1.0,
            team_player_count=4,
            draw_gp=0.0,
        )

    @staticmethod
    def _team(
        team_id: int, name: str, ratings_per_round: list[tuple[int | None, ...]]
    ) -> TeamRecord:
        return TeamRecord(
            team_id=team_id,
            name=name,
            total_mp=0.0,
            total_gp=0.0,
            matches=[
                TeamMatchRecord(
                    round_=round_,
                    opponent_id=None,
                    own_mp=0.0,
                    own_gp=0.0,
                    match_type=TeamMatchType.PLAYED,
                    board_ratings=ratings,
                )
                for round_, ratings in enumerate(ratings_per_round, start=1)
            ],
        )

    def test_lower_rating_team_outranks_higher(self):
        from plugins.ffe.ffe_tie_breaks import LowestOwnAverageRatingTieBreak

        # One round, 4-board team, every player rated.
        low = self._team(1, 'Low', [(1400, 1500, 1500, 1600)])  # avg 1500
        high = self._team(2, 'High', [(1800, 1800, 1800, 1800)])  # avg 1800
        records = {1: low, 2: high}
        tb = LowestOwnAverageRatingTieBreak([])
        # Tie-break is descending — the higher returned value wins.
        # Lower rating must return the larger (less-negative) value.
        self.assertGreater(
            tb.compute_team_value(low, records, self._context(), after_round=1),
            tb.compute_team_value(high, records, self._context(), after_round=1),
        )
        self.assertEqual(
            tb.compute_team_value(low, records, self._context(), after_round=1),
            -1500.0,
        )

    def test_weighted_by_appearances_across_rounds(self):
        """A regular starter counts in every round; a substitute fielded
        once weighs 1/N. The average is over (player, round) samples,
        not over the roster."""
        from plugins.ffe.ffe_tie_breaks import LowestOwnAverageRatingTieBreak

        # 3 rounds, board 4 occupied by 1200-rated player only in R3.
        team = self._team(
            1,
            'A',
            [
                (1500, 1500, 1500, 1500),
                (1500, 1500, 1500, 1500),
                (1500, 1500, 1500, 1200),
            ],
        )
        tb = LowestOwnAverageRatingTieBreak([])
        # (11 × 1500 + 1 × 1200) / 12 = 1475
        self.assertEqual(
            tb.compute_team_value(team, {1: team}, self._context(), after_round=3),
            -1475.0,
        )

    def test_unrated_players_excluded_from_average(self):
        from plugins.ffe.ffe_tie_breaks import LowestOwnAverageRatingTieBreak

        team = self._team(1, 'A', [(1600, 1400, None, None)])  # avg of two rated
        tb = LowestOwnAverageRatingTieBreak([])
        self.assertEqual(
            tb.compute_team_value(team, {1: team}, self._context(), after_round=1),
            -1500.0,
        )

    def test_no_ratings_returns_zero(self):
        from plugins.ffe.ffe_tie_breaks import LowestOwnAverageRatingTieBreak

        team = TeamRecord(
            team_id=1,
            name='Empty',
            total_mp=0.0,
            total_gp=0.0,
        )
        tb = LowestOwnAverageRatingTieBreak([])
        self.assertEqual(
            tb.compute_team_value(team, {1: team}, self._context(), after_round=1),
            0.0,
        )
