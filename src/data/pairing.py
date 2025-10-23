import weakref
from typing import TYPE_CHECKING, Optional

from trf.Player import Game as TrfGame

from logging import Logger
from common.logger import get_logger
from data.board import Board
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPairing
from utils import Utils
from utils.enum import Result, BoardColor

if TYPE_CHECKING:
    from _weakref import ReferenceType
    from data.player import Player

logger: Logger = get_logger()


class Pairing:
    """A pairing (from the point of view of the `Player` class)"""

    def __init__(
        self, player: 'Player', stored_pairing: StoredPairing, exists: bool = True
    ):
        self._player_ref: 'ReferenceType[Player]' = weakref.ref(player)
        self.stored_pairing = stored_pairing

        # NOTE (Molrn) Flag indicating if the stored object exists in the database or not.
        # Pre-big move, the unpaired rounds had their own *Pairing* objects in the DB
        # This maintains the legacy usages of the *Pairing* class
        # TODO Remove all *Pairing* legacy usages (and this flag)
        self.exists = exists

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

    @property
    def points(self) -> float:
        return self.result.points(self.player.point_values)

    @property
    def points_str(self) -> str:
        return Utils.points_str(self.points)

    @property
    def illegal_moves(self) -> int:
        return self.stored_pairing.illegal_moves

    def update_result(self, event_database: EventDatabase, result: Result):
        self.stored_pairing.result = result.value
        self.update(event_database)

    def update(self, event_database: EventDatabase):
        if self.exists:
            event_database.update_stored_pairing(self.stored_pairing)
        else:
            event_database.add_stored_pairing(self.stored_pairing)
            self.exists = True

    def add_illegal_move(self, event_database: EventDatabase):
        if self.illegal_moves < self.player.tournament.record_illegal_moves:
            self.stored_pairing.illegal_moves += 1
            self.update(event_database)
            logger.info(
                'An illegal move has been recorded for player [%s].', self.player.id
            )
            return True
        return False

    def delete_illegal_move(self, event_database: EventDatabase):
        if self.illegal_moves > 0:
            self.stored_pairing.illegal_moves -= 1
            self.update(event_database)
            logger.info(
                'An illegal move has been deleted for player [%s].', self.player.id
            )
            return True
        else:
            logger.info('No illegal move found for player [%s].', self.player.id)
            return False

    @property
    def zero_point_bye(self) -> bool:
        return self.result == Result.ZERO_POINT_BYE

    @property
    def needs_pairing(self) -> bool:
        return (self.result == Result.NO_RESULT) and (self.opponent_id is None)

    @property
    def needs_pairing_or_has_bye(self) -> bool:
        return self.opponent_id is None

    @property
    def paired(self) -> bool:
        return not self.needs_pairing_or_has_bye

    @property
    def paired_no_result(self) -> bool:
        return (self.result == Result.NO_RESULT) and (self.opponent_id is not None)

    @property
    def exempt(self) -> bool:
        return self.result.is_board_bye

    @property
    def loss(self) -> bool:
        return self.result.is_loss

    @property
    def unrated_loss(self) -> bool:
        return self.result.is_unrated_loss

    @property
    def draw(self) -> bool:
        return self.result.is_draw

    @property
    def unrated_draw(self) -> bool:
        return self.result.is_unrated_draw

    @property
    def win(self) -> bool:
        return self.result.is_win

    @property
    def unrated_gain(self) -> bool:
        return self.result == Result.UNRATED_WIN

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
        return self.result == Result.FORFEIT_WIN

    @property
    def unplayed(self) -> bool:
        return self.result.is_unplayed

    @property
    def played(self) -> bool:
        return not self.unplayed

    @property
    def voluntary_unplayed(self) -> bool:
        return self.result.is_voluntary_unplayed

    @property
    def requested_bye(self) -> bool:
        return self.result.is_requested_bye

    @property
    def next_round_bye(self) -> bool:
        return self.result.is_next_round_bye

    def to_trf(self, round_number: int) -> TrfGame:
        from data.input_output.trf_mappers import TrfColor

        return TrfGame(
            startrank=(
                0
                if self.result.is_bye
                else getattr(self.opponent, 'pairing_number', None)
            ),
            color=TrfColor.get_outer_value(self.color, self.result.is_bye),
            result=self.result.to_trf,
            round=round_number,
        )

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
    def opponent(self) -> Optional['Player']:
        board = self.board
        if not board or not board.black_player:
            return None
        return (
            board.black_player if self.color == BoardColor.WHITE else board.white_player
        )

    @property
    def opponent_id(self) -> int | None:
        opponent = self.opponent
        return opponent.id if opponent else None

    def __str__(self):
        return f'{self.__class__.__name__}({self.color} {self.opponent_id} {self.result.to_trf})'

    def __repr__(self):
        return f'{self.__class__.__name__}(player={self.player!r}, stored_pairing={self.stored_pairing!r}, exists={self.exists!r})'
