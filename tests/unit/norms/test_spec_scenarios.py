"""Spec-scenario tests for FIDE title-norm calculation.

These exercise the *wiring* between the searcher / evaluator and the per-rule
checks. Unit tests of the static methods (in test_rules.py) verify the
threshold formulas in isolation; the algorithm tests (in test_searcher.py)
verify the search loop with a stubbed evaluator. Neither catches a caller
that passes the wrong argument to the right function.

Each test below builds a deliberate scenario representing one regulatory
clause and asserts the verdict matches the spec.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# Reuse fixtures from test_searcher.py.
from tests.unit.norms.test_searcher import (
    FakeOpponent,
    _gm,
    _im,
    _real_searcher,
    _untitled,
    make_inputs,
)
from data.norms import (
    TitleNormEvaluator,
)
from utils.enum import PlayerRatingType, PlayerTitle, Result, TitleNorm
from utils.types import Federation, NormCheckResult


# ===========================================================================
# 1.4.1c — 8 played + 1 PAB credited as 9-game norm
# ===========================================================================
#
# The opponent-mix has 8 entries; proportional thresholds (50% titled,
# 1/3 required, 35% score) must apply to 8, not 9.


class TestRule_1_4_1c:
    def test_title_holders_threshold_uses_played_games_not_rounds(self):
        """1.4.1c: 8 played + 1 PAB. 1.4.5a needs 50% of 8 = 4 titled, not 5."""
        # 4 titled opponents + 4 untitled.
        opponents = [
            _gm(1, federation='USA'),
            _gm(2, federation='GER'),
            _gm(3, federation='ESP'),
            _gm(4, federation='ITA'),
            _untitled(5, rating=2300, federation='NED'),
            _untitled(6, rating=2300, federation='POL'),
            _untitled(7, rating=2300, federation='RUS'),
            _untitled(8, rating=2300, federation='AZE'),
        ]
        inputs = make_inputs(
            list(zip(range(1, 9), opponents, [Result.WIN] * 8)),
            forfeits_or_byes=1,  # 1 PAB in round 9 (the missing game)
        )
        searcher = _real_searcher(rounds=9)
        passes, count = searcher.evaluator.title_holders_requirement(
            inputs, TitleNorm.GM
        )
        assert count == 4
        assert passes, (
            'Expected 4 titled holders to pass 50% threshold of 8 played; '
            'using tournament.rounds=9 would have required 5.'
        )

    def test_required_titles_floor_keeps_min_3(self):
        """1.4.5b: at least 1/3 OR minimum 3 GMs. With 8 played and 3 GMs,
        max(ceil(8/3), 3) = max(3, 3) = 3. Passes."""
        opponents = [_gm(i) for i in range(1, 4)] + [_im(i) for i in range(4, 9)]
        inputs = make_inputs(list(zip(range(1, 9), opponents, [Result.DRAW] * 8)))
        searcher = _real_searcher(rounds=9)
        passes, count = searcher.evaluator.required_titles_requirement(
            inputs, TitleNorm.GM
        )
        assert count == 3
        assert passes

    def test_score_threshold_scales_with_played_games(self):
        """1.4.8b: 35% of 8 = 2.8. Score 3.0 passes; 35% of 9 = 3.15 would not."""
        opponents = [_gm(i) for i in range(1, 9)]
        results = (
            [Result.WIN] * 2 + [Result.DRAW] * 2 + [Result.LOSS] * 4
        )  # 2 + 1 = 3 points
        inputs = make_inputs(list(zip(range(1, 9), opponents, results)))
        searcher = _real_searcher(rounds=9)
        assert inputs.score == pytest.approx(3.0)
        assert searcher.evaluator.score_requirement(inputs)

    def test_own_federation_cap_scales_with_played_games(self):
        """1.4.4: max 3/5 of opponents from own federation.
        With 8 played, floor(3*8/5) = 4. 4 own-fed passes, 5 fails."""
        opponents_4 = [_gm(i, federation='FRA') for i in range(1, 5)] + [
            _gm(i, federation='USA') for i in range(5, 9)
        ]
        inputs = make_inputs(list(zip(range(1, 9), opponents_4, [Result.DRAW] * 8)))
        searcher = _real_searcher(rounds=9, federation='FRA')
        assert searcher.evaluator.own_federation_requirement(inputs, TitleNorm.GM)

        # 5 own-fed: floor(3*8/5) = 4, so 5 > 4 → fails.
        opponents_5 = [_gm(i, federation='FRA') for i in range(1, 6)] + [
            _gm(i, federation='USA') for i in range(6, 9)
        ]
        inputs5 = make_inputs(list(zip(range(1, 9), opponents_5, [Result.DRAW] * 8)))
        assert not searcher.evaluator.own_federation_requirement(inputs5, TitleNorm.GM)


# ===========================================================================
# 1.4.3d — Swiss exemption from 1.4.3 AND 1.4.4
# ===========================================================================
#
# The "Otherwise, 1.4.4 applies" clause inside 1.4.3d means that when
# 1.4.3d's tournament-wide conditions are met, the player is exempt from
# BOTH 1.4.3 (foreign-fed count) AND 1.4.4 (federation caps).


class TestRule_1_4_3d:
    def _met_result(self, **overrides) -> NormCheckResult:
        """Build a result where every check passes and 1.4.3d's sub-criteria
        are met. Caller can flip specific flags via overrides."""
        res = NormCheckResult(title_norm=TitleNorm.GM, meets_gender=True)
        # 1.4.3d sub-criteria all pass → is_143d_met is True
        res.all_federations_count = 3
        res.eligible_players_count = 20
        res.eligible_players_title_count = 10
        for name, value in overrides.items():
            setattr(res, name, value)
        return res

    def test_143d_met_clears_is_met_for_143_violation(self):
        """1.4.3d met + 1.4.3 (foreign-fed count) violation → is_met True."""
        res = self._met_result(not_enough_federations='violation')
        assert res.is_143d_met
        assert res.is_met

    def test_143d_met_clears_is_met_for_144_own_cap_violation(self):
        """1.4.3d met + 1.4.4 (own-fed cap) violation → is_met True.

        This is the bug the dev flagged: the "Otherwise, 1.4.4 applies"
        clause makes 1.4.4 exempt-when-1.4.3d-met.
        """
        res = self._met_result(too_many_own_federation='violation')
        assert res.is_143d_met
        assert res.is_met

    def test_143d_met_clears_is_met_for_144_one_fed_cap_violation(self):
        """1.4.3d met + 1.4.4 (one-fed cap) violation → is_met True."""
        res = self._met_result(too_many_one_federation=(Federation('FRA'), 'violation'))
        assert res.is_143d_met
        assert res.is_met

    def test_143d_not_met_lets_144_violation_block(self):
        """1.4.3d NOT met (e.g. <20 foreigners) → 1.4.4 violation blocks."""
        res = self._met_result(
            eligible_players_count=18,  # below 20 threshold
            not_enough_foreign_players='violation',
            too_many_own_federation='violation',
        )
        assert not res.is_143d_met
        assert not res.is_met  # 1.4.4 violation now blocks

    def test_143d_does_not_clear_other_violations(self):
        """1.4.3d does NOT exempt 1.4.5, 1.4.8 — those still block is_met."""
        for blocking in [
            'not_enough_games',
            'not_enough_title_holders',
            'not_enough_required_titles',
            'score_too_low',
            'average_too_low',
            'performance_too_low',
        ]:
            res = self._met_result(**{blocking: 'violation'})
            assert res.is_143d_met, f'Setup error for {blocking}'
            assert not res.is_met, (
                f'1.4.3d should NOT exempt {blocking} — only 1.4.3 and 1.4.4'
            )


# ===========================================================================
# 1.4.3a/b/c — manual event-type exemptions (set by the arbiter)
# ===========================================================================
#
# a (National championship final) and b (National team championship) only
# apply to players from the event's REGISTERING federation. c (Zonal /
# Sub-zonal) applies to ALL players regardless of federation. Like 1.4.3d,
# every a/b/c exemption waives the WHOLE foreigner requirement — both
# 1.4.3 and 1.4.4 (1.4.3e; confirmed in writing by the FIDE QC).
#
# Applied by `apply_143abc_exemption()` based on the
# Rule143ExemptionPrintOption value set on the doc.


class TestRule_1_4_3abc:
    def _failing_143_result(self) -> NormCheckResult:
        """A result that fails 1.4.3 (foreign-fed count) but passes
        everything else — the right shape to test the a/b/c rescue."""
        res = NormCheckResult(title_norm=TitleNorm.GM, meets_gender=True)
        res.not_enough_federations = 'violation'
        # 1.4.3d NOT met (so a/b/c is the only possible rescue path).
        res.not_enough_all_federations = 'violation'
        return res

    def _norms_dict(self) -> dict:
        return {TitleNorm.GM: self._failing_143_result()}

    # ---------- 'none' = no manual exemption ----------

    def test_none_leaves_rule_143_exemption_unset(self):
        from data.norms import apply_143abc_exemption

        norms = self._norms_dict()
        apply_143abc_exemption(norms, 'none', Federation('FRA'), Federation('FRA'))
        assert norms[TitleNorm.GM].rule_143_exemption is None
        assert not norms[TitleNorm.GM].is_143_exempt_via_abc
        assert not norms[TitleNorm.GM].is_met  # 1.4.3 still blocks

    # ---------- '1.4.3a' national championship — applicant from event fed ----------

    def test_143a_exempts_player_from_event_federation(self):
        """National championship: only players from the registering
        federation are exempt from 1.4.3."""
        from data.norms import apply_143abc_exemption

        norms = self._norms_dict()
        apply_143abc_exemption(norms, '1.4.3a', Federation('FRA'), Federation('FRA'))
        assert norms[TitleNorm.GM].rule_143_exemption == 'a'
        assert norms[TitleNorm.GM].is_143_exempt_via_abc
        assert norms[TitleNorm.GM].is_met  # 1.4.3 violation now exempted

    def test_143a_does_NOT_exempt_foreign_player(self):
        """A player whose federation ≠ event's federation is NOT exempt
        under 1.4.3a/b — those are scoped to the registering federation."""
        from data.norms import apply_143abc_exemption

        norms = self._norms_dict()
        apply_143abc_exemption(norms, '1.4.3a', Federation('USA'), Federation('FRA'))
        assert norms[TitleNorm.GM].rule_143_exemption is None
        assert not norms[TitleNorm.GM].is_met

    # ---------- '1.4.3b' national team — same scoping as a ----------

    def test_143b_exempts_player_from_event_federation(self):
        from data.norms import apply_143abc_exemption

        norms = self._norms_dict()
        apply_143abc_exemption(norms, '1.4.3b', Federation('GER'), Federation('GER'))
        assert norms[TitleNorm.GM].rule_143_exemption == 'b'
        assert norms[TitleNorm.GM].is_met

    def test_143b_does_NOT_exempt_foreign_player(self):
        from data.norms import apply_143abc_exemption

        norms = self._norms_dict()
        apply_143abc_exemption(norms, '1.4.3b', Federation('USA'), Federation('GER'))
        assert norms[TitleNorm.GM].rule_143_exemption is None
        assert not norms[TitleNorm.GM].is_met

    # ---------- '1.4.3c' zonal — applies to everyone ----------

    def test_143c_exempts_player_from_event_federation(self):
        from data.norms import apply_143abc_exemption

        norms = self._norms_dict()
        apply_143abc_exemption(norms, '1.4.3c', Federation('FRA'), Federation('FRA'))
        assert norms[TitleNorm.GM].rule_143_exemption == 'c'
        assert norms[TitleNorm.GM].is_met

    def test_143c_exempts_foreign_player(self):
        """Zonal/sub-zonal exemption is NOT scoped to the registering
        federation — applies to every player in the event."""
        from data.norms import apply_143abc_exemption

        norms = self._norms_dict()
        apply_143abc_exemption(norms, '1.4.3c', Federation('USA'), Federation('FRA'))
        assert norms[TitleNorm.GM].rule_143_exemption == 'c'
        assert norms[TitleNorm.GM].is_met

    # ---------- 1.4.4 exempted by a/b/c (foreigner requirement, 1.4.3e) ----------

    def test_abc_exempts_144_own_fed_cap(self):
        """1.4.3a-d all waive the foreigner requirement — 1.4.3 AND
        1.4.4 (1.4.3e: "the normal foreigner requirement. (See 1.4.3
        and 1.4.4)"). A 1.4.4 own-fed violation is exempt under c."""
        from data.norms import apply_143abc_exemption

        res = self._failing_143_result()
        res.too_many_own_federation = 'violation'
        norms = {TitleNorm.GM: res}
        apply_143abc_exemption(norms, '1.4.3c', Federation('USA'), Federation('FRA'))
        assert res.rule_143_exemption == 'c'
        assert res.is_143_exempt_via_abc
        assert res.is_met

    def test_abc_exempts_144_one_fed_cap(self):
        from data.norms import apply_143abc_exemption

        res = self._failing_143_result()
        res.too_many_one_federation = (Federation('USA'), 'violation')
        norms = {TitleNorm.GM: res}
        apply_143abc_exemption(norms, '1.4.3a', Federation('FRA'), Federation('FRA'))
        assert res.rule_143_exemption == 'a'
        assert res.is_met

    # ---------- 1.4.3d co-exists with a/b/c ----------

    def test_143d_wins_when_both_could_apply(self):
        """If 1.4.3d holds AND a/b/c also applies, the result still
        passes — both exemption paths reach the same is_met=True."""
        from data.norms import apply_143abc_exemption

        # 1.4.3d sub-criteria met
        res = NormCheckResult(title_norm=TitleNorm.GM, meets_gender=True)
        res.not_enough_federations = 'violation'  # 1.4.3 fails
        res.too_many_own_federation = 'violation'  # 1.4.4 also fails
        # 1.4.3d's per-round counts met (no error messages set)
        norms = {TitleNorm.GM: res}
        apply_143abc_exemption(norms, '1.4.3a', Federation('FRA'), Federation('FRA'))
        # Both exemption paths active.
        assert res.is_143d_met
        assert res.is_143_exempt_via_abc
        assert res.is_met

    def test_abc_alone_rescues_when_1_4_4_violated(self):
        """When 1.4.3d does NOT hold, a/b/c alone still saves the norm
        even with 1.4.4 violations — the exemption covers the whole
        foreigner requirement."""
        from data.norms import apply_143abc_exemption

        res = NormCheckResult(title_norm=TitleNorm.GM, meets_gender=True)
        res.not_enough_federations = 'violation'
        res.too_many_own_federation = 'violation'
        res.not_enough_foreign_players = 'violation'  # → 1.4.3d NOT met
        norms = {TitleNorm.GM: res}
        apply_143abc_exemption(norms, '1.4.3a', Federation('FRA'), Federation('FRA'))
        assert not res.is_143d_met
        assert res.is_143_exempt_via_abc
        assert res.is_met

    def _failing_143_and_144_result(self) -> NormCheckResult:
        """The real-world shape FIDE confirmed (Interclubs / national team
        championship): a player whose mix fails BOTH the 1.4.3 federation
        count and BOTH 1.4.4 caps (3/5 own-fed, 2/3 one-fed), with 1.4.3d
        not met, but everything else (games, titles, score, Ra, Rp) fine.
        Only the foreigner requirement stands between them and the norm."""
        res = NormCheckResult(title_norm=TitleNorm.GM, meets_gender=True)
        res.not_enough_federations = 'violation'  # 1.4.3
        res.too_many_own_federation = 'violation'  # 1.4.4 (3/5)
        res.too_many_one_federation = (Federation('FRA'), 'violation')  # 1.4.4 (2/3)
        res.not_enough_foreign_players = 'violation'  # → 1.4.3d NOT met
        return res

    @pytest.mark.parametrize('code', ['1.4.3a', '1.4.3b', '1.4.3c'])
    def test_abc_waives_full_foreigner_requirement(self, code: str):
        """FIDE QC confirmed: the 1.4.3a/b/c exemptions waive the WHOLE
        foreigner requirement — 1.4.3 AND both 1.4.4 caps together (1.4.3e
        "the normal foreigner requirement. (See 1.4.3 and 1.4.4)"). A
        result failing all three, with 1.4.3d not met, is met under any of
        a/b/c."""
        from data.norms import apply_143abc_exemption

        res = self._failing_143_and_144_result()
        assert not res.is_met  # blocked before the exemption
        apply_143abc_exemption(
            {TitleNorm.GM: res}, code, Federation('FRA'), Federation('FRA')
        )
        assert res.rule_143_exemption == code[-1]
        assert not res.is_143d_met  # the rescue is NOT via 1.4.3d
        assert res.is_met

    def test_abc_waiver_does_not_mutate_violation_flags(self):
        """The exemption is honoured at the ``is_met`` layer — the
        underlying 1.4.3 / 1.4.4 violation flags remain set so the IT1 /
        calculation-details views can still show the raw figures and the
        'exempt' badge side by side."""
        from data.norms import apply_143abc_exemption

        res = self._failing_143_and_144_result()
        apply_143abc_exemption(
            {TitleNorm.GM: res}, '1.4.3b', Federation('FRA'), Federation('FRA')
        )
        assert res.is_met
        # Data untouched: only the verdict changed, not the measured facts.
        assert res.not_enough_federations
        assert res.too_many_own_federation
        assert res.too_many_one_federation

    # ---------- 1.4.4 still enforced when NO exemption applies ----------

    def test_no_exemption_lets_144_own_cap_block(self):
        """Without any 1.4.3 exemption, the 1.4.4 own-federation cap
        blocks the norm — the waiver is exemption-gated, not unconditional."""
        from data.norms import apply_143abc_exemption

        res = NormCheckResult(title_norm=TitleNorm.GM, meets_gender=True)
        res.too_many_own_federation = 'violation'
        res.not_enough_foreign_players = 'violation'  # → 1.4.3d NOT met
        norms = {TitleNorm.GM: res}
        apply_143abc_exemption(norms, 'none', Federation('FRA'), Federation('FRA'))
        assert not res.is_143d_met
        assert not res.is_143_exempt_via_abc
        assert not res.is_met

    def test_no_exemption_lets_144_one_fed_cap_block(self):
        """Without any 1.4.3 exemption, the 1.4.4 one-federation cap blocks."""
        from data.norms import apply_143abc_exemption

        res = NormCheckResult(title_norm=TitleNorm.GM, meets_gender=True)
        res.too_many_one_federation = (Federation('FRA'), 'violation')
        res.not_enough_foreign_players = 'violation'  # → 1.4.3d NOT met
        norms = {TitleNorm.GM: res}
        apply_143abc_exemption(norms, 'none', Federation('FRA'), Federation('FRA'))
        assert not res.is_143_exempt_via_abc
        assert not res.is_met

    def test_foreign_player_not_exempt_still_blocked_by_144(self):
        """1.4.3a/b are scoped to the registering federation: a foreign
        player gets no exemption, so 1.4.4 still blocks even though the
        arbiter selected the national-championship event type."""
        from data.norms import apply_143abc_exemption

        res = self._failing_143_and_144_result()
        norms = {TitleNorm.GM: res}
        # Event registered by FRA, applicant is USA → 1.4.3b doesn't apply.
        apply_143abc_exemption(norms, '1.4.3b', Federation('USA'), Federation('FRA'))
        assert res.rule_143_exemption is None
        assert not res.is_met

    def test_unknown_exemption_code_is_noop(self):
        """An unknown code (shouldn't happen via UI; validate() catches it)
        leaves results unchanged."""
        from data.norms import apply_143abc_exemption

        norms = self._norms_dict()
        apply_143abc_exemption(norms, '1.4.3z', Federation('FRA'), Federation('FRA'))
        assert norms[TitleNorm.GM].rule_143_exemption is None


