from functools import partial, cached_property
from typing import override

from common.exception import SharlyChessException
from common.i18n import _
from data.input_output.player_updaters import (
    FidePlayerComparator,
    PlayerComparator,
    PlayerUpdater,
    PlayerUpdaterField,
)
from data.pairings.settings import PairingSetting
from data.pairings.variations import SwissVariation
from data.player import Player
from data.print_documents import PlayerSplitter
from data.tournament import Tournament
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_database import FfeDatabase
from plugins.ffe.ffe_sql_server import FFESqlServer
from plugins.pairing_acceleration.pairing_settings import DualRatingLimitsSetting
from plugins.utils import PluginUtils
from utils.enum import Result

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


class FfePlayerUpdater(PlayerUpdater):
    @staticmethod
    def static_name() -> str:
        return _('FFE database')

    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-ffe'

    @override
    def fields(self) -> list[PlayerUpdaterField]:
        return (
            self._ratings_fields()
            + self._identity_fields()
            + self._federation_fields()
            + self._club_fields()
            + self._fide_fields()
        ) + [
            PlayerUpdaterField(_('League'), 'league'),
            PlayerUpdaterField(_('FFE licence number'), 'ffe_licence_number'),
            PlayerUpdaterField(_('FFE Licence'), 'ffe_licence'),
        ]

    @staticmethod
    def _get_ffe_licence_number(player) -> str | None:
        return get_data(player.plugin_data, 'ffe_licence_number')

    @override
    async def get_player_matches(
        self,
        players: list[Player],
        field_ids: list[str],
        diff_only: bool,
    ) -> list[PlayerComparator] | None:
        ffe_licence_numbers: list[str] = []
        for player in players:
            if ffe_licence_number := self._get_ffe_licence_number(player):
                ffe_licence_numbers.append(ffe_licence_number)
        match_players: list[Player]
        try:
            async with FFESqlServer() as server:
                match_players = [
                    player
                    async for player in await server.get_players_by_ffe_licence_number(
                        ffe_licence_numbers
                    )
                ]
        except SharlyChessException:
            database = FfeDatabase()
            if database.exists():
                assert database.updated_at is not None
                self.warning_message = _(
                    'Warning: connection to the online FFE database failed, '
                    'local database was used. Some data might be outdated '
                    '(last update on {date})'
                ).format(date=database.updated_at.strftime('%d-%m-%Y'))
                with database:
                    match_players = database.get_players_by_ffe_licence_number(
                        ffe_licence_numbers
                    )
            else:
                return None
        return self._create_player_comparators(
            players,
            match_players,
            lambda p1, p2: (
                self._get_ffe_licence_number(p1) is not None
                and self._get_ffe_licence_number(p1) == self._get_ffe_licence_number(p2)
            ),
            field_ids,
            diff_only,
            FfePlayerComparator,
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
