"""Unplayed rounds in Swiss tournaments (C.07 Art. 16), and the final round
Fore Buchholz takes as drawn (Art. 8.3), for individuals and teams alike.

A participant's rounds are read into :class:`RoundRecord` values, one per
round, in the score the tie-break is computed on: the points of an
individual, the match or game points of a team.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RoundRecord:
    """One round of one participant."""

    round_: int
    #: The opponent faced or scheduled; None for a bye.
    opponent_id: int | None
    #: The points the participant was given for the round.
    points: float
    played: bool
    #: Art. 16.1.1: a half-point or zero-point bye.
    requested_bye: bool
    #: Art. 16.1.2: a requested bye or a forfeit loss.
    voluntary_unplayed: bool


def fore_round_is_paired(rounds: Iterable[RoundRecord], after_round: int) -> bool:
    """Whether Art. 8.3's hypothesis reaches the participant: it replaces
    the *paired* games of the final round with draws, so a participant who
    was not paired for that round keeps what they were given."""
    return any(
        record.round_ == after_round and record.opponent_id is not None
        for record in rounds
    )


def adjusted_score(
    rounds: Sequence[RoundRecord],
    *,
    after_round: int,
    draw: float,
    fore: bool = False,
) -> float:
    """The participant's score for the purposes of their opponents'
    tie-breaks.

    A requested bye followed only by voluntary unplayed rounds, or in the
    last round, counts as a draw (Art. 16.2.5 and 16.3.2); every other
    round counts what it was given (16.3.1). With *fore*, the final round
    counts as a draw when the participant was paired for it (Art. 8.3),
    which also makes it a round that is not a VUR."""
    fore = fore and fore_round_is_paired(rounds, after_round)
    counted = [record for record in rounds if record.round_ <= after_round]

    def counts_as_draw(record: RoundRecord) -> bool:
        if fore:
            return record.round_ == after_round
        return record.requested_bye and all(
            later.voluntary_unplayed
            for later in counted
            if later.round_ > record.round_
        )

    return sum(draw if counts_as_draw(record) else record.points for record in counted)


def dummy_score(
    own_score: float,
    *,
    draw: float,
    tournament_rounds: int,
    opponent_adjusted: float | None = None,
    legacy: bool = False,
) -> float:
    """The score of the dummy an unplayed round is played against: the
    participant's own score (Art. 16.4), capped by the scheduled opponent's
    adjusted score for a forfeit (16.4.1), else by the draw points times the
    rounds of the tournament (16.4.2). The two caps are alternatives.

    *legacy* is the wording in force until March 2026, which capped
    nothing."""
    if legacy:
        return own_score
    if opponent_adjusted is not None:
        return min(own_score, opponent_adjusted)
    return min(own_score, tournament_rounds * draw)


def cut_sum(
    scores: Iterable[float],
    voluntary_unplayed: Iterable[float],
    bottom_cut: int,
    top_cut: int,
) -> float:
    """The sum of Buchholz-like contributions once cut: the lowest ones
    from the voluntary unplayed rounds first (Art. 16.5), then the lowest
    of the rest; the highest ones from all of them alike."""
    kept = sorted(voluntary_unplayed) + sorted(scores)
    kept = sorted(kept[bottom_cut:])
    if top_cut:
        kept = kept[:-top_cut]
    return sum(kept)


@dataclass(frozen=True)
class WeightedContribution:
    """A Sonneborn-Berger-like contribution: the opponent's score and what
    it contributes once weighted by the result against them."""

    opponent_score: float
    value: float
    voluntary_unplayed: bool


def cut_least_significant(
    contributions: Iterable[WeightedContribution], cuts: int
) -> list[WeightedContribution]:
    """The contributions left once *cuts* least significant values are cut.

    Art. 14.1.1.d: the least significant value is the contribution of the
    opponent with the lowest score, and the lowest such contribution where
    several opponents share that score. Art. 16.5.1: against it stands the
    lowest contribution coming from a voluntary unplayed round, and the one
    cut is whichever of the two is worth more -- the same element when the
    least significant value is itself such a round. Two unplayed rounds
    alike are told apart by the lower opponent score, as Art. 14.1.1.d
    tells apart contributions of equal opponents."""
    kept = list(contributions)
    for _cut in range(cuts):
        if not kept:
            break
        least = min(kept, key=lambda entry: (entry.opponent_score, entry.value))
        cut_away = least
        unplayed = [entry for entry in kept if entry.voluntary_unplayed]
        if unplayed:
            lowest = min(
                unplayed, key=lambda entry: (entry.value, entry.opponent_score)
            )
            if lowest.value >= least.value:
                cut_away = lowest
        kept.remove(cut_away)
    return kept
