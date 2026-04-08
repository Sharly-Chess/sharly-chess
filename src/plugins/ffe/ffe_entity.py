import re
from collections import Counter
from collections.abc import Callable
from functools import partial, cached_property, cache
from types import UnionType
from typing import Any

from common.exception import OptionError, SharlyChessException
from common.i18n import _
from data.columns.player_datasheet import DatasheetColumn
from data.columns.player_table import TournamentPlayerTableColumn
from data.columns.players_tab import FilterPlayersTabColumn
from data.criteria.player_filter_options import (
    PlayerFilterOption,
    SelectPlayerFilterOption,
    ExcludeFilterOption,
)
from data.criteria.player_filters import PlayerFilter
from data.event import Event
from data.player import Player, TournamentPlayer
from data.print_documents import PlayerSplitter, PrintOption
from data.print_documents.documents import QRCodePrintDocument, TournamentPrintOption
from data.print_documents.qrcode_types import QRCodeType
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredPlayer
from plugins.ffe import PLUGIN_NAME, PLUGIN_DIR
from plugins.ffe.ffe_database import PlayerFFELicence
from plugins.ffe.utils import FFEUtils, FfePlayerPluginData, FFE_LEAGUES
from plugins.pairing_acceleration.pairing_settings import AccelerationGroup
from plugins.pairing_acceleration.pairing_variations import (
    Acceleration3GroupsSwissVariation,
)
from plugins.utils import PluginUtils
from utils.enum import Result

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class LeaguePlayerSplitter(PlayerSplitter):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-ffe_league'

    @staticmethod
    def static_name() -> str:
        return _('League')

    @staticmethod
    def get_split_key(tournament_player: TournamentPlayer) -> str:
        return FFEUtils.get_player_plugin_data(tournament_player).league or ''

    @staticmethod
    def get_empty_key_default() -> str:
        return _('League not specified')


