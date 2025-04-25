from packaging.version import Version

from common.i18n import _
from data.pairings.variations import SwissVariation, StandardSwissVariation
from plugins.hookspec import hookimpl
from plugins.pairing_acceleration.pairing_variations import (
    HaleySwissVariation,
    HaleySoftSwissVariation,
    ProgressiveSwissVariation,
)
from plugins.utils import Plugin, PluginUtils


class PairingAccelerationPlugin(Plugin):
    @staticmethod
    def static_id() -> str:
        return 'pairing_acceleration'

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
    def default_is_enabled(self) -> bool:
        # TODO (Molrn) switch to False once Papi-dependency has been removed
        return True

    @property
    def is_state_editable(self) -> bool:
        # FFE plugin is dependent from acceleration for Papi compatibility
        # Until FFE plugin can be disabled, this one should remain not editable
        return False

    @hookimpl
    def insert_swiss_pairing_variation_types(
        self, variation_types: list[type[SwissVariation]]
    ):
        ordered_types: list[type[SwissVariation]] = [
            HaleySwissVariation,
            HaleySoftSwissVariation,
            ProgressiveSwissVariation,
        ]
        for variation_type in reversed(ordered_types):
            standard: type[SwissVariation] = StandardSwissVariation
            PluginUtils.insert_on_equals(variation_types, variation_type, standard)
