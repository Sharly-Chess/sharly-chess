import weakref
from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTeamBoard
from utils.date_time import format_datetime
from utils.enum import TeamByeType, Result, ScoreType

if TYPE_CHECKING:
    from _weakref import ReferenceType
    from data.board import Board
    from data.team import Team
    from data.tournament import Tournament


class TeamBoard:
    """A team-vs-team match for a given round.
    The two teams are symmetric (no home/away). *team_b* is None for a bye.
    Holds the individual *Board* objects making up the match."""

    def __init__(
        self,
        tournament: 'Tournament',
        stored_team_board: StoredTeamBoard,
    ):
        self._tournament_ref: 'ReferenceType[Tournament]' = weakref.ref(tournament)
        self.stored_team_board = stored_team_board

    @property
    def tournament(self) -> 'Tournament':
        if (tournament := self._tournament_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return tournament

    @property
    def id(self) -> int:
        assert self.stored_team_board.id is not None
        return self.stored_team_board.id

    @property
    def round(self) -> int:
        return self.stored_team_board.round_

    @property
    def index(self) -> int | None:
        return self.stored_team_board.index

    @property
    def display_number(self) -> int | None:
        """1-based table number for this match, straight from the stored
        ``index``. ``None`` for a hidden bye (HPB / FPB / ZPB), which has
        no table. Because the number is carried by the stored ``index``,
        it is stable: unpairing a match leaves a hole rather than
        renumbering the matches after it (exactly like individual board
        numbers), and a new pairing reuses that hole."""
        if self.index is None:
            return None
        return self.index + 1

    @property
    def _counts_as_displayed_match(self) -> bool:
        """Whether this team board is rendered as a numbered match in
        the pairings table (matches the controller's filter: manual /
        auto byes are hidden)."""
        stb = self.stored_team_board
        return not (
            stb.team_b_id is None and stb.bye_type in TeamByeType.manual_bye_types()
        )

    @property
    def team_a(self) -> 'Team':
        return self.tournament.event.teams_by_id[self.stored_team_board.team_a_id]

    @property
    def team_b(self) -> 'Team | None':
        team_b_id = self.stored_team_board.team_b_id
        if team_b_id is None:
            return None
        return self.tournament.event.teams_by_id.get(team_b_id)

    @property
    def is_bye(self) -> bool:
        return self.stored_team_board.team_b_id is None

    @property
    def bye_type(self) -> str | None:
        """One of ``PAB`` / ``HPB`` / ``FPB`` / ``ZPB`` for a bye
        team_board; ``None`` for a regular paired match. Stored byes
        that pre-date the column default to ``PAB`` since that's the
        only bye the pairing engine produced before this field existed."""
        if not self.is_bye:
            return None
        return self.stored_team_board.bye_type or TeamByeType.PAB

    @cached_property
    def boards(self) -> list['Board']:
        """Individual boards belonging to this team match, ordered by index."""
        return sorted(
            (
                board
                for board in self.tournament.boards_by_id.values()
                if board.stored_board.team_board_id == self.id
            ),
            key=lambda board: board.index,
        )

    def board_team_ids(self, board: 'Board') -> tuple[int | None, int | None]:
        """The ``(white_team_id, black_team_id)`` for ``board`` within
        this match. A forfeited side is a hole — no player, hence no
        team — so it's inferred from the present side and the match's
        two teams. Without this, every per-board team attribution would
        mis-credit a forfeited board to the opponent whenever the
        forfeiting team sat on the white side."""
        players_by_id = self.tournament.event.players_by_id
        w_id = board.stored_board.white_player_id
        b_id = board.stored_board.black_player_id
        white_player = players_by_id.get(w_id) if w_id else None
        black_player = players_by_id.get(b_id) if b_id else None
        white_team_id = white_player.team_id if white_player else None
        black_team_id = black_player.team_id if black_player else None
        team_a_id = self.stored_team_board.team_a_id
        team_b_id = self.stored_team_board.team_b_id
        if white_team_id is None and black_team_id is not None:
            white_team_id = team_a_id if black_team_id == team_b_id else team_b_id
        elif black_team_id is None and white_team_id is not None:
            black_team_id = team_a_id if white_team_id == team_b_id else team_b_id
        return white_team_id, black_team_id

    @property
    def game_points(self) -> tuple[float, float]:
        """(team_a_points, team_b_points) — sum of individual board
        game-points across this match. Scored via the tournament's
        :attr:`team_game_points` mapping so the ``gp_*`` override
        (e.g. 3/2/1) applies at team-scoring level; ``point_values``
        (individual scoring) stays at FIDE defaults."""
        a, b = 0.0, 0.0
        team_a_id = self.stored_team_board.team_a_id
        team_game_points = self.tournament.team_game_points
        for board in self.boards:
            white_team_id, _black_team_id = self.board_team_ids(board)
            white_pairing = board.optional_white_pairing
            white_pts = (
                white_pairing.result.points(team_game_points) if white_pairing else 0.0
            )
            black_tp = board.black_tournament_player
            black_pts = (
                board.black_pairing.result.points(team_game_points) if black_tp else 0.0
            )
            if white_team_id == team_a_id:
                a += white_pts
                b += black_pts
            else:
                a += black_pts
                b += white_pts
        return a, b

    @property
    def match_score_pair(self) -> tuple[str, str] | None:
        """``(team_a_score, team_b_score)`` strings following the
        tournament's primary score, or ``None`` for an unplayed match
        or a bye envelope. Lets callers orient the score from either
        team's perspective (crosstables)."""
        if self.stored_team_board.team_b_id is None:
            return None
        if self.boards and all(board.no_result for board in self.boards):
            return None
        a_gp, b_gp = self.game_points
        tournament = self.tournament
        if tournament.primary_score == ScoreType.MATCH_POINTS:
            mp = tournament.match_points
            win_mp = mp.get(Result.WIN, 2.0)
            draw_mp = mp.get(Result.DRAW, 1.0)
            loss_mp = mp.get(Result.LOSS, 0.0)
            if a_gp > b_gp:
                mp_a, mp_b = win_mp, loss_mp
            elif a_gp < b_gp:
                mp_a, mp_b = loss_mp, win_mp
            else:
                mp_a = mp_b = draw_mp
            return f'{mp_a:g}', f'{mp_b:g}'
        return f'{a_gp:g}', f'{b_gp:g}'

    @property
    def match_score_display(self) -> str:
        """Human-readable score line shown in the team-block header. Format
        follows the tournament's primary score: match points if
        primary_score is MATCH_POINTS, otherwise game points."""
        if (
            self.stored_team_board.team_b_id is not None
            and self.boards
            and all(board.no_result for board in self.boards)
        ):
            return '–'
        a_gp, b_gp = self.game_points
        tournament = self.tournament
        if (
            self.stored_team_board.team_b_id is None
            and self.bye_type == TeamByeType.PAB
            and tournament.team_bye_is_rest
        ):
            # Round-robin rest game: no points to display.
            return '–'
        if tournament.primary_score == ScoreType.MATCH_POINTS:
            mp = tournament.match_points
            win_mp = mp.get(Result.WIN, 2.0)
            draw_mp = mp.get(Result.DRAW, 1.0)
            loss_mp = mp.get(Result.LOSS, 0.0)
            if self.stored_team_board.team_b_id is None:
                mp_a = mp.get(Result.PAIRING_ALLOCATED_BYE, win_mp)
                return f'{mp_a:g} – 0'
            if a_gp > b_gp:
                mp_a, mp_b = win_mp, loss_mp
            elif a_gp < b_gp:
                mp_a, mp_b = loss_mp, win_mp
            else:
                mp_a = mp_b = draw_mp
            return f'{mp_a:g} – {mp_b:g}'
        if self.stored_team_board.team_b_id is None:
            return f'{tournament.team_pab_game_points:g} – 0'
        return f'{a_gp:g} – {b_gp:g}'

    @property
    def last_result_update(self) -> datetime | None:
        return self.stored_team_board.last_result_update

    @property
    def last_result_update_str(self) -> str:
        return (
            format_datetime(self.last_result_update) if self.last_result_update else ''
        )

    def set_last_result_update(self, clear: bool, database: EventDatabase):
        self.stored_team_board.last_result_update = (
            database.update_team_board_last_result_update(self.id, clear=clear)
        )

    def update(self, database: EventDatabase):
        database.update_stored_team_board(self.stored_team_board)

    def __repr__(self) -> str:
        return (
            f'{self.__class__.__name__}(id={self.id!r}, round={self.round!r}, '
            f'team_a={self.stored_team_board.team_a_id!r}, '
            f'team_b={self.stored_team_board.team_b_id!r})'
        )
