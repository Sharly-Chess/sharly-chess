"""Unit tests for the soft prohibited pairings.

These exercise the pure decision logic (no bbpPairings / no DB): given a
``feasible`` oracle over rank cutoffs, ``resolve_soft_protect_rank`` picks
the largest cutoff ``N`` that still pairs — protecting the top N members
(they keep every soft separation), relaxing only separations where both
members rank below N. The lowest-criterion mode hands the soft groups to
bbpPairings whole, as SCS records.
"""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest

from data.prohibited_pairings import (
    ProhibitedPairings,
    expand_groups_to_pairs,
    resolve_soft_protect_rank,
)
from database.sqlite.event.event_store import StoredProhibitedPairingGroup
from plugins.ffe.ffe_rule_sets import (
    ChampionnatFemininN1N2RuleSet,
    CoupeDeLaPariteRuleSet,
    CoupeJeanClaudeLoubatiereRuleSet,
)
from utils.enum import ProhibitedPairingConstraint


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


def _prohibited_pairings(
    groups: list[StoredProhibitedPairingGroup] | None = None,
    rule_set: Any = None,
    dimension_constraint: str = 'HARD',
) -> ProhibitedPairings:
    """Prohibited pairings of an individual tournament whose player ``n``
    has pairing number ``10 + n``."""
    tournament = SimpleNamespace(
        is_team_tournament=False,
        tournament_players_by_id={
            n: SimpleNamespace(pairing_number=10 + n) for n in range(1, 7)
        },
        rule_set=rule_set,
        stored_tournament=SimpleNamespace(
            stored_prohibited_pairing_groups=groups or [],
            prohibited_pairing_dimension='club',
            prohibited_pairing_dimension_constraint=dimension_constraint,
        ),
    )
    return ProhibitedPairings(cast(Any, tournament))


def _manual_group(constraint: ProhibitedPairingConstraint, member_ids: list[int]):
    return StoredProhibitedPairingGroup(
        id=None, tournament_id=1, constraint=constraint.value, member_ids=member_ids
    )


@pytest.mark.unit
class TestConstraints:
    def test_lowest_criterion_groups_become_whole_scs_lines(self):
        lines = _prohibited_pairings().lowest_criterion_lines([[3, 4, 5], [6, 1]], 2)

        assert [(line.pairing_numbers, line.soft) for line in lines] == [
            ([13, 14, 15], True),
            ([16, 11], True),
        ]
        assert all(line.first_round == line.last_round == 2 for line in lines)

    def test_each_group_is_paired_with_its_own_constraint(self):
        prohibited_pairings = _prohibited_pairings(
            [
                _manual_group(ProhibitedPairingConstraint.HARD, [1, 2]),
                _manual_group(ProhibitedPairingConstraint.PROTECT_TOP, [3, 4]),
                _manual_group(ProhibitedPairingConstraint.LOWEST_CRITERION, [5, 6]),
            ],
            dimension_constraint=ProhibitedPairingConstraint.LOWEST_CRITERION.value,
        )
        ranks = {1: 1, 2: 2}
        with (
            patch.object(
                ProhibitedPairings, 'dimension_buckets', return_value=[('A', [1, 3])]
            ),
            patch.object(ProhibitedPairings, 'round_rule_groups', return_value=[]),
            patch.object(
                ProhibitedPairings, 'member_weakness_ranks', return_value=ranks
            ),
        ):
            inputs = prohibited_pairings.relaxation_inputs(after_round=1)

        assert inputs == ([[1, 2]], [[3, 4]], [[1, 3], [5, 6]], ranks)

    def test_no_constraint_turns_the_automatic_groups_off(self):
        prohibited_pairings = _prohibited_pairings(
            dimension_constraint=ProhibitedPairingConstraint.NONE.value
        )
        with patch.object(
            ProhibitedPairings, 'dimension_buckets', return_value=[('A', [1, 3])]
        ):
            assert prohibited_pairings.dimension_groups() == []

    def test_the_ffe_cups_avoid_same_club_teams_as_the_lowest_criterion(self):
        for rule_set in (
            CoupeJeanClaudeLoubatiereRuleSet(),
            CoupeDeLaPariteRuleSet(),
            ChampionnatFemininN1N2RuleSet({'division': 'n2f-zone'}),
        ):
            prohibited_pairings = _prohibited_pairings(rule_set=rule_set)

            assert prohibited_pairings.dimension_id == 'team-group', rule_set
            assert (
                prohibited_pairings.dimension_constraint
                == ProhibitedPairingConstraint.LOWEST_CRITERION
            ), rule_set

    def test_a_division_without_club_avoidance_leaves_the_choice_free(self):
        prohibited_pairings = _prohibited_pairings(
            rule_set=ChampionnatFemininN1N2RuleSet({'division': 'n1f'}),
            dimension_constraint=ProhibitedPairingConstraint.PROTECT_TOP.value,
        )

        assert prohibited_pairings.forced_by_rule_set is None
        assert (
            prohibited_pairings.dimension_constraint
            == ProhibitedPairingConstraint.PROTECT_TOP
        )