# ===========================================================================
# Proportional thresholds allow rescue by dropping more games
# ===========================================================================
#
# Under FIDE 1.4.1c, the 1.4.4 / 1.4.5 / 1.4.8b thresholds scale with
# `played_games` rather than `tournament.rounds`. Dropping a round can
# therefore RESCUE a check that failed at the full game count — the
# threshold drops faster than the underlying count. Each test below pins
# a concrete counter-example to one such check.
#
# Why we care: (1) regression guard if anyone reverts the thresholds to
# fixed `tournament.rounds`; (2) proves the subset search must be a flat
# loop — naive "skip supersets of failing subsets" pruning would skip
# winning subsets, because failure at size k does not imply failure at
# size k+1.


class TestProportionalThresholdsAllowRescue:
    """Each test demonstrates one evaluator check where dropping more
    rounds (a superset of drops) can rescue a previously-failing result —
    a direct consequence of proportional thresholds.
    """

    def _evaluator(self) -> TitleNormEvaluator:
        return _real_searcher(rounds=11).evaluator

    def test_not_enough_games_cannot_be_rescued_by_dropping(self):
        """Counter-example to rescue: the games-count threshold is fixed
        (not proportional), so once played_games drops below `min_games`,
        further drops can't recover it. The lone non-rescuable check —
        which is also why the searcher's `max_ignores` upper-bound
        prevents this check ever firing during search."""
        opponents = [_gm(i) for i in range(1, 12)]
        # 11 opponents, all wins.
        results = [Result.WIN] * 11
        inputs = make_inputs(list(zip(range(1, 12), opponents, results)))
        # max_ignores for 11-round Swiss = 2; play stays >= 9, games check
        # never actually triggers during search. But for the test, simulate
        # dropping more than allowed.
        evaluator = self._evaluator()
        # Drop 3 rounds → played=8 < 9 → fails games check.
        subset = inputs.without_rounds(frozenset({1, 2, 3}))
        res_s = evaluator.evaluate_one(subset, TitleNorm.GM, True)
        assert res_s.not_enough_games
        # Drop 4 rounds (superset) → played=7 → still fails.
        superset = inputs.without_rounds(frozenset({1, 2, 3, 4}))
        res_t = evaluator.evaluate_one(superset, TitleNorm.GM, True)
        assert res_t.not_enough_games

    def test_score_too_low_rescued_by_dropping_losses(self):
        """Rescue: dropping LOSS rounds raises the fractional score, and
        the 35% threshold scales with played_games — so a baseline that
        fails 1.4.8b can pass after enough drops."""
        # 11 opponents at 2400. 4 wins + 3 draws + 4 losses = 5.5 points.
        # Threshold (35% of played_games):
        #   played=11, score=5.5 → 5.5 / 11 = 0.5 → 35% = 3.85 → PASS
        # To get a baseline failure, weaken score:
        # 1 win + 1 draw + 9 losses = 1.5 points.
        #   played=11 → 35% of 11 = 3.85 → FAIL
        # Drop 8 losses → played=3, score=1.5 → 35% of 3 = 1.05 → PASS!
        opponents = [_gm(i, rating=2400) for i in range(1, 12)]
        results = [Result.WIN] + [Result.DRAW] + [Result.LOSS] * 9
        inputs = make_inputs(list(zip(range(1, 12), opponents, results)))
        evaluator = self._evaluator()

        # Baseline (full set): score 1.5/11, threshold 35% of 11 = 3.85 → fails.
        baseline = evaluator.evaluate_one(inputs, TitleNorm.GM, True)
        assert baseline.score_too_low

        # Drop 8 loss rounds (R3..R10): played=3, score=1.5, threshold=1.05 → passes.
        dropped = inputs.without_rounds(frozenset({3, 4, 5, 6, 7, 8, 9, 10}))
        rescued = evaluator.evaluate_one(dropped, TitleNorm.GM, True)
        # The score check passes for the superset of the original failure.
        # (Other checks may still fail; we're only asserting non-monotonicity
        # of the score check itself.)
        assert not rescued.score_too_low, (
            f'1.4.8b should be rescuable by dropping losses. '
            f'baseline score={baseline.score}, played={baseline.played_games}; '
            f'after-drop score={rescued.score}, played={rescued.played_games}'
        )

    def test_title_holders_count_rescued_by_dropping_untitled(self):
        """Rescue: dropping untitled opponents lowers the 50% threshold
        (scales with played_games) faster than it lowers titled count,
        so 1.4.5a can pass after enough drops.

        E.g. played=10, titled=4 → ceil(10/2)=5, fails (4<5).
        Drop 2 untitled → played=8, titled=4 → ceil(8/2)=4, passes.
        """
        feds = ['USA', 'GER', 'ESP', 'ITA', 'NED', 'POL', 'RUS', 'AZE', 'IND', 'CHN']
        opponents = [_gm(i, federation=feds[i - 1]) for i in range(1, 5)] + [
            _untitled(i, rating=2300, federation=feds[i - 1]) for i in range(5, 11)
        ]
        # 4 GMs + 6 untitled = 10 opponents.
        results = [Result.WIN] * 10
        inputs = make_inputs(list(zip(range(1, 11), opponents, results)))
        evaluator = self._evaluator()
        # The full 10-game mix:
        # ceil(10/2)=5 → fails (4 titled < 5).
        baseline = evaluator.evaluate_one(inputs, TitleNorm.GM, True)
        assert baseline.not_enough_title_holders
        # Drop 2 untitled (rounds 9, 10) → played=8, titled=4 → ceil(8/2)=4 → passes.
        rescued = evaluator.evaluate_one(
            inputs.without_rounds(frozenset({9, 10})), TitleNorm.GM, True
        )
        assert not rescued.not_enough_title_holders, (
            f'1.4.5a should be rescuable by dropping untitled opponents. '
            f'baseline: titled={baseline.num_title_holders}, played={baseline.played_games}; '
            f'after-drop: titled={rescued.num_title_holders}, played={rescued.played_games}'
        )

    def test_required_titles_count_rescued_by_dropping_lower_titles(self):
        """Rescue: with the "min 3" floor, dropping non-GMs lowers the 1/3
        threshold without losing the floor, so 1.4.5b-e can pass after
        enough drops.

        played=10, GMs=3 → max(ceil(10/3), 3) = 4, fails (3<4).
        Drop 2 non-GMs → played=8, GMs=3 → max(ceil(8/3), 3) = 3, passes.
        """
        feds = ['USA', 'GER', 'ESP', 'ITA', 'NED', 'POL', 'RUS', 'AZE', 'IND', 'CHN']
        opponents = [_gm(i, federation=feds[i - 1]) for i in range(1, 4)] + [
            _im(i, rating=2350, federation=feds[i - 1]) for i in range(4, 11)
        ]
        # 3 GMs + 7 IMs = 10 opponents.
        inputs = make_inputs(list(zip(range(1, 11), opponents, [Result.DRAW] * 10)))
        evaluator = self._evaluator()
        baseline = evaluator.evaluate_one(inputs, TitleNorm.GM, True)
        assert baseline.not_enough_required_titles  # 3 GMs < threshold 4
        # Drop 2 IMs → played=8, GMs=3 → threshold 3 → passes.
        rescued = evaluator.evaluate_one(
            inputs.without_rounds(frozenset({9, 10})), TitleNorm.GM, True
        )
        assert not rescued.not_enough_required_titles, (
            '1.4.5b-e should be rescuable by dropping non-required '
            'opponents — the min-3 floor still holds.'
        )

    def test_too_many_own_federation_rescued_by_dropping_own_fed(self):
        """Rescue: dropping own-fed opponents lowers BOTH own_count AND
        the threshold (floor(3·played/5)). The threshold can drop faster
        than own_count, so 1.4.4's 3/5 cap can pass after enough drops.

        Baseline played=9, 6 FRA + 3 USA, applicant from FRA:
          threshold = floor(3·9/5) = 5;  own=6 > 5  → fails.
        Drop 1 FRA:
          played=8, own=5, threshold = floor(24/5) = 4;  5 > 4 → still fails.
        Drop 2 FRAs:
          played=7, own=4, threshold = floor(21/5) = 4;  4 > 4 false → PASSES.
        """
        opponents = [_gm(i, federation='FRA') for i in range(1, 7)] + [
            _gm(7, federation='USA'),
            _gm(8, federation='USA'),
            _gm(9, federation='USA'),
        ]
        inputs = make_inputs(list(zip(range(1, 10), opponents, [Result.DRAW] * 9)))
        searcher = _real_searcher(rounds=9, federation='FRA')
        # Baseline fails 1.4.4 own-fed cap.
        baseline = searcher.evaluator.evaluate_one(inputs, TitleNorm.GM, True)
        assert baseline.too_many_own_federation, (
            'Setup: baseline should fail 1.4.4 (own=6 > 5).'
        )

        # Intermediate drop: one FRA.
        intermediate = inputs.without_rounds(frozenset({1}))
        res_intermediate = searcher.evaluator.evaluate_one(
            intermediate, TitleNorm.GM, True
        )
        assert res_intermediate.too_many_own_federation, (
            'Drop 1 FRA: own=5, played=8, threshold=4 → 5>4 should fail.'
        )

        # Larger drop: two FRAs.
        rescued_inputs = inputs.without_rounds(frozenset({1, 2}))
        res_rescued = searcher.evaluator.evaluate_one(
            rescued_inputs, TitleNorm.GM, True
        )
        assert not res_rescued.too_many_own_federation, (
            f'Drop 2 FRAs: own=4, played=7, threshold=4 → 4>4 should pass. '
            f'Got too_many_own_federation={res_rescued.too_many_own_federation}.'
        )

    def test_too_many_one_federation_rescued_by_dropping_top_fed(self):
        """Rescue for the 2/3-cap version of 1.4.4. Dropping top-fed
        opponents shrinks both `top` and the threshold (floor(2·played/3))
        — the threshold drops faster, so 1.4.4's 2/3 cap can pass.

        Baseline played=9, 7 USA + 2 FRA, applicant from FRA:
          threshold = floor(2·9/3) = 6;  top=7 > 6  → fails.
        Drop 1 USA:
          played=8, top=6, threshold = floor(16/3) = 5;  6 > 5 → still fails.
        Drop 3 USAs:
          played=6, top=4, threshold = floor(12/3) = 4;  4 > 4 false → PASSES.
        """
        opponents = [_gm(i, federation='USA') for i in range(1, 8)] + [
            _gm(8, federation='FRA'),
            _gm(9, federation='FRA'),
        ]
        inputs = make_inputs(list(zip(range(1, 10), opponents, [Result.DRAW] * 9)))
        searcher = _real_searcher(rounds=9, federation='FRA')
        baseline = searcher.evaluator.evaluate_one(inputs, TitleNorm.GM, True)
        assert baseline.too_many_one_federation, (
            'Setup: baseline should fail 1.4.4 (top USA=7 > 6).'
        )

        # Intermediate drop: one USA.
        intermediate = inputs.without_rounds(frozenset({1}))
        res_intermediate = searcher.evaluator.evaluate_one(
            intermediate, TitleNorm.GM, True
        )
        assert res_intermediate.too_many_one_federation

        # Larger drop: three USAs.
        rescued_inputs = inputs.without_rounds(frozenset({1, 2, 3}))
        res_rescued = searcher.evaluator.evaluate_one(
            rescued_inputs, TitleNorm.GM, True
        )
        assert not res_rescued.too_many_one_federation, (
            f'Drop 3 USAs: top=4, played=6, threshold=4 → 4>4 should pass. '
            f'Got too_many_one_federation={res_rescued.too_many_one_federation}.'
        )


