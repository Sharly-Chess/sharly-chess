from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from functools import partial
from typing import Self, Any

from common.i18n import _
from data.event import Event
from data.player import Player
from data.tournament import Tournament
from plugins.ffe import PLUGIN_NAME
from plugins.utils import PluginUtils, PluginData
from web.controllers.base_controller import WebContext

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

    @staticmethod
    def get_player_plugin_data(player: Player) -> 'FfePlayerPluginData':
        plugin_data = player.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, FfePlayerPluginData)
        return plugin_data


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


@dataclass
class FfePlayerPluginData(PluginData):
    ffe_id: int | None
    ffe_licence: PlayerFFELicence
    ffe_licence_number: str | None
    league: str | None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            ffe_id=stored_value.get('ffe_id', None),
            ffe_licence=PlayerFFELicence(
                stored_value.get('ffe_licence', PlayerFFELicence.NONE)
            ),
            ffe_licence_number=stored_value.get('ffe_licence_number', None),
            league=stored_value.get('league', None),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'ffe_id': self.ffe_id,
            'ffe_licence': self.ffe_licence.value,
            'ffe_licence_number': self.ffe_licence_number,
            'league': self.league,
        }

    @classmethod
    def from_form_data(
        cls, data: dict[str, str], previous_object: Self | None = None
    ) -> Self:
        return cls(
            ffe_id=WebContext.form_data_to_int(data, 'ffe_id'),
            ffe_licence=PlayerFFELicence(
                WebContext.form_data_to_int(data, 'ffe_licence')
                or PlayerFFELicence.NONE
            ),
            ffe_licence_number=WebContext.form_data_to_str(data, 'ffe_licence_number'),
            league=WebContext.form_data_to_str(data, 'ffe_league'),
        )

    def to_form_data(self) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'ffe_id': self.ffe_id,
                'ffe_licence': self.ffe_licence.value,
                'ffe_licence_number': self.ffe_licence_number,
                'ffe_league': self.league,
            }
        )
