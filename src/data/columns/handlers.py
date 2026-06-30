from functools import partial
from typing import Callable, Collection, TYPE_CHECKING, Optional

from data.columns import player_table as pt, board_table as bt
from data.columns.board_table import BoardColumn
from data.columns.column import ColumnUsage
from data.columns.player_table import TournamentPlayerTableColumn
from data.columns.player_datasheet import DatasheetColumn
import data.columns.player_datasheet as pds
from data.columns.players_tab import (
    PlayersTabColumn,
    NamePlayersTabColumn,
    CheckInPlayersTabColumn,
    RatingPlayersTabColumn,
    FederationPlayersTabColumn,
    ClubPlayersTabColumn,
    DateOfBirthPlayersTabColumn,
    CategoryPlayersTabColumn,
    MailPlayersTabColumn,
    PhonePlayersTabColumn,
    GenderPlayersTabColumn,
    FixedPlayersTabColumn,
    FideIdPlayersTabColumn,
    PaymentPlayersTabColumn,
    TournamentPlayersTabColumn,
    TeamPlayersTabColumn,
    CommentPlayersTabColumn,
    RecordPlayersTabColumn,
)
from data.event import Event
from data.tournament import Tournament
from plugins.manager import plugin_manager
from utils.enum import TournamentRating, PlayerRatingType

if TYPE_CHECKING:
    from data.input_output import DataSource


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
            pt.CommentsColumn,
        ]
        return self.get_columns(column_types)

    def get_player_ranking_columns(
        self, tournament: Tournament
    ) -> list[TournamentPlayerTableColumn]:
        return self.get_columns(
            [
                pt.ExAequoRankColumn,
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
        self, tournament: Tournament, ranking_round: int
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


class PlayersTabColumnHandler:
    def __init__(self, event: Event):
        self._columns_by_id = self._get_columns_by_id(event)

    @staticmethod
    def _get_columns_by_id(event: Event) -> dict[str, PlayersTabColumn]:
        columns: list[PlayersTabColumn] = [
            NamePlayersTabColumn(),
            CheckInPlayersTabColumn(),
            RatingPlayersTabColumn(),
            FederationPlayersTabColumn(),
            ClubPlayersTabColumn(),
            DateOfBirthPlayersTabColumn(),
            CategoryPlayersTabColumn(),
            MailPlayersTabColumn(),
            PhonePlayersTabColumn(),
            GenderPlayersTabColumn(),
            FixedPlayersTabColumn(),
            FideIdPlayersTabColumn(),
            PaymentPlayersTabColumn(),
            TournamentPlayersTabColumn(),
            TeamPlayersTabColumn(),
            CommentPlayersTabColumn(),
            RecordPlayersTabColumn(),
        ]
        plugin_manager.hook_for_event(event, 'alter_players_tab_columns')(
            columns=columns
        )
        return {column.id: column for column in columns}

    def set_column_states(
        self,
        disabled_column_ids: list[str],
        hidden_column_ids: list[str] | None = None,
    ):
        for column in self.columns:
            column.is_enabled = column.id not in disabled_column_ids
            column.is_visible = (
                column.id not in hidden_column_ids
                if hidden_column_ids is not None
                else column.is_default_visible
            )

    @property
    def columns(self) -> Collection[PlayersTabColumn]:
        return self._columns_by_id.values()

    @property
    def visible_columns(self) -> list[PlayersTabColumn]:
        return [
            column for column in self.columns if column.is_visible and column.is_enabled
        ]

    @property
    def enabled_columns(self) -> list[PlayersTabColumn]:
        return [column for column in self.columns if column.is_enabled]

    @property
    def searchable_columns(self) -> list[PlayersTabColumn]:
        return [
            column
            for column in self.columns
            if column.is_searchable and column.is_visible
        ]

    def get_column(self, column_id: str) -> PlayersTabColumn | None:
        return self._columns_by_id.get(column_id, None)


class PlayerDatasheetColumnHandler:
    def __init__(self, event: Event, data_source: Optional['DataSource'] = None):
        self._event = event
        columns = self._base_columns
        plugin_manager.hook_for_event(event, 'insert_player_datasheet_columns')(
            datasheet_columns=columns
        )
        if data_source:
            identifier_column = data_source.import_identifier_column
            source_column_ids = [
                column.id for column in data_source.imported_datasheet_columns
            ]
            pop_index = 0
            for index, column in enumerate(columns):
                if column.id in source_column_ids:
                    column.is_informative = True
                    column.is_required = False
                if column.id == identifier_column.id:
                    pop_index = index
            if pop_index:
                columns.pop(pop_index)
            identifier_column.is_required = True
            columns.insert(0, identifier_column)
        self.columns = columns

    @property
    def _base_columns(self) -> list[DatasheetColumn]:
        columns: list[DatasheetColumn] = [
            pds.TitleColumn(),
            pds.LastNameColumn(),
            pds.FirstNameColumn(),
            pds.DateOfBirthColumn(),
            pds.YearOfBirthColumn(),
            pds.MailColumn(),
            pds.PhoneColumn(),
            pds.GenderColumn(),
            pds.FideIDColumn(),
            # Team events list a team column (export + import) instead of
            # the export-only tournament column.
            pds.TeamColumn() if self._event.is_team_event else pds.TournamentColumn(),
            pds.FederationColumn(),
            pds.ClubColumn(),
            pds.OwedColumn(),
            pds.PaidColumn(),
            pds.CheckInColumn(),
            pds.CommentColumn(),
        ]
        columns += self.get_rating_columns()
        return columns

    @staticmethod
    def get_rating_columns(
        rating_types: list[PlayerRatingType] | None = None,
    ) -> list[DatasheetColumn]:
        if rating_types is None:
            rating_types = [rating for rating in PlayerRatingType]
        columns: list[DatasheetColumn] = [pds.RatingColumn(), pds.RatingTypeColumn()]
        for tournament_type in TournamentRating:
            for rating_type in rating_types:
                columns.append(pds.TypedRatingColumn(tournament_type, rating_type))
        return columns

    @property
    def import_columns(self) -> Collection[DatasheetColumn]:
        return [column for column in self.columns if not column.export_only]
