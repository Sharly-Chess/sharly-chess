import random
from dataclasses import dataclass, field
from typing import Any, Self

import chess
import chess.svg

from plugins.utils import PluginData

MIN_POSITION: int = 0
MAX_POSITION: int = 959


def random_position_number() -> int:
    """A random Chess960 start-position number (0-959)."""
    return random.randint(MIN_POSITION, MAX_POSITION)


def is_valid_position_number(number: int | None) -> bool:
    return number is not None and MIN_POSITION <= number <= MAX_POSITION


def board_svg(number: int | None) -> str | None:
    """An inline SVG rendering of the Chess960 start position *number*, or
    ``None`` when the number is missing or out of range."""
    if not is_valid_position_number(number):
        return None
    assert number is not None
    board = chess.Board.from_chess960_pos(number)
    # No size: the SVG keeps only its viewBox, so it scales to its container.
    return chess.svg.board(board)


@dataclass
class Chess960Set:
    """One tournament's start positions on a screen, keyed by round."""

    tournament_id: int
    positions: dict[int, int] = field(default_factory=dict)

    def position_for_round(self, round_: int) -> int | None:
        """The position for *round_*, falling back to the latest earlier round
        that has one (so a position need not be entered for every round)."""
        best: int | None = None
        for stored_round in sorted(self.positions):
            if stored_round <= round_:
                best = self.positions[stored_round]
            else:
                break
        return best

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'tournament_id': self.tournament_id,
            'positions': {
                str(round_): number for round_, number in sorted(self.positions.items())
            },
        }

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            tournament_id=int(stored_value['tournament_id']),
            positions={
                int(round_): int(number)
                for round_, number in (stored_value.get('positions') or {}).items()
                if number is not None
            },
        )


@dataclass
class Chess960ScreenPluginData(PluginData):
    show_all_rounds: bool = False
    fit_to_screen: bool = True
    sets: list[Chess960Set] = field(default_factory=list)

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        stored_value = stored_value or {}
        return cls(
            show_all_rounds=bool(stored_value.get('show_all_rounds', False)),
            fit_to_screen=bool(stored_value.get('fit_to_screen', True)),
            sets=[
                Chess960Set.from_stored_value(stored_set)
                for stored_set in stored_value.get('sets', [])
            ],
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'show_all_rounds': self.show_all_rounds,
            'fit_to_screen': self.fit_to_screen,
            'sets': [stored_set.to_stored_value() for stored_set in self.sets],
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        # The screen form only carries the toggles; the sets are managed from
        # the Positions modal, so they are preserved as-is.
        sets = list(previous_object.sets) if previous_object is not None else []
        return cls(
            show_all_rounds=data.get('show_all_rounds') == 'true',
            fit_to_screen=data.get('fit_to_screen') == 'true',
            sets=sets,
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return {
            'show_all_rounds': 'true' if self.show_all_rounds else '',
            'fit_to_screen': 'true' if self.fit_to_screen else '',
        }
