from dataclasses import dataclass
from typing import TYPE_CHECKING

from utils import Utils
from utils.enum import BoardColor, Result

if TYPE_CHECKING:
    from data.player import TournamentPlayer
    from data.teams.team_board import TeamBoard


EXTRA_GAME_RESULTS: tuple[Result, ...] = (
    Result.NO_RESULT,
    Result.WIN,
    Result.DRAW,
    Result.LOSS,
    Result.FORFEIT_WIN,
    Result.FORFEIT_LOSS,
    Result.DOUBLE_FORFEIT,
)
"""The results an extra game takes, ``NO_RESULT`` clearing the one it had."""


EXTRA_GAME_ROW_PREFIX = 'x'


def parse_extra_game_row_id(row_id: str) -> tuple[int, str] | None:
    """The team board and the key of the extra game *row_id* names, or
    ``None`` for the id of a board."""
    if not row_id.startswith(EXTRA_GAME_ROW_PREFIX):
        return None
    team_board_id, separator, key = row_id[len(EXTRA_GAME_ROW_PREFIX) :].partition('-')
    if not separator or not team_board_id.isdigit():
        return None
    return int(team_board_id), key


@dataclass(frozen=True)
class ExtraGameSeat:
    """A game a rule set has a team match count beyond its boards: who
    plays it, and the board each side plays it for. ``key`` names the game
    within its match; ``label`` stands where a board has its number, in a
    column a few characters wide, and ``description`` says the same in
    full. A player id is ``None`` when the team fielded nobody."""

    key: str
    label: str
    description: str
    white_board_index: int
    black_board_index: int
    white_player_id: int | None
    black_player_id: int | None


