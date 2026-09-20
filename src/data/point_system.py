"""What a tournament's results are worth.

A tournament stores only the values its arbiter overrode; the FIDE
defaults fill in the rest, and which default applies depends on the
kind of tournament and on its pairing system. Working that out once,
here, gives every reader — standings, tie-breaks, the TRF export, the
prohibited pairings — the same figures.
"""

from dataclasses import dataclass
from functools import cached_property

from utils.enum import Result, ScoreType


@dataclass(frozen=True)
class PointSystem:
    """The points a tournament awards, per result.

    ``pab_is_draw`` says what an engine-allocated bye is worth to a team
    by default: a drawn match under the Team Swiss system (FIDE C.04.6
    §1.4, which also avoids over-rewarding an odd team out), a won match
    under the others. ``bye_is_rest`` says whether such a bye is a rest
    game (round robin, two-game matches: not played, no points) rather
    than a points-scoring PAB. ``boards`` is the number of boards of a
    team match, since a team PAB stands in for a whole match.
    """

    game_point_overrides: dict[int, float]
    match_point_overrides: dict[int, float]
    is_team: bool
    boards: int
    pab_is_draw: bool
    bye_is_rest: bool
    primary_score: ScoreType

    @cached_property
    def game_points(self) -> dict[Result, float]:
        """Game points awarded per result on an individual board game.
        Team tournaments always use the standard 1 / 0.5 / 0 FIDE
        defaults — team-level PAB / match scoring lives in
        :attr:`match_points`. The override only applies to individual
        tournaments. Individual default: WIN=1, DRAW=0.5, LOSS=0,
        ZPB=LOSS, PAB=WIN."""
        if self.is_team:
            return {
                r: r.point_value
                for r in (
                    Result.WIN,
                    Result.DRAW,
                    Result.LOSS,
                    Result.ZERO_POINT_BYE,
                    Result.PAIRING_ALLOCATED_BYE,
                )
            }
        raw = self.game_point_overrides
        win = float(raw.get(Result.WIN.value, 1.0))
        draw = float(raw.get(Result.DRAW.value, 0.5))
        loss = float(raw.get(Result.LOSS.value, 0.0))
        return {
            Result.WIN: win,
            Result.DRAW: draw,
            Result.LOSS: loss,
            Result.ZERO_POINT_BYE: float(raw.get(Result.ZERO_POINT_BYE.value, loss)),
            Result.PAIRING_ALLOCATED_BYE: float(
                raw.get(Result.PAIRING_ALLOCATED_BYE.value, win)
            ),
        }

    @cached_property
    def team_game_points(self) -> dict[Result, float]:
        """Per-board game points awarded to a team for an individual
        result. The same override carries the values (3/2/1 etc. via
        the tournament modal); team scoring respects it, while
        :attr:`game_points` (used for individual rankings within the
        team and for individual mode) stays at the FIDE defaults.
        Defaults: WIN=1, DRAW=0.5, LOSS=0, ABS / FORFAIT fall back to
        LOSS unless the form sets ``gp_zpb`` explicitly (e.g. a
        federation rule scoring forfeits as -1)."""
        raw = self.game_point_overrides
        loss = float(raw.get(Result.LOSS.value, 0.0))
        absent = float(raw.get(Result.ZERO_POINT_BYE.value, loss))
        return {
            Result.WIN: float(raw.get(Result.WIN.value, 1.0)),
            Result.DRAW: float(raw.get(Result.DRAW.value, 0.5)),
            Result.LOSS: loss,
            Result.ZERO_POINT_BYE: absent,
            # ``Result.points()`` only falls back to LOSS for these;
            # surface the absent override explicitly so a forfeit-loss
            # or double-forfeit also gets the configured value.
            Result.FORFEIT_LOSS: absent,
            Result.DOUBLE_FORFEIT: absent,
        }

    @cached_property
    def match_points(self) -> dict[Result, float]:
        """Points awarded for a team match outcome. Empty for individual
        tournaments. The override only carries what was set; Olympiad
        defaults (2/1/0) fill in the rest.

        ``ZERO_POINT_BYE`` is the absent team's score, whether it was
        left unpaired as absent or forfeited a paired match outright. It
        defaults to LOSS, the score such a team took before the value
        could be set."""
        if not self.is_team:
            return {}
        raw = self.match_point_overrides
        win = float(raw.get(Result.WIN.value, 2.0))
        draw = float(raw.get(Result.DRAW.value, 1.0))
        loss = float(raw.get(Result.LOSS.value, 0.0))
        return {
            Result.WIN: win,
            Result.DRAW: draw,
            Result.LOSS: loss,
            Result.ZERO_POINT_BYE: float(raw.get(Result.ZERO_POINT_BYE.value, loss)),
            Result.PAIRING_ALLOCATED_BYE: float(
                raw.get(
                    Result.PAIRING_ALLOCATED_BYE.value,
                    draw if self.pab_is_draw else win,
                )
            ),
        }

    @cached_property
    def team_pab_game_points(self) -> float:
        """Game points awarded to a team for a PAIRING_ALLOCATED_BYE
        match. An explicit ``gp_pab`` field in the tournament settings
        modal overrides it; the default is a drawn or a won match, per
        ``pab_is_draw``, scaled by the board count."""
        raw = self.game_point_overrides
        per_board = (
            float(raw.get(Result.DRAW.value, Result.DRAW.point_value))
            if self.pab_is_draw
            else float(raw.get(Result.WIN.value, Result.WIN.point_value))
        )
        return float(
            raw.get(Result.PAIRING_ALLOCATED_BYE.value, self.boards * per_board)
        )

    @property
    def secondary_score(self) -> ScoreType:
        """The score basis that isn't the primary — derived, not chosen:
        "The rules of the competition shall state which, between 'match
        points' and 'game points', is called 'primary score'" (FIDE Swiss
        Team Pairing System §1.2.1), the other one being the secondary."""
        if self.primary_score == ScoreType.MATCH_POINTS:
            return ScoreType.GAME_POINTS
        return ScoreType.MATCH_POINTS

    @property
    def win(self) -> float:
        return Result.WIN.points(self.game_points)

    @property
    def draw(self) -> float:
        return Result.DRAW.points(self.game_points)

    @property
    def loss(self) -> float:
        return Result.LOSS.points(self.game_points)

    @property
    def pab(self) -> float:
        return Result.PAIRING_ALLOCATED_BYE.points(self.game_points)

    @property
    def zpb(self) -> float:
        return Result.ZERO_POINT_BYE.points(self.game_points)

    @property
    def is_standard(self) -> bool:
        """Whether the game points are the FIDE default 1 / 0.5 / 0 with
        PAB = 1."""
        return (
            self.win == 1.0
            and self.draw == 0.5
            and self.loss == 0.0
            and self.pab == 1.0
        )

    @property
    def pab_equivalent_result(self) -> Result:
        """Which game result (WIN / DRAW / LOSS) the Pairing Allocated Bye
        is worth, for the formats that express a PAB as one of those."""
        if self.pab == self.win:
            return Result.WIN
        if self.pab == self.draw:
            return Result.DRAW
        if self.pab == self.loss:
            return Result.LOSS
        return Result.WIN
