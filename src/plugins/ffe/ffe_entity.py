from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Callable
from functools import partial, cached_property, cache
from types import UnionType
from typing import override, Any

from common.exception import SharlyChessException, OptionError
from common.i18n import _
from common.i18n.utils import unicode_normalize
from data.columns.player_datasheet import DatasheetColumn
from data.input_output.data_source import (
    FidePlayerComparator,
    PlayerComparator,
    DataSource,
    PlayerUpdaterField,
    LocalDataSource,
    OnlineDataSource,
)
from data.player import Player
from data.print_documents import PlayerSplitter
from data.criteria.player_filter_options import (
    PlayerFilterOption,
    SelectPlayerFilterOption,
    ExcludeFilterOption,
)
from data.criteria.player_filters import PlayerFilter
from data.print_documents.documents import QRCodePrintDocument, TournamentPrintOption
from data.print_documents.qrcode_types import QRCodeType
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.local_source_database import LocalSourcePlayerDatabase
from plugins.ffe import PLUGIN_NAME, PLUGIN_DIR
from plugins.ffe.ffe_database import FfeDatabase, PlayerFFELicence
from plugins.ffe.ffe_sql_server import FFESqlServer
from plugins.ffe.utils import FFEUtils
from plugins.pairing_acceleration.pairing_settings import AccelerationGroup
from plugins.pairing_acceleration.pairing_variations import (
    Acceleration3GroupsSwissVariation,
)
from plugins.utils import PluginUtils
from utils.enum import Result
from web.utils import PlayerColumn

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FfePlayerComparator(FidePlayerComparator):
    @cached_property
    def diff_field_ids(self) -> list[str] | None:
        if not self.match_player:
            return None
        diff_field_ids = super().diff_field_ids or []
        plugin_data = FFEUtils.get_player_plugin_data(self.player)
        match_plugin_data = FFEUtils.get_player_plugin_data(self.match_player)
        if (
            (field_id := 'league') in self.field_ids
            and match_plugin_data.league
            and plugin_data.league != match_plugin_data.league
        ):
            diff_field_ids.append(field_id)
        if (
            (field_id := 'ffe_licence') in self.field_ids
            and plugin_data.ffe_licence != match_plugin_data.ffe_licence
        ):
            diff_field_ids.append(field_id)
        return diff_field_ids

    @override
    def update_player_from_match(self, field_ids: list[str]):
        if not self.match_player:
            return
        super().update_player_from_match(field_ids)
        plugin_data = FFEUtils.get_player_plugin_data(self.player)
        match_plugin_data = FFEUtils.get_player_plugin_data(self.match_player)
        if (
            'league' in self.field_ids
            and match_plugin_data.league
            and plugin_data.league != match_plugin_data.league
        ):
            plugin_data.league = match_plugin_data.league
        if (
            'ffe_licence' in self.field_ids
            and plugin_data.ffe_licence != match_plugin_data.ffe_licence
        ):
            plugin_data.ffe_licence = match_plugin_data.ffe_licence
        self.player.stored_player.plugin_data[PLUGIN_NAME] = (
            plugin_data.to_stored_value()
        )


class _FfeDataSource(ABC):
    @property
    def _player_updater_fields(self) -> list[PlayerUpdaterField]:
        return (
            PlayerUpdaterField.ratings_fields()
            + PlayerUpdaterField.identity_fields()
            + PlayerUpdaterField.federation_fields()
            + PlayerUpdaterField.club_fields()
            + PlayerUpdaterField.fide_fields()
        ) + [
            PlayerUpdaterField(_('League'), 'league'),
            PlayerUpdaterField(_('FFE licence number'), 'ffe_licence_number'),
            PlayerUpdaterField(_('FFE Licence'), 'ffe_licence'),
        ]

    @abstractmethod
    async def player_matches_from_licence_number(
        self, ffe_licence_numbers: list[str]
    ) -> list[StoredPlayer] | None:
        """Fetch player matches in the data source from their licence numbers.
        Return None if it fails."""

    @staticmethod
    def _get_ffe_licence_number(stored_player: StoredPlayer) -> str | None:
        return get_data(stored_player.plugin_data, 'ffe_licence_number', None)

    async def _get_player_matches(
        self,
        players: list[Player],
        field_ids: list[str],
        diff_only: bool,
    ) -> list[PlayerComparator] | None:
        ffe_licence_numbers: list[str] = []
        for player in players:
            if licence_number := self._get_ffe_licence_number(player.stored_player):
                ffe_licence_numbers.append(licence_number)
        match_stored_players = await self.player_matches_from_licence_number(
            ffe_licence_numbers
        )
        if match_stored_players is None:
            return None
        return DataSource.create_player_comparators(
            players,
            match_stored_players,
            lambda p1, p2: (
                self._get_ffe_licence_number(p1) is not None
                and self._get_ffe_licence_number(p1) == self._get_ffe_licence_number(p2)
            ),
            field_ids,
            diff_only,
            FfePlayerComparator,
        )

    @property
    def _search_fields(self) -> list[str]:
        return [_('Name'), _('FFE ID'), _('FIDE ID')]

    @property
    def _player_search_result_template(self) -> str:
        return '/ffe_search_result.html'

    @staticmethod
    def _get_player_source_id(stored_player: StoredPlayer) -> str:
        return str(get_data(stored_player.plugin_data, 'ffe_id'))


