from abc import ABC
from typing import Any

from common.i18n import _
from data.player import Player
from data.tournament import Tournament
from utils import Utils
from web.utils import Column, ColumnUsage


class PlayerTableColumn(Column[Player], ABC):
    """Base class for player table columns."""

    def __init__(self, usage: ColumnUsage):
        self.usage = usage


class CheckinColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return ''

    def get_cell_content(self, player: Player) -> Any:
        return '☑' if player.check_in else '☐'

    def get_cell_classes(self, player: Player) -> str:
        return 'checkin'


class NumberColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('No. *** NB FOR TABLE HEADER')

    @property
    def cell_template(self) -> str | None:
        return '/admin/print/cells/number.html'

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class RankColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Rk. *** RANK FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return player.rank

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class RankOverallColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Rk. O. *** RANK OVERALL FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return f'({Utils.ordinal_integer(player.rank)})'

    @property
    def is_cell_content_safe(self) -> bool:
        return True

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-start'


class TitleColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return '\u00a0'

    def get_cell_content(self, player: Player) -> Any:
        return player.title.short_name

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class NameColumn(PlayerTableColumn):
    @property
    def grid_column_template(self) -> str:
        return '1fr'

    @property
    def header_content(self) -> str:
        return _('Name *** NAME FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return player.full_name

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-start'


class RatingColumn(PlayerTableColumn):
    @property
    def header_template(self) -> str | None:
        return '/admin/print/headers/rating.html'

    def get_cell_content(self, player: Player) -> Any:
        return player.rating_str

    def get_cell_classes(self, player: Player) -> str:
        return 'text-end'


class CategoryColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Cat *** CATEGORY FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return player.category.short_name

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class GenderColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Gen *** GENDER FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return player.gender.short_name

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class FederationColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Fed *** FEDERATION FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return player.federation.name

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class ClubColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Club *** CLUB FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return player.club.name

    @property
    def shared_classes(self) -> str:
        return 'text-start'


class PointsColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Pts *** POINTS FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return player.points_str

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-center'


class AlphaPointsColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return ''

    def get_cell_content(self, player: Player) -> Any:
        return f'[{player.points_str}]'

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-center'


class RoundColumn(PlayerTableColumn):
    def __init__(self, usage: ColumnUsage, round_: int):
        super().__init__(usage)
        self.round = round_

    @property
    def header_content(self) -> str:
        return _('R {round} *** ROUND FOR TABLE HEADER').format(round=self.round)

    def get_cell_content(self, player: Player) -> Any:
        pairing = player.pairings_by_round[self.round]
        content = pairing.result.to_crosstable
        if opponent := pairing.opponent:
            content += str(opponent.rank).rjust(3, '\u00a0') + getattr(
                pairing.color, 'to_crosstable'
            )
        return content

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class TournamentColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Tournament *** TOURNAMENT FOR PLAYERS COLUMNS')

    def get_cell_content(self, player: Player) -> Any:
        return player.tournament.name

    @property
    def shared_classes(self) -> str:
        return 'text-start'


class TieBreakColumn(PlayerTableColumn):
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

    def get_cell_content(self, player: Player) -> Any:
        return str(player.tie_break_values[self.index])

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class PaidColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Paid *** PAID COLUMN HEADER FOR PLAYERS')

    def get_cell_content(self, player: Player) -> Any:
        return str(player.paid)

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class OwedColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Owed *** OWED COLUMN HEADER FOR PLAYERS')

    def get_cell_content(self, player: Player) -> Any:
        return str(player.owed)

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class CommentsColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Comments *** COMMENTS FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return player.comment or ''

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class PlayerColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Player')

    def get_cell_content(self, player: Player) -> Any:
        return player.full_name

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-start'


class OpponentColumn(PlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Opponent')

    def get_cell_content(self, player: Player) -> Any:
        return player.full_name

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-start'
