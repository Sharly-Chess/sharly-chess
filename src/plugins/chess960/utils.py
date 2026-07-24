import random
from dataclasses import dataclass
from typing import Any, Self

import chess
import chess.svg

from plugins.utils import PluginData

MIN_POSITION: int = 1
MAX_POSITION: int = 960


def random_position_number() -> int:
    """A random Chess960 start-position number (1-960)."""
    return random.randint(MIN_POSITION, MAX_POSITION)


def is_valid_position_number(number: int) -> bool:
    return MIN_POSITION <= number <= MAX_POSITION


def board_svg(number: int) -> str | None:
    """An inline SVG rendering of the Chess960 start position *number*, or
    ``None`` when the number is missing or out of range."""
    if not is_valid_position_number(number):
        return None
    board = chess.Board.from_chess960_pos(number)
    # No size: the SVG keeps only its viewBox, so it scales to its container.
    return chess.svg.board(board)


@dataclass
class Chess960ScreenPluginData(PluginData):
    chess960_number: int = 0

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        stored_value = stored_value or {}
        return cls(
            chess960_number=stored_value.get('chess960_number', 0),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'chess960_number': self.chess960_number,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        return cls(
            chess960_number=int(data.get('chess960_number') or '0'),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return {
            'chess960_number': str(self.chess960_number)
            if self.chess960_number
            else '',
        }
