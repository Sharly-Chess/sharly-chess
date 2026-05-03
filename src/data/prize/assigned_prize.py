from dataclasses import dataclass
from typing import TYPE_CHECKING

from data.player import TournamentPlayer
from data.prize.prize_type import MonetaryPrizeType

if TYPE_CHECKING:
    from data.prize.prize import Prize


@dataclass
class AssignedPrize:
    prize: 'Prize'
    priority: int
    place_index: int
    assigned_to: TournamentPlayer | None
    value: float = 0.0
    warning: str | None = None
    is_own: bool = True
    is_main: bool = False

    @property
    def name(self) -> str:
        type_ = self.prize.type if self.is_own else MonetaryPrizeType()
        return type_.get_prize_name(
            self.value, self.prize.description, self.prize.currency
        )

    @property
    def full_name(self) -> str:
        type_ = self.prize.type if self.is_own else MonetaryPrizeType()
        return type_.get_prize_full_name(
            self.value,
            self.prize.description,
            self.prize.currency,
            self.prize.complementary_value if self.is_own else None,
        )
