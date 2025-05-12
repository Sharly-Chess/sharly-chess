from dataclasses import dataclass
from typing import Callable

from trf.Player import Game as TrfGame

from utils.enum import Result, BoardColor


@dataclass
class Pairing:
    """A pairing (from the point of view of the `Player` class)"""

    color: BoardColor | None = None
    opponent_id: int | None = None
    result: Result = Result.NO_RESULT

    @property
    def zero_point_bye(self) -> bool:
        return self.result == Result.ZERO_POINT_BYE

    @property
    def not_paired(self) -> bool:
        return (self.result == Result.NO_RESULT) and (self.opponent_id is None)

    @property
    def paired_no_result(self) -> bool:
        return (self.result == Result.NO_RESULT) and (self.opponent_id is not None)

    @property
    def exempt(self) -> bool:
        return self.result == Result.PAIRING_ALLOCATED_BYE

    @property
    def loss(self) -> bool:
        return self.result in (Result.LOSS, Result.UNRATED_LOSS)

    @property
    def unrated_loss(self) -> bool:
        return self.result == Result.UNRATED_LOSS

    @property
    def draw(self) -> bool:
        return self.result in (Result.DRAW, Result.UNRATED_DRAW)

    @property
    def unrated_draw(self) -> bool:
        return self.result == Result.UNRATED_DRAW

    @property
    def gain(self) -> bool:
        return self.result in (Result.GAIN, Result.UNRATED_GAIN)

    @property
    def unrated_gain(self) -> bool:
        return self.result == Result.UNRATED_GAIN

    @property
    def half_point_bye(self) -> bool:
        return self.result == Result.HALF_POINT_BYE

    @property
    def full_point_bye(self) -> bool:
        return self.result == Result.FULL_POINT_BYE

    @property
    def forfeit_loss(self) -> bool:
        return self.result == Result.FORFEIT_LOSS

    @property
    def double_forfeit(self) -> bool:
        return self.result == Result.DOUBLE_FORFEIT

    @property
    def forfeit_gain(self) -> bool:
        return self.result == Result.FORFEIT_GAIN

    @property
    def unplayed(self) -> bool:
        return self.result in (
            Result.NO_RESULT,
            Result.FORFEIT_GAIN,
            Result.FORFEIT_LOSS,
            Result.DOUBLE_FORFEIT,
            Result.HALF_POINT_BYE,
            Result.ZERO_POINT_BYE,
            Result.FULL_POINT_BYE,
            Result.PAIRING_ALLOCATED_BYE,
        )

    @property
    def played(self) -> bool:
        return not self.unplayed

    @property
    def voluntary_unplayed(self) -> bool:
        return self.result in (
            Result.FORFEIT_LOSS,
            Result.DOUBLE_FORFEIT,
            Result.HALF_POINT_BYE,
            Result.ZERO_POINT_BYE,
        )

    @property
    def requested_bye(self) -> bool:
        return self.result in (Result.HALF_POINT_BYE, Result.ZERO_POINT_BYE)

    @property
    def next_round_bye(self) -> bool:
        return self.result in (
            Result.ZERO_POINT_BYE,
            Result.HALF_POINT_BYE,
            Result.FULL_POINT_BYE,
        )

    def to_trf(
        self, round_number: int, player_id_to_trf_id: Callable[[int], int]
    ) -> TrfGame:
        return TrfGame(
            startrank=(
                '0000'
                if self.result.is_bye
                else player_id_to_trf_id(self.opponent_id)
                if self.opponent_id
                else ''
            ),
            color=(
                '-' if self.result.is_bye else self.color.to_trf if self.color else ''
            ),
            result=self.result.to_trf,
            round=round_number,
        )

    def __repr__(self):
        return f'{self.__class__.__name__}({self.color} {self.opponent_id} {self.result.to_trf})'
