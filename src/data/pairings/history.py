from dataclasses import dataclass, field
from typing import List, Literal


Color = Literal['W', 'B'] | None
Result = Literal['win', 'loss', 'draw'] | None
Floater = Literal['none', 'up', 'down'] | None


@dataclass
class Points:
    game: float | int
    virtual: float | int
    total: float | int


@dataclass
class RoundResult:
    round: int
    opponent: int | None
    color: Color
    result: Result
    floater: Floater
    points: Points


@dataclass
class TournamentHistoryPlayer:
    id: int  # pairing number
    rounds: List[RoundResult] = field(default_factory=list)


@dataclass
class TournamentHistory:
    rounds: int
    players: List[TournamentHistoryPlayer] = field(default_factory=list)
