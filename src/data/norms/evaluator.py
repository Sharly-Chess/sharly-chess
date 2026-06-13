"""`TitleNormEvaluator` — per-applicant FIDE title-norm evaluator."""

from __future__ import annotations

from operator import attrgetter
from typing import TYPE_CHECKING

from common.i18n import _
from data.norms.inputs import (
    NormInputs,
    REASON_BOARD_BYE,
    REASON_FORFEIT_WIN_EXCLUDED,
    REASON_INCLUDED,
    REASON_INCLUDED_AS_142C_LOSS,
    REASON_NO_OPPONENT,
    REASON_RULE_142A,
    REASON_RULE_142B,
    REASON_UNPLAYED_NO_PAIRING,
    RoundAuditEntry,
    RoundDecision,
)
from utils import Utils
from utils.enum import PlayerRatingType, Result, TitleNorm
from utils.types import Federation, NormCheckResult, PlayerRatingAndType

if TYPE_CHECKING:
    from data.player import TournamentPlayer
    from data.tournament import Tournament


def _no_opponent_reason(opponent, effective_result: Result) -> str:
    """Audit reason for a round the evaluator did NOT include as a played
    game. Four distinct cases — kept separate so the IT1 audit makes
    the cause explicit (a forfeit-win-against-no-show is not the same
    thing as a half-point bye or a missing pairing).

    The result is checked first because a PAB round legitimately has no
    opponent (`pairing.opponent is None`); falling through to
    `REASON_NO_OPPONENT` for that case would mask the bye."""
    if effective_result == Result.FORFEIT_WIN:
        return REASON_FORFEIT_WIN_EXCLUDED
    if effective_result.is_board_bye:
        return REASON_BOARD_BYE
    if opponent is None:
        return REASON_NO_OPPONENT
    return REASON_UNPLAYED_NO_PAIRING


def _resolve_min_games(
    tn: TitleNorm,
    tournament: 'Tournament',
    override: int | None,
) -> int:
    """The minimum games count this norm must clear under 1.4.1.

    `override` lets the arbiter pin a specific value (e.g. 7 for a
    7-round qualifying event under 1.4.1b); otherwise the spec default
    from the tournament's round count is used.

    Both `TitleNormEvaluator` and `TitleNormSubsetSearcher` resolve the
    same value through this helper — keeping them in lock-step matters
    because the searcher's `max_ignores = rounds - min_games` must use
    the same minimum the evaluator will check against.
    """
    if override is not None:
        return override
    return tn.minimum_rounds(tournament)