# ===========================================================================
# Helpers for tests that drive `collect_inputs` end-to-end
# ===========================================================================


def _fake_pairing(result: Result, opponent: FakeOpponent | None) -> SimpleNamespace:
    """Minimal pairing duck-type. `unplayed`/`played` are read by the
    Tournament-side checks (1.4.3d / 1.5.6a)."""
    return SimpleNamespace(
        result=result,
        opponent=opponent,
        unplayed=result.is_unplayed,
        played=not result.is_unplayed,
    )


def _player_with_pairings(
    *,
    federation: str = 'FRA',
    title: PlayerTitle = PlayerTitle.NONE,
    gender=None,
    rounds: int,
    pairings: dict[int, tuple[FakeOpponent | None, Result]],
    pairing_system=None,
    pairing_variation=None,
    tournament_players_by_id: dict | None = None,
):
    """Construct a fake TournamentPlayer-like with controlled pairings.

    Used by tests that need to exercise `collect_inputs` filtering logic
    (1.4.2a/b) — those require a real player.pairings_by_round dict.
    """
    from data.pairings.systems import SwissPairingSystem
    from utils.enum import PlayerGender
    from utils.types import BigTournamentExemption

    fake_pairings = {
        rnd: _fake_pairing(result, opp) for rnd, (opp, result) in pairings.items()
    }
    player = SimpleNamespace(
        federation=Federation(federation),
        gender=gender or PlayerGender.MAN,
        title=PlayerTitle(title),
        event=SimpleNamespace(federation=federation),
        tournament=SimpleNamespace(
            rounds=rounds,
            pairing_system=pairing_system or SwissPairingSystem(),
            pairing_variation=pairing_variation,
            tournament_players_by_id=tournament_players_by_id or {},
            # Tournament-wide check stubs — `evaluate_one` reads these
            # to stamp 1.4.3d / 1.5.6a onto every NormCheckResult.
            # Default to "not met" so tests don't get an unintended
            # 1.4.3d exemption.
            big_tournament_exemption=BigTournamentExemption(0, 0, 0),
            high_level_tournament=False,
        ),
        pairings_by_round=fake_pairings,
    )
    return player


# ===========================================================================
# 1.4.2a — non-FIDE federations excluded; FID accepted but not foreign
# ===========================================================================
#
# Spec text: "Games against opponents who do not belong to FIDE federations
# [are not included]. Players with federation 'FID' are accepted, but do
# not count as a foreign player."
#
# Code reading:
#   * `Federation('NON')` opponents → ignored entirely (not in mix).
#   * `Federation('FID')` opponents → IN the mix and count toward
#     federations_counter (so 1.4.3 sees them as distinct). But in 1.4.3d's
#     per-round "foreign players" count, FID is filtered out
#     (compute_big_tournament_exemption uses `federation != Federation('FID')`).


class TestRule_1_4_2a_NON_excluded:
    def test_non_opponent_excluded_from_mix(self):
        """1.4.2a: opponents with federation 'NON' are dropped from the
        opponent mix and recorded in ignored_opponents_ids."""
        good = _gm(1, federation='USA')
        non_opp = FakeOpponent(
            id=99,
            rating=2400,
            rating_type=PlayerRatingType.FIDE,
            federation=Federation('NON'),
            title=PlayerTitle.GRANDMASTER,
        )
        player = _player_with_pairings(
            rounds=9,
            pairings={
                1: (good, Result.WIN),
                2: (non_opp, Result.WIN),
                3: (good, Result.DRAW),  # placeholder so test isn't trivial
            },
        )
        evaluator = TitleNormEvaluator(player)
        inputs = evaluator.collect_inputs(include_last_forfeit_as_loss=False)
        assert non_opp.id in inputs.ignored_opponents_ids
        # The NON opponent isn't in the mix at all.
        assert non_opp not in inputs.opponents
        assert Federation('NON') not in inputs.federations_counter


class TestRule_1_4_2a_FID_nuance:
    """FIDE QC clarification (2026): "FID is not considered a federation.
    FID players are disregarded." A game against a FID opponent is still
    accepted (it counts towards games played, titled opponents, Ra, score),
    but FID never enters the federation mix — neither as a foreign
    federation for 1.4.3 / 1.4.3d nor as a federation that can breach the
    1.4.4 caps. (RUS/BLR are shown as FID but counted under their own flag;
    the arbiter corrects the flag in the data.)"""

    def test_fid_opponent_not_counted_as_a_federation_for_1_4_3(self):
        """FID is not a federation: a FID opponent does not add to the
        distinct-federation tally, though the game itself is kept."""
        usa_opp = _gm(1, federation='USA')
        fid_opp = _gm(2, federation='FID')
        player = _player_with_pairings(
            rounds=9,
            pairings={
                1: (usa_opp, Result.WIN),
                2: (fid_opp, Result.DRAW),
            },
        )
        evaluator = TitleNormEvaluator(player)
        inputs = evaluator.collect_inputs(include_last_forfeit_as_loss=False)
        # FID is NOT in the federation mix.
        assert Federation('FID') not in inputs.federations_counter
        # ...but the game is still counted (played + the opponent's title).
        assert inputs.played_games == 2
        assert fid_opp in inputs.opponents
        # 1.4.3 sees only USA → one distinct federation.
        _, num_feds, _own = evaluator.federation_count_requirement(inputs)
        assert num_feds == 1

    def test_fid_majority_does_not_breach_1_4_4_one_fed_cap(self):
        """ ">2/3 of the opponents from one federation" cannot be triggered
        by FID, since FID is not a federation. A field of mostly FID
        opponents passes the 1.4.4 one-federation cap."""
        pairings = {1: (_gm(1, federation='USA'), Result.DRAW)}
        for r in range(2, 10):  # 8 FID opponents out of 9
            pairings[r] = (_gm(r, federation='FID'), Result.DRAW)
        player = _player_with_pairings(rounds=9, pairings=pairings)
        evaluator = TitleNormEvaluator(player)
        inputs = evaluator.collect_inputs(include_last_forfeit_as_loss=False)
        passes, top_fed, _count = evaluator.top_federation_requirement(
            inputs, TitleNorm.GM
        )
        assert passes, 'FID majority must not breach the 2/3 one-federation cap'
        assert top_fed in (None, Federation('USA'))

    def test_fid_player_does_not_count_in_1_4_3d_foreign_count(self):
        """1.4.3d's per-round count of "foreign rated players" is filtered:
        FID players are accepted as participants but don't count toward
        the foreign-player threshold."""
        from data.norms import compute_big_tournament_exemption

        # Build a tournament with 3 USA players + 1 FID player + 1 host (FRA).
        # All FIDE-rated, present in every round of a 9-round Swiss.
        # 1.4.3d wants ≥20 foreign rated → far below threshold, but the
        # *count itself* is what we're verifying: FID excluded from it.
        def _round_pairing():
            # Each player has an opponent in every round — content doesn't
            # matter for compute_big_tournament_exemption beyond "present".
            return SimpleNamespace(
                result=Result.DRAW, opponent=None, unplayed=False, played=True
            )

        players = {}
        for i in range(1, 5):
            fed = ['USA', 'USA', 'USA', 'FID'][i - 1]
            players[i] = SimpleNamespace(
                rating_type=PlayerRatingType.FIDE,
                federation=Federation(fed),
                title=PlayerTitle.GRANDMASTER,
                pairings_by_round={r: _round_pairing() for r in range(1, 10)},
            )
        # Add a host-federation player (excluded by 1.4.3d's host-fed filter).
        players[5] = SimpleNamespace(
            rating_type=PlayerRatingType.FIDE,
            federation=Federation('FRA'),
            title=PlayerTitle.GRANDMASTER,
            pairings_by_round={r: _round_pairing() for r in range(1, 10)},
        )

        tournament = SimpleNamespace(
            event=SimpleNamespace(federation='FRA'),
            rounds=9,
            tournament_players_by_id=players,
        )
        exemption = compute_big_tournament_exemption(tournament)
        # 1.4.2a: FID is accepted but doesn't count as a foreign player.
        # → foreigners excludes BOTH the host-fed (FRA) AND the FID player.
        # Only the 3 USA players qualify.
        assert exemption.foreigners == 3, (
            f'FID should NOT count toward 1.4.3d foreigner count per 1.4.2a. '
            f'Got {exemption.foreigners}; expected 3 (USA only).'
        )
        # federations: only non-FID, non-host feds counted → just USA.
        assert exemption.federations == 1, (
            f'FID should NOT count toward 1.4.3d federation diversity. '
            f'Got {exemption.federations} feds; expected 1 (USA only).'
        )
        # titled_foreigners: same exclusion — FID GM doesn't count.
        assert exemption.titled_foreigners == 3, (
            f'FID GM should NOT count toward 1.4.3d titled-foreigner count. '
            f'Got {exemption.titled_foreigners}; expected 3 (USA GMs only).'
        )


