"""Pure-data team match records used by team tie-breaks.

These are intentionally decoupled from the SQLite-backed Team / TeamBoard
models so that tie-break logic can be tested by constructing records
directly from a published crosstable (see TEC-2023 exercises 34-49).
The ``Tournament.team_records()`` helper builds them at runtime from
``team_boards_by_round``.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from utils.enum import ScoreType


class TeamMatchType(StrEnum):
    """Kind of match a team played in a given round.

    Maps to FIDE Art. 16 categories for tie-break unplayed-rounds
    handling. ``PLAYED`` is the normal case; the rest are unplayed
    variants that change how the match contributes to opponents'
    Buchholz / SB calculations and to the team's own dummy opponent."""

    PLAYED = 'PLAYED'
    PAB = 'PAB'  # Pairing-allocated bye (no opponent, scored as a win)
    HPB = 'HPB'  # Half-point bye (no opponent, scored as a draw)
    ZPB = 'ZPB'  # Zero-point bye (requested, no subsequent play)
    FORFEIT_WIN = 'FORFEIT_WIN'  # +F
    FORFEIT_LOSS = 'FORFEIT_LOSS'  # -F


@dataclass(frozen=True)
class TeamMatchRecord:
    """One team's record for one round.

    ``own_mp`` / ``own_gp`` are the score the *team* obtained; for
    unplayed matches these follow the tournament regulations (PAB and
    HPB typically award match points equal to a win or a draw and the
    GP value specified in the rules — TEC test data: PAB / HPB → 1 MP,
    2 GP; ZPB / -F → 0/0; +F → 2 MP, 4 GP).

    ``opponent_id`` is None for byes (PAB / HPB / ZPB); for forfeit
    wins / losses the opponent is the originally scheduled team.
    """

    round_: int
    opponent_id: int | None
    own_mp: float
    own_gp: float
    match_type: TeamMatchType
    # Per-board own scores in board-order (board 1 first). Empty when
    # the consumer doesn't need board-level data; tie-breaks that rely
    # on board weighting (FFE Berlin, BC / TBR / BBE) require this.
    board_scores: tuple[float, ...] = ()
    # Per-board own players' ratings, parallel to ``board_scores``.
    # ``None`` for unrated players or boards with no player attributed.
    # Used by tie-breaks that average own-team ratings.
    board_ratings: tuple[int | None, ...] = ()

    @property
    def played(self) -> bool:
        return self.match_type == TeamMatchType.PLAYED

    @property
    def unplayed(self) -> bool:
        return not self.played

    @property
    def voluntary_unplayed(self) -> bool:
        """HPB, ZPB and forfeit losses are voluntary absences (Art. 16.5
        VUR rule). Their contributions are cut before any other when a
        Cut-1 / Cut-2 modifier applies, provided they are not greater
        than the standard least-significant value."""
        return self.match_type in (
            TeamMatchType.HPB,
            TeamMatchType.ZPB,
            TeamMatchType.FORFEIT_LOSS,
        )

    @property
    def is_bye(self) -> bool:
        return self.match_type in (
            TeamMatchType.PAB,
            TeamMatchType.HPB,
            TeamMatchType.ZPB,
        )


@dataclass
class TeamRecord:
    """All the data about one team that team tie-breaks consume."""

    team_id: int
    name: str
    total_mp: float
    total_gp: float
    matches: list[TeamMatchRecord] = field(default_factory=list)
    # Tournament pairing number (1-based). Set by ``Tournament.team_records``
    # from the underlying :class:`Team`. Required by TPN.
    pairing_number: int | None = None

    def match_at(self, round_: int) -> TeamMatchRecord | None:
        for match in self.matches:
            if match.round_ == round_:
                return match
        return None

    def total(self, score_type: ScoreType) -> float:
        """Total of the requested score type (primary or secondary)."""
        return self.total_mp if score_type == ScoreType.MATCH_POINTS else self.total_gp

    def own_against(self, match: TeamMatchRecord, score_type: ScoreType) -> float:
        """The team's own MP or GP scored in a given round's match."""
        return match.own_mp if score_type == ScoreType.MATCH_POINTS else match.own_gp


def adjust_opponent_total(
    opponent: 'TeamRecord',
    score_type: ScoreType,
    *,
    after_round: int,
    draw_mp: float,
    draw_gp: float,
    adjust_fore: bool = False,
) -> float:
    """``opponent``'s total ``score_type`` adjusted for tie-break use by
    *other* teams. ZPB rounds not followed by any played round (Art.
    16.2.5) are reclassified as a draw (Art. 16.3.2); the opponent's
    own tie-breaks still use the actual score (Art. 16.4) — adjustment
    is one-sided.

    When ``adjust_fore`` is True (Fore Buchholz), the *last* round
    contribution is replaced with a draw — "all paired games for the
    final round are considered draws"."""
    total = 0.0
    seen_played_or_pab = False
    draw_val = draw_mp if score_type == ScoreType.MATCH_POINTS else draw_gp
    for match in sorted(
        (m for m in opponent.matches if m.round_ <= after_round),
        key=lambda m: m.round_,
        reverse=True,
    ):
        own = opponent.own_against(match, score_type)
        if adjust_fore and match.round_ == after_round:
            total += draw_val
        elif match.match_type == TeamMatchType.ZPB and not seen_played_or_pab:
            total += draw_val
        else:
            total += own
        if match.played or match.match_type == TeamMatchType.PAB:
            seen_played_or_pab = True
    return total


def dummy_opponent_score(
    own_record: 'TeamRecord',
    score_type: ScoreType,
    *,
    after_round: int,
    rounds: int,
    win_mp: float,
) -> float:
    """Score attributed to the virtual opponent when our team had an
    unplayed match (Art. 16.4). Equals the team's own actual total,
    capped at the maximum primary score (``rounds × win_mp`` for MP).
    For GP there is no FIDE-defined hard cap; the own total stands."""
    own_total = own_record.total(score_type)
    if score_type == ScoreType.MATCH_POINTS:
        return min(own_total, rounds * win_mp)
    return own_total
