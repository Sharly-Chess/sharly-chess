import weakref
from typing import Callable, TYPE_CHECKING

from trf.Player import Game as TrfGame

from data.board import Board
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPairing
from utils.enum import Result, BoardColor

if TYPE_CHECKING:
    from _weakref import ReferenceType
    from data.player import Player


class Pairing:
    """A pairing (from the point of view of the `Player` class)"""

    def __init__(self, player: 'Player', stored_pairing: StoredPairing):
        self._player_ref: 'ReferenceType[Player]' = weakref.ref(player)
        self.stored_pairing = stored_pairing

    @property
    def player(self) -> 'Player':
        if (player := self._player_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return player

    @property
    def board(self) -> Board | None:
        if not (board_id := self.stored_pairing.board_id):
            return None
        return self.player.tournament.boards_by_id[board_id]

    @property
    def round(self) -> int:
        return self.stored_pairing.round_

    @property
    def result(self) -> Result:
        return Result(self.stored_pairing.result)

    def update_result(self, event_database: EventDatabase, result: Result):
        self.stored_pairing.result = result.value
        event_database.update_stored_pairing_result(self.stored_pairing)

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
        return self.result in (Result.PAIRING_ALLOCATED_BYE, Result.REST_GAME)

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
            Result.REST_GAME,
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

    # --------------------------------------------------------------------------
    # Legacy
    # --------------------------------------------------------------------------

    @property
    def color(self) -> BoardColor | None:
        if not (board := self.board):
            return None
        return (
            BoardColor.WHITE
            if board.white_player.id == self.player.id
            else BoardColor.BLACK
        )

    @property
    def opponent_id(self) -> int | None:
        board = self.board
        if not board or not board.black_player:
            return None
        return (
            board.black_player.id
            if self.color == BoardColor.WHITE
            else board.white_player.id
        )
