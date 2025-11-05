from typing import Any

from common.i18n import _
from data.player import Player
from data.tournament import Tournament
from utils import Utils
from web.utils import PlayerColumn


class CheckinColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return ''

    def get_cell_content(self, player: Player) -> Any:
        return '☑' if player.check_in else '☐'

    @property
    def cell_classes(self) -> str:
        return 'checkin'


class NumberColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('No. *** NB FOR TABLE HEADER')

    @property
    def cell_template(self) -> str | None:
        return '/admin/print/cells/number.html'

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class RankColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Rk. *** RANK FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return str(player.rank)

    @property
    def is_cell_content_safe(self) -> bool:
        return True

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class RankOverallColumn(PlayerColumn):
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


class TitleColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return '&nbsp;'

    @property
    def is_header_content_safe(self) -> bool:
        return True

    def get_cell_content(self, player: Player) -> Any:
        return player.title.short_name

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class NameColumn(PlayerColumn):
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


class RatingColumn(PlayerColumn):
    @property
    def header_template(self) -> str | None:
        return '/admin/print/headers/rating.html'

    def get_cell_content(self, player: Player) -> Any:
        return player.rating_str

    @property
    def cell_classes(self) -> str:
        return 'text-end'


class CategoryColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Cat *** CATEGORY FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return player.category.short_name

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class GenderColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Gen *** GENDER FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return player.gender.short_name

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class FederationColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Fed *** FEDERATION FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return player.federation.name

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class ClubColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Club *** CLUB FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return player.club.name

    @property
    def shared_classes(self) -> str:
        return 'text-start'


class PointsColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Pts *** POINTS FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return player.points_str

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-center'


class PairingPointsColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return ''

    def get_cell_content(self, player: Player) -> Any:
        return f'[{player.points_str}]'

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-center'


class RoundColumn(PlayerColumn):
    def __init__(self, round_: int):
        self.round = round_

    @property
    def header_content(self) -> str:
        return _('R {round} *** ROUND FOR TABLE HEADER').format(round=self.round)

    def get_cell_content(self, player: Player) -> Any:
        pairing = player.pairings_by_round[self.round]
        return (
            f'{pairing.opponent.rank:>3}{pairing.color.to_crosstable}'
            if pairing.opponent and pairing.color
            else ''
        )

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class TournamentColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Tournament *** TOURNAMENT FOR PLAYERS COLUMNS')

    def get_cell_content(self, player: Player) -> Any:
        return player.tournament.name

    @property
    def shared_classes(self) -> str:
        return 'text-start'


class TieBreakColumn(PlayerColumn):
    def __init__(self, tournament: Tournament, index: int):
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


class PaidColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Paid *** PAID COLUMN HEADER FOR PLAYERS')

    def get_cell_content(self, player: Player) -> Any:
        return str(player.paid)

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class OwedColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Owed *** OWED COLUMN HEADER FOR PLAYERS')

    def get_cell_content(self, player: Player) -> Any:
        return str(player.owed)

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class CommentsColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Comments *** COMMENTS FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return player.comment or ''

    @property
    def shared_classes(self) -> str:
        return 'text-center'
