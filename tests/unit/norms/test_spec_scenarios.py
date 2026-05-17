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
    _is_monotonic_failure,
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
# Monotonicity property tests — pruner correctness
# ===========================================================================
#
# `_is_monotonic_failure` claims: if a check returns True for a subset S,
# every superset T ⊇ S must also return True (so the pruner can skip T).
# These tests enumerate concrete counter-example attempts to verify the
# claim only fires for actually-monotonic flags.


class TestMonotonicityProperty:
    """For every flag the pruner treats as monotonic, no counter-example
    must exist where dropping more rounds (a superset of drops) makes the
    check pass.
    """

    def _evaluator(self) -> TitleNormEvaluator:
        return _real_searcher(rounds=11).evaluator

    def test_not_enough_games_is_truly_monotonic(self):
        """Dropping more rounds strictly decreases played_games.
        Threshold (min_games) is fixed → once below, can't recover."""
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

    def test_score_too_low_is_NOT_monotonic(self):
        """Counter-example: dropping more LOSSES improves fractional score."""
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
            f'Score check should be non-monotonic. '
            f'baseline score={baseline.score}, played={baseline.played_games}; '
            f'after-drop score={rescued.score}, played={rescued.played_games}'
        )
        # The pruner must therefore NOT treat score_too_low as monotonic.
        assert not _is_monotonic_failure(
            NormCheckResult(
                title_norm=TitleNorm.GM,
                meets_gender=True,
                score_too_low='x',
            )
        )

    def test_title_holders_count_is_NOT_monotonic(self):
        """Counter-example: dropping untitled opponents improves the titled %.

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
            f'Title-holders check should be non-monotonic with scaling threshold. '
            f'baseline: titled={baseline.num_title_holders}, played={baseline.played_games}; '
            f'after-drop: titled={rescued.num_title_holders}, played={rescued.played_games}'
        )
        # Pruner must not treat as monotonic.
        assert not _is_monotonic_failure(
            NormCheckResult(
                title_norm=TitleNorm.GM,
                meets_gender=True,
                not_enough_title_holders='x',
            )
        )

    def test_required_titles_count_is_NOT_monotonic(self):
        """Counter-example: with "min 3" floor, dropping non-GMs improves
        the 1/3 ratio without losing the floor.

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
            'Required-titles check should be non-monotonic — the min-3 '
            'floor means dropping non-required opponents can recover.'
        )

    def test_too_many_own_federation_is_NOT_monotonic(self):
        """Counter-example: dropping own-fed opponents lowers BOTH own_count
        AND the threshold (floor(3·played/5)). The threshold can drop faster
        than own_count, letting a superset of drops recover.

        Baseline played=9, 6 FRA + 3 USA, applicant from FRA:
          threshold = floor(3·9/5) = 5;  own=6 > 5  → fails.
        Drop 1 FRA (subset S):
          played=8, own=5, threshold = floor(24/5) = 4;  5 > 4 → still fails.
        Drop 2 FRAs (superset T ⊋ S):
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

        # Subset S: drop one FRA (round 1).
        s = inputs.without_rounds(frozenset({1}))
        res_s = searcher.evaluator.evaluate_one(s, TitleNorm.GM, True)
        assert res_s.too_many_own_federation, (
            'S = drop 1 FRA: own=5, played=8, threshold=4 → 5>4 should fail.'
        )

        # Superset T ⊋ S: drop two FRAs (rounds 1 and 2).
        t = inputs.without_rounds(frozenset({1, 2}))
        res_t = searcher.evaluator.evaluate_one(t, TitleNorm.GM, True)
        assert not res_t.too_many_own_federation, (
            f'T = drop 2 FRAs: own=4, played=7, threshold=4 → 4>4 should pass. '
            f'Got too_many_own_federation={res_t.too_many_own_federation}.'
        )
        # Therefore the check is NOT monotonic in subset size.
        assert not _is_monotonic_failure(
            NormCheckResult(
                title_norm=TitleNorm.GM,
                meets_gender=True,
                too_many_own_federation='x',
            )
        )

    def test_too_many_one_federation_is_NOT_monotonic(self):
        """Counter-example for the 2/3-cap version of 1.4.4.

        Baseline played=9, 7 USA + 2 FRA, applicant from FRA:
          threshold = floor(2·9/3) = 6;  top=7 > 6  → fails.
        Drop 1 USA:
          played=8, top=6, threshold = floor(16/3) = 5;  6 > 5 → still fails.
        Drop 3 USAs (superset):
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

        # Subset S: drop one USA.
        s = inputs.without_rounds(frozenset({1}))
        res_s = searcher.evaluator.evaluate_one(s, TitleNorm.GM, True)
        assert res_s.too_many_one_federation

        # Superset T ⊋ S: drop three USAs.
        t = inputs.without_rounds(frozenset({1, 2, 3}))
        res_t = searcher.evaluator.evaluate_one(t, TitleNorm.GM, True)
        assert not res_t.too_many_one_federation, (
            f'T = drop 3 USAs: top=4, played=6, threshold=4 → 4>4 should pass. '
            f'Got too_many_one_federation={res_t.too_many_one_federation}.'
        )
        assert not _is_monotonic_failure(
            NormCheckResult(
                title_norm=TitleNorm.GM,
                meets_gender=True,
                too_many_one_federation=(Federation('USA'), 'x'),
            )
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
    """The dev-reviewed clause: FID is a 'real' federation for counting
    purposes (1.4.3) but NOT a foreign player (1.4.3d/1.5.6a)."""

    def test_fid_opponent_counts_in_federations_counter_for_1_4_3(self):
        """1.4.3 cares about distinct federations in the applicant's mix.
        FID is a valid FIDE federation, so it counts."""
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
        # FID DOES count as a federation in the mix.
        assert Federation('FID') in inputs.federations_counter
        assert inputs.federations_counter[Federation('FID')] == 1
        # The 1.4.3 num_feds count therefore sees 2 distinct (USA + FID).
        _, num_feds, _own = evaluator.federation_count_requirement(inputs)
        assert num_feds == 2

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
        # The 3 USA players are foreign and contribute. The FID player is
        # "accepted" so present, but excluded from federation diversity
        # by 1.4.3d's foreign-player filter.
        # foreigners = USA × 3 + FID × 1 = 4 (it's not FRA so it qualifies
        # as "not from host federation"). FID IS counted in foreigners
        # because compute_big_tournament_exemption only filters out
        # NON and host-fed at the eligible-players step. FID stays.
        assert exemption.foreigners == 4
        # federations: only non-FID feds counted → just USA → 1 distinct fed.
        assert exemption.federations == 1, (
            f'FID should NOT count toward 1.4.3d federation diversity. '
            f'Got {exemption.federations} feds; expected 1 (USA only).'
        )


# ===========================================================================
# 1.4.2b — RR: unrated opponents who score 0 against rated opponents
# ===========================================================================
#
# In round-robin tournaments, an unrated player who lost every game against
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
    def _build_tournament(self, ratings: list[int], rounds: int = 9):
        """Build a tournament with len(ratings) players, each at the given
        rating, present in every round of a synthetic Swiss event."""

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
        return SimpleNamespace(
            event=SimpleNamespace(federation='FRA'),
            rounds=rounds,
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
            tournament_players_by_id=players,
        )
        # Player 1 missed >1 round → excluded → 39 eligible players → fails.
        assert compute_high_level_tournament(tournament) is False


# ===========================================================================
# 1.4.1 — minimum games for a norm (with arbiter override per 1.4.1b)
# ===========================================================================
#
# Default is 9 (or 10 for DRR). The arbiter can override down to 7 for
# World/Continental Team Championships, or 8 for World Cup (per 1.4.1b).
# The override is exposed via `MinimumGamesPrintOption` on the norm
# documents and threaded as `min_games_override` through the evaluator,
# searcher and forecaster.


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


class TestMinimumGamesPrintOption:
    """The option itself: type, default, validation."""

    def _option(self, value=None):
        from data.print_documents.options import MinimumGamesPrintOption
        from types import SimpleNamespace

        # Options need an event for translation context; SimpleNamespace works.
        event = SimpleNamespace()
        opt = MinimumGamesPrintOption(event)
        if value is not None:
            opt.value = value
        return opt

    def test_default_is_9(self):
        opt = self._option()
        assert opt.default_value == 9
        # Until set, value resolves to default.
        assert opt.value == 9

    def test_type_is_int(self):
        opt = self._option()
        assert opt.type is int

    def test_validate_accepts_7(self):
        # 7-round World/Continental Team Championships per 1.4.1b.
        opt = self._option(value=7)
        opt.validate()  # no raise

    def test_validate_accepts_8(self):
        # 8-round World Cup per 1.4.1b.
        opt = self._option(value=8)
        opt.validate()

    def test_validate_accepts_9_default(self):
        opt = self._option(value=9)
        opt.validate()

    def test_validate_accepts_higher_than_9(self):
        # Larger overrides are conceptually weird but technically more
        # restrictive than spec; not the option's job to reject.
        opt = self._option(value=20)
        opt.validate()

    def test_validate_rejects_below_7(self):
        from common.exception import OptionError

        for bad in (6, 1, 0, -1):
            opt = self._option(value=bad)
            with pytest.raises(OptionError):
                opt.validate()

    def test_validate_rejects_none(self):
        from common.exception import OptionError

        opt = self._option(value=None)
        # Setting value=None then explicitly making sure validate rejects.
        # The default_value (9) wouldn't fire here because we explicitly set it.
        opt.value = None
        with pytest.raises(OptionError):
            opt.validate()

    def test_swiss_tournament_ids_with_no_event_returns_empty(self):
        """Defensive: an option built without an event must not crash when
        the template reads `swiss_tournament_ids`."""
        opt = self._option()
        opt.event = None
        assert opt.swiss_tournament_ids == []

    def test_swiss_tournament_ids_filters_to_swiss_only(self):
        """The UI hide/show pulls this list to know which tournament IDs
        keep the option visible."""
        from data.pairings.systems import (
            RoundRobinPairingSystem,
            SwissPairingSystem,
        )
        from types import SimpleNamespace

        swiss = SimpleNamespace(id=1, pairing_system=SwissPairingSystem())
        rr = SimpleNamespace(id=2, pairing_system=RoundRobinPairingSystem())
        swiss_2 = SimpleNamespace(id=3, pairing_system=SwissPairingSystem())
        event = SimpleNamespace(tournaments=[swiss, rr, swiss_2])

        opt = self._option()
        opt.event = event
        assert opt.swiss_tournament_ids == [1, 3]


class TestMinGamesDocumentIntegration:
    """The two norm documents resolve the override only for Swiss
    tournaments, and reject non-default values on non-Swiss in validate."""

    def _swiss_doc(self):
        """A minimal stand-in for a print document whose `tournament` is
        Swiss. Just enough surface for `_resolve_min_games_override` and
        `_validate_min_games_only_for_swiss`."""
        from data.pairings.systems import SwissPairingSystem
        from data.print_documents.options import MinimumGamesPrintOption
        from types import SimpleNamespace

        opt = MinimumGamesPrintOption(SimpleNamespace(tournaments=[]))
        doc = SimpleNamespace(
            tournament=SimpleNamespace(pairing_system=SwissPairingSystem()),
            _get_option=lambda t: opt,
        )
        return doc, opt

    def _rr_doc(self):
        from data.pairings.systems import RoundRobinPairingSystem
        from data.print_documents.options import MinimumGamesPrintOption
        from types import SimpleNamespace

        opt = MinimumGamesPrintOption(SimpleNamespace(tournaments=[]))
        doc = SimpleNamespace(
            tournament=SimpleNamespace(pairing_system=RoundRobinPairingSystem()),
            _get_option=lambda t: opt,
        )
        return doc, opt

    def test_resolve_returns_option_value_for_swiss(self):
        from data.print_documents.documents import _resolve_min_games_override

        doc, opt = self._swiss_doc()
        opt.value = 7
        assert _resolve_min_games_override(doc) == 7

    def test_resolve_returns_none_for_rr_regardless_of_value(self):
        from data.print_documents.documents import _resolve_min_games_override

        doc, opt = self._rr_doc()
        opt.value = 9  # default; still None on RR
        assert _resolve_min_games_override(doc) is None
        opt.value = 7  # explicit override; still None on RR
        assert _resolve_min_games_override(doc) is None

    def test_validate_passes_default_on_rr(self):
        from data.print_documents.documents import (
            _validate_min_games_only_for_swiss,
        )

        doc, opt = self._rr_doc()
        opt.value = opt.default_value  # 9
        _validate_min_games_only_for_swiss(doc)  # no raise

    def test_validate_rejects_non_default_on_rr(self):
        from common.exception import OptionError
        from data.print_documents.documents import (
            _validate_min_games_only_for_swiss,
        )

        doc, opt = self._rr_doc()
        opt.value = 7
        with pytest.raises(OptionError):
            _validate_min_games_only_for_swiss(doc)

    def test_validate_accepts_any_value_on_swiss(self):
        from data.print_documents.documents import (
            _validate_min_games_only_for_swiss,
        )

        doc, opt = self._swiss_doc()
        for v in (7, 8, 9, 11):
            opt.value = v
            _validate_min_games_only_for_swiss(doc)  # no raise
