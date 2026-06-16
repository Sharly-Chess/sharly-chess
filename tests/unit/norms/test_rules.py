"""Pure-function tests for the FIDE title-norm rules.

Source spec: docs/technical-appendices/fide-title-norms.md
(FIDE Handbook B.01, effective 1 January 2024).

These tests cover the deterministic helpers — thresholds, table lookups,
rounding, federation caps, title-holder set — without touching the
database or building synthetic tournaments. Integration scenarios
(achieves_any_title_norm) live in test_norm_check.py.
"""

from __future__ import annotations

from unittest import TestCase

import pytest

from utils import Utils
from utils.enum import PlayerGender, PlayerTitle, Result, TitleNorm


# ---------------------------------------------------------------------------
# 1.4.6 — minimum rating floor for opponents
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'norm,expected',
    [
        (TitleNorm.GM, 2200),
        (TitleNorm.IM, 2050),
        (TitleNorm.WGM, 2000),
        (TitleNorm.WIM, 1850),
    ],
)
def test_minimum_rating_floor(norm: TitleNorm, expected: int):
    assert norm.minimum_rating == expected


# ---------------------------------------------------------------------------
# 1.4.8a — minimum opponent average (Ra)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'norm,expected',
    [
        (TitleNorm.GM, 2380),
        (TitleNorm.IM, 2230),
        (TitleNorm.WGM, 2180),
        (TitleNorm.WIM, 2030),
    ],
)
def test_minimum_average_opponent_rating(norm: TitleNorm, expected: int):
    assert norm.minimum_average == expected


# ---------------------------------------------------------------------------
# 1.4.8 — minimum performance rating (Rp)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'norm,expected',
    [
        (TitleNorm.GM, 2600),
        (TitleNorm.IM, 2450),
        (TitleNorm.WGM, 2400),
        (TitleNorm.WIM, 2250),
    ],
)
def test_minimum_performance(norm: TitleNorm, expected: int):
    assert norm.minimum_performance == expected


# ---------------------------------------------------------------------------
# 1.4.5a — TITLE_HOLDERS set (CM/WCM explicitly excluded)
# ---------------------------------------------------------------------------


def test_title_holders_includes_required_titles():
    expected = {
        PlayerTitle.GRANDMASTER,
        PlayerTitle.INTERNATIONAL_MASTER,
        PlayerTitle.WOMAN_GRANDMASTER,
        PlayerTitle.WOMAN_INTERNATIONAL_MASTER,
        PlayerTitle.FIDE_MASTER,
        PlayerTitle.WOMAN_FIDE_MASTER,
    }
    assert set(TitleNorm.TITLE_HOLDERS) == expected


def test_title_holders_excludes_cm_wcm():
    # 1.4.5a: "title-holders (TH) as in 0.3, excluding CM and WCM."
    assert PlayerTitle.CANDIDATE_MASTER not in TitleNorm.TITLE_HOLDERS
    assert PlayerTitle.WOMAN_CANDIDATE_MASTER not in TitleNorm.TITLE_HOLDERS


def test_title_holders_excludes_none():
    assert PlayerTitle.NONE not in TitleNorm.TITLE_HOLDERS


def test_title_holders_is_not_an_enum_member():
    # enum.nonmember sanity — TitleNorm should still have exactly 4 members.
    assert {m.name for m in TitleNorm} == {'WIM', 'WGM', 'IM', 'GM'}


# ---------------------------------------------------------------------------
# 1.4.3d — MASTER_TITLES set (GM/IM/WGM/WIM only; FM/WFM/CM/WCM excluded)
# ---------------------------------------------------------------------------


def test_master_titles_set():
    # Spec 1.4.3d: "at least 10 GM/IM/WGM/WIM titleholders" — FM/WFM NOT included.
    assert set(TitleNorm.MASTER_TITLES) == {
        PlayerTitle.GRANDMASTER,
        PlayerTitle.INTERNATIONAL_MASTER,
        PlayerTitle.WOMAN_GRANDMASTER,
        PlayerTitle.WOMAN_INTERNATIONAL_MASTER,
    }


