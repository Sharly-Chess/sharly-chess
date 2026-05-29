import weakref
from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTeamBoard
from utils.date_time import format_datetime

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
    def index(self) -> int:
        return self.stored_team_board.index

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