class FfeLocalDataSource(LocalDataSource, _FfeDataSource):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-local'

    @staticmethod
    def static_name() -> str:
        return _('FFE database (local)')

    @property
    def local_database_type(self) -> type[LocalSourcePlayerDatabase]:
        return FfeDatabase

    @property
    def player_updater_fields(self) -> list[PlayerUpdaterField]:
        return self._player_updater_fields

    async def get_player_matches(
        self,
        players: list[Player],
        field_ids: list[str],
        diff_only: bool,
    ) -> list[PlayerComparator] | None:
        return await self._get_player_matches(players, field_ids, diff_only)

    async def player_matches_from_licence_number(
        self, ffe_licence_numbers: list[str]
    ) -> list[StoredPlayer] | None:
        database = FfeDatabase()
        if not database.exists():
            return None
        with database:
            return database.get_stored_players_by_ffe_licence_number(
                ffe_licence_numbers
            )

    @property
    def search_fields(self) -> list[str]:
        return self._search_fields

    @property
    def player_search_result_template(self) -> str:
        return self._player_search_result_template

    def get_player_source_id(self, stored_player: StoredPlayer) -> str:
        return self._get_player_source_id(stored_player)

    async def get_stored_player_by_source_id(
        self, player_source_id: str
    ) -> StoredPlayer | None:
        if not player_source_id.isdigit():
            return None
        with FfeDatabase() as database:
            return database.get_stored_player_by_ffe_id(int(player_source_id))


class FfeOnlineDataSource(OnlineDataSource, _FfeDataSource):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-online'

    @staticmethod
    def static_name() -> str:
        return _('FFE database (online)')

    @classmethod
    async def check_connection(cls) -> bool:
        try:
            async with FFESqlServer():
                return True
        except SharlyChessException:
            return False

    @property
    def player_updater_fields(self) -> list[PlayerUpdaterField]:
        return self._player_updater_fields

    async def get_player_matches(
        self,
        players: list[Player],
        field_ids: list[str],
        diff_only: bool,
    ) -> list[PlayerComparator] | None:
        return await self._get_player_matches(players, field_ids, diff_only)

    async def player_matches_from_licence_number(
        self, ffe_licence_numbers: list[str]
    ) -> list[StoredPlayer] | None:
        try:
            async with FFESqlServer() as server:
                return await server.get_stored_players_by_ffe_licence_number(
                    ffe_licence_numbers
                )
        except SharlyChessException:
            return None

    @property
    def search_fields(self) -> list[str]:
        return self._search_fields

    @property
    def player_search_result_template(self) -> str:
        return self._player_search_result_template

    def get_player_source_id(self, stored_player: StoredPlayer) -> str:
        return self._get_player_source_id(stored_player)

    async def get_stored_player_by_source_id(
        self, player_source_id: str
    ) -> StoredPlayer | None:
        if not player_source_id.isdigit():
            return None
        async with FFESqlServer() as ffe_sql_server:
            return await ffe_sql_server.get_stored_player_by_ffe_id(
                int(player_source_id)
            )

    async def _search_player(
        self, string: str, federation: str, page: int = 0, limit: int | None = None
    ) -> list[StoredPlayer]:
        async with FFESqlServer() as ffe_sql_server:
            return await ffe_sql_server.search_player(
                unicode_normalize(string), federation, page, limit
            )


