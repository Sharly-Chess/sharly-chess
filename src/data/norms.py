"""FIDE title-norm evaluation (B.01, effective 1 January 2024).

Entry point: `TitleNormEvaluator(tournament_player).evaluate()` returns a
`dict[TitleNorm, NormCheckResult]` covering all four norms (GM, IM, WGM, WIM).

Spec mapping is annotated inline; section numbers refer to FIDE Handbook B.01
as summarised in `docs/technical-appendices/fide-title-norms.md`.

Public API:
- `TitleNormEvaluator` — the per-applicant evaluator.
- `NormInputs` — snapshot of pairings-derived data used by the per-rule checks.

The 1.4.3d and 1.5.6a tournament-wide checks live on `Tournament` itself
(`big_tournament_exemption`, `high_level_tournament`) since they don't depend
on the applicant.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from operator import attrgetter
from typing import TYPE_CHECKING, Iterable

from common.i18n import _
from utils import Utils
from utils.enum import PlayerRatingType, PlayerTitle, Result, TitleNorm
from utils.types import (
    Federation,
    NormCheckResult,
    PlayerRatingAndType,
)

if TYPE_CHECKING:
    from data.player import TournamentPlayer


@dataclass
class NormInputs:
    """Snapshot of pairings-derived inputs for the per-norm checks.

    Built once (`include_last_forfeit_as_loss=False`) for the default 1.4.1c
    interpretation. Rebuilt with `include_last_forfeit_as_loss=True` for the
    1.4.2c fallback if 1.4.1c fails. Carries `has_last_round_forfeit_against`
    so the orchestrator can decide whether a B-pass is worth doing.

    `included_rounds` runs parallel to `opponents` / `results_list` — entry
    `i` corresponds to round `included_rounds[i]`. The subset searcher uses
    this to drop specific rounds via `without_rounds()`.
    """

    played_games: int = 0
    federations_counter: Counter[Federation] = field(default_factory=Counter)
    titles_counter: Counter[PlayerTitle] = field(default_factory=Counter)
    opponents: list['TournamentPlayer'] = field(default_factory=list)
    results_list: list[Result] = field(default_factory=list)
    included_rounds: list[int] = field(default_factory=list)
    forfeits_or_byes: int = 0
    ignored_opponents_ids: set[int] = field(default_factory=set)
    score: float = 0.0
    has_last_round_forfeit_against: bool = False

    def without_rounds(self, drop: frozenset[int]) -> 'NormInputs':
        """Return a copy with the specified rounds removed from the mix.

        Counters and score are recomputed from the kept entries.
        `forfeits_or_byes`, `ignored_opponents_ids` and
        `has_last_round_forfeit_against` are preserved unchanged — they
        describe properties of the FULL pairing set, not the search subset.
        """
        if not drop:
            return self
        kept_idx = [i for i, r in enumerate(self.included_rounds) if r not in drop]
        kept_opponents = [self.opponents[i] for i in kept_idx]
        kept_results = [self.results_list[i] for i in kept_idx]
        kept_rounds = [self.included_rounds[i] for i in kept_idx]

        feds: Counter[Federation] = Counter()
        titles: Counter[PlayerTitle] = Counter()
        for opponent in kept_opponents:
            feds[opponent.federation] += 1
            if opponent.title in TitleNorm.TITLE_HOLDERS:
                titles[opponent.title] += 1

        return NormInputs(
            played_games=len(kept_idx),
            federations_counter=feds,
            titles_counter=titles,
            opponents=kept_opponents,
            results_list=kept_results,
            included_rounds=kept_rounds,
            forfeits_or_byes=self.forfeits_or_byes,
            ignored_opponents_ids=self.ignored_opponents_ids,
            score=sum(r.points() for r in kept_results),
            has_last_round_forfeit_against=self.has_last_round_forfeit_against,
        )


class TitleNormEvaluator:
    """Per-applicant FIDE title-norm evaluator.

    Builds the opponent mix from the applicant's pairings, runs every per-norm
    requirement check, and orchestrates the 1.4.2c dual evaluation (try
    1.4.1c first; fall back to 1.4.2c only if the default doesn't satisfy).
    """

    def __init__(self, player: 'TournamentPlayer'):
        self.player = player

    @property
    def tournament(self):
        return self.player.tournament

    # ---------- top-level orchestration ----------

    def evaluate(
        self,
        result_overrides: dict[int, Result] | None = None,
    ) -> dict[TitleNorm, NormCheckResult]:
        # Default 1.4.1c interpretation: forfeit-wins excluded from the mix;
        # a single forfeit-win/PAB in a 9-round event lets 8 played games
        # still credit as a 9-game norm.
        inputs_a = self.collect_inputs(
            include_last_forfeit_as_loss=False,
            result_overrides=result_overrides,
        )

        # 1.4.2c fallback: only built when a last-round opponent-forfeit
        # exists. Includes that game as a played LOSS so the applicant
        # "must have played" but "can afford to lose". Different mix and
        # score → different Rp than the 1.4.1c interpretation.
        inputs_b: NormInputs | None = (
            self.collect_inputs(
                include_last_forfeit_as_loss=True,
                result_overrides=result_overrides,
            )
            if inputs_a.has_last_round_forfeit_against
            else None
        )

        results: dict[TitleNorm, NormCheckResult] = {}
        for tn in TitleNorm.values():
            meets_gender = tn.satisfies_gender_requirement(self.player.gender)
            res = self.evaluate_one(inputs_a, tn, meets_gender)
            if inputs_b is not None and not res.is_met:
                res_b = self.evaluate_one(inputs_b, tn, meets_gender)
                if res_b.is_met:
                    res_b.applied_142c = True
                    res = res_b
            results[tn] = res

        # 1.4.3d and 1.5.6a are tournament-wide. Pull the cached values
        # off the Tournament — same answer for every applicant, computed once.
        self.apply_big_tournament_exemption(results)
        self.apply_high_level_tournament_flag(results)
        return results

    # ---------- input gathering ----------

    def collect_inputs(
        self,
        include_last_forfeit_as_loss: bool,
        result_overrides: dict[int, Result] | None = None,
    ) -> NormInputs:
        """Single pass over the applicant's pairings → opponent mix + score.

        When `include_last_forfeit_as_loss` is True, a last-round FORFEIT_WIN
        is counted as a played game with the applicant scored as LOSS — the
        1.4.2c interpretation. Otherwise (default 1.4.1c), forfeit-wins are
        excluded from the mix and `forfeits_or_byes` tracks them for the
        9-round 8+1 exemption.

        `result_overrides` substitutes a hypothetical result for given
        rounds — used by the forecaster to evaluate "what if round 9 is a
        WIN/DRAW/LOSS" without mutating the stored tournament state.
        Overrides only apply where the pairing has an opponent.
        """
        from data.pairings.systems import RoundRobinPairingSystem

        inputs = NormInputs()
        is_round_robin = self.tournament.pairing_system == RoundRobinPairingSystem()
        last_round = self.tournament.rounds
        overrides = result_overrides or {}

        for rnd, pairing in self.player.pairings_by_round.items():
            override = overrides.get(rnd)
            effective_pairing_result = (
                override
                if override is not None and pairing.opponent is not None
                else pairing.result
            )
            if (
                effective_pairing_result.is_board_bye
                or effective_pairing_result == Result.FORFEIT_WIN
            ):
                inputs.forfeits_or_byes += 1

            is_last_round_forfeit_against = (
                rnd == last_round
                and effective_pairing_result == Result.FORFEIT_WIN
                and pairing.opponent is not None
            )
            if is_last_round_forfeit_against:
                inputs.has_last_round_forfeit_against = True

            include_as_played = pairing.opponent is not None and (
                not effective_pairing_result.is_unplayed
                or (include_last_forfeit_as_loss and is_last_round_forfeit_against)
            )
            if not include_as_played:
                continue

            inputs.played_games += 1
            opponent = pairing.opponent
            assert opponent is not None  # narrowed by include_as_played

            # 1.4.2b — round-robin only: ignore unrated opponents who lost every
            # game they actually played against a FIDE-rated opponent.
            if is_round_robin and opponent.rating_type != PlayerRatingType.FIDE:
                scored_zero_against_rated = True
                for opponent_pairing in opponent.pairings_by_round.values():
                    if (
                        opponent_pairing.opponent
                        and not opponent_pairing.result.is_loss
                        and not opponent_pairing.result.is_unplayed
                        and opponent_pairing.opponent.rating_type
                        == PlayerRatingType.FIDE
                    ):
                        scored_zero_against_rated = False
                        break
                if scored_zero_against_rated:
                    inputs.ignored_opponents_ids.add(opponent.id)
                    continue

            # 1.4.2a — opponent must belong to a FIDE federation.
            if opponent.federation == Federation('NON'):
                inputs.ignored_opponents_ids.add(opponent.id)
                continue
            inputs.federations_counter[opponent.federation] += 1

            # 1.4.5a — CM/WCM are NOT counted as title-holders.
            if opponent.title in TitleNorm.TITLE_HOLDERS:
                inputs.titles_counter[opponent.title] += 1

            # 1.4.2c — the last-round forfeit-against is scored as a LOSS.
            effective_result = (
                Result.LOSS
                if include_last_forfeit_as_loss and is_last_round_forfeit_against
                else effective_pairing_result
            )
            inputs.results_list.append(effective_result)
            inputs.opponents.append(opponent)
            inputs.included_rounds.append(rnd)

        inputs.score = sum(r.points() for r in inputs.results_list)
        return inputs

    # ---------- per-rule requirement checks (granular, testable) ----------
    # Each returns the boolean outcome and any measured value(s) the form
    # needs to display. Names mirror the spec sections.

    def games_requirement(self, inputs: NormInputs, tn: TitleNorm) -> tuple[bool, int]:
        """1.4.1 — minimum game count, plus 1.4.1c exemption (9-round events
        only: 8 played + exactly 1 forfeit-win/PAB → credited as a 9-game
        norm). DRR (10 rounds) gets no 8+1 exemption.

        Returns (passes, min_required) so the form can render the threshold.
        """
        min_games = tn.minimum_rounds(self.tournament)
        allow_1_4_1c = (
            self.tournament.rounds == 9
            and inputs.played_games == 8
            and inputs.forfeits_or_byes == 1
        )
        passes = inputs.played_games >= min_games or allow_1_4_1c
        return passes, min_games

    def federation_count_requirement(self, inputs: NormInputs) -> tuple[bool, int, int]:
        """1.4.3 — at least 2 federations other than the applicant's.
        Returns (passes, distinct_federations, own_count)."""
        own_count = inputs.federations_counter.get(self.player.federation, 0)
        num_feds = len(inputs.federations_counter)
        if own_count:
            passes = num_feds > 2
        else:
            passes = num_feds >= 2
        return passes, num_feds, own_count

    def own_federation_requirement(self, inputs: NormInputs, tn: TitleNorm) -> bool:
        """1.4.4 — at most 3/5 of opponents from the applicant's federation."""
        own_count = inputs.federations_counter.get(self.player.federation, 0)
        return own_count <= tn.maximum_of_own_federation(self.tournament.rounds)

    def top_federation_requirement(
        self, inputs: NormInputs, tn: TitleNorm
    ) -> tuple[bool, Federation | None, int]:
        """1.4.4 — at most 2/3 of opponents from any single federation.
        Returns (passes, top_federation, top_count) — top_federation is None
        when the applicant has no counted opponents."""
        if not inputs.federations_counter:
            return True, None, 0
        top_fed, top_count = inputs.federations_counter.most_common(1)[0]
        passes = top_count <= tn.maximum_of_one_federation(self.tournament.rounds)
        return passes, top_fed, top_count

    def title_holders_requirement(
        self, inputs: NormInputs, tn: TitleNorm
    ) -> tuple[bool, int]:
        """1.4.5a — at least 50% of opponents are title-holders (CM/WCM
        excluded; the inputs already filter those out via TITLE_HOLDERS).
        Returns (passes, num_title_holders)."""
        num_titles = sum(inputs.titles_counter.values())
        return (
            num_titles >= tn.minimum_title_holders(self.tournament.rounds),
            num_titles,
        )

    def required_titles_requirement(
        self, inputs: NormInputs, tn: TitleNorm
    ) -> tuple[bool, int]:
        """1.4.5b-e — minimum count of opponents holding the norm's required
        title set (e.g. GM norm needs 3+ GMs, IM norm needs 3+ IMs/GMs, etc.).
        Returns (passes, count_met)."""
        count = sum(inputs.titles_counter.get(t, 0) for t in tn.required_titles)
        return count >= tn.minimum_required_titles(self.tournament), count

    def score_requirement(self, inputs: NormInputs) -> bool:
        """1.4.8b — at least 35%. Threshold uses the tournament's round count
        (the norm's nominal length), not played_games — so a 1.4.1c-credited
        9-game norm achieved in 8 games still requires 35% of 9."""
        return inputs.score >= TitleNorm.minimum_score(self.tournament.rounds)

    def opponent_rating_floor_and_average(
        self, inputs: NormInputs, tn: TitleNorm
    ) -> tuple[float, 'TournamentPlayer | None', int | None]:
        """1.4.6 + 1.4.7 — apply rating floor to (at most) the single lowest
        opponent, then return the rounded average. Also returns the adjusted
        opponent and the floor value so the form can show the adjustment.
        """
        sorted_opponents = sorted(
            inputs.opponents,
            key=lambda o: o.rating if o.rating_type == PlayerRatingType.FIDE else 1400,
        )
        rating_list = [
            PlayerRatingAndType(
                o.rating if o.rating_type == PlayerRatingType.FIDE else 1400,
                o.rating_type,
            )
            for o in sorted_opponents
        ]

        adjusted_player: 'TournamentPlayer | None' = None
        adjusted_rating: int | None = None
        if rating_list and rating_list[0].value < tn.minimum_rating:
            rating_list[0].value = tn.minimum_rating
            rating_list[0].type = PlayerRatingType.FIDE
            adjusted_player = sorted_opponents[0]
            adjusted_rating = tn.minimum_rating
            rating_list.sort(key=attrgetter('value'))

        values = [r.value for r in rating_list]
        avg = Utils.round_ranking(sum(values) / len(values)) if values else 0
        return avg, adjusted_player, adjusted_rating

    @staticmethod
    def norm_performance(avg: float, score: float, played_games: int) -> float:
        """1.4.8 — Rp = Ra + dp, where dp comes from the 1.4.9 table looked up
        on the rounded fractional score."""
        max_score = Result.WIN.points() * played_games
        if not max_score:
            return avg
        fractional = Utils.round_ranking(100 * score / max_score) / 100
        return avg + Utils.performance_bonus(fractional)

    # ---------- per-norm orchestrator ----------

    def evaluate_one(
        self,
        inputs: NormInputs,
        tn: TitleNorm,
        meets_gender: bool,
    ) -> NormCheckResult:
        """Run every per-norm check against one set of inputs."""
        res = NormCheckResult(title_norm=tn, meets_gender=meets_gender)
        res.ignored_opponents_ids = inputs.ignored_opponents_ids
        res.played_games = inputs.played_games

        # 1.4.1 / 1.4.1c
        games_ok, min_games = self.games_requirement(inputs, tn)
        if not games_ok:
            res.not_enough_games = _('At least {min} games must be played.').format(
                min=min_games
            )

        # 1.4.3 / 1.4.4
        feds_ok, num_feds, own_count = self.federation_count_requirement(inputs)
        if not feds_ok:
            res.not_enough_federations = _(
                '<b>1.4.3</b> At least two federations other than that of the title applicant must be included, except 1.4.3a - 1.4.3d shall be exempt.'
            )
        res.from_own_federations_count = own_count
        res.from_host_federations_count = inputs.federations_counter.get(
            Federation(self.player.event.federation), 0
        )
        res.federations_count = num_feds

        if not self.own_federation_requirement(inputs, tn):
            res.too_many_own_federation = _(
                "<b>1.4.4</b> A maximum of 3/5 of the opponents may come from the applicant's federation."
            )

        top_ok, top_fed, _top_count = self.top_federation_requirement(inputs, tn)
        if not top_ok and top_fed is not None:
            res.too_many_one_federation = (
                top_fed,
                _(
                    '<b>1.4.4</b> A maximum of 2/3 of the opponents from one federation.'
                ),
            )

        # 1.4.5a / 1.4.5b-e
        th_ok, num_titles = self.title_holders_requirement(inputs, tn)
        if not th_ok:
            res.not_enough_title_holders = _(
                '<b>1.4.5a</b> At least 50%% of the opponents shall be title-holders, excluding CM and WCM.'
            ).replace('%%', '%')
        res.num_title_holders = num_titles
        res.title_counts = inputs.titles_counter

        rt_ok, rt_met = self.required_titles_requirement(inputs, tn)
        if not rt_ok:
            res.not_enough_required_titles = _(
                '<b>1.4.5</b> For this norm, at least {min} opponents must have these title(s): {titles}'
            ).format(
                min=tn.minimum_required_titles(self.tournament),
                titles=', '.join(str(title) for title in tn.required_titles),
            )
        res.required_titles = list(tn.required_titles)
        res.required_titles_met = rt_met

        # 1.4.8b
        if not self.score_requirement(inputs):
            res.score_too_low = _(
                '<b>1.4.8b</b> The minimum score is 35%% for all norms.'
            ).replace('%%', '%')
        res.score = inputs.score

        # 1.4.6 / 1.4.7
        avg, adjusted_player, adjusted_rating = self.opponent_rating_floor_and_average(
            inputs, tn
        )
        res.adjusted_player = adjusted_player
        res.adjusted_player_rating = adjusted_rating
        res.num_rated_players = sum(
            1 for o in inputs.opponents if o.rating_type == PlayerRatingType.FIDE
        ) + (
            1
            if adjusted_player and adjusted_player.rating_type != PlayerRatingType.FIDE
            else 0
        )
        res.average_rating = avg
        if avg < tn.minimum_average:
            res.average_too_low = _(
                '<b>1.4.8a</b> The minimum average rating of the opponents for this norm is {min}.'
            ).format(min=tn.minimum_average)

        # 1.4.8 — performance
        performance = self.norm_performance(avg, inputs.score, inputs.played_games)
        res.performance = performance
        if performance < tn.minimum_performance:
            res.performance_too_low = _(
                '<b>1.4.8</b> The minimum performance for this norm is {min}.'
            ).format(min=tn.minimum_performance)

        # How many points off the threshold the applicant is. Positive when
        # exceeding, negative when short. Iterates by half-points to find the
        # tipping score.
        res.performance_diff = self._performance_diff(
            avg, inputs.score, inputs.played_games, tn.minimum_performance
        )
        return res

    def _performance_diff(
        self,
        avg: float,
        score: float,
        played_games: int,
        target_performance: float,
    ) -> float | None:
        """Distance (in points) from the tipping score where Rp crosses the
        target. Positive ⇒ exceeded by this much; negative ⇒ short by this
        much. None when there's no max_score (no games)."""
        max_score = Result.WIN.points() * played_games
        if not max_score:
            return None
        draw = Result.DRAW.points()
        if self.norm_performance(avg, score, played_games) < target_performance:
            new_score = score
            while new_score < max_score:
                new_score += draw
                if (
                    self.norm_performance(avg, new_score, played_games)
                    >= target_performance
                ):
                    return score - new_score
            return None
        new_score = score
        while new_score > 0:
            new_score -= draw
            if self.norm_performance(avg, new_score, played_games) < target_performance:
                return score - new_score - draw
        return None

    # ---------- tournament-wide checks (delegate to Tournament) ----------

    def apply_big_tournament_exemption(self, results: dict[TitleNorm, NormCheckResult]):
        """1.4.3d — apply the cached tournament-wide counts to every result."""
        exemption = self.tournament.big_tournament_exemption
        msg = _(
            '<b>1.4.3d</b> Swiss System tournaments in which participants include in every round at least 20 FIDE rated players, not from the host federation, from at least 3 different federations, at least 10 of whom hold GM, IM, WGM or WIM titles.'
        )
        for res in results.values():
            res.all_federations_count = exemption.federations
            res.not_enough_all_federations = msg if exemption.federations < 3 else None
            res.eligible_players_count = exemption.foreigners
            res.not_enough_foreign_players = msg if exemption.foreigners < 20 else None
            res.eligible_players_title_count = exemption.titled_foreigners
            res.not_enough_all_title_holders = (
                msg if exemption.titled_foreigners < 10 else None
            )

    def apply_high_level_tournament_flag(
        self, results: dict[TitleNorm, NormCheckResult]
    ):
        """1.5.6a — set the cached flag on every result."""
        flag = self.tournament.high_level_tournament
        for res in results.values():
            res.requirement_156a_met = flag


# ---------------------------------------------------------------------------
# Subset search — FIDE 1.4.1e and 1.4.1f
# ---------------------------------------------------------------------------


class _MonotonicPruner:
    """Tracks ignore-subsets known to fail a *monotonic* requirement.

    A check is monotonic in subset size when dropping more games can never
    fix it. Once we know subset S fails such a check, every superset T ⊇ S
    must also fail, so we skip T without evaluation.

    Five of the per-norm checks are monotonic in this sense:
    - games (played count strictly decreases with more drops)
    - score (each drop removes ≥0 points)
    - federations count (distinct federations never grows)
    - title-holders count
    - required-titles count

    Performance and average-rating are NOT monotonic — dropping a low
    opponent can improve Ra → fix performance — so we don't track those.
    """

    def __init__(self):
        self._failed: list[frozenset[int]] = []

    def is_doomed(self, candidate: frozenset[int]) -> bool:
        return any(failed <= candidate for failed in self._failed)

    def record_failure(self, candidate: frozenset[int]):
        self._failed.append(candidate)


def _is_monotonic_failure(result: NormCheckResult) -> bool:
    """True iff `result` failed at least one of the monotonic checks.

    Such failures imply every superset will also fail the same check.
    """
    return bool(
        result.not_enough_games
        or result.score_too_low
        or result.not_enough_federations
        or result.not_enough_title_holders
        or result.not_enough_required_titles
    )


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
         meets the norm. Prune supersets of known monotonic failures.

    When no subset meets the norm, returns the baseline result so the
    arbiter still sees diagnostic flags.
    """

    def __init__(self, player: 'TournamentPlayer'):
        self.player = player
        self.evaluator = TitleNormEvaluator(player)

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

        self.evaluator.apply_big_tournament_exemption(results)
        self.evaluator.apply_high_level_tournament_flag(results)
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

        pruner = _MonotonicPruner()
        for candidate in self._candidates(droppable, max_ignores, inputs):
            if pruner.is_doomed(candidate):
                continue
            modified = inputs.without_rounds(candidate)
            result = self.evaluator.evaluate_one(modified, tn, meets_gender)
            if result.is_met:
                result.ignored_rounds_via_search = candidate
                return result
            if _is_monotonic_failure(result):
                pruner.record_failure(candidate)
        return None

    # ---------- candidate generation ----------

    def _max_ignores(self, tn: TitleNorm) -> int:
        """Maximum number of rounds the applicant may drop while still
        meeting the norm's minimum game count."""
        return self.tournament.rounds - tn.minimum_rounds(self.tournament)

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


# ---------------------------------------------------------------------------
# What-if forecasting — feeds hypothetical results to the searcher
# ---------------------------------------------------------------------------


# Outcomes the forecaster enumerates, in worst-to-best order. The summariser
# walks this list and returns the first outcome that achieves the norm —
# which is therefore the minimum required result.
_FORECAST_OUTCOMES: tuple[Result, ...] = (Result.LOSS, Result.DRAW, Result.WIN)


@dataclass(frozen=True)
class ForecastRequirement:
    """What a player needs in a future round to achieve a norm.

    `minimum_outcome` is the cheapest OTB result that achieves the norm
    (LOSS = even a played loss works; DRAW = ≥ ½ point; WIN = full point).

    `play_required` distinguishes two "any-result-works" cases:
      * True (typical 9-round Swiss): all three OTB outcomes pass the
        9-game evaluation, but a no-show becomes a forfeit-loss → 1.4.2c
        excludes it → only 8 played games → norm fails 1.4.1. The player
        must sit at the board even if the result doesn't matter.
      * False (rounds > min_games, 1.4.1e drops round N): the searcher
        confirmed the norm holds with round N removed entirely. The
        player technically doesn't need to play this round for the norm
        (tournament rules may still require attendance).
    """

    minimum_outcome: Result
    play_required: bool


class TitleNormForecaster:
    """Computes "what does this player need in round N?" by running the
    full searcher against hypothetical round-N results.

    Used when the tournament is not yet finished: round N is paired but
    not played, and the arbiter wants to know what each candidate player
    needs from their last game.
    """

    def __init__(self, player: 'TournamentPlayer'):
        self.player = player

    @property
    def tournament(self):
        return self.player.tournament

    def can_forecast_round(self, round_: int) -> bool:
        """True iff the player has an opponent in `round_` (round paired)
        and the result isn't already entered."""
        pairing = self.player.pairings_by_round.get(round_)
        if pairing is None or pairing.opponent is None:
            return False
        return pairing.result == Result.NO_RESULT

    def forecast_round(
        self, round_: int
    ) -> dict[Result, dict[TitleNorm, NormCheckResult]]:
        """For each candidate outcome (LOSS, DRAW, WIN) of `round_`, return
        the per-norm result that would arise."""
        out: dict[Result, dict[TitleNorm, NormCheckResult]] = {}
        for outcome in _FORECAST_OUTCOMES:
            searcher = TitleNormSubsetSearcher(self.player)
            out[outcome] = searcher.evaluate(result_overrides={round_: outcome})
        return out

    def minimum_required_result(
        self,
        round_: int,
        tn: TitleNorm,
    ) -> Result | None:
        """The cheapest result in `round_` that achieves `tn`. Returns:
        - LOSS  ⇒ the norm is achieved regardless of outcome ("any").
        - DRAW  ⇒ draw or better suffices.
        - WIN   ⇒ only a win achieves it.
        - None  ⇒ the norm is unachievable from any outcome."""
        forecast = self.forecast_round(round_)
        for outcome in _FORECAST_OUTCOMES:
            if forecast[outcome][tn].is_met:
                return outcome
        return None

    def chaseable_norms(self, round_: int) -> dict[TitleNorm, ForecastRequirement]:
        """All norms within reach via at least one outcome, mapped to a
        `ForecastRequirement` describing the minimum result and whether
        the player must play the round. Skips norms below or equal to
        the applicant's current title, and norms unreachable from any
        outcome."""
        forecast = self.forecast_round(round_)
        chaseable: dict[TitleNorm, ForecastRequirement] = {}
        for tn in TitleNorm.values():
            # Skip norms not above the applicant's current title.
            if tn.player_title.sort_index <= self.player.title.sort_index:
                continue
            # First outcome (in LOSS, DRAW, WIN order) that achieves it.
            for outcome in _FORECAST_OUTCOMES:
                result = forecast[outcome][tn]
                if result.is_met:
                    # If the searcher dropped round_ from the mix at this
                    # outcome (i.e. 1.4.1e applied), the round is optional
                    # for the norm.
                    round_dropped = round_ in result.ignored_rounds_via_search
                    chaseable[tn] = ForecastRequirement(
                        minimum_outcome=outcome,
                        play_required=not round_dropped,
                    )
                    break
        return chaseable