def test_master_titles_excludes_fm_wfm():
    assert PlayerTitle.FIDE_MASTER not in TitleNorm.MASTER_TITLES
    assert PlayerTitle.WOMAN_FIDE_MASTER not in TitleNorm.MASTER_TITLES


def test_master_titles_is_not_an_enum_member():
    # Adding the constant must not have changed TitleNorm's enum members.
    assert {m.name for m in TitleNorm} == {'WIM', 'WGM', 'IM', 'GM'}


# ---------------------------------------------------------------------------
# 1.4.5 — required titles per norm
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'norm,expected',
    [
        (
            TitleNorm.GM,
            {PlayerTitle.GRANDMASTER},
        ),
        (
            TitleNorm.IM,
            {PlayerTitle.GRANDMASTER, PlayerTitle.INTERNATIONAL_MASTER},
        ),
        (
            TitleNorm.WGM,
            {
                PlayerTitle.GRANDMASTER,
                PlayerTitle.INTERNATIONAL_MASTER,
                PlayerTitle.WOMAN_GRANDMASTER,
            },
        ),
        (
            TitleNorm.WIM,
            {
                PlayerTitle.GRANDMASTER,
                PlayerTitle.INTERNATIONAL_MASTER,
                PlayerTitle.WOMAN_GRANDMASTER,
                PlayerTitle.WOMAN_INTERNATIONAL_MASTER,
            },
        ),
    ],
)
def test_required_titles(norm: TitleNorm, expected: set[PlayerTitle]):
    assert set(norm.required_titles) == expected


# ---------------------------------------------------------------------------
# 1.4.8b — minimum score (35%)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'rounds,expected_points',
    [
        # WIN = 1 point. 35% of N rounds.
        (9, 0.35 * 9 * Result.WIN.points()),
        (10, 0.35 * 10 * Result.WIN.points()),
        (11, 0.35 * 11 * Result.WIN.points()),
        (13, 0.35 * 13 * Result.WIN.points()),
    ],
)
def test_minimum_score_threshold(rounds: int, expected_points: float):
    assert TitleNorm.minimum_score(rounds) == pytest.approx(expected_points)


# ---------------------------------------------------------------------------
# 1.4.5a — minimum number of titled opponents (50% rounded up)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'rounds,expected',
    [
        (9, 5),  # ceil(9/2) = 5
        (10, 5),  # ceil(10/2) = 5
        (11, 6),
        (13, 7),
    ],
)
def test_minimum_title_holders(rounds: int, expected: int):
    assert TitleNorm.minimum_title_holders(rounds) == expected


# ---------------------------------------------------------------------------
# 1.4.4 — federation caps (3/5 own, 2/3 from any one; "to next lower number")
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'rounds,expected',
    [
        # max own = floor(3*rounds/5)
        (9, 5),  # floor(27/5) = 5
        (10, 6),
        (11, 6),
        (13, 7),
    ],
)
def test_maximum_of_own_federation(rounds: int, expected: int):
    assert TitleNorm.maximum_of_own_federation(rounds) == expected


@pytest.mark.parametrize(
    'rounds,expected',
    [
        # max one fed = floor(2*rounds/3)
        (9, 6),
        (10, 6),
        (11, 7),
        (13, 8),
    ],
)
def test_maximum_of_one_federation(rounds: int, expected: int):
    assert TitleNorm.maximum_of_one_federation(rounds) == expected


# ---------------------------------------------------------------------------
# 0.5 — gender requirement for women's titles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'norm,gender,expected',
    [
        (TitleNorm.GM, PlayerGender.MAN, True),
        (TitleNorm.GM, PlayerGender.WOMAN, True),
        (TitleNorm.IM, PlayerGender.MAN, True),
        (TitleNorm.IM, PlayerGender.WOMAN, True),
        (TitleNorm.WGM, PlayerGender.MAN, False),
        (TitleNorm.WGM, PlayerGender.WOMAN, True),
        (TitleNorm.WIM, PlayerGender.MAN, False),
        (TitleNorm.WIM, PlayerGender.WOMAN, True),
    ],
)
def test_satisfies_gender_requirement(
    norm: TitleNorm, gender: PlayerGender, expected: bool
):
    assert norm.satisfies_gender_requirement(gender) is expected


