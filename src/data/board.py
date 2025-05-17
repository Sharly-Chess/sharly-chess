from functools import total_ordering
from dataclasses import dataclass
from typing import TYPE_CHECKING

from common import format_timestamp
from utils.enum import Result, PlayerRatingType
from data.player import Player

if TYPE_CHECKING:
    from data.tournament import Tournament


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
    result: Result = Result.NO_RESULT

    @property
    def id(self) -> int | None:
        return self.board_id

    @id.setter
    def id(self, new_id):
        self.board_id = new_id

    @property
    def exempt(self) -> bool:
        return self.result in (Result.PAIRING_ALLOCATED_BYE, Result.REST_GAME)

    @property
    def no_result(self) -> bool:
        return self.result == Result.NO_RESULT

    @property
    def result_str(self) -> str:
        return str(self.result) if self.result else ''

    @property
    def white_player_id(self) -> int | None:
        if self.white_player:
            return self.white_player.id
        return None

    @property
    def black_player_id(self) -> int | None:
        if self.black_player:
            return self.black_player.id
        return None

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
    def _player_to_pgn(cls, player: Player | None, is_white: bool) -> str:
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
        if self.white_player is None:
            raise ValueError('The white player is not defined.')
        if self.white_player < self.black_player:
            self_player_1 = self.black_player
            self_player_2 = self.white_player
        else:
            self_player_1 = self.white_player
            self_player_2 = self.black_player
        # Here self_player_1 is the strongest player of this board
        other_player_1: Player
        other_player_2: Player
        if other.white_player is None:
            raise ValueError('The white player is not defined.')
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
        if self.board_id is not None and other.board_id is not None:
            return self.board_id == other.board_id
        if self.black_player is None or other.black_player is None:
            raise ValueError('The black player is not defined.')
        # There is only one pairing allocated bye
        self_player_1: Player
        self_player_2: Player
        if self.white_player is None:
            raise ValueError('The white player is not defined.')
        if self.white_player < self.black_player:
            self_player_1 = self.black_player
            self_player_2 = self.white_player
        else:
            self_player_1 = self.white_player
            self_player_2 = self.black_player
        other_player_1: Player
        other_player_2: Player
        if other.white_player is None:
            raise ValueError('The white player is not defined.')
        if other.white_player < other.black_player:
            other_player_1 = other.black_player
            other_player_2 = other.white_player
        else:
            other_player_1 = other.white_player
            other_player_2 = other.black_player
        return self_player_1 == other_player_1 and self_player_2 == other_player_2

    def __repr__(self):
        return f'{self.__class__.__name__}({self.number}. {self.white_player} {self.result_str} {self.black_player})'
