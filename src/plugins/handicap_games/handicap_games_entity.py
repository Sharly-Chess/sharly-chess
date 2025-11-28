from abc import ABC
from typing import Any

from common.i18n import _
from data.board import Board
from data.columns.board_table import BoardColumn
from data.player import Player
from plugins.handicap_games.utils import HandicapGameUtils


class TimeControlColumn(BoardColumn, ABC):
    @property
    def header_content(self) -> str:
        return _('Time control')

    @staticmethod
    def get_cell_content_from_player(player: Player) -> Any:
        transient_data = HandicapGameUtils.get_transient_player_plugin_data(
            player.single_tournament_player
        )
        time_control_initial_time_minutes = (
            transient_data.initial_time // 60 if transient_data.initial_time else None
        )
        time_control_initial_time_seconds = (
            transient_data.initial_time % 60 if transient_data.initial_time else None
        )

        cls = (
            'time-control-modified'
            if transient_data.modified
            else 'time-control-unchanged'
        )
        inner = ''

        if time_control_initial_time_minutes:
            inner += (
                f'<span class="minutes">{time_control_initial_time_minutes}\'</span>'
            )

        if time_control_initial_time_seconds:
            inner += (
                f'<span class="seconds">{time_control_initial_time_seconds}"</span>'
            )

        if transient_data.increment:
            inner += f' + {transient_data.increment}"{_("/move")}'
        return f'<span class="{cls}">{inner}</span>'

    @property
    def is_cell_content_safe(self) -> bool:
        return True

    @property
    def shared_classes(self) -> str:
        return 'text-end text-nowrap'


class WhiteTimeControlColumn(TimeControlColumn):
    def get_cell_content(self, board: Board) -> Any:
        if not board.black_tournament_player:
            return ''
        return self.get_cell_content_from_player(board.white_tournament_player)


class BlackTimeControlColumn(TimeControlColumn):
    def get_cell_content(self, board: Board) -> Any:
        if not board.black_tournament_player:
            return ''
        return self.get_cell_content_from_player(board.black_tournament_player)
