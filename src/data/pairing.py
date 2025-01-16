from logging import Logger
from common.logger import get_logger
from dataclasses import dataclass

from data.util import Result

logger: Logger = get_logger()


@dataclass(frozen=True)
class Pairing:
    """A pairing (from the point of view of the `Player` class)"""
    color: str | None = None
    opponent_id: int | None = None
    opponent_papi_id: int | None = None
    result: Result | None = None

    @property
    def forfeit(self) -> bool:
        return (self.result == Result.NO_RESULT) and (self.color == 'F')

    @property
    def not_paired(self) -> bool:
        return (self.result == Result.NO_RESULT) and (self.color == 'R') and (self.opponent_id is None)

    @property
    def playing(self) -> bool:
        return (self.result == Result.NO_RESULT) and (self.opponent_id is not None)

    @property
    def exempt(self) -> bool:
        return (self.result == Result.PAB_OR_FORFEIT_GAIN_OR_FPB) \
            and (self.opponent_papi_id is not None) and (self.opponent_papi_id == 1)

    @property
    def loss(self) -> bool:
        return self.result == Result.LOSS

    @property
    def draw(self) -> bool:
        return (self.result == Result.DRAW_OR_HPB) and (self.opponent_papi_id is not None)

    @property
    def gain(self) -> bool:
        return self.result == Result.GAIN

    @property
    def half_point_bye(self) -> bool:
        return (self.result == Result.DRAW_OR_HPB) and (self.opponent_papi_id is None)

    @property
    def full_point_bye(self) -> bool:
        return (self.result == Result.PAB_OR_FORFEIT_GAIN_OR_FPB) and (self.opponent_papi_id is None)

    @property
    def forfeit_loss(self) -> bool:
        return self.result == Result.FORFEIT_LOSS

    @property
    def double_forfeit(self) -> bool:
        return self.result == Result.DOUBLE_FORFEIT

    @property
    def forfeit_gain(self) -> bool:
        return (self.result == Result.PAB_OR_FORFEIT_GAIN_OR_FPB) \
            and (self.opponent_papi_id is not None) and (self.opponent_papi_id > 1)

    def __repr__(self):
        return f'{self.__class__.__name__}({self.color} {self.opponent_id} {self.result})'
