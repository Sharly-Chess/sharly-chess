from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Callable
from functools import partial, cached_property
from types import UnionType
from typing import override, Any

from common import unicode_normalize
from common.exception import SharlyChessException
from common.i18n import _
from data.input_output.data_source import (
    FidePlayerComparator,
    PlayerComparator,
    DataSource,
    PlayerUpdaterField,
    LocalDataSource,
    OnlineDataSource,
)
from data.pairings.settings import PairingSetting
from data.pairings.variations import SwissVariation
from data.player import Player
from data.print_documents import PlayerSplitter
from data.prize.player_filter_options import (
    PlayerFilterOption,
    SelectPlayerFilterOption,
)
from data.prize.player_filters import PlayerFilter
from data.tournament import Tournament
from database.access.papi.papi_store import StoredPlayer
from database.sqlite.local_source_database import LocalSourceDatabase
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_database import FfeDatabase
from plugins.ffe.ffe_sql_server import FFESqlServer
from plugins.pairing_acceleration.pairing_settings import DualRatingLimitsSetting
from plugins.utils import PluginUtils
from utils.enum import Result
from utils.option import OptionError

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FfePlayerComparator(FidePlayerComparator):
    @cached_property
    def diff_field_ids(self) -> list[str] | None:
        if not self.match_player:
            return None
        diff_field_ids = super().diff_field_ids or []
        for field_id in ('league', 'ffe_licence'):
            if field_id in self.field_ids and get_data(
                self.player.plugin_data, field_id
            ) != get_data(self.match_player.plugin_data, field_id):
                diff_field_ids.append(field_id)
        return diff_field_ids

    @override
    def update_player_from_match(self, field_ids: list[str]):
        if not self.match_player:
            return
        super().update_player_from_match(field_ids)
        for field_id in ('league', 'ffe_licence'):
            if field_id in self.field_ids and get_data(
                self.player.plugin_data, field_id
            ) != (match := get_data(self.match_player.plugin_data, field_id)):
                self.player.plugin_data[PLUGIN_NAME][field_id] = match


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
        return get_data(stored_player.plugin_data, 'ffe_licence_number')

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
    def local_database_type(self) -> type[LocalSourceDatabase]:
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

    async def search_player(
        self, string: str, limit: int | None = None
    ) -> list[StoredPlayer]:
        async with FFESqlServer() as ffe_sql_server:
            return await ffe_sql_server.search_player(unicode_normalize(string), limit)


class LeaguePlayerSplitter(PlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-ffe_league'

    @staticmethod
    def static_name() -> str:
        return _('League')

    @staticmethod
    def get_split_key(player: Player) -> str:
        return get_data(player.plugin_data, 'league', '')


class NicoisSwissVariation(SwissVariation):
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

    @property
    def settings(self) -> list[PairingSetting]:
        return super().settings + [DualRatingLimitsSetting()]

    @staticmethod
    def compute_virtual_points(
        tournament: Tournament,
        player: Player,
        at_round: int,
    ) -> float:
        lower_limit, upper_limit = DualRatingLimitsSetting.get_value(tournament)

        draw_points = Result.DRAW.points(tournament.point_values)
        gain_points = Result.GAIN.points(tournament.point_values)

        if at_round >= tournament.rounds - 1:
            # Before the second to last round, we remove the virtual
            # points, and use a simple Swiss Dutch system.
            return 0.0

        points = player.points_before(at_round)
        if 2 * points >= tournament.rounds * gain_points:
            # If a player gets at least half the possible score,
            # their capital is set at 2 points.
            return 2 * gain_points

        if player.rating >= upper_limit:
            # Group A: starts with 2 gain points (max)
            return 2 * gain_points

        if player.rating >= lower_limit:
            # Group B: starts with 1 gain point
            # Earns a draw point at 3 real draw points, and a final one at 5
            vpoints = gain_points
            if points >= 3 * draw_points:
                vpoints += draw_points
                if points >= 5 * draw_points:
                    vpoints += draw_points
        else:
            # Group C: starts with 0 virtual points
            # Players get a virtual draw points for 2 real draw points
            vpoints = draw_points * (points // (2 * draw_points))

        # Players cannot have more than 2 virtual points
        return min(2 * gain_points, vpoints)


class FfeLeaguePlayerFilter(PlayerFilter):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-LEAGUE'

    @staticmethod
    def static_name() -> str:
        return _('League')

    @staticmethod
    def available_options() -> list[type[PlayerFilterOption]]:
        return [FfeLeaguesFilterOption]

    @cached_property
    def is_player_included_function(self) -> Callable[[Player], bool]:
        leagues = self.get_option_values()[0]
        return lambda player: get_data(player.plugin_data, 'league') in leagues

    def __str__(self) -> str:
        return f'{self.name} ({", ".join(self.get_option_values()[0])})'


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

        return [code for code in FfePlugin.FFE_LEAGUES.keys() if code]

    def get_player_counter(self, tournament: 'Tournament') -> Counter[str]:
        counter: Counter[str] = Counter[str]()
        for player in tournament.players:
            if league := get_data(player.plugin_data, 'league'):
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
