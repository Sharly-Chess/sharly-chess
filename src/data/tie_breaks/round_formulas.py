"""Tie-breaks that are a count over a participant's rounds, the same for
individuals and teams (C.07 Art. 7.1 and 7.2)."""

from collections.abc import Iterable

from data.tie_breaks.unplayed_rounds import RoundRecord


def rounds_won(rounds: Iterable[RoundRecord], *, after_round: int, win: float) -> int:
    """WIN: the rounds that gave a win's points, played or not (Art. 7.1)."""
    return sum(
        1 for record in rounds if record.round_ <= after_round and record.points == win
    )


def games_won(rounds: Iterable[RoundRecord], *, after_round: int, win: float) -> int:
    """WON: the games or matches won over the board (Art. 7.2)."""
    return sum(
        1
        for record in rounds
        if record.round_ <= after_round and record.played and record.points == win
    )
