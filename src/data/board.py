import weakref
from functools import total_ordering
from typing import TYPE_CHECKING, Optional, Literal

from common import format_timestamp
from database.access.papi.papi_store import StoredBoard
from utils.enum import Result, PlayerRatingType

if TYPE_CHECKING:
    from _weakref import ReferenceType
    from data.pairing import Pairing
    from data.player import Player
    from data.tournament import Tournament


@total_ordering
class Board:
    """The Board class, represented by its index in the board order and its
    display number (fixed tables).
    Stores both players and the result of the match between the two."""

    def __init__(
        self, tournament: 'Tournament', round_: int, stored_board: StoredBoard
    ):
        self.round = round_
        self.stored_board = stored_board
        self._white_player_ref: 'ReferenceType[Player]' = weakref.ref(
            tournament.players_by_id[stored_board.white_player_id]
        )
        self._black_player_ref: Optional['ReferenceType[Player]'] = (
            weakref.ref(tournament.players_by_id[stored_board.black_player_id])
            if stored_board.black_player_id
            else None
        )

    @property
    def white_player(self) -> 'Player':
        if (player := self._white_player_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return player

    @property
    def black_player(self) -> Optional['Player']:
        if not self._black_player_ref:
            return None
        if (player := self._black_player_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return player

    @property
    def white_pairing(self) -> 'Pairing':
        return self.white_player.pairings_by_round[self.round]

    @property
    def black_pairing(self) -> Optional['Pairing']:
        if not self.black_player:
            return None
        return self.black_player.pairings_by_round[self.round]

    @property
    def identifier(self) -> int:
        # TODO (Molrn - Big move) rename to *id* once *Board.id*'s usages have been replaced
        assert self.stored_board.id is not None
        return self.stored_board.id

    @property
    def index(self) -> int:
        return self.stored_board.index

    @property
    def number(self) -> int:
        return (
            self.white_player.fixed
            or getattr(self.black_player, 'fixed', None)
            or self.white_player.tournament.first_board_number + self.index
        )

    @property
    def result(self) -> Result:
        return self.white_pairing.result

    @property
    def no_result(self) -> bool:
        return self.result == Result.NO_RESULT

    @property
    def result_str(self) -> str:
        return str(self.result)

    def replace_player(
        self, new_player: 'Player', player_color: Literal['white', 'black']
    ):
        if player_color == 'white':
            self._white_player_ref = weakref.ref(new_player)
            self.stored_board.white_player_id = new_player.id
        else:
            self._black_player_ref = weakref.ref(new_player)
            self.stored_board.black_player_id = new_player.id

    def permute_colors(self):
        white_player = self.white_player
        black_player = self.black_player
        assert black_player is not None
        self.stored_board.white_player_id = black_player.id
        self.stored_board.black_player_id = white_player.id
        self.replace_player(black_player, 'white')
        self.replace_player(white_player, 'black')

    def to_pgn(
        self,
        tournament: 'Tournament',
        round_: int,
        pairings_usage: bool = True,
    ) -> str:
        assert self.number is not None
        result = self.result.to_pgn if self.result and not pairings_usage else '*'
        return (
            f'[Event "{self._format_pgn_string(tournament.full_name)}"]\n'
            f'[Site "{self._format_pgn_string(tournament.location or "?")}"]\n'
            f'[Date "{format_timestamp(tournament.start_timestamp, "%Y.%m.%d")}"]\n'
            f'[EventDate "{format_timestamp(tournament.event.start, "%Y.%m.%d")}"]\n'
            f'[Round "{round_}.{self.number}"]\n'
            + self._player_to_pgn(self.white_player, True)
            + self._player_to_pgn(self.black_player, False)
            + f'[Result "{result}"]\n'
            '\n*\n\n'
        )

    @classmethod
    def _player_to_pgn(cls, player: Optional['Player'], is_white: bool) -> str:
        field_prefix = 'White' if is_white else 'Black'
        if player is None:
            return f'[{field_prefix} ""]'
        rating = player.rating if player.rating_type == PlayerRatingType.FIDE else '-'
        name = f'{player.last_name}, {player.first_name or "?"}'
        return (
            f'[{field_prefix} "{cls._format_pgn_string(name)}"]\n'
            f'[{field_prefix}Title "{player.title.to_fide_value or "-"}"]\n'
            f'[{field_prefix}Elo "{rating or "-"}"]\n'
        )

    @staticmethod
    def _format_pgn_string(string: str) -> str:
        return string[:255].replace('\\', '\\\\').replace('"', '\\"')

    def __lt__(self, other):
        # p1 < p2 calls p1.__lt__(p2)
        if not isinstance(other, Board):
            return NotImplemented
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

        # We should have vpoints for all players at this point
        assert self_player_1.vpoints is not None, 'Self Player 1 has no vpoints.'
        assert other_player_1.vpoints is not None, 'Other Player 1 has no vpoints.'
        assert self_player_2.vpoints is not None, 'Self Player 2 has no vpoints.'
        assert other_player_2.vpoints is not None, 'Other Player 2 has no vpoints.'

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
        if self.black_player is None or other.black_player is None:
            raise ValueError('The black player is not defined.')
        # There is only one pairing allocated bye
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

    # --------------------------------------------------------------------------
    # Legacy
    # --------------------------------------------------------------------------

    @property
    def board_id(self) -> int:
        return self.index + 1

    @property
    def id(self) -> int:
        return self.index + 1

    @property
    def exempt(self) -> bool:
        return self.black_player is None
