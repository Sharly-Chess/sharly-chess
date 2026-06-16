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
        rule_143_exemption: str = 'none',
    ):
        """`min_games_override` is forwarded to the evaluator and used by
        the subset-search to bound `max_ignores`.

        `rule_143_exemption` is the arbiter's 1.4.3a/b/c selection. It is
        resolved (with the player's federation scoping) and applied to
        every result the search evaluates — so a subset that the
        exemption rescues (e.g. dropping a round to clear `1.4.4` /
        performance once the foreigner requirement is waived) is
        recognised *during* the search, not only after it."""
        from data.norms.tournament_checks import resolve_143abc_code
        from utils.types import Federation

        self.player = player
        self.min_games_override = min_games_override
        self.evaluator = TitleNormEvaluator(
            player, min_games_override=min_games_override
        )
        self._exemption_code = resolve_143abc_code(
            rule_143_exemption,
            player.federation,
            Federation(player.event.federation),
        )

    def _evaluate(
        self, inputs: 'NormInputs', tn: TitleNorm, meets_gender: bool
    ) -> NormCheckResult:
        """Evaluate one subset and stamp the resolved 1.4.3a/b/c
        exemption so ``is_met`` reflects the waiver during the search."""
        result = self.evaluator.evaluate_one(inputs, tn, meets_gender)
        result.rule_143_exemption = self._exemption_code
        return result

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
        baseline_result = self._evaluate(baseline, tn, meets_gender)
        if baseline_result.is_met:
            return baseline_result

        # Fast path 2: 1.4.2c interpretation on the full set.
        if baseline_142c is not None:
            result_142c = self._evaluate(baseline_142c, tn, meets_gender)
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

        for candidate in self._candidates(inputs, max_ignores):
            modified = inputs.without_rounds(candidate)
            result = self._evaluate(modified, tn, meets_gender)
            if result.is_met:
                result.ignored_rounds_via_search = candidate
                # Flip the dropped rounds' audit entries to DROPPED so the
                # IT1 reflects what the search did, not just what
                # collect_inputs produced. `audit_with_dropped` returns a
                # fresh list — entries themselves stay frozen.
                result.round_audit = inputs.audit_with_dropped(
                    self._classify_drops(inputs, candidate)
                )
                return result
        return None

    def _classify_drops(
        self, inputs: NormInputs, candidate: frozenset[int]
    ) -> dict[int, str]:
        """Map each dropped round to the rule that ignored it.

        The maximal trailing suffix of the schedule contained in the drop
        is the 1.4.1e tail (every game after the title result). The rest
        are isolated 1.4.1f drops against defeated opponents. In a system
        with pre-determined pairings 1.4.1e never applies, so every drop
        is 1.4.1f.
        """
        from data.norms.inputs import REASON_DROPPED_BY_141E, REASON_DROPPED_BY_141F
        from data.pairings.systems import RoundRobinPairingSystem

        tail: set[int] = set()
        if self.tournament.pairing_system != RoundRobinPairingSystem():
            for rnd in sorted(inputs.included_rounds, reverse=True):
                if rnd not in candidate:
                    break
                tail.add(rnd)

        return {
            rnd: REASON_DROPPED_BY_141E if rnd in tail else REASON_DROPPED_BY_141F
            for rnd in candidate
        }

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

    def _candidates(
        self,
        inputs: NormInputs,
        max_ignores: int,
    ) -> Iterable[frozenset[int]]:
        """Yield the ignore-subsets the spec allows, by ascending size and
        most-promising-first (drops lifting Ra the most — i.e. the
        lowest-rated opponents — come first within a size class).

        The two rules drop rounds with different shapes, and conflating
        them produces illegal subsets:

        1.4.1f — games against *defeated* opponents may be ignored, in any
                 combination. So any subset of won rounds is a candidate.
                 (Real wins only; forfeit-wins aren't in `included_rounds`
                 under the 1.4.1c interpretation.)
        1.4.1e — once a title result is reached, *all* later games may be
                 ignored. The drop is therefore a whole trailing suffix of
                 the schedule, never an isolated middle round. Non-RR only
                 (pre-determined pairings must use every scheduled round).
                 The after-a-title-result test isn't applied explicitly:
                 if dropping the tail still yields a norm, the prefix
                 achieved it by definition.

        A non-won round (loss/draw) may thus be dropped *only* as part of a
        1.4.1e tail — dropping round k pulls in every later round too. A
        candidate is the union of one 1.4.1e tail (possibly empty) and any
        1.4.1f subset of the won rounds left in the prefix.
        """
        from data.pairings.systems import RoundRobinPairingSystem

        ordered = sorted(inputs.included_rounds)
        if not ordered or max_ignores <= 0:
            return

        opponent_by_round = dict(zip(inputs.included_rounds, inputs.opponents))
        won = {
            rnd
            for rnd, result in zip(inputs.included_rounds, inputs.results_list)
            if result in (Result.WIN, Result.UNRATED_WIN)
        }

        def drop_score(rnd: int) -> int:
            opponent = opponent_by_round[rnd]
            if opponent.rating_type == PlayerRatingType.FIDE:
                return opponent.rating
            return 1400  # unrated ⇒ treat as the 1.4.6 floor

        allow_tail = self.tournament.pairing_system != RoundRobinPairingSystem()
        max_tail = max_ignores if allow_tail else 0

        seen: set[frozenset[int]] = set()
        collected: list[frozenset[int]] = []
        n = len(ordered)
        for tail_len in range(min(max_tail, n) + 1):
            tail = frozenset(ordered[n - tail_len :]) if tail_len else frozenset()
            prefix_won = [r for r in ordered[: n - tail_len] if r in won]
            for extra in range(max_ignores - tail_len + 1):
                for won_combo in combinations(prefix_won, extra):
                    candidate = tail | frozenset(won_combo)
                    if not candidate or candidate in seen:
                        continue
                    seen.add(candidate)
                    collected.append(candidate)

        collected.sort(
            key=lambda combo: (len(combo), sum(drop_score(r) for r in combo))
        )
        yield from collected