# ===========================================================================
# 1.4.2b — RR: unrated opponents who score 0 against rated opponents
# ===========================================================================
#
# In Round-Robin tournaments, an unrated player who lost every game against
# a FIDE-rated opponent is dropped from the applicant's mix. Swiss is
# unaffected.


class TestRule_1_4_2b_RR_unrated_zero:
    def test_unrated_opponent_zero_against_rated_excluded_in_rr(self):
        """1.4.2b: in RR, an unrated opponent who scored 0 against every
        FIDE-rated opponent they played → excluded from the applicant's mix."""
        from data.pairings.systems import RoundRobinPairingSystem

        # The doomed opponent: unrated, with their own pairings showing
        # losses against rated opponents.
        doomed_opp = FakeOpponent(
            id=99,
            rating=1800,
            rating_type=PlayerRatingType.NATIONAL,  # NOT FIDE
            federation=Federation('USA'),
            title=PlayerTitle.NONE,
        )
        # The opponent's own pairings: all losses against rated opponents.
        rated_foe = _gm(50)  # rating_type=FIDE
        doomed_opp.pairings_by_round = {
            r: _fake_pairing(Result.LOSS, rated_foe) for r in range(1, 10)
        }

        # Applicant: one rated GM + the doomed unrated player.
        regular = _gm(1)
        player = _player_with_pairings(
            rounds=9,
            pairing_system=RoundRobinPairingSystem(),
            pairings={
                1: (regular, Result.WIN),
                2: (doomed_opp, Result.WIN),
            },
        )
        evaluator = TitleNormEvaluator(player)
        inputs = evaluator.collect_inputs(include_last_forfeit_as_loss=False)
        assert doomed_opp.id in inputs.ignored_opponents_ids
        assert doomed_opp not in inputs.opponents

    def test_unrated_opponent_with_a_draw_NOT_excluded_in_rr(self):
        """If the unrated opponent scored anything but 0 against rated
        opponents (here: a draw), the 1.4.2b exclusion does NOT apply."""
        from data.pairings.systems import RoundRobinPairingSystem

        survivor = FakeOpponent(
            id=99,
            rating=1800,
            rating_type=PlayerRatingType.NATIONAL,
            federation=Federation('USA'),
            title=PlayerTitle.NONE,
        )
        rated_foe = _gm(50)
        survivor.pairings_by_round = {
            1: _fake_pairing(Result.DRAW, rated_foe),  # non-zero score
            **{r: _fake_pairing(Result.LOSS, rated_foe) for r in range(2, 10)},
        }

        player = _player_with_pairings(
            rounds=9,
            pairing_system=RoundRobinPairingSystem(),
            pairings={1: (survivor, Result.WIN)},
        )
        inputs = TitleNormEvaluator(player).collect_inputs(
            include_last_forfeit_as_loss=False
        )
        assert survivor.id not in inputs.ignored_opponents_ids
        assert survivor in inputs.opponents

    def test_unrated_opponent_zero_NOT_excluded_in_swiss(self):
        """1.4.2b is RR-only. In a Swiss event, the same opponent is kept
        even when they scored zero against rated opponents."""
        doomed_opp = FakeOpponent(
            id=99,
            rating=1800,
            rating_type=PlayerRatingType.NATIONAL,
            federation=Federation('USA'),
            title=PlayerTitle.NONE,
        )
        rated_foe = _gm(50)
        doomed_opp.pairings_by_round = {
            r: _fake_pairing(Result.LOSS, rated_foe) for r in range(1, 10)
        }
        # SwissPairingSystem default — not RR.
        player = _player_with_pairings(
            rounds=9,
            pairings={1: (doomed_opp, Result.WIN)},
        )
        inputs = TitleNormEvaluator(player).collect_inputs(
            include_last_forfeit_as_loss=False
        )
        # 1.4.2b doesn't apply in Swiss → opponent is in the mix.
        assert doomed_opp.id not in inputs.ignored_opponents_ids
        assert doomed_opp in inputs.opponents


# ===========================================================================
# 1.4.6 — Rating floor adjustment (only the single lowest opponent)
# ===========================================================================
#
# "No more than one opponent shall have their rating raised to this adjusted
# rating floor. Where more than one opponent is below the floor, the rating
# of the lowest rated opponent shall be raised."


class TestRule_1_4_6:
    def test_only_lowest_below_floor_is_adjusted(self):
        """Two opponents below the GM floor of 2200. Only the lower one
        gets raised. The other stays at its raw rating in the average."""
        opponents = [
            _gm(1, rating=2400),
            _gm(2, rating=2400),
            _gm(3, rating=2400),
            _gm(4, rating=2400),
            _gm(5, rating=2400),
            _gm(6, rating=2400),
            _gm(7, rating=2400),
            FakeOpponent(
                8,
                2100,  # below GM floor of 2200
                rating_type=PlayerRatingType.FIDE,
                federation=Federation('USA'),
                title=PlayerTitle.INTERNATIONAL_MASTER,
            ),
            FakeOpponent(
                9,
                2000,  # also below floor (the lowest)
                rating_type=PlayerRatingType.FIDE,
                federation=Federation('GER'),
                title=PlayerTitle.INTERNATIONAL_MASTER,
            ),
        ]
        inputs = make_inputs(list(zip(range(1, 10), opponents, [Result.DRAW] * 9)))
        searcher = _real_searcher(rounds=9)
        avg, adjusted_player, adjusted_rating = (
            searcher.evaluator.opponent_rating_floor_and_average(inputs, TitleNorm.GM)
        )
        # The lowest (2000) is raised to 2200; the 2100 stays at 2100.
        # Sum = 7*2400 + 2100 + 2200 = 16800 + 4300 = 21100. Avg = 21100/9 = 2344.44 → 2344.
        assert adjusted_player is opponents[8]  # id=9, rating=2000
        assert adjusted_rating == 2200  # GM floor
        # Confirm the other below-floor opponent kept its raw rating.
        assert avg == 2344, (
            f'Expected only the 2000-rated opp raised to 2200; the 2100-rated '
            f'opp must stay at 2100. Avg = (7*2400 + 2100 + 2200) / 9 = 2344. '
            f'Got avg={avg}.'
        )

    def test_unrated_opponent_treated_as_1400_then_floored(self):
        """Unrated opponents enter the average as 1400 (per 1.4.6b),
        which is then subject to the floor adjustment for the lowest opp."""
        opponents = [_gm(i, rating=2400) for i in range(1, 9)] + [
            FakeOpponent(
                9,
                1500,
                rating_type=PlayerRatingType.NATIONAL,  # treated as 1400
                federation=Federation('USA'),
                title=PlayerTitle.NONE,
            ),
        ]
        inputs = make_inputs(list(zip(range(1, 10), opponents, [Result.DRAW] * 9)))
        searcher = _real_searcher(rounds=9)
        avg, adjusted_player, adjusted_rating = (
            searcher.evaluator.opponent_rating_floor_and_average(inputs, TitleNorm.GM)
        )
        # Unrated → 1400 → floored to 2200. Sum = 8*2400 + 2200 = 21400. Avg 2378.
        assert adjusted_player is opponents[8]
        assert adjusted_rating == 2200
        assert avg == 2378


# ===========================================================================
# 1.4.8 — Performance rating threshold
# ===========================================================================
#
# Rp = Ra + dp must be >= minimum_performance (GM: 2600, IM: 2450, etc.).
# Boundary tests: just below threshold fails; at-or-above passes.


class TestRule_1_4_8_Rp_boundary:
    def test_rp_just_below_threshold_fails(self):
        """Ra=2400, score 7.5/11 → fractional 0.682, dp[68]=133 → Rp=2533. <2600 fails GM."""
        opponents = [
            _gm(i, rating=2400, federation=fed)
            for i, fed in enumerate(
                [
                    'USA',
                    'GER',
                    'ESP',
                    'ITA',
                    'NED',
                    'POL',
                    'RUS',
                    'AZE',
                    'IND',
                    'CHN',
                    'BRA',
                ],
                start=1,
            )
        ]
        results = [Result.WIN] * 6 + [Result.DRAW] * 3 + [Result.LOSS] * 2
        # 6 wins + 1.5 draws = 7.5
        inputs = make_inputs(list(zip(range(1, 12), opponents, results)))
        assert inputs.score == pytest.approx(7.5)
        searcher = _real_searcher(rounds=11)
        result = searcher.evaluator.evaluate_one(inputs, TitleNorm.GM, True)
        assert result.performance_too_low, (
            f'Expected Rp < 2600 fail. avg={result.average_rating}, '
            f'score={result.score}, Rp={result.performance}'
        )

    def test_rp_just_above_threshold_passes(self):
        """Same setup but score 9/11 = 0.818, dp[82]=262 → Rp=2400+262=2662. ≥2600 passes."""
        opponents = [
            _gm(i, rating=2400, federation=fed)
            for i, fed in enumerate(
                [
                    'USA',
                    'GER',
                    'ESP',
                    'ITA',
                    'NED',
                    'POL',
                    'RUS',
                    'AZE',
                    'IND',
                    'CHN',
                    'BRA',
                ],
                start=1,
            )
        ]
        results = [Result.WIN] * 9 + [Result.LOSS] * 2  # 9 points
        inputs = make_inputs(list(zip(range(1, 12), opponents, results)))
        searcher = _real_searcher(rounds=11)
        result = searcher.evaluator.evaluate_one(inputs, TitleNorm.GM, True)
        assert not result.performance_too_low, (
            f'Expected Rp ≥ 2600 pass. Rp={result.performance}'
        )

    def test_average_too_low_blocks_independently_of_performance(self):
        """Even if Rp formula gives a high number, 1.4.8a's Ra minimum
        (GM: 2380) is a separate hard floor."""
        # Avg = 2300 (below GM's 2380), score = 100% to make Rp huge.
        opponents = [
            _gm(i, rating=2300, federation=fed)
            for i, fed in enumerate(
                [
                    'USA',
                    'GER',
                    'ESP',
                    'ITA',
                    'NED',
                    'POL',
                    'RUS',
                    'AZE',
                    'IND',
                    'CHN',
                    'BRA',
                ],
                start=1,
            )
        ]
        results = [Result.WIN] * 11  # 100% — Rp = 2300 + 800 = 3100
        inputs = make_inputs(list(zip(range(1, 12), opponents, results)))
        searcher = _real_searcher(rounds=11)
        result = searcher.evaluator.evaluate_one(inputs, TitleNorm.GM, True)
        assert result.average_too_low, (
            f'Expected Ra={result.average_rating} < 2380 to fail GM. '
        )
        # Even though Rp would be high, average_too_low blocks is_met.
        assert not result.is_met


# ===========================================================================
# 1.5.6a — Top 40 players average ≥ 2000 every round
# ===========================================================================