# ---------------------------------------------------------------------------
# 0.5 — mapping TitleNorm -> player title awarded
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'norm,expected_title',
    [
        (TitleNorm.GM, PlayerTitle.GRANDMASTER),
        (TitleNorm.IM, PlayerTitle.INTERNATIONAL_MASTER),
        (TitleNorm.WGM, PlayerTitle.WOMAN_GRANDMASTER),
        (TitleNorm.WIM, PlayerTitle.WOMAN_INTERNATIONAL_MASTER),
    ],
)
def test_player_title_mapping(norm: TitleNorm, expected_title: PlayerTitle):
    assert norm.player_title == expected_title


# ---------------------------------------------------------------------------
# 1.4.7 — opponent average rounding (round-half-up)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'raw,expected',
    [
        (2380.0, 2380),
        (2380.49, 2380),
        (2380.50, 2381),  # 0.5 rounds up
        (2380.51, 2381),
        (2379.99, 2380),
        (-0.5, 0),  # round-half-up of -0.5 is 0 (per impl: lowest_int=-1, +1=0)
    ],
)
def test_round_ranking_half_up(raw: float, expected: int):
    assert Utils.round_ranking(raw) == expected


# ---------------------------------------------------------------------------
# 1.4.9 — performance bonus table (Rp = Ra + dp)
# ---------------------------------------------------------------------------
# Selected entries lifted directly from FIDE 1.4.9.
# Sign convention: p > 0.5 → positive dp; p < 0.5 → negative dp; p == 0.5 → 0.


@pytest.mark.parametrize(
    'fractional_score,expected_dp',
    [
        # Anchor points
        (0.50, 0),
        (1.00, 800),
        (0.00, -800),
        # Spot-checks above 0.5
        (0.51, 7),
        (0.66, 117),
        (0.67, 125),
        (0.75, 193),
        (0.83, 273),
        (0.99, 677),
        # Mirror below 0.5
        (0.49, -7),
        (0.34, -117),
        (0.33, -125),
        (0.25, -193),
        (0.17, -273),
        (0.01, -677),
    ],
)
def test_performance_bonus(fractional_score: float, expected_dp: int):
    assert Utils.performance_bonus(fractional_score) == expected_dp


def test_performance_table_length():
    # 1.4.9 table spans p = .50..1.00 in 0.01 steps → 51 entries.
    assert len(Utils.PERFORMANCE_TABLE) == 51


def test_performance_table_anchors():
    assert Utils.PERFORMANCE_TABLE[0] == 0  # p = 0.50
    assert Utils.PERFORMANCE_TABLE[50] == 800  # p = 1.00 (or 0.00 with sign flip)


# ---------------------------------------------------------------------------
# 1.4.8 — Rp = Ra + dp end-to-end
# ---------------------------------------------------------------------------


class TestPerformanceRatingFormula(TestCase):
    """Cross-check Rp = Ra + dp against worked examples a TD might compute
    by hand from the FIDE table. Ra rounding follows 1.4.7."""

    def test_perfect_score(self):
        # 9 opponents averaging 2400, scored 9/9 (100%).
        ra = 2400
        dp = Utils.performance_bonus(1.00)
        assert ra + dp == 3200  # 2400 + 800

    def test_break_even_score(self):
        ra = 2400
        dp = Utils.performance_bonus(0.50)
        assert ra + dp == 2400  # 2400 + 0

    def test_gm_norm_threshold_example(self):
        # Minimum GM Ra = 2380. To hit Rp >= 2600, need dp >= 220.
        # 0.78 corresponds to dp = 220 per FIDE 1.4.9.
        assert Utils.performance_bonus(0.78) == 220
        assert 2380 + 220 >= TitleNorm.GM.minimum_performance