class ExtraGame:
    """A game of a team match played beyond its boards, with its result.
    The result is stored by round and players, so a game whose players
    change is a game still to play."""

    def __init__(self, team_board: TeamBoard, seat: ExtraGameSeat):
        self.team_board = team_board
        self.seat = seat

    @property
    def key(self) -> str:
        return self.seat.key

    @property
    def row_id(self) -> str:
        """What names the game among the rows of the boards of its round,
        which their numeric ids name."""
        return f'{EXTRA_GAME_ROW_PREFIX}{self.team_board.id}-{self.key}'

    @property
    def label(self) -> str:
        return self.seat.label

    @property
    def description(self) -> str:
        return self.seat.description

    @property
    def round(self) -> int:
        return self.team_board.round

    def _tournament_player(self, player_id: int | None) -> TournamentPlayer | None:
        if player_id is None:
            return None
        return self.team_board.tournament.tournament_players_by_id.get(player_id)

    @property
    def white_tournament_player(self) -> TournamentPlayer | None:
        return self._tournament_player(self.seat.white_player_id)

    @property
    def black_tournament_player(self) -> TournamentPlayer | None:
        return self._tournament_player(self.seat.black_player_id)

    @property
    def has_both_players(self) -> bool:
        return (
            self.white_tournament_player is not None
            and self.black_tournament_player is not None
        )

    @property
    def white_team_id(self) -> int | None:
        """The team playing white, taken from the other side when white
        fielded nobody."""
        stored_team_board = self.team_board.stored_team_board
        team_ids = (stored_team_board.team_a_id, stored_team_board.team_b_id)
        white = self.white_tournament_player
        if white is not None and white.team_id in team_ids:
            return white.team_id
        black = self.black_tournament_player
        if black is not None and black.team_id in team_ids:
            return next(
                (team_id for team_id in team_ids if team_id != black.team_id), None
            )
        return None

    @property
    def team_a_is_white(self) -> bool:
        return self.white_team_id == self.team_board.stored_team_board.team_a_id

    @property
    def stored_result(self) -> Result:
        """The result entered for the two players, whoever may see it."""
        white_id, black_id = self.seat.white_player_id, self.seat.black_player_id
        if white_id is None or black_id is None:
            return Result.NO_RESULT
        return self.team_board.tournament.extra_game_results.get(
            (self.round, white_id, black_id), Result.NO_RESULT
        )

    @property
    def result(self) -> Result:
        """The result of white. A side that fielded nobody forfeits; a game
        neither side fields has none."""
        if self.team_board.tournament.hides_round_results(self.round):
            return Result.NO_RESULT
        white = self.white_tournament_player
        black = self.black_tournament_player
        if white is None and black is None:
            return Result.NO_RESULT
        if white is None:
            return Result.FORFEIT_LOSS
        if black is None:
            return Result.FORFEIT_WIN
        return self.stored_result

    @property
    def no_result(self) -> bool:
        return self.result == Result.NO_RESULT

    @property
    def pending(self) -> bool:
        """Whether the game is still to play or to enter."""
        return self.has_both_players and self.stored_result == Result.NO_RESULT

    @property
    def played(self) -> bool:
        """Whether the two players met over the board."""
        return self.has_both_players and self.result not in (
            Result.NO_RESULT,
            Result.FORFEIT_WIN,
            Result.FORFEIT_LOSS,
            Result.DOUBLE_FORFEIT,
        )

    def _side_result(self, team_id: int) -> tuple[Result, int] | None:
        """The result of *team_id* and the board it plays the game for, or
        ``None`` for a team that is not in the game."""
        white_team_id = self.white_team_id
        if white_team_id is None:
            return None
        stored_team_board = self.team_board.stored_team_board
        if team_id not in (stored_team_board.team_a_id, stored_team_board.team_b_id):
            return None
        if team_id == white_team_id:
            return self.result, self.seat.white_board_index
        return self.result.opposite_result, self.seat.black_board_index

    def board_index_of(self, team_id: int) -> int | None:
        side = self._side_result(team_id)
        return side[1] if side else None

    def team_points(self, team_id: int) -> float:
        """The game points the game brings *team_id*, on the scale of the
        board the team plays it for."""
        side = self._side_result(team_id)
        if side is None:
            return 0.0
        result, board_index = side
        if result == Result.NO_RESULT:
            return 0.0
        return result.points(self.team_board.board_game_points(board_index))

    def player_points(self, team_id: int) -> float:
        """The points of *team_id*'s player, as an individual game."""
        side = self._side_result(team_id)
        if side is None or side[0] == Result.NO_RESULT:
            return 0.0
        return side[0].points(self.team_board.tournament.point_values)

    def seats(self, player_id: int) -> bool:
        return player_id in (self.seat.white_player_id, self.seat.black_player_id)

    def result_of(self, player_id: int) -> Result:
        """The result of the player, who is one of the two."""
        if player_id == self.seat.white_player_id:
            return self.result
        return self.result.opposite_result

    def points_of(self, player_id: int) -> float:
        """The points of the player, as an individual game."""
        result = self.result_of(player_id)
        if result == Result.NO_RESULT:
            return 0.0
        return result.points(self.team_board.tournament.point_values)

    def points_str_of(self, player_id: int) -> str:
        if self.result_of(player_id) == Result.NO_RESULT:
            return ''
        return Utils.points_str(self.points_of(player_id))

    def color_of(self, player_id: int) -> BoardColor:
        if player_id == self.seat.white_player_id:
            return BoardColor.WHITE
        return BoardColor.BLACK

    def opponent_of(self, player_id: int) -> TournamentPlayer | None:
        if player_id == self.seat.white_player_id:
            return self.black_tournament_player
        return self.white_tournament_player

    @property
    def result_str(self) -> str:
        return str(self.result)

    @property
    def display_result_str(self) -> str:
        """The result with team A's side first."""
        result = self.result if self.team_a_is_white else self.result.opposite_result
        return str(result)

    def __repr__(self) -> str:
        return (
            f'{self.__class__.__name__}(round={self.round!r}, key={self.key!r}, '
            f'white={self.seat.white_player_id!r}, '
            f'black={self.seat.black_player_id!r}, result={self.result!r})'
        )
