from dataclasses import dataclass
from data.prize.prize import Prize
from data.player import Player


@dataclass
class AssignedPrize:
    prize: Prize
    priority: int
    place_index: int
    assigned_to: Player | None
    value: float = 0.0
    warning: str | None = None
    is_main: bool = False