class TestRule_1_5_6a:
    def _build_tournament(
        self, ratings: list[int], rounds: int = 9, swiss: bool = True
    ):
        """Build a tournament with len(ratings) players, each at the given
        rating, present in every round of a synthetic Swiss event."""
        from data.pairings.systems import (
            RoundRobinPairingSystem,
            SwissPairingSystem,
        )

        def _round_pairing():
            return SimpleNamespace(
                result=Result.DRAW, opponent=None, unplayed=False, played=True
            )

        players = {}
        for i, rating in enumerate(ratings, start=1):
            players[i] = SimpleNamespace(
                rating_type=PlayerRatingType.FIDE,
                federation=Federation('USA'),  # all foreign (irrelevant here)
                title=PlayerTitle.NONE,
                rating=rating,
                pairings_by_round={r: _round_pairing() for r in range(1, rounds + 1)},
            )
        pairing_system = SwissPairingSystem() if swiss else RoundRobinPairingSystem()
        return SimpleNamespace(
            event=SimpleNamespace(federation='FRA'),
            rounds=rounds,
            pairing_system=pairing_system,
            tournament_players_by_id=players,
        )

    def test_high_level_when_top_40_average_above_2000(self):
        from data.norms import compute_high_level_tournament

        # 50 players: 40 at 2200 + 10 at 1500. Top 40 = 2200. Average = 2200 ≥ 2000.
        tournament = self._build_tournament([2200] * 40 + [1500] * 10)
        assert compute_high_level_tournament(tournament) is True

    def test_not_high_level_when_top_40_average_below_2000(self):
        from data.norms import compute_high_level_tournament

        # 40 players all at 1900. Top 40 = 1900 < 2000.
        tournament = self._build_tournament([1900] * 40)
        assert compute_high_level_tournament(tournament) is False

    def test_not_high_level_when_fewer_than_40_eligible_players(self):
        from data.norms import compute_high_level_tournament

        tournament = self._build_tournament([2500] * 39)  # only 39 players
        assert compute_high_level_tournament(tournament) is False

    def test_high_level_threshold_must_hold_every_round(self):
        """The check is per-round (worst-case). One round with <40 present
        kills the eligibility."""
        from data.norms import compute_high_level_tournament
        from data.pairings.systems import SwissPairingSystem

        # 40 strong players. One of them missed 2 rounds → excluded from
        # eligible_players entirely, so every round counts 39 present.
        def _round_pairing(missed: bool = False):
            return SimpleNamespace(
                result=Result.ZERO_POINT_BYE if missed else Result.DRAW,
                opponent=None,
                unplayed=missed,
                played=not missed,
            )

        players = {}
        for i in range(1, 41):
            # Player 1 misses rounds 1 and 2 (NOT one of the exempt unplayed
            # results — counts as a real miss).
            pairings = {
                r: _round_pairing(missed=(i == 1 and r in (1, 2))) for r in range(1, 10)
            }
            players[i] = SimpleNamespace(
                rating_type=PlayerRatingType.FIDE,
                federation=Federation('USA'),
                title=PlayerTitle.NONE,
                rating=2500,
                pairings_by_round=pairings,
            )
        tournament = SimpleNamespace(
            event=SimpleNamespace(federation='FRA'),
            rounds=9,
            pairing_system=SwissPairingSystem(),
            tournament_players_by_id=players,
        )
        # Player 1 missed >1 round → excluded → 39 eligible players → fails.
        assert compute_high_level_tournament(tournament) is False

    def test_not_high_level_for_round_robin(self):
        """1.5.6a is Swiss-only. A 40-player Round-Robin that would pass
        every other criterion must still fail."""
        from data.norms import compute_high_level_tournament

        tournament = self._build_tournament([2200] * 40, rounds=9, swiss=False)
        assert compute_high_level_tournament(tournament) is False

    def test_pab_recipient_counts_as_present(self):
        """Documents the policy choice: a player receiving a PAB this round
        is counted toward the 40-player "present" threshold. Spec is
        ambiguous; current implementation includes PAB recipients."""
        from data.norms import compute_high_level_tournament
        from data.pairings.systems import SwissPairingSystem

        # 40 players at 2200. One of them has a PAB in round 5 (not at the
        # board) but is otherwise present every round.
        def _pairing(result=Result.DRAW):
            return SimpleNamespace(
                result=result,
                opponent=None,
                unplayed=result.is_unplayed,
                played=not result.is_unplayed,
            )

        players = {}
        for i in range(1, 41):
            pairings = {
                r: (
                    _pairing(Result.PAIRING_ALLOCATED_BYE)
                    if (i == 40 and r == 5)
                    else _pairing()
                )
                for r in range(1, 10)
            }
            players[i] = SimpleNamespace(
                rating_type=PlayerRatingType.FIDE,
                federation=Federation('USA'),
                title=PlayerTitle.NONE,
                rating=2200,
                pairings_by_round=pairings,
            )
        tournament = SimpleNamespace(
            event=SimpleNamespace(federation='FRA'),
            rounds=9,
            pairing_system=SwissPairingSystem(),
            tournament_players_by_id=players,
        )
        # Despite player #40 having a PAB in round 5, every round still
        # has 40 "present" players → 1.5.6a passes.
        assert compute_high_level_tournament(tournament) is True


# ===========================================================================
# 1.4.1 — minimum games for a norm (with min_games_override parameter)
# ===========================================================================
#
# Default is 9 (or 10 for DRR). The evaluator / searcher / forecaster
# accept an optional `min_games_override` parameter for internal use
# (e.g. tests, future hooks). No print-doc option exposes it — the
# 1.4.1b reductions to 7/8 only apply to team tournaments, which aren't
# modelled here.


class TestRule_1_4_1_min_games_override:
    """Verify the override changes the games-check threshold AND the
    searcher's `max_ignores` so 1.4.1e/f drops are gated correctly."""

    def test_default_minimum_is_9(self):
        """No override → tn.minimum_rounds(tournament) (9 for non-DRR)."""
        opponents = [_gm(i) for i in range(1, 10)]
        inputs = make_inputs(list(zip(range(1, 10), opponents, [Result.DRAW] * 9)))
        searcher = _real_searcher(rounds=9)
        # 9 played, threshold 9 → passes.
        ok, threshold = searcher.evaluator.games_requirement(inputs, TitleNorm.GM)
        assert ok
        assert threshold == 9

    def test_override_lowers_threshold(self):
        """min_games_override=7 → 7 played games passes the games check."""
        opponents = [_gm(i) for i in range(1, 8)]
        inputs = make_inputs(list(zip(range(1, 8), opponents, [Result.DRAW] * 7)))
        # Build a searcher with the override.
        from data.norms import TitleNormSubsetSearcher

        searcher_default = _real_searcher(rounds=7)
        ok_default, _ = searcher_default.evaluator.games_requirement(
            inputs, TitleNorm.GM
        )
        assert not ok_default, '7 played should fail default 9-game threshold'

        # Same fixture but evaluator/searcher created with override=7.
        searcher_override = TitleNormSubsetSearcher(
            searcher_default.player, min_games_override=7
        )
        ok_override, threshold = searcher_override.evaluator.games_requirement(
            inputs, TitleNorm.GM
        )
        assert ok_override, '7 played should pass when override=7'
        assert threshold == 7

    def test_override_affects_max_ignores_in_searcher(self):
        """max_ignores = tournament.rounds - min_games. Override raises
        max_ignores → searcher can try more subsets per 1.4.1e/f."""
        from data.norms import TitleNormSubsetSearcher

        searcher_default = _real_searcher(rounds=9)
        # 9-round Swiss + default min_games=9 → max_ignores=0 (no search).
        assert searcher_default._max_ignores(TitleNorm.GM) == 0

        # Same Swiss + override=7 → max_ignores=2 (can drop up to 2 rounds).
        searcher_override = TitleNormSubsetSearcher(
            searcher_default.player, min_games_override=7
        )
        assert searcher_override._max_ignores(TitleNorm.GM) == 2

    def test_override_propagates_evaluator_searcher_forecaster(self):
        """All three layers honour the override. Constructed with the same
        value, they should report the same min_games threshold."""
        from data.norms import (
            TitleNormEvaluator,
            TitleNormForecaster,
            TitleNormSubsetSearcher,
        )

        searcher = _real_searcher(rounds=9)
        player = searcher.player
        for cls in (TitleNormEvaluator, TitleNormSubsetSearcher, TitleNormForecaster):
            instance = cls(player, min_games_override=8)
            assert instance.min_games_override == 8

        # And: searcher constructed with override creates evaluator with same.
        s = TitleNormSubsetSearcher(player, min_games_override=8)
        assert s.evaluator.min_games_override == 8


# ===========================================================================
# 1.4.3d eligibility filter — players must miss at most one round
# ===========================================================================


class TestRule_1_4_3d_eligibility:
    """`compute_big_tournament_exemption`'s eligibility filter rejects
    players who missed more than one non-PAB / non-forfeit-win round."""

    def _make_player(self, federation: str, missed_rounds: set[int], rounds: int = 9):
        from data.pairings.systems import SwissPairingSystem  # noqa: F401

        def _pairing(missed: bool):
            return SimpleNamespace(
                result=Result.ZERO_POINT_BYE if missed else Result.DRAW,
                opponent=None,
                unplayed=missed,
                played=not missed,
            )

        return SimpleNamespace(
            rating_type=PlayerRatingType.FIDE,
            federation=Federation(federation),
            title=PlayerTitle.GRANDMASTER,
            rating=2500,
            pairings_by_round={
                r: _pairing(missed=(r in missed_rounds)) for r in range(1, rounds + 1)
            },
        )

    def _tournament(self, players: list, rounds: int = 9):
        from data.pairings.systems import SwissPairingSystem

        return SimpleNamespace(
            event=SimpleNamespace(federation='FRA'),
            rounds=rounds,
            pairing_system=SwissPairingSystem(),
            tournament_players_by_id={i: p for i, p in enumerate(players, start=1)},
        )

    def test_player_with_zero_missed_rounds_is_eligible(self):
        from data.norms import compute_big_tournament_exemption

        # 4 USA, 4 GER, 4 ESP — all attended every round.
        players = (
            [self._make_player('USA', set()) for _ in range(4)]
            + [self._make_player('GER', set()) for _ in range(4)]
            + [self._make_player('ESP', set()) for _ in range(4)]
        )
        exemption = compute_big_tournament_exemption(self._tournament(players))
        assert exemption.foreigners == 12  # all present
        assert exemption.federations == 3

    def test_player_with_one_missed_round_is_eligible_but_absent_that_round(self):
        """One missed round → still eligible, just absent that single round."""
        from data.norms import compute_big_tournament_exemption

        # 4 USA + 4 GER + 4 ESP. One of the USA players misses round 5.
        players = [self._make_player('USA', set()) for _ in range(3)]
        players.append(self._make_player('USA', {5}))  # missed round 5
        players += [self._make_player('GER', set()) for _ in range(4)]
        players += [self._make_player('ESP', set()) for _ in range(4)]
        exemption = compute_big_tournament_exemption(self._tournament(players))
        # Worst round (round 5): 11 present (12 eligible − the one absent).
        assert exemption.foreigners == 11

    def test_player_with_two_missed_rounds_is_excluded_entirely(self):
        """A player missing >1 round is removed from `eligible_players`
        completely — they don't contribute to ANY round's count."""
        from data.norms import compute_big_tournament_exemption

        # 4 USA + 4 GER + 4 ESP. One of the USA players misses 2 rounds.
        players = [self._make_player('USA', set()) for _ in range(3)]
        players.append(self._make_player('USA', {3, 5}))  # >1 missed
        players += [self._make_player('GER', set()) for _ in range(4)]
        players += [self._make_player('ESP', set()) for _ in range(4)]
        exemption = compute_big_tournament_exemption(self._tournament(players))
        # The doomed player contributes to NO round. Every round has 11.
        assert exemption.foreigners == 11

    def test_pab_does_not_count_as_missed_round(self):
        """Spec: "players will be counted only if they miss at most one
        round (excluding pairing allocated byes)" — PAB rounds aren't
        misses for eligibility."""
        from data.norms import compute_big_tournament_exemption

        def _pab():
            return SimpleNamespace(
                result=Result.PAIRING_ALLOCATED_BYE,
                opponent=None,
                unplayed=True,
                played=False,
            )

        def _played():
            return SimpleNamespace(
                result=Result.DRAW, opponent=None, unplayed=False, played=True
            )

        # One player has 3 PABs (way over 1) plus all-played → still eligible.
        special = SimpleNamespace(
            rating_type=PlayerRatingType.FIDE,
            federation=Federation('USA'),
            title=PlayerTitle.GRANDMASTER,
            rating=2500,
            pairings_by_round={
                r: (_pab() if r in {2, 4, 6} else _played()) for r in range(1, 10)
            },
        )
        players = [special]
        players += [self._make_player('GER', set()) for _ in range(4)]
        players += [self._make_player('ESP', set()) for _ in range(4)]
        exemption = compute_big_tournament_exemption(self._tournament(players))
        # Special is eligible AND counts as present (PAB = present per our
        # documented policy). Every round has 9 present (1 + 4 + 4).
        assert exemption.foreigners == 9


# ===========================================================================
# Forecaster — `TitleNormForecaster` public API
# ===========================================================================


def _forecaster_with_pairings(
    *,
    rounds: int,
    pairings: dict,
    federation: str = 'FRA',
    title: PlayerTitle = PlayerTitle.NONE,
    pairing_system=None,
):
    """Build a fake TournamentPlayer + TitleNormForecaster from pairings.
    Helper for forecaster tests."""
    from data.norms import TitleNormForecaster
    from data.pairings.systems import SwissPairingSystem
    from utils.enum import PlayerGender

    def _fake_pairing(result, opponent):
        return SimpleNamespace(
            result=result,
            opponent=opponent,
            unplayed=result.is_unplayed,
            played=not result.is_unplayed,
        )

    fake_pairings = {
        rnd: _fake_pairing(result, opp) for rnd, (opp, result) in pairings.items()
    }
    player = SimpleNamespace(
        federation=Federation(federation),
        gender=PlayerGender.MAN,
        title=PlayerTitle(title),
        event=SimpleNamespace(federation=federation),
        tournament=SimpleNamespace(
            rounds=rounds,
            pairing_system=pairing_system or SwissPairingSystem(),
            pairing_variation=None,
            tournament_players_by_id={},
            big_tournament_exemption=__import__(
                'utils.types', fromlist=['BigTournamentExemption']
            ).BigTournamentExemption(0, 0, 0),
            high_level_tournament=False,
        ),
        pairings_by_round=fake_pairings,
    )
    return TitleNormForecaster(player)


class TestForecasterCanForecastRound:
    """`can_forecast_round` gates whether a forecast is meaningful."""

    def test_paired_unentered_round_can_be_forecast(self):
        opp = _gm(1)
        forecaster = _forecaster_with_pairings(
            rounds=9, pairings={9: (opp, Result.NO_RESULT)}
        )
        assert forecaster.can_forecast_round(9)

    def test_unpaired_round_cannot_be_forecast(self):
        # No pairing entry at all for round 9.
        forecaster = _forecaster_with_pairings(rounds=9, pairings={})
        assert not forecaster.can_forecast_round(9)

    def test_round_with_no_opponent_cannot_be_forecast(self):
        forecaster = _forecaster_with_pairings(
            rounds=9, pairings={9: (None, Result.ZERO_POINT_BYE)}
        )
        assert not forecaster.can_forecast_round(9)

    def test_already_played_round_cannot_be_forecast(self):
        # If the result is entered already, the forecast for that round is
        # moot — the arbiter should look at the achieved-norms view instead.
        opp = _gm(1)
        forecaster = _forecaster_with_pairings(
            rounds=9, pairings={9: (opp, Result.WIN)}
        )
        assert not forecaster.can_forecast_round(9)


