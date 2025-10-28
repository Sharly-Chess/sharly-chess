from types import ModuleType

from packaging.version import Version

from common.i18n import _
from data.pairings.variations import SwissVariation, StandardSwissVariation
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from plugins.hookspec import hookimpl
from plugins.migration import PluginMigrationManager
from plugins.pairing_acceleration import PLUGIN_NAME, migrations
from plugins.pairing_acceleration.pairing_variations import (
    HaleySwissVariation,
    HaleySoftSwissVariation,
    ProgressiveSwissVariation,
    BakuSwissVariation,
)
from plugins.utils import Plugin, PluginUtils


class PairingAccelerationPlugin(Plugin):
    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return _('Accelerated pairings')

    @property
    def description(self) -> str:
        return _('Accelerated variations of the swiss pairing system.')

    @property
    def version(self) -> Version:
        return Version('0.1.0')

    @property
    def base_migration_module(self) -> ModuleType:
        return migrations

    def used_by_tournament(self, tournament: 'Tournament') -> bool:
        return any(
            isinstance(tournament.pairing_variation, variation_type)
            for variation_type in self._pairing_variation_types
        )

    @hookimpl
    def get_event_migration_manager(
        self, event_database: EventDatabase
    ) -> PluginMigrationManager:
        return self.get_migration_manager(event_database)

    @property
    def _pairing_variation_types(self) -> list[type[SwissVariation]]:
        return [
            BakuSwissVariation,
            HaleySwissVariation,
            HaleySoftSwissVariation,
            ProgressiveSwissVariation,
        ]

    @hookimpl
    def insert_swiss_pairing_variation_types(
        self, variation_types: list[type[SwissVariation]]
    ):
        for variation_type in reversed(self._pairing_variation_types):
            standard: type[SwissVariation] = StandardSwissVariation
            PluginUtils.insert_on_equals(variation_types, variation_type, standard)
