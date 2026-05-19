"""`TitleNormForecaster` — what-if analysis over a single future round."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from data.norms.searcher import TitleNormSubsetSearcher
from utils.enum import Result, TitleNorm
from utils.types import NormCheckResult

if TYPE_CHECKING:
    from data.player import TournamentPlayer


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

    def __init__(
        self,
        player: 'TournamentPlayer',
        min_games_override: int | None = None,
        rule_143_exemption: str = 'none',
    ):
        """`rule_143_exemption` is the arbiter's manual selection for
        1.4.3a/b/c. Defaults to 'none' so existing callers see no behavior
        change. Applied to every forecast result so a/b/c-eligible
        players show the right `chaseable_norms` for their event type."""
        self.player = player
        self.min_games_override = min_games_override
        self.rule_143_exemption = rule_143_exemption

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
        from data.norms.tournament_checks import apply_143abc_exemption
        from utils.types import Federation

        event_fed = Federation(self.player.event.federation)
        out: dict[Result, dict[TitleNorm, NormCheckResult]] = {}
        for outcome in _FORECAST_OUTCOMES:
            searcher = TitleNormSubsetSearcher(
                self.player, min_games_override=self.min_games_override
            )
            results = searcher.evaluate(result_overrides={round_: outcome})
            # Apply 1.4.3a/b/c exemption so `is_met` reflects the spec
            # exemption when the arbiter has flagged the event type.
            apply_143abc_exemption(
                results, self.rule_143_exemption, self.player.federation, event_fed
            )
            out[outcome] = results
        return out

    def minimum_required_result(
        self,
        round_: int,
        tn: TitleNorm,
    ) -> Result | None:
        """The cheapest result in `round_` that achieves `tn`. Returns:
        - LOSS  ⇒ the norm is achieved regardless of outcome ("any").
        - DRAW  ⇒ draw suffices.
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
        # Separate "is R_N dispensable?" check — run the searcher with
        # R_N forced out of the mix (NO_RESULT → unplayed → not collected).
        # Whether the searcher's per-outcome winner happens to drop R_N
        # depends on heuristic ordering, so we can't use that. This check
        # is authoritative: if the norm holds with R_N entirely excluded,
        # then play is genuinely optional for the norm.
        secured_norms = self._secured_norms_without_round(round_)

        chaseable: dict[TitleNorm, ForecastRequirement] = {}
        for tn in TitleNorm.values():
            # Skip norms not above the applicant's current title.
            if tn.player_title.sort_index <= self.player.title.sort_index:
                continue
            # First outcome (in LOSS, DRAW, WIN order) that achieves it.
            for outcome in _FORECAST_OUTCOMES:
                result = forecast[outcome][tn]
                if result.is_met:
                    chaseable[tn] = ForecastRequirement(
                        minimum_outcome=outcome,
                        play_required=tn not in secured_norms,
                    )
                    break
        return chaseable

    def _secured_norms_without_round(self, round_: int) -> set[TitleNorm]:
        """Norms achieved with `round_` excluded from the mix entirely.

        Equivalent to "what if the player no-shows" — the override
        Result.NO_RESULT marks the pairing as unplayed, so collect_inputs
        skips it. The searcher's 1.4.1e/f explorations apply normally to
        the prefix R1..R(round_-1).
        """
        searcher = TitleNormSubsetSearcher(
            self.player, min_games_override=self.min_games_override
        )
        results = searcher.evaluate(result_overrides={round_: Result.NO_RESULT})
        return {tn for tn, res in results.items() if res.is_met}