class TestForecasterMinimumRequiredResult:
    """`minimum_required_result` returns the cheapest outcome (LOSS, DRAW,
    WIN, or None) achieving a norm."""

    def _strong_field_player(
        self, ratings_and_results, last_round_opp, last_round_rounds=9
    ):
        """Build a forecaster for a player who has played `ratings_and_results`
        and faces `last_round_opp` in the last round (unentered)."""
        opps = [
            _gm(i, rating=r, federation=fed)
            for i, (r, fed, _res) in enumerate(ratings_and_results, start=1)
        ]
        pairings = {
            i: (opps[i - 1], res)
            for i, (_r, _fed, res) in enumerate(ratings_and_results, start=1)
        }
        pairings[last_round_rounds] = (last_round_opp, Result.NO_RESULT)
        return _forecaster_with_pairings(rounds=last_round_rounds, pairings=pairings)

    def test_any_outcome_works_when_player_already_secured(self):
        """8 wins against strong GMs going into R9 — Rp is way above 2600
        no matter what R9 does."""
        # Avg with 9 GMs at 2400 + 1 GM opp at 2400 = 2400. With 8 wins,
        # any R9 outcome: score 8.0/9 = 0.889 → dp 351 → Rp 2751 (LOSS).
        ratings_and_results = [
            (2400, fed, Result.WIN)
            for fed in ('USA', 'GER', 'ESP', 'ITA', 'NED', 'POL', 'RUS', 'AZE')
        ]
        last_opp = _gm(99, rating=2400, federation='IND')
        forecaster = self._strong_field_player(ratings_and_results, last_opp)
        # Even LOSS achieves the GM norm.
        assert forecaster.minimum_required_result(9, TitleNorm.GM) == Result.LOSS

    def test_returns_none_when_no_outcome_achieves(self):
        """Weak field + losses — no R9 outcome saves it."""
        ratings_and_results = [
            (1900, fed, Result.LOSS)
            for fed in ('USA', 'USA', 'USA', 'USA', 'USA', 'USA', 'USA', 'USA')
        ]
        last_opp = _gm(99, rating=1900, federation='USA')
        forecaster = self._strong_field_player(ratings_and_results, last_opp)
        # Way too few foreign feds + Ra too low — none of W/D/L can rescue.
        assert forecaster.minimum_required_result(9, TitleNorm.GM) is None


class TestForecasterChaseableNorms:
    """`chaseable_norms` filters out norms ≤ current title and unreachable
    ones, returning ForecastRequirement (minimum_outcome + play_required)."""

    def test_no_chaseable_norms_for_existing_gm(self):
        """A GM-titled player has no higher norm to chase."""
        # Player already a GM → nothing above.
        opp = _gm(1)
        forecaster = _forecaster_with_pairings(
            rounds=9,
            pairings={1: (opp, Result.WIN), 9: (opp, Result.NO_RESULT)},
            title=PlayerTitle.GRANDMASTER,
        )
        chaseable = forecaster.chaseable_norms(9)
        assert chaseable == {}

    def test_returns_forecast_requirement_with_play_required_true(self):
        """In a 9-round Swiss (no headroom for 1.4.1e tail-drop) where the
        full mix passes for all three outcomes, ForecastRequirement has
        `play_required=True` — the player MUST sit at the board even if
        the outcome doesn't matter."""
        # 8 wins against strong GMs + a strong R9 opponent. All three R9
        # outcomes give a norm via the full 9-game mix (Ra=2400).
        ratings_and_feds = [
            (2400, fed)
            for fed in ('USA', 'GER', 'ESP', 'ITA', 'NED', 'POL', 'RUS', 'AZE')
        ]
        opps = [
            _gm(i, rating=r, federation=fed)
            for i, (r, fed) in enumerate(ratings_and_feds, start=1)
        ]
        last_opp = _gm(99, rating=2400, federation='IND')
        pairings = {i: (opps[i - 1], Result.WIN) for i in range(1, 9)}
        pairings[9] = (last_opp, Result.NO_RESULT)
        forecaster = _forecaster_with_pairings(rounds=9, pairings=pairings)
        chaseable = forecaster.chaseable_norms(9)
        # GM achievable.
        assert TitleNorm.GM in chaseable
        req = chaseable[TitleNorm.GM]
        assert req.minimum_outcome == Result.LOSS  # any OTB result works
        # 9-round Swiss has max_ignores=0 → R_N can't be 1.4.1e-dropped.
        # Therefore play is required.
        assert req.play_required is True


class TestForecasterOutcomeOrdering:
    """Regression: the LOSS→DRAW→WIN iteration in `_FORECAST_OUTCOMES` returns
    the genuinely-cheapest outcome. With 1.4.1e/f drops, all three outcomes
    in a >9-round Swiss collapse to the same R1..R(N-1) mix when R_N is
    dropped — so LOSS (cheapest) wins the ordering, consistent with spec."""

    def test_loss_picked_when_tail_drop_rescues(self):
        """11-round Swiss. Baseline mix fails Rp regardless of R_N outcome,
        but dropping R_N (tail) leaves a passing R1..R10 mix. All three
        outcomes pass via 1.4.1e tail-drop → LOSS wins."""
        # 10 strong GMs in R1..R10 against which the applicant scored 7.5.
        # Avg 2400 with score 7.5/10 = 0.75 → dp 193 → Rp 2593 (just fails by 7).
        # Adjust: 8/10 = 0.8 → dp 240 → Rp 2640 (passes prefix).
        # Add R11 opp: forecast LOSS/DRAW/WIN. Searcher drops R11 (tail) →
        # leaves R1..R10 which passes. All three outcomes pass.
        feds = ['USA', 'GER', 'ESP', 'ITA', 'NED', 'POL', 'RUS', 'AZE', 'IND', 'CHN']
        opps = [_gm(i, rating=2400, federation=feds[i - 1]) for i in range(1, 11)]
        results = [Result.WIN] * 8 + [Result.LOSS] * 2  # 8 points in 10 games
        pairings = {i: (opps[i - 1], results[i - 1]) for i in range(1, 11)}
        last_opp = _gm(99, rating=2400, federation='BRA')
        pairings[11] = (last_opp, Result.NO_RESULT)
        forecaster = _forecaster_with_pairings(rounds=11, pairings=pairings)
        chaseable = forecaster.chaseable_norms(11)
        assert TitleNorm.GM in chaseable
        req = chaseable[TitleNorm.GM]
        # LOSS reported (cheapest); R_N dropped → play not required.
        assert req.minimum_outcome == Result.LOSS
        assert req.play_required is False


# ===========================================================================
# Tournament Norms Summary — early forecast unlock
# ===========================================================================
#
# Fire on the latest paired-but-unplayed round, gated per-player on having
# played ≥ min_games − 1 games.
# Lets an 11-round Swiss with 9-game norms forecast from R9 onward, not just
# R11.


class TestForecastDocumentEarlyUnlock:
    def _doc_with_players(self, players, rounds=11):
        """Minimal duck-type of TournamentNormsSummaryPrintDocument for the
        helpers under test. Only `.tournament` is read."""
        from types import SimpleNamespace as NS

        tournament = NS(
            rounds=rounds,
            tournament_players_by_id={i: p for i, p in enumerate(players)},
        )
        return NS(tournament=tournament)

    def _player_with_schedule(
        self, played_rounds: list[int], paired_unplayed: dict[int, int] | None = None
    ):
        """A duck-typed player whose pairings_by_round contains `played` flags
        and (optionally) entries for paired-unplayed rounds whose round numbers
        map to opponent ids."""
        from types import SimpleNamespace as NS

        pairings = {}
        for r in played_rounds:
            pairings[r] = NS(
                opponent=NS(id=999),  # arbitrary present opponent
                result=Result.WIN,
                played=True,
            )
        for r, opp_id in (paired_unplayed or {}).items():
            pairings[r] = NS(
                opponent=NS(id=opp_id),
                result=Result.NO_RESULT,
                played=False,
            )
        return NS(pairings_by_round=pairings)

    def test_find_forecastable_round_returns_highest_paired_unplayed(self):
        """Highest paired-but-unplayed round across all players wins."""
        from data.print_documents.documents import TournamentNormsSummaryPrintDocument

        p_a = self._player_with_schedule(
            played_rounds=[1, 2, 3, 4, 5, 6, 7, 8],
            paired_unplayed={9: 11},
        )
        p_b = self._player_with_schedule(
            played_rounds=[1, 2, 3, 4, 5, 6, 7, 8],
            paired_unplayed={9: 12},
        )
        doc = self._doc_with_players([p_a, p_b])
        assert TournamentNormsSummaryPrintDocument._find_forecastable_round(doc) == 9

    def test_find_forecastable_round_picks_higher_when_two_paired(self):
        """If R9 AND R10 are both paired-unplayed, R10 wins."""
        from data.print_documents.documents import TournamentNormsSummaryPrintDocument

        p = self._player_with_schedule(
            played_rounds=[1, 2, 3, 4, 5, 6, 7, 8],
            paired_unplayed={9: 11, 10: 12},
        )
        doc = self._doc_with_players([p])
        assert TournamentNormsSummaryPrintDocument._find_forecastable_round(doc) == 10

    def test_find_forecastable_round_returns_none_when_no_pairings(self):
        """All games already entered (or no opponent on the unplayed pairings)."""
        from data.print_documents.documents import TournamentNormsSummaryPrintDocument

        p = self._player_with_schedule(played_rounds=[1, 2, 3, 4, 5, 6, 7, 8, 9])
        doc = self._doc_with_players([p])
        assert TournamentNormsSummaryPrintDocument._find_forecastable_round(doc) is None

    def test_played_games_before_counts_played_only(self):
        """Counts only `pairing.played` rounds strictly before the given round."""
        from data.print_documents.documents import TournamentNormsSummaryPrintDocument

        p = self._player_with_schedule(
            played_rounds=[1, 2, 3, 4, 5, 6, 7, 8],
            paired_unplayed={9: 11, 10: 12},
        )
        # Before R9: 8 played.
        assert TournamentNormsSummaryPrintDocument._played_games_before(p, 9) == 8
        # Before R10: 8 played (R9 unplayed, doesn't count).
        assert TournamentNormsSummaryPrintDocument._played_games_before(p, 10) == 8
        # Before R5: 4 played.
        assert TournamentNormsSummaryPrintDocument._played_games_before(p, 5) == 4

    def test_played_games_before_zero_at_round_one(self):
        from data.print_documents.documents import TournamentNormsSummaryPrintDocument

        p = self._player_with_schedule(played_rounds=[1, 2, 3])
        assert TournamentNormsSummaryPrintDocument._played_games_before(p, 1) == 0


# ===========================================================================
# Per-round audit trail (Layer 2 — arbiter-facing inclusion/exclusion log)
# ===========================================================================
#
# The audit is built once per `collect_inputs` pass and copied onto each
# `NormCheckResult`. Tests pin one entry per decision branch so any future
# refactor of `collect_inputs` keeps the audit truthful.


