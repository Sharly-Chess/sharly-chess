from functools import total_ordering
from logging import Logger
from dataclasses import dataclass

from common.logger import get_logger
from data.util import Result
from data.player import Player

logger: Logger = get_logger()


@dataclass
@total_ordering
class Board:
    """The Board class, represented by its index in the board order and its
    display number (fixed tables).
    Stores both players and the result of the match between the two."""

    board_id: int | None = None
    number: int | None = None
    white_player: Player | None = None
    black_player: Player | None = None
    result: Result | None = None

    @property
    def id(self) -> int | None:
        return self.board_id

    @property
    def exempt(self) -> bool:
        return self.result == Result.PAIRING_ALLOCATED_BYE

    @id.setter
    def id(self, new_id):
        self.board_id = new_id

    @property
    def result_str(self) -> str:
        return str(self.result) if self.result else ''

    def __lt__(self, other):
        # p1 < p2 calls p1.__lt__(p2)
        if not isinstance(other, Board):
            return NotImplemented
        if self.board_id is not None and other.board_id is not None:
            return self.board_id < other.board_id
        if self.black_player is None:
            # The pairing allocated bye board is last
            return True
        elif other.black_player is None:
            # The pairing allocated bye is last
            return False
        # Here we have no board id, so we need to compare
        # the highest-scoring players
        self_player_1: Player
        self_player_2: Player
        if self.white_player < self.black_player:
            self_player_1 = self.black_player
            self_player_2 = self.white_player
        else:
            self_player_1 = self.white_player
            self_player_2 = self.black_player
        # Here self_player_1 is the strongest player of this board
        other_player_1: Player
        other_player_2: Player
        if other.white_player < other.black_player:
            other_player_1 = other.black_player
            other_player_2 = other.white_player
        else:
            other_player_1 = other.white_player
            other_player_2 = other.black_player
        # Here other_player_1 is the strongest player of the other board
        if self_player_1.vpoints < other_player_1.vpoints:
            return True
        if self_player_1.vpoints > other_player_1.vpoints:
            return False
        if self_player_2.vpoints < other_player_2.vpoints:
            return True
        if self_player_2.vpoints > other_player_2.vpoints:
            return False
        if self_player_1 < other_player_1:
            return True
        if self_player_1 > other_player_1:
            return False
        return self_player_2 < other_player_2

    def __eq__(self, other):
        # p1 == p2 calls p1.__eq__(p2)
        if not isinstance(other, Board):
            return NotImplemented
        if self.board_id is not None and other.board_id is not None:
            return self.board_id == other.board_id
        assert self.black_player is not None, 'The black player is not defined.'
        assert other.black_player is not None, 'The black player is not defined.'
        # There is only one pairing allocated bye
        if self.black_player is None:
            return False
        self_player_1: Player
        self_player_2: Player
        if self.white_player < self.black_player:
            self_player_1 = self.black_player
            self_player_2 = self.white_player
        else:
            self_player_1 = self.white_player
            self_player_2 = self.black_player
        other_player_1: Player
        other_player_2: Player
        if other.white_player < other.black_player:
            other_player_1 = other.black_player
            other_player_2 = other.white_player
        else:
            other_player_1 = other.white_player
            other_player_2 = other.black_player
        return self_player_1 == other_player_1 and self_player_2 == other_player_2

    def __repr__(self):
        return f'{self.__class__.__name__}({self.number}. {self.white_player} {self.result_str} {self.black_player})'
