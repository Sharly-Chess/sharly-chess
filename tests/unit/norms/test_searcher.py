"""Tests for the 1.4.1e/f subset searcher.

The searcher's hard edges live in two places, tested individually:

  * `NormInputs.without_rounds` — pure data manipulation (no Tournament).
  * `TitleNormSubsetSearcher._droppable_rounds` / `_candidates` —
    candidate generation. Tested against a faked-evaluator setup so we
    can drive the search without building a full tournament.

Then end-to-end scenarios exercise `_search_one` with a fake evaluator
that returns is_met for specific subsets, verifying:

  * Smallest winning subset is returned.
  * 1.4.2c interacts correctly with the search (forfeit-as-loss search).
  * Search exits early when an earlier (smaller) subset already won.
  * When nothing wins, the baseline (full game set) result is returned.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

from utils.enum import PlayerGender

import pytest

from data.norms import (
    NormInputs,
    TitleNormEvaluator,
    TitleNormSubsetSearcher,
)
from utils.enum import PlayerRatingType, PlayerTitle, Result, TitleNorm
from utils.types import Federation, NormCheckResult


# ---------------------------------------------------------------------------
# Test fixtures — fake opponents and inputs without a real Tournament
# ---------------------------------------------------------------------------


@dataclass
class FakeOpponent:
    """Duck-typed stand-in for `TournamentPlayer`. The norm code only
    reads `id`, `rating`, `rating_type`, `federation`, `title` on opponents.
    """

    id: int
    rating: int
    rating_type: PlayerRatingType = PlayerRatingType.FIDE
    federation: Federation = Federation('FRA')
    title: PlayerTitle = PlayerTitle.NONE


def make_inputs(
    rounds_data: list[tuple[int, FakeOpponent, Result]],
    *,
    forfeits_or_byes: int = 0,
    has_last_round_forfeit_against: bool = False,
) -> NormInputs:
    """Build a NormInputs directly from per-round data, bypassing
    `collect_inputs`. Used by tests to construct precise subset scenarios."""
    feds: Counter[Federation] = Counter()
    titles: Counter[PlayerTitle] = Counter()
    opponents: list = []
    results: list[Result] = []
    included: list[int] = []
    for rnd, opp, res in rounds_data:
        opponents.append(opp)
        results.append(res)
        included.append(rnd)
        feds[opp.federation] += 1
        if opp.title in TitleNorm.TITLE_HOLDERS:
            titles[opp.title] += 1
    return NormInputs(
        played_games=len(rounds_data),
        federations_counter=feds,
        titles_counter=titles,
        opponents=opponents,
        results_list=results,
        included_rounds=included,
        forfeits_or_byes=forfeits_or_byes,
        ignored_opponents_ids=set(),
        score=sum(r.points() for r in results),
        has_last_round_forfeit_against=has_last_round_forfeit_against,
    )


# ---------------------------------------------------------------------------
# NormInputs.without_rounds — pure data manipulation
# ---------------------------------------------------------------------------


class TestWithoutRounds:
    def _build(self) -> NormInputs:
        gm = FakeOpponent(
            1, 2500, federation=Federation('USA'), title=PlayerTitle.GRANDMASTER
        )
        im = FakeOpponent(
            2,
            2400,
            federation=Federation('GER'),
            title=PlayerTitle.INTERNATIONAL_MASTER,
        )
        weak = FakeOpponent(3, 1900, federation=Federation('FRA'))
        return make_inputs(
            [
                (1, gm, Result.DRAW),
                (2, im, Result.WIN),
                (3, weak, Result.WIN),
            ]
        )

    def test_empty_drop_returns_same_instance(self):
        inputs = self._build()
        assert inputs.without_rounds(frozenset()) is inputs

    def test_drop_one_round_filters_counters(self):
        inputs = self._build()
        filtered = inputs.without_rounds(frozenset([3]))
        assert filtered.played_games == 2
        assert filtered.included_rounds == [1, 2]
        assert filtered.federations_counter == Counter(
            {Federation('USA'): 1, Federation('GER'): 1}
        )
        assert filtered.titles_counter == Counter(
            {PlayerTitle.GRANDMASTER: 1, PlayerTitle.INTERNATIONAL_MASTER: 1}
        )

    def test_drop_recomputes_score(self):
        # Original score: 0.5 + 1 + 1 = 2.5
        # After dropping round 3 (a WIN): 0.5 + 1 = 1.5
        inputs = self._build()
        filtered = inputs.without_rounds(frozenset([3]))
        assert filtered.score == pytest.approx(1.5)

    def test_drop_preserves_unaffected_metadata(self):
        inputs = NormInputs(
            forfeits_or_byes=1,
            has_last_round_forfeit_against=True,
            ignored_opponents_ids={42},
        )
        # Add a round manually to drop.
        opp = FakeOpponent(1, 2500)
        inputs.opponents.append(opp)
        inputs.results_list.append(Result.WIN)
        inputs.included_rounds.append(1)
        inputs.played_games = 1
        inputs.score = 1.0
        inputs.federations_counter[opp.federation] = 1

        filtered = inputs.without_rounds(frozenset([1]))
        # These describe the ORIGINAL pairings; they don't change with drops.
        assert filtered.forfeits_or_byes == 1
        assert filtered.has_last_round_forfeit_against is True
        assert filtered.ignored_opponents_ids == {42}

    def test_drop_multiple_rounds(self):
        inputs = self._build()
        filtered = inputs.without_rounds(frozenset([1, 3]))
        assert filtered.played_games == 1
        assert filtered.included_rounds == [2]
        assert filtered.score == pytest.approx(1.0)

    def test_drop_nonexistent_round_is_noop(self):
        inputs = self._build()
        filtered = inputs.without_rounds(frozenset([99]))
        assert filtered.played_games == 3
        assert filtered.included_rounds == [1, 2, 3]
        assert filtered.score == inputs.score

    def test_drop_returns_new_object_not_mutating_original(self):
        inputs = self._build()
        inputs.without_rounds(frozenset([3]))
        assert inputs.played_games == 3  # unchanged


# ---------------------------------------------------------------------------
# Candidate generation — _droppable_rounds and _candidates
# ---------------------------------------------------------------------------
# These need a TitleNormSubsetSearcher instance, but we only exercise its
# pure helpers — so a MagicMock for `player` suffices.


def _make_searcher(
    *,
    rounds: int,
    pairing_system=None,
    pairing_variation=None,
) -> TitleNormSubsetSearcher:
    from data.pairings.systems import SwissPairingSystem

    player = MagicMock()
    player.tournament.rounds = rounds
    player.tournament.pairing_system = pairing_system or SwissPairingSystem()
    player.tournament.pairing_variation = pairing_variation
    return TitleNormSubsetSearcher(player)


class TestDroppableRounds:
    def test_only_wins_droppable_in_round_robin(self):
        from data.pairings.systems import RoundRobinPairingSystem

        opps = [FakeOpponent(i, 2400) for i in range(1, 11)]
        rounds_data = [
            (1, opps[0], Result.WIN),
            (2, opps[1], Result.DRAW),
            (3, opps[2], Result.WIN),
            (4, opps[3], Result.LOSS),
            (5, opps[4], Result.WIN),
            (6, opps[5], Result.WIN),
            (7, opps[6], Result.DRAW),
            (8, opps[7], Result.WIN),
            (9, opps[8], Result.LOSS),
            (10, opps[9], Result.WIN),
        ]
        inputs = make_inputs(rounds_data)
        searcher = _make_searcher(rounds=10, pairing_system=RoundRobinPairingSystem())
        # RR — only 1.4.1f applies. All wins droppable, regardless of position.
        droppable = searcher._droppable_rounds(inputs)
        assert droppable == {1, 3, 5, 6, 8, 10}

    def test_wins_and_tail_rounds_droppable_in_swiss(self):
        opps = [FakeOpponent(i, 2400) for i in range(1, 12)]
        rounds_data = [
            (1, opps[0], Result.WIN),
            (2, opps[1], Result.DRAW),
            (3, opps[2], Result.WIN),
            (4, opps[3], Result.LOSS),
            (5, opps[4], Result.LOSS),
            (6, opps[5], Result.WIN),
            (7, opps[6], Result.DRAW),
            (8, opps[7], Result.WIN),
            (9, opps[8], Result.LOSS),  # tail
            (10, opps[9], Result.DRAW),  # tail
            (11, opps[10], Result.WIN),  # tail (also a win)
        ]
        inputs = make_inputs(rounds_data)
        searcher = _make_searcher(rounds=11)
        droppable = searcher._droppable_rounds(inputs)
        # Wins: {1, 3, 6, 8, 11}
        # Tail (last 2, since max_ignores = 11-9 = 2): {10, 11}
        # Union: {1, 3, 6, 8, 10, 11}
        assert droppable == {1, 3, 6, 8, 10, 11}

    def test_no_ignores_available_in_9_round_swiss(self):
        # max_ignores = 0 — tail-window empty, only wins droppable per 1.4.1f
        # but 1.4.1f also requires headroom (max_ignores > 0). The droppable
        # set still surfaces wins, but the search will refuse to enumerate.
        opps = [FakeOpponent(i, 2400) for i in range(1, 10)]
        rounds_data = [(r, opps[r - 1], Result.WIN) for r in range(1, 10)]
        inputs = make_inputs(rounds_data)
        searcher = _make_searcher(rounds=9)
        # All rounds are wins → droppable includes them, but search exits
        # because max_ignores == 0.
        droppable = searcher._droppable_rounds(inputs)
        assert all(r in droppable for r in range(1, 10))
        candidates = list(searcher._candidates(droppable, max_ignores=0, inputs=inputs))
        assert candidates == []

    def test_unrated_win_counts_as_win_for_1_4_1f(self):
        opps = [FakeOpponent(i, 2400) for i in range(1, 5)]
        rounds_data = [
            (1, opps[0], Result.UNRATED_WIN),
            (2, opps[1], Result.WIN),
            (3, opps[2], Result.LOSS),
            (4, opps[3], Result.DRAW),
        ]
        inputs = make_inputs(rounds_data)
        searcher = _make_searcher(rounds=10)
        droppable = searcher._droppable_rounds(inputs)
        assert 1 in droppable  # UNRATED_WIN counted
        assert 2 in droppable  # WIN counted


class TestCandidateOrdering:
    def test_smaller_subsets_yielded_first(self):
        opps = [
            FakeOpponent(1, 2400),
            FakeOpponent(2, 2400),
            FakeOpponent(3, 2400),
        ]
        inputs = make_inputs([(r, opps[r - 1], Result.WIN) for r in (1, 2, 3)])
        searcher = _make_searcher(rounds=10)
        # max_ignores = 1 — only size-1 subsets.
        size1 = list(searcher._candidates({1, 2, 3}, max_ignores=1, inputs=inputs))
        assert all(len(c) == 1 for c in size1)
        assert len(size1) == 3

    def test_within_size_class_lowest_rating_sum_first(self):
        opps = [
            FakeOpponent(1, 2500),  # high
            FakeOpponent(2, 2000),  # low
            FakeOpponent(3, 2300),  # medium
        ]
        inputs = make_inputs([(r, opps[r - 1], Result.WIN) for r in (1, 2, 3)])
        searcher = _make_searcher(rounds=10)
        candidates = list(searcher._candidates({1, 2, 3}, max_ignores=1, inputs=inputs))
        # Drop round 2 (lowest) first.
        assert candidates[0] == frozenset({2})
        # Then round 3, then round 1.
        assert candidates[1] == frozenset({3})
        assert candidates[2] == frozenset({1})

    def test_size_2_candidates_after_size_1(self):
        opps = [FakeOpponent(i, 2400) for i in range(1, 4)]
        inputs = make_inputs([(r, opps[r - 1], Result.WIN) for r in (1, 2, 3)])
        searcher = _make_searcher(rounds=11)  # max_ignores = 2
        candidates = list(searcher._candidates({1, 2, 3}, max_ignores=2, inputs=inputs))
        # First 3 are size-1, next 3 are size-2.
        assert all(len(c) == 1 for c in candidates[:3])
        assert all(len(c) == 2 for c in candidates[3:])
        assert len(candidates) == 6

    def test_unrated_opponents_default_to_1400_in_score(self):
        # The drop-score heuristic should treat non-FIDE-rated opponents
        # as 1400 (the 1.4.6 floor for unrated).
        rated_high = FakeOpponent(1, 2500, rating_type=PlayerRatingType.FIDE)
        unrated = FakeOpponent(2, 1800, rating_type=PlayerRatingType.NATIONAL)
        inputs = make_inputs(
            [
                (1, rated_high, Result.WIN),
                (2, unrated, Result.WIN),
            ]
        )
        searcher = _make_searcher(rounds=10)
        candidates = list(searcher._candidates({1, 2}, max_ignores=1, inputs=inputs))
        # unrated (1400 effective) should sort BEFORE rated_high (2500).
        assert candidates[0] == frozenset({2})


# ---------------------------------------------------------------------------
# End-to-end search behaviour via a stubbed TitleNormEvaluator
# ---------------------------------------------------------------------------


def _make_result(meets: bool = False, **flags) -> NormCheckResult:
    """Build a NormCheckResult. By default everything passes (meets=True)."""
    res = NormCheckResult(title_norm=TitleNorm.GM, meets_gender=True)
    if not meets:
        # Set a generic failing flag so is_met is False but no monotonic
        # constraint is triggered (caller can override).
        res.performance_too_low = 'fail'
    for name, value in flags.items():
        setattr(res, name, value)
    return res


class TestSearchOne:
    """Drive `_search_one` with a stubbed evaluator. The evaluator's
    `evaluate_one` is a callable that decides per-call whether the
    inputs satisfy the norm."""

    @pytest.fixture
    def searcher(self):
        s = _make_searcher(rounds=11)
        return s

    def test_baseline_passes_no_search(self, searcher):
        baseline = make_inputs([])
        searcher.evaluator = MagicMock(spec=TitleNormEvaluator)
        searcher.evaluator.evaluate_one.return_value = _make_result(meets=True)
        result = searcher._search_one(baseline, None, TitleNorm.GM, True)
        assert result.is_met
        # No search needed → evaluator called exactly once.
        assert searcher.evaluator.evaluate_one.call_count == 1

    def test_142c_path_taken_when_baseline_fails(self, searcher):
        baseline = make_inputs([], has_last_round_forfeit_against=True)
        baseline_142c = make_inputs([], has_last_round_forfeit_against=True)
        searcher.evaluator = MagicMock(spec=TitleNormEvaluator)
        searcher.evaluator.evaluate_one.side_effect = [
            _make_result(meets=False),  # baseline fails
            _make_result(meets=True),  # 1.4.2c interpretation passes
        ]
        result = searcher._search_one(baseline, baseline_142c, TitleNorm.GM, True)
        assert result.is_met
        assert result.applied_142c is True

    def test_returns_baseline_when_nothing_helps(self, searcher):
        baseline = make_inputs([])
        searcher.evaluator = MagicMock(spec=TitleNormEvaluator)
        # Every evaluation fails non-monotonically.
        searcher.evaluator.evaluate_one.return_value = _make_result(meets=False)
        result = searcher._search_one(baseline, None, TitleNorm.GM, True)
        # No search winner found → returns baseline failure for diagnostics.
        assert not result.is_met
        assert result.performance_too_low == 'fail'

    def test_search_skips_when_max_ignores_zero(self, searcher):
        # 9-round Swiss against a 9-min norm has no headroom — search exits.
        baseline = make_inputs([])
        searcher.player.tournament.rounds = 9
        searcher.evaluator = MagicMock(spec=TitleNormEvaluator)
        searcher.evaluator.evaluate_one.return_value = _make_result(meets=False)
        result = searcher._search_one(baseline, None, TitleNorm.GM, True)
        assert not result.is_met
        # One call: only the baseline. No subset attempted.
        assert searcher.evaluator.evaluate_one.call_count == 1


class TestSearchSubsets:
    """`_search_subsets` is the inner loop. Drive it with a stub evaluator
    that decides per-call based on the subset shape."""

    def test_finds_smallest_winning_subset(self):
        # 11-round Swiss, 5 wins. Set up so dropping round 5 makes the norm pass.
        opps = [FakeOpponent(i, 2000 + i * 50) for i in range(1, 12)]
        rounds_data = [
            (r, opps[r - 1], Result.WIN if r in {1, 3, 5, 7, 9} else Result.DRAW)
            for r in range(1, 12)
        ]
        inputs = make_inputs(rounds_data)
        searcher = _make_searcher(rounds=11)

        # Stub: pass when dropping exactly round 5 (the smallest winning subset).
        def stub_evaluate_one(inp, tn, gender):
            dropped = set(range(1, 12)) - set(inp.included_rounds)
            if dropped == {5}:
                return _make_result(meets=True)
            return _make_result(meets=False)

        searcher.evaluator = MagicMock(spec=TitleNormEvaluator)
        searcher.evaluator.evaluate_one.side_effect = stub_evaluate_one
        result = searcher._search_subsets(inputs, TitleNorm.GM, True)
        assert result is not None
        assert result.is_met
        assert result.ignored_rounds_via_search == frozenset({5})

    def test_returns_none_when_no_subset_wins(self):
        opps = [FakeOpponent(i, 2400) for i in range(1, 12)]
        rounds_data = [(r, opps[r - 1], Result.WIN) for r in range(1, 12)]
        inputs = make_inputs(rounds_data)
        searcher = _make_searcher(rounds=11)

        searcher.evaluator = MagicMock(spec=TitleNormEvaluator)
        searcher.evaluator.evaluate_one.return_value = _make_result(meets=False)
        result = searcher._search_subsets(inputs, TitleNorm.GM, True)
        assert result is None

    def test_max_ignores_zero_returns_none(self):
        # 9-round Swiss → no headroom for any drops.
        opps = [FakeOpponent(i, 2400) for i in range(1, 10)]
        rounds_data = [(r, opps[r - 1], Result.WIN) for r in range(1, 10)]
        inputs = make_inputs(rounds_data)
        searcher = _make_searcher(rounds=9)
        searcher.evaluator = MagicMock(spec=TitleNormEvaluator)
        result = searcher._search_subsets(inputs, TitleNorm.GM, True)
        assert result is None
        # Evaluator never invoked.
        assert searcher.evaluator.evaluate_one.call_count == 0

    def test_no_droppable_rounds_returns_none(self):
        # RR with no wins → 1.4.1f has nothing, 1.4.1e doesn't apply.
        from data.pairings.systems import RoundRobinPairingSystem

        opps = [FakeOpponent(i, 2400) for i in range(1, 11)]
        rounds_data = [(r, opps[r - 1], Result.DRAW) for r in range(1, 11)]
        inputs = make_inputs(rounds_data)
        searcher = _make_searcher(rounds=10, pairing_system=RoundRobinPairingSystem())
        searcher.evaluator = MagicMock(spec=TitleNormEvaluator)
        result = searcher._search_subsets(inputs, TitleNorm.GM, True)
        assert result is None
        assert searcher.evaluator.evaluate_one.call_count == 0


class TestSearchEndToEnd:
    """Integration-style: the whole `_search_one` flow with a real
    `TitleNormEvaluator` would need a real Tournament. Instead we stub
    the evaluator's `evaluate_one` while still exercising every code path
    (fast paths + slow path + 1.4.2c interaction)."""

    def test_142c_search_path_marks_applied(self):
        # Neither baseline nor 1.4.2c-at-full passes; A-subsets all fail;
        # a B-subset passes → result must have applied_142c=True.
        # We mark A and B with distinct `forfeits_or_byes` values so the
        # stub can tell them (and their subsets, via without_rounds-preserved
        # metadata) apart.
        opps = [FakeOpponent(i, 2400) for i in range(1, 12)]
        rounds_data = [
            (r, opps[r - 1], Result.WIN if r % 2 else Result.DRAW) for r in range(1, 12)
        ]
        baseline = make_inputs(
            rounds_data,
            forfeits_or_byes=11,  # A-marker
            has_last_round_forfeit_against=True,
        )
        baseline_142c = make_inputs(
            rounds_data,
            forfeits_or_byes=22,  # B-marker
            has_last_round_forfeit_against=True,
        )
        searcher = _make_searcher(rounds=11)

        def stub_evaluate_one(inp, tn, gender):
            # A and all its subsets fail. B itself fails. B-subsets pass.
            if inp.forfeits_or_byes == 11:
                return _make_result(meets=False)
            # B-side. Full set fails; any drop wins.
            if inp.played_games == 11:
                return _make_result(meets=False)
            return _make_result(meets=True)

        searcher.evaluator = MagicMock(spec=TitleNormEvaluator)
        searcher.evaluator.evaluate_one.side_effect = stub_evaluate_one
        result = searcher._search_one(baseline, baseline_142c, TitleNorm.GM, True)
        assert result.is_met
        assert result.applied_142c is True
        assert len(result.ignored_rounds_via_search) >= 1

    def test_a_search_path_does_not_mark_142c(self):
        # Sister case: A-subset passes → applied_142c must stay False.
        opps = [FakeOpponent(i, 2400) for i in range(1, 12)]
        rounds_data = [
            (r, opps[r - 1], Result.WIN if r % 2 else Result.DRAW) for r in range(1, 12)
        ]
        baseline = make_inputs(rounds_data, forfeits_or_byes=11)
        searcher = _make_searcher(rounds=11)

        def stub_evaluate_one(inp, tn, gender):
            if inp.played_games == 11:
                return _make_result(meets=False)
            return _make_result(meets=True)  # any subset wins

        searcher.evaluator = MagicMock(spec=TitleNormEvaluator)
        searcher.evaluator.evaluate_one.side_effect = stub_evaluate_one
        result = searcher._search_one(baseline, None, TitleNorm.GM, True)
        assert result.is_met
        assert result.applied_142c is False


# ---------------------------------------------------------------------------
# Integration tests — searcher driven by the REAL TitleNormEvaluator
# ---------------------------------------------------------------------------
#
# Up to here, tests stub `searcher.evaluator.evaluate_one` so the search
# algorithm can be probed in isolation. These tests use the real evaluator
# with synthesised inputs to verify that the algorithm + the actual per-rule
# checks produce correct verdicts. Tournament/Player/Event are duck-typed
# via SimpleNamespace to avoid building a full SQLite-backed tournament.


def _real_searcher(
    *,
    rounds: int = 11,
    federation: str = 'FRA',
    gender: PlayerGender = PlayerGender.MAN,
    pairing_system=None,
    rule_143_exemption: str = 'none',
) -> TitleNormSubsetSearcher:
    from data.pairings.systems import SwissPairingSystem
    from utils.types import BigTournamentExemption

    player = SimpleNamespace(
        federation=Federation(federation),
        gender=gender,
        event=SimpleNamespace(federation=federation),
        tournament=SimpleNamespace(
            rounds=rounds,
            pairing_system=pairing_system or SwissPairingSystem(),
            pairing_variation=None,
            # Stubs for the tournament-wide checks that `evaluate_one`
            # stamps onto every NormCheckResult. Default to "not met"
            # so tests don't inadvertently get the 1.4.3d exemption.
            big_tournament_exemption=BigTournamentExemption(0, 0, 0),
            high_level_tournament=False,
        ),
    )
    return TitleNormSubsetSearcher(player, rule_143_exemption=rule_143_exemption)


def _gm(id_: int, rating: int = 2400, federation: str = 'USA') -> FakeOpponent:
    return FakeOpponent(
        id_,
        rating,
        rating_type=PlayerRatingType.FIDE,
        federation=Federation(federation),
        title=PlayerTitle.GRANDMASTER,
    )


def _im(id_: int, rating: int = 2300, federation: str = 'GER') -> FakeOpponent:
    return FakeOpponent(
        id_,
        rating,
        rating_type=PlayerRatingType.FIDE,
        federation=Federation(federation),
        title=PlayerTitle.INTERNATIONAL_MASTER,
    )


def _untitled(id_: int, rating: int = 2000, federation: str = 'FRA') -> FakeOpponent:
    return FakeOpponent(
        id_,
        rating,
        rating_type=PlayerRatingType.FIDE,
        federation=Federation(federation),
        title=PlayerTitle.NONE,
    )


class TestSearcherWithRealEvaluator:
    """Drives `_search_one` with the real `TitleNormEvaluator`, against
    synthesised NormInputs that exercise specific GM-norm scenarios."""

    def test_gm_norm_easily_achieved_no_search_needed(self):
        # 11 GMs at 2400 (avg = 2400, well above 2380). Player scores
        # 8.5/11 = 77.3% → dp ≈ 211 → Rp ≈ 2611 → meets GM threshold.
        # Federations chosen to give a strong, varied mix.
        opponents = [
            _gm(1, federation='USA'),
            _gm(2, federation='GER'),
            _gm(3, federation='ESP'),
            _gm(4, federation='ITA'),
            _gm(5, federation='NED'),
            _gm(6, federation='POL'),
            _gm(7, federation='RUS'),
            _gm(8, federation='AZE'),
            _gm(9, federation='IND'),
            _gm(10, federation='CHN'),
            _gm(11, federation='BRA'),
        ]
        # 7 wins + 3 draws + 1 loss = 8.5 / 11.
        results = [
            Result.WIN,
            Result.WIN,
            Result.WIN,
            Result.WIN,
            Result.WIN,
            Result.WIN,
            Result.WIN,
            Result.DRAW,
            Result.DRAW,
            Result.DRAW,
            Result.LOSS,
        ]
        inputs = make_inputs(list(zip(range(1, 12), opponents, results)))
        searcher = _real_searcher(rounds=11)
        result = searcher._search_one(inputs, None, TitleNorm.GM, meets_gender=True)
        assert result.is_met, (
            f'Expected GM norm met. Diagnostics: '
            f'Ra={result.average_rating}, Rp={result.performance}, '
            f'score={result.score}/11, num_titled={result.num_title_holders}'
        )
        assert result.ignored_rounds_via_search == frozenset()

    def test_gm_norm_rescued_by_dropping_tail_loss(self):
        # 11-round Swiss with mix engineered so baseline Rp falls just
        # short of 2600 but dropping a tail loss pushes it over.
        #
        # 4 GMs (2500) + 7 IMs (2350). Avg = (10000 + 16450) / 11 = 2404.
        # GM requires Ra ≥ 2380 ✓. GM required-titles ≥ 3 ✓ (4 GMs).
        # Player scores 7 wins + 2 draws + 2 losses = 8.0 pts.
        # Baseline fractional = 8/11 = 0.727 → dp ≈ 175 → Rp = 2579 (< 2600).
        # Drop a tail LOSS: 8/10 = 0.80 → dp = 240. Ra over 10 opponents
        # rises slightly. Rp ≈ 2640 → ≥ 2600 ✓.
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
        opponents = [
            _gm(1, rating=2500, federation=feds[0]),
            _gm(2, rating=2500, federation=feds[1]),
            _gm(3, rating=2500, federation=feds[2]),
            _gm(4, rating=2500, federation=feds[3]),
            _im(5, rating=2350, federation=feds[4]),
            _im(6, rating=2350, federation=feds[5]),
            _im(7, rating=2350, federation=feds[6]),
            _im(8, rating=2350, federation=feds[7]),
            _im(9, rating=2350, federation=feds[8]),
            _im(10, rating=2350, federation=feds[9]),
            _im(11, rating=2350, federation=feds[10]),
        ]
        results = [Result.WIN] * 7 + [Result.DRAW] * 2 + [Result.LOSS] * 2
        inputs = make_inputs(list(zip(range(1, 12), opponents, results)))
        searcher = _real_searcher(rounds=11)
        baseline = searcher.evaluator.evaluate_one(
            inputs, TitleNorm.GM, meets_gender=True
        )
        assert not baseline.is_met, (
            f'Baseline was supposed to fail; check fixture. '
            f'Rp={baseline.performance}, score={baseline.score}, '
            f'avg={baseline.average_rating}'
        )
        # The losses are R10 and R11 (last two); the search prefers
        # the lower-rated drop, both IMs at 2350 → first found in iteration order.
        result = searcher._search_one(inputs, None, TitleNorm.GM, meets_gender=True)
        assert result.is_met, (
            f'Expected search to find a winning subset. '
            f'Rp={result.performance}, score={result.score}, '
            f'avg={result.average_rating}, '
            f'ignored={result.ignored_rounds_via_search}'
        )
        # Either R10 or R11 alone is a winning size-1 subset (both are
        # equivalent tail-loss drops).
        assert result.ignored_rounds_via_search in (frozenset({10}), frozenset({11}))

    def test_search_applies_143abc_exemption_to_dropped_subset(self):
        # Regression: a norm reachable only by (drop a round) AND (the
        # 1.4.3a/b/c exemption) TOGETHER must be found. All 11 opponents
        # share the applicant's federation (FRA) — so 1.4.3 / 1.4.4 fail —
        # and the baseline Rp (2580) is below the GM 2600 line. Dropping a
        # tail loss lifts Rp over 2600; the exemption waives the federation
        # caps. The search must apply the exemption to each candidate, or
        # it rejects the rescuing subset (federations still failing) and
        # returns the baseline → false negative.
        opponents = [_gm(i, rating=2500, federation='FRA') for i in range(1, 5)] + [
            _im(i, rating=2350, federation='FRA') for i in range(5, 12)
        ]
        results = [Result.WIN] * 7 + [Result.DRAW] * 2 + [Result.LOSS] * 2
        inputs = make_inputs(list(zip(range(1, 12), opponents, results)))

        # Without the exemption: the dropped-tail subset clears performance
        # but still fails the all-FRA federation caps → not met, no drop.
        no_exempt = _real_searcher(rounds=11, rule_143_exemption='none')
        blind = no_exempt._search_one(inputs, None, TitleNorm.GM, meets_gender=True)
        assert not blind.is_met
        assert blind.ignored_rounds_via_search == frozenset()

        # With 1.4.3c (applies to every player): the search waives the
        # federation caps on each candidate, so dropping a tail loss is a
        # winning subset.
        exempt = _real_searcher(rounds=11, rule_143_exemption='1.4.3c')
        found = exempt._search_one(inputs, None, TitleNorm.GM, meets_gender=True)
        assert found.is_met, (
            f'Exemption should let the search find the dropped subset. '
            f'Rp={found.performance}, ignored={found.ignored_rounds_via_search}'
        )
        assert found.rule_143_exemption == 'c'
        assert found.ignored_rounds_via_search in (frozenset({10}), frozenset({11}))

    def test_search_exemption_scoped_to_event_federation(self):
        # 1.4.3a/b apply only to the registering federation's players. A
        # foreign applicant (USA) in an FRA-registered event gets no
        # exemption, so the all-foreign-cap failure still blocks the
        # dropped subset → not met.
        opponents = [_gm(i, rating=2500, federation='FRA') for i in range(1, 5)] + [
            _im(i, rating=2350, federation='FRA') for i in range(5, 12)
        ]
        results = [Result.WIN] * 7 + [Result.DRAW] * 2 + [Result.LOSS] * 2
        inputs = make_inputs(list(zip(range(1, 12), opponents, results)))
        # Applicant USA, event FRA → 1.4.3b does not apply.
        searcher = _real_searcher(
            rounds=11, federation='USA', rule_143_exemption='1.4.3b'
        )
        searcher.player.event.federation = 'FRA'
        # Re-resolve the exemption against the FRA event federation.
        from data.norms.tournament_checks import resolve_143abc_code

        searcher._exemption_code = resolve_143abc_code(
            '1.4.3b', searcher.player.federation, Federation('FRA')
        )
        result = searcher._search_one(inputs, None, TitleNorm.GM, meets_gender=True)
        assert searcher._exemption_code is None
        assert not result.is_met

    def test_gm_norm_unachievable_returns_baseline_failure(self):
        # 11-round Swiss where the player has too few wins to recover even
        # after dropping rounds. Mix is poor (low average, weak opponents).
        opponents = [_untitled(i, rating=1900, federation='FRA') for i in range(1, 12)]
        # Player from FRA → all opponents own-fed → 1.4.3 fails (no foreign
        # feds) AND 1.4.4 fails (own count = 11 > floor(3*11/5)=6).
        # Also avg = 1900 < 2380 → Ra fails. No subset can recover.
        results = [Result.WIN] * 11
        inputs = make_inputs(list(zip(range(1, 12), opponents, results)))
        searcher = _real_searcher(rounds=11)
        result = searcher._search_one(inputs, None, TitleNorm.GM, meets_gender=True)
        assert not result.is_met
        # Baseline diagnostics preserved.
        assert result.not_enough_federations is not None
        # No winning subset.
        assert result.ignored_rounds_via_search == frozenset()

    def test_drr_no_search_runs(self):
        # 10-round DRR (tournament.rounds == minimum_rounds → max_ignores=0).
        # Even if the norm fails, no subset search is attempted.
        from data.pairings.variations import DoubleBergerRoundRobinVariation
        from data.pairings.systems import RoundRobinPairingSystem

        results = [Result.WIN] * 10
        searcher = _real_searcher(rounds=10, pairing_system=RoundRobinPairingSystem())
        searcher.player.tournament.pairing_variation = DoubleBergerRoundRobinVariation()
        # Engineer a baseline that fails 1.4.4 (all-own-fed) so we can
        # observe that the search does NOT run despite the failure.
        own_fed_opponents = [
            _im(i, rating=2300, federation='FRA') for i in range(1, 11)
        ]
        inputs = make_inputs(list(zip(range(1, 11), own_fed_opponents, results)))
        result = searcher._search_one(inputs, None, TitleNorm.GM, meets_gender=True)
        assert not result.is_met  # all-own-fed fails
        # Searcher returned without dropping anything.
        assert result.ignored_rounds_via_search == frozenset()

    def test_9_round_swiss_no_search_runs(self):
        # 9-round Swiss = exactly min_games. max_ignores=0. No search.
        # 9 GMs at 2400, varied federations so 1.4.3/1.4.4 pass.
        feds = ['USA', 'GER', 'ESP', 'ITA', 'NED', 'POL', 'RUS', 'AZE', 'IND']
        opponents = [_gm(i, rating=2400, federation=feds[i - 1]) for i in range(1, 10)]
        # 8 wins + 1 draw = 8.5 → 0.944 → dp = 444 → Rp = 2844 ✓.
        results = [Result.WIN] * 8 + [Result.DRAW]
        inputs = make_inputs(list(zip(range(1, 10), opponents, results)))
        searcher = _real_searcher(rounds=9)
        result = searcher._search_one(inputs, None, TitleNorm.GM, meets_gender=True)
        assert result.is_met
        assert result.ignored_rounds_via_search == frozenset()

    def test_wim_norm_fails_for_male_applicant(self):
        # WIM is a women's-only title; meets_gender=False short-circuits the
        # is_met check regardless of opponent mix. The searcher still runs
        # (it doesn't peek at meets_gender) but no result it returns will
        # mark is_met=True.
        opponents = [_im(i, rating=2200) for i in range(1, 12)]
        results = [Result.WIN] * 8 + [Result.DRAW] * 3
        inputs = make_inputs(list(zip(range(1, 12), opponents, results)))
        searcher = _real_searcher(rounds=11)
        result = searcher._search_one(inputs, None, TitleNorm.WIM, meets_gender=False)
        assert not result.is_met
        # meets_gender is False → preserved on the result.
        assert result.meets_gender is False

    def test_search_actually_uses_real_perf_calc(self):
        # Sanity: with the real evaluator wired up, the searcher's chosen
        # subset has a real Rp value computable independently.
        # 11 GMs at 2400, varied federations, 9 wins + 2 losses.
        # Score 9/11 = 0.818 → dp = 240 → Rp = 2640 → baseline passes.
        from utils import Utils

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
        opponents = [_gm(i, rating=2400, federation=feds[i - 1]) for i in range(1, 12)]
        results = [Result.WIN] * 9 + [Result.LOSS] * 2
        inputs = make_inputs(list(zip(range(1, 12), opponents, results)))
        searcher = _real_searcher(rounds=11)
        result = searcher._search_one(inputs, None, TitleNorm.GM, meets_gender=True)
        assert result.is_met
        # Independent Rp computation.
        avg = Utils.round_ranking(sum(o.rating for o in opponents) / 11)
        dp = Utils.performance_bonus(Utils.round_ranking(100 * 9 / 11) / 100)
        assert result.performance == avg + dp


class TestSearcherWholeEvaluate:
    """Smoke-test the full `evaluate()` pipeline. Stubs the tournament-side
    cached_properties because building a real Tournament is heavy."""

    def test_evaluate_runs_all_four_norms(self):
        from utils.types import BigTournamentExemption

        # Tiny baseline scenario where GM fails but IM/WGM/WIM may or may not pass.
        opponents = [_im(i, rating=2300) for i in range(1, 12)]
        results = [Result.WIN] * 8 + [Result.DRAW] * 3
        inputs = make_inputs(list(zip(range(1, 12), opponents, results)))

        searcher = _real_searcher(rounds=11)
        # Patch the tournament-wide cached values.
        searcher.player.tournament.big_tournament_exemption = BigTournamentExemption(
            0, 0, 0
        )
        searcher.player.tournament.high_level_tournament = False

        # Patch collect_inputs to return our hand-built inputs (twice — for
        # baseline and for the 1.4.2c branch, which is None here).
        searcher.evaluator.collect_inputs = MagicMock(return_value=inputs)
        results_dict = searcher.evaluate()
        assert set(results_dict.keys()) == {
            TitleNorm.GM,
            TitleNorm.IM,
            TitleNorm.WGM,
            TitleNorm.WIM,
        }
        for tn, res in results_dict.items():
            # Every result has tournament-wide flags populated.
            assert res.all_federations_count == 0
            assert res.requirement_156a_met is False