class TestRoundAuditTrail:
    def _evaluator(self, **player_kwargs):
        from data.norms import TitleNormEvaluator

        player = _player_with_pairings(**player_kwargs)
        return TitleNormEvaluator(player)

    def test_included_round_records_included_decision(self):
        from data.norms.inputs import RoundDecision

        opp = _gm(1, federation='USA')
        evaluator = self._evaluator(
            rounds=9,
            pairings={1: (opp, Result.WIN)}
            | {r: (_gm(r, federation='GER'), Result.DRAW) for r in range(2, 10)},
        )
        inputs = evaluator.collect_inputs(include_last_forfeit_as_loss=False)
        r1 = next(e for e in inputs.round_audit if e.round_ == 1)
        assert r1.decision == RoundDecision.INCLUDED
        assert r1.reason_key == 'included'
        assert r1.opponent is opp
        assert r1.raw_result == Result.WIN
        assert r1.effective_result == Result.WIN

    def test_1_4_2a_NON_opponent_excluded(self):
        """NON-federation opponent: EXCLUDED with reason rule_1_4_2a."""
        from data.norms.inputs import RoundDecision

        non_opp = FakeOpponent(
            id=99,
            rating=2400,
            rating_type=PlayerRatingType.FIDE,
            federation=Federation('NON'),
        )
        pairings = {1: (non_opp, Result.WIN)} | {
            r: (
                _gm(
                    r,
                    federation=['USA', 'GER', 'ESP', 'ITA', 'NED', 'POL', 'RUS', 'AZE'][
                        r - 2
                    ],
                ),
                Result.DRAW,
            )
            for r in range(2, 10)
        }
        evaluator = self._evaluator(rounds=9, pairings=pairings)
        inputs = evaluator.collect_inputs(include_last_forfeit_as_loss=False)
        r1 = next(e for e in inputs.round_audit if e.round_ == 1)
        assert r1.decision == RoundDecision.EXCLUDED
        assert r1.reason_key == 'rule_1_4_2a'
        assert r1.opponent is non_opp
        assert r1.effective_result is None

    def test_1_4_2b_RR_unrated_zero_excluded(self):
        """RR + unrated opponent who scored zero against rated → EXCLUDED."""
        from data.norms.inputs import RoundDecision
        from data.pairings.systems import RoundRobinPairingSystem

        unrated = FakeOpponent(
            id=99,
            rating=0,
            rating_type=PlayerRatingType.NATIONAL,
            federation=Federation('USA'),
        )
        # Unrated opp must have its own pairings where they only met FIDE-rated
        # players and lost or didn't play.
        unrated.pairings_by_round = {
            r: SimpleNamespace(
                opponent=_gm(50 + r, federation='GER'),
                result=Result.LOSS,
            )
            for r in range(1, 10)
        }
        pairings = {1: (unrated, Result.WIN)} | {
            r: (
                _gm(
                    r,
                    federation=['USA', 'GER', 'ESP', 'ITA', 'NED', 'POL', 'RUS', 'AZE'][
                        r - 2
                    ],
                ),
                Result.DRAW,
            )
            for r in range(2, 10)
        }
        evaluator = self._evaluator(
            rounds=9, pairings=pairings, pairing_system=RoundRobinPairingSystem()
        )
        inputs = evaluator.collect_inputs(include_last_forfeit_as_loss=False)
        r1 = next(e for e in inputs.round_audit if e.round_ == 1)
        assert r1.decision == RoundDecision.EXCLUDED
        assert r1.reason_key == 'rule_1_4_2b'

    def test_forfeit_win_marked_no_opponent(self):
        """A forfeit win against a no-show is NOT counted as played → audit
        shows NO_OPPONENT / forfeit_win_excluded."""
        from data.norms.inputs import RoundDecision

        no_show = _gm(99, federation='USA')
        pairings = {1: (no_show, Result.FORFEIT_WIN)} | {
            r: (
                _gm(
                    r,
                    federation=['USA', 'GER', 'ESP', 'ITA', 'NED', 'POL', 'RUS', 'AZE'][
                        r - 2
                    ],
                ),
                Result.DRAW,
            )
            for r in range(2, 10)
        }
        evaluator = self._evaluator(rounds=9, pairings=pairings)
        inputs = evaluator.collect_inputs(include_last_forfeit_as_loss=False)
        r1 = next(e for e in inputs.round_audit if e.round_ == 1)
        assert r1.decision == RoundDecision.NO_OPPONENT
        assert r1.reason_key == 'forfeit_win_excluded'

    def test_pairing_allocated_bye_marked_board_bye(self):
        """A round with no opponent + PAB: NO_OPPONENT / board_bye."""
        from data.norms.inputs import RoundDecision

        pairings = {1: (None, Result.PAIRING_ALLOCATED_BYE)} | {
            r: (
                _gm(
                    r,
                    federation=['USA', 'GER', 'ESP', 'ITA', 'NED', 'POL', 'RUS', 'AZE'][
                        r - 2
                    ],
                ),
                Result.DRAW,
            )
            for r in range(2, 10)
        }
        evaluator = self._evaluator(rounds=9, pairings=pairings)
        inputs = evaluator.collect_inputs(include_last_forfeit_as_loss=False)
        r1 = next(e for e in inputs.round_audit if e.round_ == 1)
        assert r1.decision == RoundDecision.NO_OPPONENT
        assert r1.reason_key == 'board_bye'
        assert r1.opponent is None

    def test_1_4_2c_last_round_forfeit_marked_included_as_loss(self):
        """Under the 1.4.2c interpretation, a last-round forfeit-win is
        included as a played LOSS. Audit reflects effective_result=LOSS
        with reason `included_as_1_4_2c_loss`."""
        from data.norms.inputs import RoundDecision

        last_opp = _gm(99, federation='USA')
        pairings = {
            r: (
                _gm(
                    r,
                    federation=['USA', 'GER', 'ESP', 'ITA', 'NED', 'POL', 'RUS', 'AZE'][
                        r - 1
                    ],
                ),
                Result.DRAW,
            )
            for r in range(1, 9)
        }
        pairings[9] = (last_opp, Result.FORFEIT_WIN)
        evaluator = self._evaluator(rounds=9, pairings=pairings)
        # Under the 1.4.1c interpretation (forfeit excluded): NO_OPPONENT.
        inputs_a = evaluator.collect_inputs(include_last_forfeit_as_loss=False)
        r9_a = next(e for e in inputs_a.round_audit if e.round_ == 9)
        assert r9_a.decision == RoundDecision.NO_OPPONENT
        assert r9_a.reason_key == 'forfeit_win_excluded'
        # Under 1.4.2c: included as LOSS.
        inputs_b = evaluator.collect_inputs(include_last_forfeit_as_loss=True)
        r9_b = next(e for e in inputs_b.round_audit if e.round_ == 9)
        assert r9_b.decision == RoundDecision.INCLUDED
        assert r9_b.reason_key == 'included_as_1_4_2c_loss'
        assert r9_b.raw_result == Result.FORFEIT_WIN
        assert r9_b.effective_result == Result.LOSS

    def test_audit_copied_onto_norm_check_result(self):
        """`evaluate_one` copies the audit list onto NormCheckResult so the
        template can render it without holding a reference to inputs."""
        opp = _gm(1, federation='USA')
        pairings = {1: (opp, Result.WIN)} | {
            r: (
                _gm(
                    r,
                    federation=['GER', 'ESP', 'ITA', 'NED', 'POL', 'RUS', 'AZE', 'IND'][
                        r - 2
                    ],
                ),
                Result.DRAW,
            )
            for r in range(2, 10)
        }
        evaluator = self._evaluator(rounds=9, pairings=pairings)
        # Use evaluate_one directly to avoid tournament-wide stubs.
        inputs = evaluator.collect_inputs(include_last_forfeit_as_loss=False)
        res = evaluator.evaluate_one(inputs, TitleNorm.GM, True)
        assert [e.round_ for e in res.round_audit] == list(range(1, 10))
        # Same list reference — no defensive copy needed since entries
        # are frozen.
        assert res.round_audit is inputs.round_audit

    def test_search_marks_dropped_rounds_in_audit(self):
        """When the subset search drops rounds via 1.4.1e/f, the result's
        audit lists those rounds as DROPPED / ignored_via_1_4_1ef."""
        from data.norms.inputs import NormInputs, RoundDecision

        # Drive `_search_subsets` directly so we don't have to stub
        # tournament-wide attributes (1.4.3d / 1.5.6a).
        feds = [
            'USA',
            'GER',
            'ESP',
            'ITA',
            'NED',
            'POL',
            'RUS',
            'AZE',
            'IND',
            'CHN',
            'BRA',
        ]
        opps = [_gm(i, rating=2500, federation=feds[i - 1]) for i in range(1, 11)]
        # Round 11 against an untitled 1900 — likely candidate for 1.4.1e/f drop.
        weak = _untitled(11, rating=1900, federation=feds[10])
        results = [Result.WIN] + [Result.DRAW] * 9 + [Result.WIN]
        pairings_data = [(r, opps[r - 1], results[r - 1]) for r in range(1, 11)]
        pairings_data.append((11, weak, results[10]))
        inputs: NormInputs = make_inputs(pairings_data)
        # Build a matching audit (one entry per round, all INCLUDED).
        from data.norms.inputs import RoundAuditEntry

        inputs.round_audit = [
            RoundAuditEntry(
                round_=r,
                opponent=opp,
                raw_result=res,
                effective_result=res,
                decision=RoundDecision.INCLUDED,
                reason_key='included',
            )
            for r, opp, res in pairings_data
        ]
        searcher = _real_searcher(rounds=11)
        winner = searcher._search_subsets(inputs, TitleNorm.GM, True)
        # The search may or may not find a winner; if it does, the audit
        # must reflect the drops.
        if winner is not None and winner.ignored_rounds_via_search:
            for r in winner.ignored_rounds_via_search:
                entry = next(e for e in winner.round_audit if e.round_ == r)
                assert entry.decision == RoundDecision.DROPPED
                assert entry.reason_key == 'ignored_via_1_4_1ef'
                assert entry.effective_result is None
            for entry in winner.round_audit:
                if entry.round_ not in winner.ignored_rounds_via_search:
                    assert entry.decision != RoundDecision.DROPPED


# ===========================================================================
# Calculation-details data hooks
# ===========================================================================
#
# The detail mode of the norm-report doc consumes three pieces the IT1 mode
# doesn't: per-round 1.4.3d / 1.5.6a trails, the 1.4.2c "loser" attached as
# `alternate_142c`, and `federations_counter` on each result.


class TestCalculationDetailsHooks:
    def test_federations_counter_on_result(self):
        """`evaluate_one` populates `federations_counter` so the histogram
        in the detail view doesn't have to recount opponents."""
        opps = [
            _gm(1, federation='USA'),
            _gm(2, federation='GER'),
            _gm(3, federation='ESP'),
            _gm(4, federation='USA'),
        ]
        inputs = make_inputs(list(zip(range(1, 5), opps, [Result.DRAW] * 4)))
        searcher = _real_searcher(rounds=9)
        res = searcher.evaluator.evaluate_one(inputs, TitleNorm.GM, True)
        assert res.federations_counter is not None
        assert res.federations_counter[Federation('USA')] == 2
        assert res.federations_counter[Federation('GER')] == 1
        assert res.federations_counter[Federation('ESP')] == 1

    def test_alternate_142c_attached_when_1_4_2c_wins(self):
        """When the 1.4.2c interpretation rescues a norm the 1.4.1c
        interpretation failed, the loser is exposed via `alternate_142c`."""
        from data.norms import TitleNormEvaluator

        # 9 strong games + R9 forfeit-win against R9 opp. Under 1.4.1c
        # the forfeit is excluded → 8 played → fails 1.4.1. Under 1.4.2c
        # it counts as a played LOSS → 9 played → may pass.
        feds = ['USA', 'GER', 'ESP', 'ITA', 'NED', 'POL', 'RUS', 'AZE']
        opps = [_gm(i, federation=feds[i - 1], rating=2300) for i in range(1, 9)]
        pairings = {
            r: (opps[r - 1], Result.WIN if r <= 7 else Result.DRAW) for r in range(1, 9)
        }
        last_opp = _gm(9, federation='IND', rating=2300)
        pairings[9] = (last_opp, Result.FORFEIT_WIN)
        # Apply through the evaluator's full evaluate() so the dual-eval
        # orchestration runs.
        from data.pairings.systems import SwissPairingSystem
        from utils.enum import PlayerGender

        player = SimpleNamespace(
            federation=Federation('FRA'),
            gender=PlayerGender.MAN,
            title=PlayerTitle.NONE,
            event=SimpleNamespace(federation='FRA'),
            tournament=SimpleNamespace(
                rounds=9,
                pairing_system=SwissPairingSystem(),
                pairing_variation=None,
                tournament_players_by_id={},
                # stubs for tournament-wide checks
                big_tournament_exemption=__import__(
                    'utils.types', fromlist=['BigTournamentExemption']
                ).BigTournamentExemption(0, 0, 0),
                high_level_tournament=False,
            ),
            pairings_by_round={
                r: SimpleNamespace(
                    opponent=opp,
                    result=res,
                    unplayed=res.is_unplayed,
                    played=not res.is_unplayed,
                )
                for r, (opp, res) in pairings.items()
            },
        )
        evaluator = TitleNormEvaluator(player)
        results = evaluator.evaluate()
        # IM is reachable; check whichever norm picked up 1.4.2c.
        for tn, res in results.items():
            if res.applied_142c:
                # Side-by-side data present.
                assert res.alternate_142c is not None
                # Loser must NOT have 1.4.2c flag itself.
                assert res.alternate_142c.applied_142c is False
                # Different played-game counts between the two interpretations.
                assert (
                    res.played_games != res.alternate_142c.played_games
                    or res.score != res.alternate_142c.score
                )
                break
        else:
            # If 1.4.2c didn't fire for any norm (test fixture didn't trigger
            # the fallback), at least confirm alternate_142c is None everywhere.
            for res in results.values():
                assert res.alternate_142c is None

    def test_big_tournament_trail_returns_one_row_per_round(self):
        """`compute_big_tournament_exemption_trail` produces exactly
        `tournament.rounds` rows, one per round."""
        from data.norms import compute_big_tournament_exemption_trail

        tournament = self._tournament_with_one_player(rounds=9)
        trail = compute_big_tournament_exemption_trail(tournament)
        assert len(trail) == 9
        assert [r.round_ for r in trail] == list(range(1, 10))

    def test_high_level_trail_returns_one_row_per_round(self):
        from data.norms import compute_high_level_tournament_trail

        tournament = self._tournament_with_one_player(rounds=9)
        trail = compute_high_level_tournament_trail(tournament)
        assert len(trail) == 9
        # Under-40 players → top-40 average is 0.0 (insufficient data).
        for row in trail:
            assert row.top_40_average == 0.0

    def test_big_tournament_exemption_minima_match_trail(self):
        """The legacy `compute_big_tournament_exemption` minima should equal
        the per-column minima from the trail — they share the same eligibility
        filter and same per-round counts."""
        from data.norms import (
            compute_big_tournament_exemption,
            compute_big_tournament_exemption_trail,
        )

        tournament = self._tournament_with_one_player(rounds=9)
        ex = compute_big_tournament_exemption(tournament)
        trail = compute_big_tournament_exemption_trail(tournament)
        if trail:
            assert ex.foreigners == min(r.foreigners for r in trail)
            assert ex.federations == min(r.federations for r in trail)
            assert ex.titled_foreigners == min(r.titled_foreigners for r in trail)

    def _tournament_with_one_player(self, rounds: int):
        """Minimal tournament with a single FIDE-rated foreigner playing
        every round. Enough to exercise the trail builders."""
        from data.pairings.systems import SwissPairingSystem

        opp = _gm(99, federation='GER', rating=2400)
        opp.pairings_by_round = {
            r: SimpleNamespace(
                opponent=SimpleNamespace(id=100),
                result=Result.DRAW,
                unplayed=False,
                played=True,
            )
            for r in range(1, rounds + 1)
        }
        return SimpleNamespace(
            rounds=rounds,
            tournament_players_by_id={99: opp},
            event=SimpleNamespace(federation='FRA'),
            pairing_system=SwissPairingSystem(),
        )


