import weakref
from datetime import datetime
from functools import total_ordering
from typing import TYPE_CHECKING, Optional, Literal

from database.sqlite.event.event_store import StoredBoard
from database.sqlite.event.event_database import EventDatabase
from utils.date_time import format_datetime
from utils.enum import Result, PlayerRatingType, PlayerTitle

if TYPE_CHECKING:
    from _weakref import ReferenceType
    from data.pairing import Pairing
    from data.player import TournamentPlayer
    from data.team_board import TeamBoard
    from data.tournament import Tournament


@total_ordering
class Board:
    """The Board class, represented by its index in the board order and its
    display number (fixed tables).
    Stores both tournament players and the result of the match between the two."""

    def __init__(
        self, tournament: 'Tournament', round_: int, stored_board: StoredBoard
    ):
        self.round = round_
        self.stored_board = stored_board
        self._tournament_ref: 'ReferenceType[Tournament]' = weakref.ref(tournament)
        self._white_player_ref: Optional['ReferenceType[TournamentPlayer]'] = (
            weakref.ref(
                tournament.tournament_players_by_id[stored_board.white_player_id]
            )
            if stored_board.white_player_id
            else None
        )
        self._black_player_ref: Optional['ReferenceType[TournamentPlayer]'] = (
            weakref.ref(
                tournament.tournament_players_by_id[stored_board.black_player_id]
            )
            if stored_board.black_player_id
            else None
        )

    @property
    def tournament(self) -> 'Tournament':
        if (tournament := self._tournament_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return tournament

    @property
    def white_tournament_player(self) -> 'TournamentPlayer':
        """Player on the physical white side. Raises if the slot is a
        hole — use ``optional_white_tournament_player`` from hole-aware
        code."""
        player = self.optional_white_tournament_player
        if player is None:
            raise RuntimeError(f'Board {self.stored_board.id} has no white player.')
        return player

    @property
    def optional_white_tournament_player(self) -> Optional['TournamentPlayer']:
        """Player on the physical white side, or ``None`` when the
        slot is a lineup hole (only possible inside a team match)."""
        if not self._white_player_ref:
            return None
        if (player := self._white_player_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return player

    @property
    def black_tournament_player(self) -> Optional['TournamentPlayer']:
        if not self._black_player_ref:
            return None
        if (player := self._black_player_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return player

    @property
    def white_pairing(self) -> 'Pairing':
        return self.white_tournament_player.pairings_by_round[self.round]

    @property
    def optional_white_pairing(self) -> Optional['Pairing']:
        player = self.optional_white_tournament_player
        if player is None:
            return None
        return player.pairings_by_round[self.round]

    @property
    def black_pairing(self) -> 'Pairing':
        assert self.black_tournament_player is not None
        return self.black_tournament_player.pairings_by_round[self.round]

    @property
    def optional_black_pairing(self) -> Optional['Pairing']:
        if self.black_tournament_player is None:
            return None
        return self.black_tournament_player.pairings_by_round[self.round]

    @property
    def identifier(self) -> int:
        # TODO (Molrn - Big move) rename to *id* once *Board.id*'s usages have been replaced
        assert self.stored_board.id is not None
        return self.stored_board.id

    @property
    def index(self) -> int:
        return self.stored_board.index

    @property
    def standard_number(self) -> int:
        return self.tournament.first_board_number + self.index

    @property
    def fixed_number(self) -> int | None:
        white_tp = self.optional_white_tournament_player
        fixed_white: int | None = white_tp.fixed if white_tp else None
        fixed_black: int | None = getattr(self.black_tournament_player, 'fixed', None)
        if fixed_white and fixed_black:
            return max(fixed_white, fixed_black)
        elif fixed_white:
            return fixed_white
        else:
            return fixed_black

    @property
    def number(self) -> int:
        return self.fixed_number or self.standard_number

    @property
    def number_str(self) -> str:
        fixed = self.fixed_number
        standard = self.standard_number
        if fixed:
            return f'{fixed} ({standard})'
        return str(standard)

    @property
    def team_board(self) -> 'TeamBoard | None':
        """The team match this board belongs to, or ``None`` for an
        individual board (no envelope)."""
        team_board_id = self.stored_board.team_board_id
        if team_board_id is None:
            return None
        return self.tournament.team_boards_by_id.get(team_board_id)

    @property
    def team_match_number_str(self) -> str | None:
        """``match.slot`` display for a board inside a team match (e.g.
        ``3.2`` = second board of the match at table 3), or ``None``
        outside team mode."""
        team_board = self.team_board
        if team_board is None:
            return None
        slot = next(
            (
                position
                for position, board in enumerate(team_board.boards, start=1)
                if board.id == self.id
            ),
            None,
        )
        match_number = team_board.display_number
        if match_number is None or slot is None:
            return None
        return f'{match_number}.{slot}'

    @property
    def result(self) -> Result:
        white_pairing = self.optional_white_pairing
        if white_pairing is not None:
            return white_pairing.result
        black_pairing = self.optional_black_pairing
        if black_pairing is not None:
            # White is a hole — black_pairing's result is the *player's*
            # outcome (e.g. ``FORFEIT_WIN`` when the opponent didn't
            # show up). The board-level result string is rendered from
            # white's perspective, so flip it when reversible. Byes
            # (PAB / HPB / FPB / ZPB) stay as-is — they aren't
            # board-level outcomes.
            result = black_pairing.result
            if result.is_bye:
                return result
            try:
                return result.opposite_result
            except ValueError:
                return result
        return Result.NO_RESULT

    @property
    def no_result(self) -> bool:
        return self.result == Result.NO_RESULT

    @property
    def result_str(self) -> str:
        if self.result == Result.PAIRING_ALLOCATED_BYE:
            tournament = self.tournament
            if tournament.pab_points == tournament.win_points:
                return str(Result.PAIRING_ALLOCATED_BYE)
            if tournament.pab_points == tournament.draw_points:
                return str(Result.PENALTY_DL)
            if tournament.pab_points == tournament.loss_points:
                return str(Result.REST_GAME)
            return str(Result.PAIRING_ALLOCATED_BYE)
        return str(self.result)

    @property
    def last_result_update(self) -> datetime | None:
        return self.stored_board.last_result_update

    @property
    def last_result_update_str(self) -> str:
        return (
            format_datetime(self.last_result_update) if self.last_result_update else ''
        )

    def replace_player(
        self, new_player: 'TournamentPlayer', player_color: Literal['white', 'black']
    ):
        if player_color == 'white':
            self._white_player_ref = weakref.ref(new_player)
            self.stored_board.white_player_id = new_player.id
        else:
            self._black_player_ref = weakref.ref(new_player)
            self.stored_board.black_player_id = new_player.id

    def permute_colors(self):
        if self.optional_white_tournament_player is None:
            raise ValueError(
                f'Board [{self.stored_board.id}] has a forfeit hole, '
                'its colors cannot be permuted.'
            )
        white_player = self.white_tournament_player
        black_player = self.black_tournament_player
        assert black_player is not None
        self.replace_player(black_player, 'white')
        self.replace_player(white_player, 'black')
        with EventDatabase(self.tournament.event.uniq_id, True) as database:
            database.update_stored_board(self.stored_board)

    def set_last_result_update(self, new_result: Result, database: EventDatabase):
        """Updates board timestamp. Clears board timestamp if result is NO_RESULT."""
        self.stored_board.last_result_update = database.update_board_last_result_update(
            self.identifier, clear=new_result == Result.NO_RESULT
        )

    def to_pgn(
        self,
        tournament: 'Tournament',
        round_: int,
        pairings_usage: bool = True,
    ) -> str:
        assert self.number is not None
        if self.optional_white_tournament_player is None:
            # A forfeit hole has no game to export.
            return ''
        result = self.result.to_pgn if self.result and not pairings_usage else '*'
        return (
            f'[Event "{self._format_pgn_string(tournament.full_name)}"]\n'
            f'[Site "{self._format_pgn_string(tournament.location or "?")}"]\n'
            f'[Date "{tournament.start_date.strftime("%Y.%m.%d")}"]\n'
            f'[EventDate "{tournament.event.start_date.strftime("%Y.%m.%d")}"]\n'
            f'[Round "{round_}.{self.number}"]\n'
            + self._player_to_pgn(self.white_tournament_player, True)
            + self._player_to_pgn(self.black_tournament_player, False)
            + f'[Result "{result}"]\n'
            '\n*\n\n'
        )

    @classmethod
    def _player_to_pgn(
        cls, tournament_player: Optional['TournamentPlayer'], is_white: bool
    ) -> str:
        field_prefix = 'White' if is_white else 'Black'
        if tournament_player is None:
            return f'[{field_prefix} ""]\n'
        rating = (
            tournament_player.rating
            if tournament_player.rating_type == PlayerRatingType.FIDE
            else '0'
        )
        name = tournament_player.last_name + (
            f', {tournament_player.first_name}' if tournament_player.first_name else ''
        )
        return (
            f'[{field_prefix} "{cls._format_pgn_string(name)}"]\n'
            + (
                f'[{field_prefix}Title "{tournament_player.title.value}"]\n'
                if tournament_player.title != PlayerTitle.NONE
                else ''
            )
            + f'[{field_prefix}Elo "{rating}"]\n'
        )

    @staticmethod
    def _format_pgn_string(string: str) -> str:
        return string[:255].replace('\\', '\\\\').replace('"', '\\"')

    def __lt__(self, other):
        # p1 < p2 calls p1.__lt__(p2)
        if not isinstance(other, Board):
            return NotImplemented
        if self.black_tournament_player is None:
            # The pairing allocated bye board is last
            return True
        elif other.black_tournament_player is None:
            # The pairing allocated bye is last
            return False
        # Here we have no board id, so we need to compare
        # the highest-scoring players
        self_player_1: TournamentPlayer
        self_player_2: TournamentPlayer
        if self.white_tournament_player < self.black_tournament_player:
            self_player_1 = self.black_tournament_player
            self_player_2 = self.white_tournament_player
        else:
            self_player_1 = self.white_tournament_player
            self_player_2 = self.black_tournament_player
        # Here self_player_1 is the strongest player of this board
        other_player_1: TournamentPlayer
        other_player_2: TournamentPlayer
        if other.white_tournament_player < other.black_tournament_player:
            other_player_1 = other.black_tournament_player
            other_player_2 = other.white_tournament_player
        else:
            other_player_1 = other.white_tournament_player
            other_player_2 = other.black_tournament_player

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
        if (
            self.black_tournament_player is None
            or other.black_tournament_player is None
        ):
            raise ValueError('The black player is not defined.')
        # There is only one pairing allocated bye
        self_player_1: TournamentPlayer
        self_player_2: TournamentPlayer
        if self.white_tournament_player < self.black_tournament_player:
            self_player_1 = self.black_tournament_player
            self_player_2 = self.white_tournament_player
        else:
            self_player_1 = self.white_tournament_player
            self_player_2 = self.black_tournament_player
        other_player_1: TournamentPlayer
        other_player_2: TournamentPlayer
        if other.white_tournament_player < other.black_tournament_player:
            other_player_1 = other.black_tournament_player
            other_player_2 = other.white_tournament_player
        else:
            other_player_1 = other.white_tournament_player
            other_player_2 = other.black_tournament_player
        return self_player_1 == other_player_1 and self_player_2 == other_player_2

    def __str__(self):
        return f'{self.__class__.__name__}({self.number}. {self.white_tournament_player} {self.result_str} {self.black_tournament_player})'

    def __repr__(self):
        return f'{self.__class__.__name__}(tournament={self.tournament!r}, round_={self.round!r}, stored_board={self.stored_board!r})'

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
        return self.black_tournament_player is None
