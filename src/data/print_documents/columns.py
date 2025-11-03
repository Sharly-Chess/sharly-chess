from common.i18n import _
from data.player import Player
from utils import Utils
from web.utils import PlayerColumn


class RankColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Rk. O. *** RANK OVERALL FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> str:
        return f'({Utils.ordinal_integer(player.rank)})'

    @property
    def is_cell_content_safe(self) -> bool:
        return True

    @property
    def cell_classes(self) -> str:
        return 'place'


class TitleColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return '&nbsp;'

    @property
    def is_header_content_safe(self) -> bool:
        return True

    def get_cell_content(self, player: Player) -> str:
        return player.title.short_name

    @property
    def cell_classes(self) -> str:
        return 'title'


class NameColumn(PlayerColumn):
    @property
    def grid_column_template(self) -> str:
        return '1fr'

    @property
    def header_content(self) -> str:
        return _('Name *** NAME FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> str:
        return player.full_name

    @property
    def cell_classes(self) -> str:
        return 'name'


class RatingColumn(PlayerColumn):
    @property
    def header_template(self) -> str | None:
        return '/admin/print/headers/rating.html'

    def get_cell_content(self, player: Player) -> str:
        return player.rating_str


class CategoryColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Cat *** CATEGORY FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> str:
        return player.category.short_name


class GenderColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Gen *** GENDER FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> str:
        return player.gender.short_name


class FederationColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Fed *** FEDERATION FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> str:
        return player.federation.name


class ClubColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Club *** CLUB FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> str:
        return player.club.name

    @property
    def cell_classes(self) -> str:
        return 'club'


class PointsColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('Pts *** POINTS FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> str:
        return player.points_str