class LeaguePlayerSplitter(PlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-ffe_league'

    @staticmethod
    def static_name() -> str:
        return _('League')

    @staticmethod
    def get_split_key(player: Player) -> str:
        return FFEUtils.get_player_plugin_data(player).league or ''


class FFESiteQRCodeType(QRCodeType):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-ffe_site'

    @staticmethod
    def static_name() -> str:
        return _('Tournament on the FFE site')

    @staticmethod
    def get_valid_options() -> list[str]:
        return [TournamentPrintOption.static_id()]

    @staticmethod
    def title(doc: QRCodePrintDocument) -> str:
        tournament = doc.tournament
        return tournament.name

    @staticmethod
    def info(doc: QRCodePrintDocument) -> str:
        return _('Scan to access the tournament on the FFE site.')

    @staticmethod
    def url(doc: QRCodePrintDocument) -> tuple[bool, str]:
        tournament = doc.tournament
        ffe_id = FFEUtils.get_tournament_plugin_data(tournament).ffe_id

        if not ffe_id:
            return False, _('No FFE ID defined for tournament [{tournament}].').format(
                tournament=tournament.uniq_id
            )
        url = f'https://echecs.asso.fr/FicheTournoi.aspx?Ref={ffe_id}'
        return True, url

    @staticmethod
    def get_qr_code(url) -> str:
        return QRCodeType.generate_qr_code(
            url=url,
            logo=PLUGIN_DIR / 'static' / 'images' / 'ffe-qr-logo.jpg',
        )


class NicoisSwissVariation(Acceleration3GroupsSwissVariation):
    """Variation of the Progressive swiss system,
    with even more progressive virtual points.
    A draw virtual point is added every 2 real draw points,
    instead of 3 in the original Progressive system"""

    @classmethod
    def static_id(cls) -> str:
        return f'{PLUGIN_NAME}-{super().static_id()}'

    @staticmethod
    def variation_id() -> str:
        return 'NICOIS'

    @staticmethod
    def static_name() -> str:
        return _('"Niçois" accelerated system')

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: Tournament,
        player: Player,
        at_round: int,
    ) -> float:
        if at_round >= tournament.rounds - 1:
            # Before the second to last round, we remove the virtual
            # points, and use a simple Swiss Dutch system.
            return 0.0
        return cls._compute_virtual_points(
            group=cls.get_player_group(tournament, player),
            points=player.points_before(at_round),
            tournament_rounds=tournament.rounds,
            draw_points=Result.DRAW.points(tournament.point_values),
            win_points=Result.WIN.points(tournament.point_values),
        )

    @classmethod
    def _get_group_a_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        win_points = Result.WIN.points(tournament.point_values)
        return [
            (cls._rounds_prefix(1, tournament.rounds - 2), 2 * win_points),
            (cls._rounds_prefix(tournament.rounds - 1, tournament.rounds), 0),
        ]

    @classmethod
    def _get_detailed_group_tooltip_lines(
        cls, tournament: Tournament, group: AccelerationGroup
    ) -> list[tuple[str, float | None]]:
        draw_points = Result.DRAW.points(tournament.point_values)
        win_points = Result.WIN.points(tournament.point_values)
        get_vpoints = partial(
            cls._compute_virtual_points,
            group=group,
            tournament_rounds=tournament.rounds,
            draw_points=draw_points,
            win_points=win_points,
        )
        return [
            (cls._rounds_prefix(1, tournament.rounds - 2), None),
            *cls._get_incremental_points_lines(
                get_vpoints, draw_points, 2 * win_points
            ),
            (cls._rounds_prefix(tournament.rounds - 1, tournament.rounds), 0),
        ]

    @classmethod
    def _get_group_b_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        return cls._get_detailed_group_tooltip_lines(tournament, AccelerationGroup.B)

    @classmethod
    def _get_group_c_tooltip_lines(
        cls, tournament: Tournament
    ) -> list[tuple[str, float | None]]:
        return cls._get_detailed_group_tooltip_lines(tournament, AccelerationGroup.C)

    @staticmethod
    @cache
    def _compute_virtual_points(
        points: int,
        group: AccelerationGroup,
        tournament_rounds: int,
        draw_points: float,
        win_points: float,
    ) -> float:
        if 2 * points >= tournament_rounds * win_points:
            # If a player gets at least half the possible score,
            # their capital is set at 2 points.
            return 2 * win_points

        vpoints = 0.0
        match group:
            case AccelerationGroup.A:
                # Starts with 2 gain points (max)
                return 2 * win_points
            case AccelerationGroup.B:
                # Starts with 1 gain point
                # Earns a draw point at 3 real draw points, and a final one at 5
                vpoints = win_points
                if points >= 3 * draw_points:
                    vpoints += draw_points
                    if points >= 5 * draw_points:
                        vpoints += draw_points
            case AccelerationGroup.C:
                # Starts with 0 virtual points
                # Players get a virtual draw points for 2 real draw points
                vpoints = draw_points * (points // (2 * draw_points))
        return min(2 * win_points, vpoints)


class FfeLeaguePlayerFilter(PlayerFilter):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-LEAGUE'

    @staticmethod
    def static_name() -> str:
        return _('League')

    @staticmethod
    def available_options() -> list[type[PlayerFilterOption]]:
        return [
            FfeLeaguesFilterOption,
            ExcludeFilterOption,
        ]

    @cached_property
    def is_player_included_function(self) -> Callable[[Player], bool]:
        leagues, exclude = self.get_option_values()
        if exclude:
            return (
                lambda player: FFEUtils.get_player_plugin_data(player).league
                not in leagues
            )
        else:
            return (
                lambda player: FFEUtils.get_player_plugin_data(player).league in leagues
            )

    def full_name(self, tournament: 'Tournament') -> str:
        leagues, exclude = self.get_option_values()
        option_str = ', '.join(leagues)
        if exclude:
            option_str = _('Exclude: {values}').format(values=option_str)
        return f'{self.name} ({option_str})'


class FfeLeaguesFilterOption(SelectPlayerFilterOption[str]):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-LEAGUES'

    @property
    def template_name(self) -> str:
        return '/ffe_league_player_filter_option.html'

    @property
    def type(self) -> type | UnionType:
        return list[str]

    @property
    def default_value(self) -> Any:
        return []

    def get_all_known_values(self, tournament: 'Tournament') -> list[str]:
        from plugins.ffe.ffe import FfePlugin

        return list(FfePlugin.FFE_LEAGUES)

    def get_player_counter(self, tournament: 'Tournament') -> Counter[str]:
        counter: Counter[str] = Counter[str]()
        for player in tournament.players:
            if league := FFEUtils.get_player_plugin_data(player).league:
                counter[league] += 1
        return counter

    def get_key(self, object_: str) -> str:
        return object_

    def get_name(self, object_: str) -> str:
        from plugins.ffe.ffe import FfePlugin

        if object_ not in FfePlugin.FFE_LEAGUES:
            return object_
        return f'{object_} - {FfePlugin.FFE_LEAGUES[object_]}'

    def validate(self):
        self._validate_list_type(str)
        if not self.value:
            raise OptionError(_('At least one league is expected.'), self)


class FfeLicencePlayerFilter(PlayerFilter):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-LICENCE'

    @staticmethod
    def static_name() -> str:
        return _('FFE Licence type')

    @staticmethod
    def available_options() -> list[type[PlayerFilterOption]]:
        return [FfeLicenceFilterOption]

    @cached_property
    def is_player_included_function(self) -> Callable[[Player], bool]:
        licences = self.get_option_values()[0]
        return (
            lambda player: FFEUtils.get_player_plugin_data(player).ffe_licence
            in licences
        )

    def full_name(self, tournament: 'Tournament') -> str:
        option_values = self.get_option_values()[0]
        licence_types = [
            PlayerFFELicence(value).compact_name for value in option_values
        ]
        return f'{self.name} ({", ".join(licence_types)})'


class FfeLicenceFilterOption(SelectPlayerFilterOption[int]):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-LICENCES'

    @property
    def template_name(self) -> str:
        return '/ffe_licence_player_filter_option.html'

    @property
    def type(self) -> type | UnionType:
        return list[int]

    @property
    def default_value(self) -> Any:
        return []

    def get_all_known_values(self, tournament: 'Tournament') -> list[int]:
        return [licence.value for licence in PlayerFFELicence]

    def get_player_counter(self, tournament: 'Tournament') -> Counter[int]:
        counter: Counter[int] = Counter[int]()
        for player in tournament.players:
            if ffe_licence := FFEUtils.get_player_plugin_data(player).ffe_licence:
                counter[ffe_licence] += 1
        return counter

    def get_key(self, object_: int) -> str:
        return str(object_)

    def get_name(self, object_: int) -> str:
        licence = PlayerFFELicence(object_)
        return licence.compact_name

    def validate(self):
        self._validate_list_type(int)
        if not self.value:
            raise OptionError(_('At least one licence type is expected.'), self)


class FfeLeagueTableColumn(PlayerColumn):
    @property
    def header_content(self) -> str:
        return _('League *** LEAGUE FOR TABLE HEADER')

    def get_cell_content(self, player: Player) -> Any:
        return FFEUtils.get_player_plugin_data(player).league or ''

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class FfeIdDatasheetColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'ffe_id'

    def get_cell_content(self, player: Player) -> Any:
        return FFEUtils.get_player_plugin_data(player).ffe_id or ''


class FfeLicenceNumberDatasheetColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'ffe_licence_number'

    def get_cell_content(self, player: Player) -> Any:
        return FFEUtils.get_player_plugin_data(player).ffe_licence_number or ''


class FfeLicenceDatasheetColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'ffe_licence'

    def get_cell_content(self, player: Player) -> Any:
        return FFEUtils.get_player_plugin_data(player).ffe_licence.short_name


class FfeLeagueDatasheetColumn(DatasheetColumn):
    @property
    def header_content(self) -> str:
        return 'league'

    def get_cell_content(self, player: Player) -> Any:
        return FFEUtils.get_player_plugin_data(player).league or ''