class FFESiteQRCodeType(QRCodeType):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-ffe_site'

    @staticmethod
    def static_name() -> str:
        return _('Tournament on the FFE site')

    @staticmethod
    def get_valid_option_types() -> list[type[PrintOption]]:
        return [TournamentPrintOption]

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
                tournament=tournament.name
            )
        return True, FFEUtils.tournament_url(ffe_id)

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
        tournament_player: TournamentPlayer,
        at_round: int,
    ) -> float:
        if at_round >= tournament.rounds - 1:
            # Before the second to last round, we remove the virtual
            # points, and use a simple Swiss Dutch system.
            return 0.0
        return cls._compute_virtual_points(
            group=cls.get_player_group(tournament, tournament_player),
            points=tournament_player.points_before(at_round),
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
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        leagues, exclude = self.get_option_values()
        if exclude:
            return lambda tournament_player: (
                FFEUtils.get_player_plugin_data(tournament_player).league not in leagues
            )
        else:
            return lambda tournament_player: (
                FFEUtils.get_player_plugin_data(tournament_player).league in leagues
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
        return list(FFE_LEAGUES)

    def get_tournament_player_counter(self, tournament: 'Tournament') -> Counter[str]:
        counter: Counter[str] = Counter[str]()
        for tournament_player in tournament.tournament_players:
            if league := FFEUtils.get_player_plugin_data(tournament_player).league:
                counter[league] += 1
        return counter

    def get_key(self, object_: str) -> str:
        return object_

    def get_name(self, object_: str) -> str:
        if object_ not in FFE_LEAGUES:
            return object_
        return f'{object_} - {FFE_LEAGUES[object_]}'

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
        return _('FFE Licence')

    @staticmethod
    def available_options() -> list[type[PlayerFilterOption]]:
        return [FfeLicenceFilterOption]

    @cached_property
    def is_player_included_function(self) -> Callable[[TournamentPlayer], bool]:
        licences = self.get_option_values()[0]
        return lambda tournament_player: (
            FFEUtils.get_player_plugin_data(tournament_player).ffe_licence in licences
        )

    def full_name(self, tournament: 'Tournament') -> str:
        option_values = self.get_option_values()[0]
        licence_types = [PlayerFFELicence(value).short_name for value in option_values]
        return f'{self.name} ({", ".join(licence_types)})'


class FfeLicenceFilterOption(SelectPlayerFilterOption[str]):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-LICENCES'

    @property
    def template_name(self) -> str:
        return '/ffe_licence_player_filter_option.html'

    @property
    def type(self) -> type | UnionType:
        return list[str]

    @property
    def default_value(self) -> Any:
        return []

    def get_all_known_values(self, tournament: 'Tournament') -> list[str]:
        return [
            licence.value
            for licence in PlayerFFELicence
            if licence != PlayerFFELicence.NONE
        ]

    def get_tournament_player_counter(self, tournament: 'Tournament') -> Counter[str]:
        counter: Counter[str] = Counter[str]()
        for tournament_player in tournament.tournament_players:
            if ffe_licence := FFEUtils.get_player_plugin_data(
                tournament_player
            ).ffe_licence:
                counter[ffe_licence] += 1
        return counter

    def get_key(self, object_: str) -> str:
        return object_

    def get_name(self, object_: str) -> str:
        licence = PlayerFFELicence(object_)
        return licence.compact_name

    def validate(self):
        self._validate_list_type(str)
        if not self.value:
            raise OptionError(_('At least one licence type is expected.'), self)


class FfeLeaguePlayersTabColumn(FilterPlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-league'

    @staticmethod
    def static_name() -> str:
        return _('League')

    @property
    def is_compact(self) -> bool:
        return True

    @staticmethod
    def _get_league(player: Player) -> str:
        return FFEUtils.get_player_plugin_data(player).league or ''

    def get_cell_content(self, player: Player) -> Any:
        return self._get_league(player)

    def _get_sort_key(self, player: Player) -> tuple:
        league = self._get_league(player)
        return not bool(league), league

    def get_filter_key(self, player: Player) -> str:
        return self._get_league(player)

    def get_filter_row_content(self, value: Any) -> str:
        if not value:
            return '-'
        if value not in FFE_LEAGUES:
            return value
        return f'{value} - {FFE_LEAGUES[value]}'


class FfeLicencePlayersTabColumn(FilterPlayersTabColumn):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-licence'

    @staticmethod
    def static_name() -> str:
        return _('FFE licence')

    @property
    def is_compact(self) -> bool:
        return True

    @property
    def header_template(self) -> str:
        return '/ffe_player_licence_header.html'

    @property
    def cell_template(self) -> str | None:
        return '/ffe_player_licence_cell.html'

    def _get_sort_key(self, player: Player) -> tuple:
        return (FFEUtils.get_player_plugin_data(player).ffe_licence,)

    def get_filter_key(self, player: Player) -> str:
        return FFEUtils.get_player_plugin_data(player).ffe_licence.value

    def get_filter_value_from_key(self, filter_key: str, event: Event) -> Any:
        return PlayerFFELicence(filter_key)

    def get_filter_row_content(self, value: Any) -> str:
        return value.compact_name


class FfeLeagueTableColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('League *** LEAGUE COLUMN HEADER')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return FFEUtils.get_player_plugin_data(tournament_player).league or ''

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class FfeLicenceTypeTableColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Lic. *** LICENCE COLUMN HEADER')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return FFEUtils.get_player_plugin_data(tournament_player).ffe_licence.short_name

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class FfeIdDatasheetColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'ffe_id'

    def get_cell_content(self, player: Player) -> Any:
        return FFEUtils.get_player_plugin_data(player).ffe_id

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if not value:
            return
        if not value.isdigit() or int(value) == 0:
            raise SharlyChessException(_('A positive integer is expected.'))
        plugin_data = FfePlayerPluginData.from_stored_value(
            stored_player.plugin_data.get(PLUGIN_NAME, {})
        )
        plugin_data.ffe_id = int(value)
        stored_player.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()


class FfeLicenceNumberDatasheetColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'ffe_licence_number'

    def get_cell_content(self, player: Player) -> Any:
        return FFEUtils.get_player_plugin_data(player).ffe_licence_number or ''

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if not value:
            return
        if not re.match(r'^[A-Z]\d{5}', value):
            raise SharlyChessException(
                _('Invalid format (expected: {format}).').format(format='A12345')
            )
        plugin_data = FfePlayerPluginData.from_stored_value(
            stored_player.plugin_data.get(PLUGIN_NAME, {})
        )
        plugin_data.ffe_licence_number = value or None
        stored_player.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()

    @property
    def is_unique(self) -> bool:
        return True


class FfeLicenceDatasheetColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'ffe_licence'

    def get_cell_content(self, player: Player) -> Any:
        return FFEUtils.get_player_plugin_data(player).ffe_licence.value

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        plugin_data = FfePlayerPluginData.from_stored_value(
            stored_player.plugin_data.get(PLUGIN_NAME, {})
        )
        try:
            plugin_data.ffe_licence = PlayerFFELicence(value)
        except ValueError:
            raise SharlyChessException(
                _('Unknown value (expected: {expected}).').format(
                    expected='|'.join(PlayerFFELicence)
                )
            )
        stored_player.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()


class FfeLeagueDatasheetColumn(DatasheetColumn):
    @property
    def id(self) -> str:
        return 'ffe_league'

    def get_cell_content(self, player: Player) -> Any:
        return FFEUtils.get_player_plugin_data(player).league or ''

    def _augment_stored_player(self, stored_player: StoredPlayer, value: str):
        if not value:
            return
        if value not in FFE_LEAGUES:
            raise SharlyChessException(_('Unknown league.'))
        plugin_data = FfePlayerPluginData.from_stored_value(
            stored_player.plugin_data.get(PLUGIN_NAME, {})
        )
        plugin_data.league = value
        stored_player.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
