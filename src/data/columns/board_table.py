from abc import ABC, abstractmethod
from typing import Any

from common.i18n import _
from data.board import Board
from web.utils import Column, ColumnUsage


class BoardColumn(Column[Board], ABC):
    """Base class for board table columns."""

    def __init__(self, usage: ColumnUsage):
        self.usage = usage

    @property
    def grid_column_template(self) -> str:
        return 'auto'

    @property
    def edit_result_on_click(self) -> bool:
        """Defines if clicking on the cell opens the result modal (if the board is editable)."""
        return True


class NumberColumn(BoardColumn):
    @property
    def header_content(self) -> str:
        return _('Bd. *** BOARD NUMBER FOR TABLE HEADER')

    def get_cell_content(self, board: Board) -> Any:
        return board.number_str

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class PointsColumn(BoardColumn, ABC):
    @property
    def header_content(self) -> str:
        return _('Pts *** POINTS FOR TABLE HEADER')

    def get_cell_content(self, board: Board) -> Any:
        if self.is_black:
            if real_points := getattr(board.black_tournament_player, 'vpoints_str', ''):
                text = f'[{real_points}]'
            else:
                text = ''
        else:
            text = board.white_tournament_player.vpoints_str
        return f'<span translate="no">{text}</span>'

    @property
    def shared_classes(self) -> str:
        return 'text-center'

    @property
    @abstractmethod
    def is_black(self) -> bool:
        """Defines if the column displays the white or black player."""


class WhitePointsColumn(PointsColumn):
    @property
    def is_black(self) -> bool:
        return False


class BlackPointsColumn(PointsColumn):
    @property
    def is_black(self) -> bool:
        return False


class RealPointsColumn(BoardColumn, ABC):
    @property
    def header_content(self) -> str:
        return ''

    def get_cell_content(self, board: Board) -> Any:
        if self.is_black:
            if points := getattr(board.black_tournament_player, 'vpoints_str', ''):
                text = f'[{points}]'
            else:
                text = ''
        else:
            text = board.white_tournament_player.vpoints_str
        return f'<span translate="no">{text}</span>'

    @property
    def shared_classes(self) -> str:
        return 'text-center'

    @property
    @abstractmethod
    def is_black(self) -> bool:
        """Defines if the column displays the white or black player."""


class WhiteRealPointsColumn(RealPointsColumn):
    @property
    def is_black(self) -> bool:
        return False


class BlackRealPointsColumn(RealPointsColumn):
    @property
    def is_black(self) -> bool:
        return False


class IllegalMovesColumn(BoardColumn, ABC):
    @property
    def header_content(self) -> str:
        return ''

    @property
    def cell_template(self) -> str | None:
        return '/user/screen/boards/board_row_illegal_moves_cell.html'

    @property
    @abstractmethod
    def is_black(self) -> bool:
        """Defines if the column displays the white or black player."""

    @property
    def edit_result_on_click(self) -> bool:
        return False


class WhiteIllegalMovesColumn(IllegalMovesColumn):
    @property
    def is_black(self) -> bool:
        return False


class BlackIllegalMovesColumn(IllegalMovesColumn):
    @property
    def is_black(self) -> bool:
        return True


class TitleColumn(BoardColumn, ABC):
    @property
    def header_content(self) -> str:
        return ''

    def get_cell_content(self, board: Board) -> Any:
        if self.is_black:
            if player := board.black_tournament_player:
                text = player.title.short_name
            else:
                text = ''
        else:
            text = board.white_tournament_player.title.short_name
        return f'<span translate="no">{text}</span>'

    @property
    @abstractmethod
    def is_black(self) -> bool:
        """Defines if the column displays the white or black player."""


class WhiteTitleColumn(TitleColumn):
    @property
    def is_black(self) -> bool:
        return False


class BlackTitleColumn(TitleColumn):
    @property
    def is_black(self) -> bool:
        return True


class NameColumn(BoardColumn, ABC):
    @property
    def grid_column_template(self) -> str:
        return '1fr'

    @property
    def header_content(self) -> str:
        return _('White') if self.is_black else _('Black')

    def get_cell_content(self, board: Board) -> Any:
        if self.is_black:
            text = getattr(
                board.black_tournament_player,
                'full_name',
                board.white_tournament_player.exempt_str.upper(),
            )
        else:
            text = board.white_tournament_player.full_name
        return f'<span translate="no">{text}</span>'

    @property
    def shared_classes(self) -> str:
        return 'text-start'

    def get_cell_classes(self, board: Board) -> str:
        return 'text-start text-nowrap overflow-hidden text-ellipsis' + (
            ' fst-italic' if (self.is_black and board.exempt) else ''
        )

    @property
    @abstractmethod
    def is_black(self) -> bool:
        """Defines if the column displays the white or black player."""


class WhiteNameColumn(NameColumn):
    @property
    def is_black(self) -> bool:
        return False


class BlackNameColumn(NameColumn):
    @property
    def is_black(self) -> bool:
        return True


class RatingColumn(Column, ABC):
    @property
    def header_content(self) -> str:
        return ''

    def get_cell_content(self, board: Board) -> Any:
        if self.is_black:
            text = getattr(board.black_tournament_player, 'rating_str', '')
        else:
            text = board.white_tournament_player.rating_str
        return f'<span translate="no">{text}</span>'

    @property
    def shared_classes(self) -> str:
        return 'text-end'

    @property
    @abstractmethod
    def is_black(self) -> bool:
        """Defines if the column displays the white or black player."""


class WhiteRatingColumn(RatingColumn):
    @property
    def is_black(self) -> bool:
        return False


class BlackRatingColumn(WhiteRatingColumn):
    @property
    def is_black(self) -> bool:
        return True


class ResultColumn(BoardColumn):
    @property
    def header_content(self) -> str:
        return _('Res. ** RESULT FOR TABLE HEADER')

    def get_cell_content(self, board: Board) -> Any:
        return f'<span translate="no">{board.result_str}</span>'


class NoResultColumn(BoardColumn):
    @property
    def header_content(self) -> str:
        return '\u00a0' * 6

    def get_cell_content(self, board: Board) -> Any:
        return f'<span translate="no">{board.result_str if board.exempt else ""}</span>'


class ScreenResultColumn(BoardColumn):
    @property
    def header_content(self) -> str:
        return _('Res. ** RESULT FOR TABLE HEADER')

    def get_cell_content(self, board: Board) -> Any:
        return board.result_str or _('#{board_number}').format(
            board_number=board.number
        )

    @property
    def shared_classes(self) -> str:
        return 'score'