class TitleNormEvaluator:
    """Per-applicant FIDE title-norm evaluator.

    Builds the opponent mix from the applicant's pairings, runs every per-norm
    requirement check, and orchestrates the 1.4.2c dual evaluation (try
    1.4.1c first; fall back to 1.4.2c only if the default doesn't satisfy).
    """

    def __init__(
        self,
        player: 'TournamentPlayer',
        min_games_override: int | None = None,
    ):
        """`min_games_override` overrides FIDE 1.4.1's default minimum (9,
        or 10 for DRR). Used for events qualifying for 1.4.1b exceptions
        (e.g. 7-round team championships) — the spec value is set by the
        arbiter via the print options, since the qualifying event types
        aren't auto-detected from the tournament metadata."""
        self.player = player
        self.min_games_override = min_games_override

    @property
    def tournament(self):
        return self.player.tournament

    def _min_games(self, tn: TitleNorm) -> int:
        return _resolve_min_games(tn, self.tournament, self.min_games_override)

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
                    # Carry the losing 1.4.1c interpretation so the
                    # detail view can render the side-by-side Rps.
                    res_b.alternate_142c = res
                    res = res_b
            results[tn] = res

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
                inputs.round_audit.append(
                    RoundAuditEntry(
                        round_=rnd,
                        opponent=pairing.opponent,
                        raw_result=pairing.result,
                        effective_result=None,
                        decision=RoundDecision.NO_OPPONENT,
                        reason_key=_no_opponent_reason(
                            pairing.opponent, effective_pairing_result
                        ),
                    )
                )
                continue

            inputs.played_games += 1
            opponent = pairing.opponent
            assert opponent is not None  # narrowed by include_as_played

            # 1.4.2b — Round-Robin only: ignore unrated opponents who lost every
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
                    inputs.round_audit.append(
                        RoundAuditEntry(
                            round_=rnd,
                            opponent=opponent,
                            raw_result=pairing.result,
                            effective_result=None,
                            decision=RoundDecision.EXCLUDED,
                            reason_key=REASON_RULE_142B,
                        )
                    )
                    continue

            # 1.4.2a — opponent must belong to a FIDE federation.
            if opponent.federation == Federation('NON'):
                inputs.ignored_opponents_ids.add(opponent.id)
                inputs.round_audit.append(
                    RoundAuditEntry(
                        round_=rnd,
                        opponent=opponent,
                        raw_result=pairing.result,
                        effective_result=None,
                        decision=RoundDecision.EXCLUDED,
                        reason_key=REASON_RULE_142A,
                    )
                )
                continue
            # 1.4.2a — players with federation 'FID' are accepted (the game
            # counts towards games played, titled opponents, Ra, score) but
            # FID "is not considered a federation": it must not enter the
            # federation mix. So it counts neither towards 1.4.3's foreign-
            # federation tally nor as a federation that can breach the 1.4.4
            # caps. (FIDE QC clarification, 2026.) RUS/BLR players are shown
            # as FID but count under their own flag — the arbiter corrects
            # the flag in the data; nothing special is done here.
            if opponent.federation != Federation('FID'):
                inputs.federations_counter[opponent.federation] += 1

            # 1.4.5a — CM/WCM are NOT counted as title-holders.
            if opponent.title in TitleNorm.TITLE_HOLDERS:
                inputs.titles_counter[opponent.title] += 1

            # 1.4.2c — the last-round forfeit-against is scored as a LOSS.
            applied_142c = (
                include_last_forfeit_as_loss and is_last_round_forfeit_against
            )
            effective_result = Result.LOSS if applied_142c else effective_pairing_result
            inputs.results_list.append(effective_result)
            inputs.opponents.append(opponent)
            inputs.included_rounds.append(rnd)
            inputs.round_audit.append(
                RoundAuditEntry(
                    round_=rnd,
                    opponent=opponent,
                    raw_result=pairing.result,
                    effective_result=effective_result,
                    decision=RoundDecision.INCLUDED,
                    reason_key=(
                        REASON_INCLUDED_AS_142C_LOSS
                        if applied_142c
                        else REASON_INCLUDED
                    ),
                )
            )

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
        The applicable minimum is `min_games_override` when set, otherwise
        `tn.minimum_rounds(tournament)` (9 / 10 for DRR).
        """
        min_games = self._min_games(tn)
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
        """1.4.4 — at most 3/5 of opponents from the applicant's federation.
        Threshold scales with the size of the opponent mix (played_games),
        per the spec wording "3/5 of the opponents"."""
        own_count = inputs.federations_counter.get(self.player.federation, 0)
        return own_count <= tn.maximum_of_own_federation(inputs.played_games)

    def top_federation_requirement(
        self, inputs: NormInputs, tn: TitleNorm
    ) -> tuple[bool, Federation | None, int]:
        """1.4.4 — at most 2/3 of opponents from any single federation.
        Threshold scales with played_games. Returns (passes, top_federation,
        top_count); top_federation is None when there are no counted
        opponents."""
        if not inputs.federations_counter:
            return True, None, 0
        top_fed, top_count = inputs.federations_counter.most_common(1)[0]
        passes = top_count <= tn.maximum_of_one_federation(inputs.played_games)
        return passes, top_fed, top_count

    def title_holders_requirement(
        self, inputs: NormInputs, tn: TitleNorm
    ) -> tuple[bool, int]:
        """1.4.5a — at least 50% of opponents are title-holders (CM/WCM
        excluded; the inputs already filter those out via TITLE_HOLDERS).
        Threshold scales with played_games per spec wording "50% of the
        opponents". Returns (passes, num_title_holders)."""
        num_titles = sum(inputs.titles_counter.values())
        return (
            num_titles >= tn.minimum_title_holders(inputs.played_games),
            num_titles,
        )

    def required_titles_requirement(
        self, inputs: NormInputs, tn: TitleNorm
    ) -> tuple[bool, int]:
        """1.4.5b-e — minimum count of opponents holding the norm's required
        title set (GM norm needs at least 1/3 GMs, min 3; etc.). Threshold
        scales with played_games. Returns (passes, count_met)."""
        count = sum(inputs.titles_counter.get(t, 0) for t in tn.required_titles)
        return (
            count >= tn.minimum_required_titles(self.tournament, inputs.played_games),
            count,
        )

    def score_requirement(self, inputs: NormInputs) -> bool:
        """1.4.8b — at least 35% of the played games. Threshold scales with
        played_games — 1.4.1c-credited 9-game norms (8 played + 1 PAB)
        require 35% of the 8 played, not 35% of 9."""
        return inputs.score >= TitleNorm.minimum_score(inputs.played_games)

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
        res.round_audit = inputs.round_audit

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
        res.federations_counter = inputs.federations_counter

        rt_ok, rt_met = self.required_titles_requirement(inputs, tn)
        if not rt_ok:
            res.not_enough_required_titles = _(
                '<b>1.4.5</b> For this norm, at least {min} opponents must have these title(s): {titles}'
            ).format(
                min=tn.minimum_required_titles(self.tournament, inputs.played_games),
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

        # Set 1.4.3d / 1.5.6a fields before returning, so `is_met` reads
        # them in the 1.4.2c fallback decision. `is_143d_met` returns
        # True while its three flag fields are None, so deferring this
        # would skip 1.4.2c when only 1.4.4 fails.
        self._apply_tournament_wide_checks(res)
        return res

    def _apply_tournament_wide_checks(self, res: NormCheckResult) -> None:
        """Stamp the 1.4.3d counts/flags and the 1.5.6a flag onto one
        result. The values are tournament-wide (cached on Tournament),
        applied per-result so `is_met` reads them correctly."""
        exemption = self.tournament.big_tournament_exemption
        msg = _(
            '<b>1.4.3d</b> Swiss System tournaments in which participants include in every round at least 20 FIDE rated players, not from the host federation, from at least 3 different federations, at least 10 of whom hold GM, IM, WGM or WIM titles.'
        )
        res.all_federations_count = exemption.federations
        res.not_enough_all_federations = None if exemption.federations_met else msg
        res.eligible_players_count = exemption.foreigners
        res.not_enough_foreign_players = None if exemption.foreigners_met else msg
        res.eligible_players_title_count = exemption.titled_foreigners
        res.not_enough_all_title_holders = (
            None if exemption.titled_foreigners_met else msg
        )
        res.requirement_156a_met = self.tournament.high_level_tournament

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
