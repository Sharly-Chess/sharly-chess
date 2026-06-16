from abc import ABC
from typing import Any

from common.i18n import _
from data.player import TournamentPlayer
from data.tournament import Tournament
from utils import Utils
from .column import Column, ColumnUsage


class TournamentPlayerTableColumn(Column[TournamentPlayer], ABC):
    """Base class for player table columns."""

    def __init__(self, usage: ColumnUsage):
        self.usage = usage


class CheckinColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return ''

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return '☑' if tournament_player.check_in else '☐'

    def get_footer_content(self, tournament_players: list[TournamentPlayer]) -> Any:
        return '☐' if tournament_players else ''

    def get_footer_classes(self, tournament_players: list[TournamentPlayer]) -> Any:
        return f'{self.shared_classes} opacity-0'

    @property
    def shared_classes(self) -> str:
        return 'checkin'


class NumberColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('No. *** NB COLUMN HEADER')

    @property
    def cell_template(self) -> str | None:
        return '/admin/print/cells/number.html'

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class RankColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Rk. *** RANK COLUMN HEADER')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.rank

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class ExAequoRankColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Rk. *** RANK COLUMN HEADER')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.tournament.ex_aequo_rank_by_player_id[
            tournament_player.id
        ]

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class RankOverallColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Rk. O. *** RANK OVERALL COLUMN HEADER')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return f'({Utils.ordinal_integer(tournament_player.rank)})'

    @property
    def is_cell_content_safe(self) -> bool:
        return True

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-start'


class TitleColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return '\u00a0'

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.title.short_name

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class NameColumn(TournamentPlayerTableColumn):
    @property
    def grid_column_template(self) -> str:
        return '1fr'

    @property
    def header_content(self) -> str:
        return _('Name *** NAME COLUMN HEADER')

    @property
    def cell_template(self) -> str | None:
        return '/admin/print/cells/name.html'

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.full_name

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-start text-nowrap'


class RatingColumn(TournamentPlayerTableColumn):
    @property
    def header_template(self) -> str | None:
        return '/admin/print/headers/rating.html'

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.rating_str

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class CategoryColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Cat. *** CATEGORY COLUMN HEADER')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.category.name

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class GenderColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Gen. *** GENDER COLUMN HEADER')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.gender.short_name

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class FederationColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Fed. *** FEDERATION COLUMN HEADER')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.federation.name

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class ClubColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Club *** CLUB COLUMN HEADER')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.club.name

    @property
    def shared_classes(self) -> str:
        return 'text-start'


class PointsColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Pts *** POINTS COLUMN HEADER')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.points_str

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-center'


class AlphaPointsColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return ''

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return f'[{tournament_player.points_str}]'

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-center'


class RoundColumn(TournamentPlayerTableColumn):
    def __init__(self, usage: ColumnUsage, round_: int):
        super().__init__(usage)
        self.round = round_

    @property
    def header_content(self) -> str:
        return _('R {round} *** ROUND COLUMN HEADER').format(round=self.round)

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        pairing = tournament_player.pairings_by_round[self.round]
        content = pairing.result.to_crosstable
        if opponent := pairing.opponent:
            content += str(opponent.rank).rjust(3, '\u00a0') + getattr(
                pairing.color, 'to_crosstable'
            )
        return content

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class TournamentColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Tournament *** TOURNAMENT FOR PLAYERS COLUMNS')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.tournament.name

    @property
    def shared_classes(self) -> str:
        return 'text-start'


class TieBreakColumn(TournamentPlayerTableColumn):
    def __init__(
        self,
        usage: ColumnUsage,
        tournament: Tournament,
        index: int,
    ):
        super().__init__(usage)
        self.tournament = tournament
        self.index = index

    @property
    def header_content(self) -> str:
        return self.tournament.tie_breaks[self.index].acronym

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return str(tournament_player.tie_break_values[self.index])

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class TeamRankingTieBreakColumn(TournamentPlayerTableColumn):
    def __init__(
        self,
        usage: ColumnUsage,
        tournament: Tournament,
        index: int,
    ):
        super().__init__(usage)
        self.tournament = tournament
        self.index = index

    @property
    def header_content(self) -> str:
        return self.tournament.team_ranking_tie_breaks[self.index].acronym

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return str(tournament_player.team_ranking_tie_break_values[self.index])

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class PaidColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Paid *** PAID COLUMN HEADER')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return Utils.currency_value_str(
            tournament_player.paid, tournament_player.tournament.event.prize_currency
        )

    def get_footer_content(self, tournament_players: list[TournamentPlayer]) -> Any:
        return Utils.currency_value_str(
            sum(tournament_player.paid for tournament_player in tournament_players),
            tournament_players[0].tournament.event.prize_currency,
        )

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class OwedColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Owed *** OWED COLUMN HEADER')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return Utils.currency_value_str(
            tournament_player.owed, tournament_player.event.prize_currency
        )

    def get_footer_content(self, tournament_players: list[TournamentPlayer]) -> Any:
        return Utils.currency_value_str(
            sum(tournament_player.owed for tournament_player in tournament_players),
            tournament_players[0].event.prize_currency,
        )

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class CommentsColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Comments *** COMMENTS COLUMN HEADER')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.comment or ''

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class PlayerColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Player')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.full_name

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-start'


class OpponentColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Opponent')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.full_name

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-start'
