"""Unit tests for the soft prohibited-pairing relaxation algorithm.

These exercise the pure decision logic (no bbpPairings / no DB): given a
``feasible`` oracle over rank cutoffs, ``resolve_soft_protect_rank`` picks
the largest cutoff ``N`` that still pairs — protecting the top N members
(they keep every soft separation), relaxing only separations where both
members rank below N.
"""

import pytest

from data.prohibited_pairings import (
    expand_groups_to_pairs,
    resolve_soft_protect_rank,
)


# Candidate cutoffs are the distinct standing ranks of the members that
# appear in soft groups (1 = top of the table).
THRESHOLDS = [1, 2, 3, 4, 5]


@pytest.mark.unit
class TestResolveSoftProtectRank:
    def test_no_thresholds(self):
        # No soft members at all → nothing to relax, no cutoff.
        assert resolve_soft_protect_rank([], lambda n: True) == (None, False)

    def test_protect_everyone_when_fully_feasible(self):
        # The whole soft set pairs → protect everyone (the top cutoff).
        protect_rank, hard_infeasible = resolve_soft_protect_rank(
            THRESHOLDS, lambda n: True
        )
        assert protect_rank == 5
        assert hard_infeasible is False

    def test_hard_infeasible_when_protecting_none_still_fails(self):
        # feasible(0) is False → even relaxing all soft separations can't
        # pair → the hard constraints alone are infeasible.
        protect_rank, hard_infeasible = resolve_soft_protect_rank(
            THRESHOLDS, lambda n: False
        )
        assert protect_rank is None
        assert hard_infeasible is True

    def test_largest_feasible_cutoff_protects_strongest(self):
        # Feasible iff at most the top 2 are protected → cutoff 2 (members
        # ranked 1 & 2 keep their separations; 3+ are relaxed).
        protect_rank, hard_infeasible = resolve_soft_protect_rank(
            THRESHOLDS, lambda n: n <= 2
        )
        assert protect_rank == 2
        assert hard_infeasible is False

    def test_protect_none_when_only_empty_feasible(self):
        # Only protecting nobody pairs → cutoff 0 (all soft relaxed), but
        # that is feasible, so not a hard infeasibility.
        protect_rank, hard_infeasible = resolve_soft_protect_rank(
            THRESHOLDS, lambda n: n == 0
        )
        assert protect_rank == 0
        assert hard_infeasible is False

    def test_bisection_calls_are_logarithmic(self):
        calls = {'n': 0}

        def feasible(n):
            calls['n'] += 1
            return n <= 1

        thresholds = list(range(1, 65))
        protect_rank, _ = resolve_soft_protect_rank(thresholds, feasible)
        assert protect_rank == 1  # only the single top member protected
        # 2 boundary probes + ~log2(64) bisection probes, not O(n).
        assert calls['n'] <= 10


@pytest.mark.unit
class TestExpandGroupsToPairs:
    def test_pair_group_is_single_pair(self):
        assert expand_groups_to_pairs([7, 9]) == [frozenset({7, 9})]

    def test_triple_group_expands_to_three_pairs(self):
        pairs = set(expand_groups_to_pairs([1, 2, 3]))
        assert pairs == {frozenset({1, 2}), frozenset({1, 3}), frozenset({2, 3})}

    def test_singleton_has_no_pairs(self):
        assert expand_groups_to_pairs([42]) == []
