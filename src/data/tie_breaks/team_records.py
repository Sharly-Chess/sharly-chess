"""Pure-data team match records used by team tie-breaks.

These are intentionally decoupled from the SQLite-backed Team / TeamBoard
models so that tie-break logic can be tested by constructing records
directly from a published crosstable (see TEC-2023 exercises 34-49).
The ``Tournament.team_records()`` helper builds them at runtime from
``team_boards_by_round``.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from data.tie_breaks import unplayed_rounds
from data.tie_breaks.unplayed_rounds import RoundRecord
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
    # A drawn match on which no board was played: unplayed for both teams,
    # and a voluntary unplayed round for both, neither having won it.
    UNPLAYED_DRAW = 'UNPLAYED_DRAW'


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
            TeamMatchType.UNPLAYED_DRAW,
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

    def rounds(self, score_type: ScoreType) -> list[RoundRecord]:
        """The team's rounds as Art. 16 reads them, in ``score_type``."""
        return [
            RoundRecord(
                round_=match.round_,
                opponent_id=match.opponent_id,
                points=self.own_against(match, score_type),
                played=match.played,
                requested_bye=match.match_type
                in (TeamMatchType.HPB, TeamMatchType.ZPB),
                voluntary_unplayed=match.voluntary_unplayed,
            )
            for match in self.matches
        ]


def fore_round_is_paired(record: 'TeamRecord', after_round: int) -> bool:
    """Whether Art. 8.3's hypothesis reaches ``record``."""
    return unplayed_rounds.fore_round_is_paired(
        record.rounds(ScoreType.MATCH_POINTS), after_round
    )


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
    *other* teams (Art. 16.3); ``adjust_fore`` is Fore Buchholz's final
    round taken as drawn (Art. 8.3)."""
    return unplayed_rounds.adjusted_score(
        opponent.rounds(score_type),
        after_round=after_round,
        draw=draw_mp if score_type == ScoreType.MATCH_POINTS else draw_gp,
        fore=adjust_fore,
    )


def dummy_opponent_score(
    own_record: 'TeamRecord',
    score_type: ScoreType,
    *,
    rounds: int,
    draw_value: float,
    opponent_adjusted: float | None = None,
    legacy: bool = False,
    fore_after_round: int | None = None,
) -> float:
    """Score attributed to the dummy an unplayed match is played against
    (Art. 16.4), ``opponent_adjusted`` being the scheduled opponent's
    adjusted score for a forfeit. For teams the draw value is read per
    score type, the closing note of Art. 16 defining "points" as match
    points and game points alike.

    ``fore_after_round`` is the final round of a Fore Buchholz: when the
    team was paired for it, its own total counts that match as a draw.
    """
    own_total = own_record.total(score_type)
    if fore_after_round is not None and fore_round_is_paired(
        own_record, fore_after_round
    ):
        final_match = own_record.match_at(fore_after_round)
        assert final_match is not None
        own_total += draw_value - own_record.own_against(final_match, score_type)
    return unplayed_rounds.dummy_score(
        own_total,
        draw=draw_value,
        tournament_rounds=rounds,
        opponent_adjusted=opponent_adjusted,
        legacy=legacy,
    )