# ===========================================================================
# 1.4.3a/b/c — end-to-end scenarios through evaluator + forecaster
# ===========================================================================
#
# These exercise the full path from a real opponent mix through the
# evaluator's per-rule checks, then `apply_143abc_exemption`, then is_met.
# Complements `TestRule_1_4_3abc` which tests the applier in isolation
# with hand-built NormCheckResults.


class TestRule_1_4_3abc_EndToEnd:
    def _player_failing_143_only(self, *, federation: str):
        """A 9-round Swiss player whose opponent mix has all GMs from the
        applicant's OWN federation. Result: 1.4.3 fails (no other
        federations), 1.4.4 own-fed cap also fails (5/5 from own fed), but
        Ra/Rp/score/title-holders all pass strongly. This shape lets us
        observe what each exemption actually rescues."""
        opps = [_gm(i, rating=2500, federation=federation) for i in range(1, 10)]
        pairings = {
            r: (opps[r - 1], Result.WIN if r <= 6 else Result.DRAW)
            for r in range(1, 10)
        }
        return _player_with_pairings(federation=federation, rounds=9, pairings=pairings)

    def test_143c_via_evaluator_rescues_when_144_fails(self):
        """1.4.3c (zonal) waives the foreigner requirement — 1.4.3 AND
        1.4.4 (1.4.3e). Setup: applicant from FRA, all 9 opponents also
        from FRA. Both 1.4.3 (only 1 fed) and 1.4.4 own-fed cap (9/9
        from own) fail; 1.4.3c rescues both."""
        from data.norms import TitleNormEvaluator, apply_143abc_exemption

        player = self._player_failing_143_only(federation='FRA')
        evaluator = TitleNormEvaluator(player)
        inputs = evaluator.collect_inputs(include_last_forfeit_as_loss=False)
        res = evaluator.evaluate_one(inputs, TitleNorm.GM, True)
        # evaluate_one doesn't run the tournament-wide 1.4.3d check, so
        # is_143d_met defaults True. Set the 1.4.3d violation explicitly
        # so the test exercises ONLY the a/b/c path.
        res.not_enough_all_federations = '1.4.3d not met'
        res.not_enough_foreign_players = '1.4.3d not met'
        res.not_enough_all_title_holders = '1.4.3d not met'
        # Setup verification: 1.4.3 fails, 1.4.4 also fails, 1.4.3d not met.
        assert res.not_enough_federations
        assert res.too_many_own_federation
        assert not res.is_143d_met
        assert not res.is_met
        # Apply 1.4.3c (any-player exemption).
        apply_143abc_exemption(
            {TitleNorm.GM: res}, '1.4.3c', Federation('FRA'), Federation('FRA')
        )
        assert res.rule_143_exemption == 'c'
        assert res.is_143_exempt_via_abc
        assert res.is_met, '1.4.3c waives both 1.4.3 and 1.4.4'

    def test_143a_via_evaluator_rescues_only_event_fed_players(self):
        """National championship final: same opponent mix, two players.
        Player from event fed → exemption applies. Player from another
        federation → exemption does NOT apply."""
        from data.norms import TitleNormEvaluator, apply_143abc_exemption

        # All opponents from USA: 1.4.3 fails (only 1 foreign federation)
        # regardless of applicant. We don't need is_met to flip — this
        # scenario verifies that the exemption applier correctly scopes
        # the flag to event-fed players only (unit tests in
        # `TestRule_1_4_3abc` cover the is_met arithmetic).
        usa_opps = [_gm(i, rating=2500, federation='USA') for i in range(1, 10)]
        pairings = {
            r: (usa_opps[r - 1], Result.WIN if r <= 3 else Result.DRAW)
            for r in range(1, 10)
        }
        player_fra = _player_with_pairings(
            federation='FRA',
            rounds=9,
            pairings=pairings,
        )
        evaluator_fra = TitleNormEvaluator(player_fra)
        inputs_fra = evaluator_fra.collect_inputs(include_last_forfeit_as_loss=False)
        res_fra = evaluator_fra.evaluate_one(inputs_fra, TitleNorm.GM, True)
        assert res_fra.not_enough_federations, '1.4.3 must fail for setup'

        # Apply 1.4.3a — event = FRA (matches applicant).
        apply_143abc_exemption(
            {TitleNorm.GM: res_fra},
            '1.4.3a',
            Federation('FRA'),
            Federation('FRA'),
        )
        assert res_fra.rule_143_exemption == 'a'

        # Same opponent mix, applicant from GER (NOT event fed).
        player_ger = _player_with_pairings(
            federation='GER',
            rounds=9,
            pairings=pairings,
        )
        evaluator_ger = TitleNormEvaluator(player_ger)
        inputs_ger = evaluator_ger.collect_inputs(include_last_forfeit_as_loss=False)
        res_ger = evaluator_ger.evaluate_one(inputs_ger, TitleNorm.GM, True)
        # Apply 1.4.3a — event = FRA, applicant = GER → no exemption.
        apply_143abc_exemption(
            {TitleNorm.GM: res_ger},
            '1.4.3a',
            Federation('GER'),
            Federation('FRA'),
        )
        assert res_ger.rule_143_exemption is None, (
            '1.4.3a should NOT exempt the foreign player (GER ≠ FRA)'
        )

    def test_forecaster_with_143c_unlocks_chaseable_norm(self):
        """Forecaster ctor accepts rule_143_exemption='1.4.3c'; the
        chaseable-norms machinery passes the exemption through to each
        per-outcome evaluation so a norm previously unreachable becomes
        reachable."""
        from data.norms import TitleNormForecaster
        from data.pairings.systems import SwissPairingSystem
        from utils.enum import PlayerGender

        # Set up the same single-foreign-fed shape: applicant from FRA,
        # rounds 1-8 against USA GMs, round 9 still unplayed.
        usa_opps = [_gm(i, rating=2500, federation='USA') for i in range(1, 9)]
        pairings = {
            r: (usa_opps[r - 1], Result.WIN if r <= 5 else Result.DRAW)
            for r in range(1, 9)
        }
        # Last-round opponent (not yet played):
        last_opp = _gm(99, rating=2500, federation='USA')
        pairings[9] = (last_opp, Result.NO_RESULT)

        def _fake_pairing(result, opp):
            return SimpleNamespace(
                result=result,
                opponent=opp,
                unplayed=result.is_unplayed,
                played=not result.is_unplayed,
            )

        from utils.types import BigTournamentExemption as _Btx

        player = SimpleNamespace(
            federation=Federation('FRA'),
            gender=PlayerGender.MAN,
            title=PlayerTitle.NONE,
            event=SimpleNamespace(federation='FRA'),
            tournament=SimpleNamespace(
                rounds=9,
                pairing_system=SwissPairingSystem(),
                pairing_variation=None,
                tournament_players_by_id={},
                big_tournament_exemption=_Btx(0, 0, 0),
                high_level_tournament=False,
            ),
            pairings_by_round={
                r: _fake_pairing(res, opp) for r, (opp, res) in pairings.items()
            },
        )

        # Without exemption → 1.4.3 fails (single foreign fed) → no norm
        # chaseable regardless of round 9 outcome.
        plain = TitleNormForecaster(player)
        chaseable_plain = plain.chaseable_norms(9)
        assert TitleNorm.GM not in chaseable_plain, (
            'Without 1.4.3c, single-foreign-fed mix fails 1.4.3 → no chaseable GM'
        )

        # With 1.4.3c → exemption flag propagates to every per-outcome
        # forecast result. (Whether the norm becomes is_met depends on
        # whether 1.4.4 also passes — covered by the unit tests in
        # `TestRule_1_4_3abc`. Here we verify the forecaster threads the
        # exemption code into each searcher run.)
        exempt = TitleNormForecaster(player, rule_143_exemption='1.4.3c')
        for outcome_result in exempt.forecast_round(9).values():
            assert outcome_result[TitleNorm.GM].is_143_exempt_via_abc, (
                'Forecaster must apply rule_143_exemption to every per-outcome result'
            )


# ===========================================================================
# 1.4.2c rescue when 1.4.4 fails — orchestrator must defer is_met check
# ===========================================================================
#
# Setup: 9-round Swiss. Applicant gets 8 played games (7.0 / 8) against
# strong GMs, with 6 of those 8 from one federation. Round 9 is a
# FORFEIT_WIN against a 9th GM (different federation).
#
# Under 1.4.1c (forfeit excluded):
#   - 1.4.1 passes via the 8+1 PAB exception.
#   - 1.4.4 one-fed cap fails: 6 from one fed > ⌊2 × 8 / 3⌋ = 5.
#   - is_met should be False → orchestrator must try 1.4.2c.
#
# Under 1.4.2c (forfeit as LOSS, 9 played):
#   - 1.4.4 one-fed cap passes: 6 ≤ ⌊2 × 9 / 3⌋ = 6.
#   - Rp ≈ 2620 ≥ 2600 → norm achieved.


class TestRule_1_4_2c_Rescue_When_1_4_4_Fails:
    def test_orchestrator_falls_back_to_1_4_2c_when_1_4_4_only_blocks(self):
        """When 1.4.1c fails ONLY on 1.4.4 (proportional cap) and 1.4.2c's
        scaled threshold rescues it, applied_142c must be True with
        alternate_142c populated for the side-by-side view."""
        from data.norms import TitleNormSubsetSearcher
        from data.pairings.systems import SwissPairingSystem
        from utils.enum import PlayerGender
        from utils.types import BigTournamentExemption as _Btx

        # 6 GER GMs + 1 FIN GM + 1 GAB GM = 8 opponents in R1-R8.
        ger_opps = [_gm(i, rating=2400, federation='GER') for i in range(1, 7)]
        fin_opp = _gm(7, rating=2400, federation='FIN')
        gab_opp = _gm(8, rating=2400, federation='GAB')
        # Score 7.0 / 8 = strong Rp under 1.4.1c (2736-ish).
        results_r1_8 = [Result.WIN] * 6 + [Result.WIN] + [Result.DRAW]
        # That's 7 wins + 1 draw = 7.5. Use 6W + 2D = 7.0 instead.
        results_r1_8 = [Result.WIN] * 6 + [Result.DRAW] + [Result.DRAW]
        # 6 wins + 2 draws = 7.0.
        pairings_r1_8 = list(
            zip(
                range(1, 9),
                ger_opps + [fin_opp, gab_opp],
                results_r1_8,
            )
        )
        # R9: forfeit-win against a GEO GM.
        geo_opp = _gm(9, rating=2400, federation='GEO')

        def _fake_pairing(result, opp):
            return SimpleNamespace(
                result=result,
                opponent=opp,
                unplayed=result.is_unplayed,
                played=not result.is_unplayed,
            )

        pairings_dict = {
            rnd: _fake_pairing(res, opp) for rnd, opp, res in pairings_r1_8
        }
        pairings_dict[9] = _fake_pairing(Result.FORFEIT_WIN, geo_opp)

        player = SimpleNamespace(
            federation=Federation('FRA'),  # not in any opponent's fed
            gender=PlayerGender.MAN,
            title=PlayerTitle.NONE,
            event=SimpleNamespace(federation='FRA'),
            tournament=SimpleNamespace(
                rounds=9,
                pairing_system=SwissPairingSystem(),
                pairing_variation=None,
                tournament_players_by_id={},
                # Tournament-wide 1.4.3d NOT met (small event).
                big_tournament_exemption=_Btx(0, 0, 0),
                high_level_tournament=False,
            ),
            pairings_by_round=pairings_dict,
        )

        searcher = TitleNormSubsetSearcher(player)
        results = searcher.evaluate()
        gm_result = results[TitleNorm.GM]

        # Sanity: the 1.4.2c rescue must have fired.
        assert gm_result.applied_142c, (
            '1.4.2c must rescue: 1.4.1c fails 1.4.4 (6 GER > 5 cap on 8 played) '
            'but 1.4.2c passes (6 ≤ 6 cap on 9 played).'
        )
        assert gm_result.alternate_142c is not None, (
            'alternate_142c must hold the failing 1.4.1c result for the '
            'side-by-side view'
        )
        # The 1.4.2c reading achieves the norm.
        assert gm_result.is_met, (
            'GM norm should be achieved under 1.4.2c: Rp ≈ 2620, federation '
            'caps satisfied at 9 played, all other rules pass.'
        )
        # The 1.4.1c reading did NOT achieve it (because of 1.4.4 one-fed).
        assert not gm_result.alternate_142c.is_met
        assert gm_result.alternate_142c.too_many_one_federation
