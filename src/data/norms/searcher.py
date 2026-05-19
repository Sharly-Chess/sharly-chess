"""`TitleNormSubsetSearcher` — subset search implementing FIDE 1.4.1e/f."""

from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING, Iterable

from data.norms.evaluator import TitleNormEvaluator, _resolve_min_games
from data.norms.inputs import NormInputs
from utils.enum import PlayerRatingType, Result, TitleNorm
from utils.types import NormCheckResult

if TYPE_CHECKING:
    from data.player import TournamentPlayer


class TitleNormSubsetSearcher:
    """Searches subsets of the applicant's games for one that satisfies
    a norm — implements FIDE 1.4.1e (ignore later games after a title
    result was already achieved) and 1.4.1f (ignore games against
    defeated opponents). Wraps `TitleNormEvaluator` for the per-subset
    norm check.

    Strategy per norm:
      1. Fast path — full game set (no ignores).
      2. 1.4.2c fast path — if a last-round forfeit-against exists, try
         the "include as LOSS" interpretation on the full game set.
      3. Search path — enumerate ignore-subsets (smallest first, most
         promising first within each size) and stop at the first that
         meets the norm.

    When no subset meets the norm, returns the baseline result so the
    arbiter still sees diagnostic flags.
    """

    def __init__(
        self,
        player: 'TournamentPlayer',
        min_games_override: int | None = None,
    ):
        """`min_games_override` is forwarded to the evaluator and used by
        the subset-search to bound `max_ignores`."""
        self.player = player
        self.min_games_override = min_games_override
        self.evaluator = TitleNormEvaluator(
            player, min_games_override=min_games_override
        )

    @property
    def tournament(self):
        return self.player.tournament

    # ---------- top-level orchestration ----------

    def evaluate(
        self,
        result_overrides: dict[int, Result] | None = None,
    ) -> dict[TitleNorm, NormCheckResult]:
        baseline = self.evaluator.collect_inputs(
            include_last_forfeit_as_loss=False,
            result_overrides=result_overrides,
        )
        baseline_142c: NormInputs | None = (
            self.evaluator.collect_inputs(
                include_last_forfeit_as_loss=True,
                result_overrides=result_overrides,
            )
            if baseline.has_last_round_forfeit_against
            else None
        )

        results: dict[TitleNorm, NormCheckResult] = {}
        for tn in TitleNorm.values():
            meets_gender = tn.satisfies_gender_requirement(self.player.gender)
            results[tn] = self._search_one(baseline, baseline_142c, tn, meets_gender)

        return results

    # ---------- per-norm search ----------

    def _search_one(
        self,
        baseline: NormInputs,
        baseline_142c: NormInputs | None,
        tn: TitleNorm,
        meets_gender: bool,
    ) -> NormCheckResult:
        # Fast path 1: full game set.
        baseline_result = self.evaluator.evaluate_one(baseline, tn, meets_gender)
        if baseline_result.is_met:
            return baseline_result

        # Fast path 2: 1.4.2c interpretation on the full set.
        if baseline_142c is not None:
            result_142c = self.evaluator.evaluate_one(baseline_142c, tn, meets_gender)
            if result_142c.is_met:
                result_142c.applied_142c = True
                result_142c.alternate_142c = baseline_result
                return result_142c

        # Search path: 1.4.1e/f over baseline.
        winner = self._search_subsets(baseline, tn, meets_gender)
        if winner is not None:
            return winner

        # Search path also over the 1.4.2c interpretation.
        if baseline_142c is not None:
            winner = self._search_subsets(baseline_142c, tn, meets_gender)
            if winner is not None:
                winner.applied_142c = True
                winner.alternate_142c = baseline_result
                return winner

        return baseline_result  # nothing helped — return the baseline diagnostics

    def _search_subsets(
        self,
        inputs: NormInputs,
        tn: TitleNorm,
        meets_gender: bool,
    ) -> NormCheckResult | None:
        """Try every promising ignore-subset against `inputs`. Returns the
        first NormCheckResult satisfying the norm, or None if none does.
        """
        max_ignores = self._max_ignores(tn)
        if max_ignores <= 0:
            return None
        droppable = self._droppable_rounds(inputs)
        if not droppable:
            return None

        for candidate in self._candidates(droppable, max_ignores, inputs):
            modified = inputs.without_rounds(candidate)
            result = self.evaluator.evaluate_one(modified, tn, meets_gender)
            if result.is_met:
                result.ignored_rounds_via_search = candidate
                # Flip the dropped rounds' audit entries to DROPPED so the
                # IT1 reflects what the search did, not just what
                # collect_inputs produced. `audit_with_dropped` returns a
                # fresh list — entries themselves stay frozen.
                result.round_audit = inputs.audit_with_dropped(candidate)
                return result
        return None

    # ---------- candidate generation ----------

    def _max_ignores(self, tn: TitleNorm) -> int:
        """Maximum number of rounds the applicant may drop while still
        meeting the norm's minimum game count.

        Resolved independently of `self.evaluator` so tests that mock the
        evaluator don't break candidate generation.
        """
        return self.tournament.rounds - _resolve_min_games(
            tn, self.tournament, self.min_games_override
        )

    def _droppable_rounds(self, inputs: NormInputs) -> set[int]:
        """Rounds the spec allows the applicant to drop.

        1.4.1f — any round where the applicant defeated their opponent
                 (a real win, not a forfeit-win — forfeit-wins aren't
                 even in `included_rounds` under the 1.4.1c interpretation).
        1.4.1e — any tail round (non-RR only). After-a-title-result test
                 isn't applied explicitly: if dropping a tail round still
                 yields a norm, by definition the prefix achieves it.
        """
        from data.pairings.systems import RoundRobinPairingSystem

        droppable: set[int] = set()

        # 1.4.1f — won rounds in the mix.
        for rnd, result in zip(inputs.included_rounds, inputs.results_list):
            if result in (Result.WIN, Result.UNRATED_WIN):
                droppable.add(rnd)

        # 1.4.1e — tail rounds, non-RR only.
        if self.tournament.pairing_system != RoundRobinPairingSystem():
            total = self.tournament.rounds
            tail_window = self._max_ignores_for_any_norm()
            for r in range(max(1, total - tail_window + 1), total + 1):
                if r in inputs.included_rounds:
                    droppable.add(r)

        return droppable

    def _max_ignores_for_any_norm(self) -> int:
        """Largest possible ignore-set size across all norms — defines the
        tail-window for 1.4.1e candidate generation."""
        return max(self._max_ignores(tn) for tn in TitleNorm.values())

    def _candidates(
        self,
        droppable: set[int],
        max_ignores: int,
        inputs: NormInputs,
    ) -> Iterable[frozenset[int]]:
        """Yield ignore-subsets by ascending size; within a size class,
        try the most-promising first (drops yielding the largest expected
        Ra improvement, i.e. dropping the lowest-rated opponents first).
        """
        opponent_by_round = dict(zip(inputs.included_rounds, inputs.opponents))
        # Pre-compute the per-round drop score: lower opponent rating ⇒
        # dropping that round is more likely to lift Ra.
        round_score: dict[int, int] = {
            rnd: (
                opponent_by_round[rnd].rating
                if opponent_by_round[rnd].rating_type == PlayerRatingType.FIDE
                else 1400
            )
            for rnd in droppable
        }
        limit = min(max_ignores, len(droppable))
        for size in range(1, limit + 1):
            sized = combinations(droppable, size)
            ranked = sorted(
                sized,
                key=lambda combo: sum(round_score[r] for r in combo),
            )
            for combo in ranked:
                yield frozenset(combo)
