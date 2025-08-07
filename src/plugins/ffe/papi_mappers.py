from enum import StrEnum

from data.pairings import PairingVariation, variations
from data.tie_breaks import TieBreak, PapiTieBreakManager
from plugins.pairing_acceleration import pairing_variations as accelerations
from plugins.utils import PluginCoreMapper
from utils.enum import TournamentRating, PlayerGender


class PapiPairingVariation(PluginCoreMapper[str, PairingVariation]):
    """Mapper of the pairing variations in the Papi database."""

    @classmethod
    def _core_object_by_plugin_value(cls) -> dict[str, PairingVariation]:
        from plugins.ffe.ffe_entity import NicoisSwissVariation

        return {
            'Standard': variations.StandardSwissVariation(),
            'Haley': accelerations.HaleySwissVariation(),
            'HaleySoft': accelerations.HaleySoftSwissVariation(),
            'SAD': accelerations.ProgressiveSwissVariation(),
            'Nicois': NicoisSwissVariation(),
            'Berger': variations.BergerRoundRobinVariation(),
        }

    @classmethod
    def get_plugin_value(cls, core_object: PairingVariation) -> str | None:
        if core_object == variations.DoubleBergerRoundRobinVariation():
            core_object = variations.BergerRoundRobinVariation()
        return super().get_plugin_value(core_object)


class PapiTieBreakMapper(PluginCoreMapper[str, TieBreak]):
    @classmethod
    def _core_object_by_plugin_value(cls) -> dict[str, TieBreak]:
        return {
            str(tie_break.static_papi_id()): tie_break
            for tie_break in PapiTieBreakManager.objects()
            if tie_break.static_papi_id() is not None
        }


class PapiTournamentRating(PluginCoreMapper[str, TournamentRating]):
    @staticmethod
    def _core_object_by_plugin_value() -> dict[str, TournamentRating]:
        return {
            'Elo': TournamentRating.STANDARD,
            'Rapide': TournamentRating.RAPID,
            'Blitz': TournamentRating.BLITZ,
        }


class PapiPlayerGender(PluginCoreMapper[str, PlayerGender]):
    @classmethod
    def _core_object_by_plugin_value(cls) -> dict[str, PlayerGender]:
        return {
            '': PlayerGender.NONE,
            'M': PlayerGender.MALE,
            'F': PlayerGender.FEMALE,
        }

    @classmethod
    def get_core_object(cls, plugin_value: str) -> PlayerGender:
        return cls._core_object_by_plugin_value()[plugin_value.upper()]


class PapiThreePointsForAWin(PluginCoreMapper[str, bool]):
    @classmethod
    def _core_object_by_plugin_value(cls) -> dict[str, bool]:
        return {
            'OUI': True,
            'NON': False,
        }

    @classmethod
    def get_core_object(cls, plugin_value: str) -> bool:
        return cls._core_object_by_plugin_value()[plugin_value.upper()]


class PapiColor(StrEnum):
    pass
