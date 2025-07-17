from datetime import datetime
from enum import IntEnum
from functools import partial
from typing import Self

from common.i18n import _
from data.event import Event
from data.tournament import Tournament
from data.pairings import PairingVariation, PairingSystem, systems, variations
from plugins.ffe import PLUGIN_NAME
from plugins.pairing_acceleration import pairing_variations as accelerations
from plugins.utils import PluginCoreMapper, PluginUtils

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)

FFE_MIN_UPLOAD_DELAY = 3
FFE_DEFAULT_UPLOAD_DELAY = 3
FFE_EPOCH = datetime(2000, 1, 1)


class FFEUtils:
    @staticmethod
    def resolve_auto_upload(tournament: Tournament) -> str | None:
        if (
            ffe_auto_upload := get_data(tournament.plugin_data, 'ffe_auto_upload')
        ) is not None:
            return ffe_auto_upload
        return get_data(tournament.event.plugin_data, 'ffe_auto_upload')

    @staticmethod
    def resolve_auto_upload_delay(event: Event) -> int:
        if (
            ffe_auto_upload_delay := get_data(
                event.plugin_data, 'ffe_auto_upload_delay'
            )
        ) is not None:
            return ffe_auto_upload_delay
        return FFE_DEFAULT_UPLOAD_DELAY


class PlayerFFELicence(IntEnum):
    NONE = 0
    N = 1
    A = 2
    B = 3

    @classmethod
    def from_papi_value(cls, value: str) -> Self:
        match value:
            case '' | None:
                return cls(cls.NONE)
            case 'N':
                return cls(cls.N)
            case 'A':
                return cls(cls.A)
            case 'B':
                return cls(cls.B)
            case _:
                raise ValueError(f'Unknown value: {value}')

    @property
    def to_papi_value(self) -> str:
        match self:
            case PlayerFFELicence.NONE:
                return ''
            case PlayerFFELicence.N:
                return 'N'
            case PlayerFFELicence.A:
                return 'A'
            case PlayerFFELicence.B:
                return 'B'
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def name(self) -> str:
        match self:
            case PlayerFFELicence.NONE:
                return _('No FFE Licence')
            case PlayerFFELicence.N:
                return _('Expired FFE licence')
            case PlayerFFELicence.B:
                return _('FFE licence B (leisure)')
            case PlayerFFELicence.A:
                return _('FFE licence A (competition)')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def short_name(self) -> str:
        match self:
            case PlayerFFELicence.NONE:
                return '-'
            case PlayerFFELicence.N:
                return 'N'
            case PlayerFFELicence.A:
                return 'A'
            case PlayerFFELicence.B:
                return 'B'
            case _:
                raise ValueError(f'Unknown value: {self}')


class PapiPairingSystem(PluginCoreMapper[str, PairingSystem]):
    @classmethod
    def _core_object_by_plugin_value(cls) -> dict[str, PairingSystem]:
        return {
            'Suisse': systems.SwissPairingSystem(),
            'ToutesRondes': systems.RoundRobinPairingSystem(),
        }


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
