from functools import partial
from typing import Callable

from data.columns import player_table as pt, board_table as bt
from data.columns.board_table import BoardColumn
from data.columns.player_table import TournamentPlayerTableColumn
from data.event import Event
from data.tournament import Tournament
from plugins.manager import plugin_manager
from web.utils import ColumnUsage


class PlayerColumnHandler:
    def __init__(self, event: Event, usage: ColumnUsage):
        self.event = event
        self.usage = usage

    def get_columns(
        self,
        column_types: list[Callable[[ColumnUsage], TournamentPlayerTableColumn]],
    ) -> list[TournamentPlayerTableColumn]:
        columns = [column_type(self.usage) for column_type in column_types]
        plugin_manager.hook_for_event(
            self.event, 'alter_print_and_screen_player_columns'
        )(usage=self.usage, player_columns=columns)
        return columns

    def get_player_list_columns(
        self, multiple_tournaments: bool
    ) -> list[TournamentPlayerTableColumn]:
        column_types: list[Callable[[ColumnUsage], TournamentPlayerTableColumn]] = [
            pt.NumberColumn,
            pt.TitleColumn,
            pt.NameColumn,
            pt.RatingColumn,
            pt.CategoryColumn,
            pt.GenderColumn,
            pt.FederationColumn,
            pt.ClubColumn,
        ]
        if multiple_tournaments:
            column_types.append(pt.TournamentColumn)
        return self.get_columns(column_types)

    def get_player_checkin_list_columns(
        self, multiple_tournaments: bool
    ) -> list[TournamentPlayerTableColumn]:
        column_types: list[Callable[[ColumnUsage], TournamentPlayerTableColumn]] = [
            pt.CheckinColumn,
            pt.TitleColumn,
            pt.NameColumn,
            pt.RatingColumn,
            pt.CategoryColumn,
            pt.GenderColumn,
            pt.FederationColumn,
            pt.ClubColumn,
        ]
        if multiple_tournaments:
            column_types.append(pt.TournamentColumn)
        column_types += [
            pt.PaidColumn,
            pt.OwedColumn,
        ]
        return self.get_columns(column_types)

    def get_player_ranking_columns(
        self, tournament: Tournament
    ) -> list[TournamentPlayerTableColumn]:
        return self.get_columns(
            [
                pt.RankColumn,
                pt.TitleColumn,
                pt.NameColumn,
                pt.RatingColumn,
                pt.CategoryColumn,
                pt.GenderColumn,
                pt.FederationColumn,
                pt.ClubColumn,
                pt.PointsColumn,
            ]
            + [
                partial(pt.TieBreakColumn, tournament=tournament, index=index)
                for index in range(len(tournament.tie_breaks))
            ]
        )

    def get_player_crosstable_columns(
        self,
        tournament: Tournament,
        ranking_round: int,
    ) -> list[TournamentPlayerTableColumn]:
        return self.get_columns(
            [
                pt.RankColumn,
                pt.TitleColumn,
                pt.NameColumn,
                pt.RatingColumn,
                pt.CategoryColumn,
                pt.GenderColumn,
                pt.FederationColumn,
                pt.ClubColumn,
            ]
            + [
                partial(pt.RoundColumn, round_=round_)
                for round_ in range(1, ranking_round + 1)
            ]
            + [
                pt.PointsColumn,
            ]
            + [
                partial(pt.TieBreakColumn, tournament=tournament, index=index)
                for index in range(len(tournament.tie_breaks))
            ]
        )

    def get_alpha_board_player_columns(self) -> list[TournamentPlayerTableColumn]:
        return self.get_columns(
            [
                pt.TitleColumn,
                pt.PlayerColumn,
                pt.RatingColumn,
                pt.AlphaPointsColumn,
            ]
        )

    def get_alpha_board_opponent_columns(self) -> list[TournamentPlayerTableColumn]:
        return self.get_columns(
            [
                pt.TitleColumn,
                pt.OpponentColumn,
                pt.RatingColumn,
                pt.AlphaPointsColumn,
            ]
        )

    def get_prize_assignment_columns(self) -> list[TournamentPlayerTableColumn]:
        return self.get_columns(
            [
                pt.RankOverallColumn,
                pt.TitleColumn,
                pt.NameColumn,
                pt.RatingColumn,
                pt.CategoryColumn,
                pt.GenderColumn,
                pt.FederationColumn,
                pt.ClubColumn,
                pt.PointsColumn,
            ],
        )


class BoardColumnHandler:
    def __init__(self, usage: ColumnUsage):
        self.usage = usage

    def get_columns(
        self,
        column_types: list[Callable[[ColumnUsage], BoardColumn]],
        tournament: Tournament,
    ) -> list[BoardColumn]:
        columns = [column_type(self.usage) for column_type in column_types]
        plugin_manager.hook_for_event(
            tournament.event, 'alter_print_and_screen_board_columns'
        )(usage=self.usage, board_columns=columns, tournament=tournament)
        return columns

    def get_pairings_columns(
        self,
        tournament: Tournament,
        round_: int,
        result_column_type: type[BoardColumn],
        show_illegal_moves: bool = False,
    ) -> list[BoardColumn]:
        show_real_points = tournament.print_real_points(round_)
        column_types: list[Callable[[ColumnUsage], BoardColumn]] = [
            bt.NumberColumn,
            bt.WhitePointsColumn,
        ]
        if show_real_points:
            column_types.append(bt.WhiteRealPointsColumn)
        if show_illegal_moves:
            column_types.append(bt.WhiteIllegalMovesColumn)
        column_types += [
            bt.WhiteTitleColumn,
            bt.WhiteNameColumn,
            bt.WhiteRatingColumn,
            result_column_type,
        ]
        if show_illegal_moves:
            column_types.append(bt.BlackIllegalMovesColumn)
        column_types += [
            bt.BlackTitleColumn,
            bt.BlackNameColumn,
            bt.BlackRatingColumn,
        ]
        if show_real_points:
            column_types.append(bt.BlackRealPointsColumn)
        column_types.append(bt.BlackPointsColumn)
        return self.get_columns(column_types, tournament)
