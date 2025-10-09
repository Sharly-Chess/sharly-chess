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
    @classmethod
    def resolve_auto_upload(cls, tournament: Tournament) -> bool:
        tournament_plugin_data = cls.get_tournament_plugin_data(tournament)
        if tournament_plugin_data.auto_upload is not None:
            return tournament_plugin_data.auto_upload
        event_plugin_data = cls.get_event_plugin_data(tournament.event)
        return event_plugin_data.auto_upload

    @classmethod
    def resolve_auto_upload_delay(cls, event: Event) -> int:
        plugin_data = cls.get_event_plugin_data(event)
        if plugin_data.auto_upload_delay is not None:
            return plugin_data.auto_upload_delay
        return FFE_DEFAULT_UPLOAD_DELAY

    @staticmethod
    def get_event_plugin_data(event: Event) -> 'FfeEventPluginData':
        plugin_data = event.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, FfeEventPluginData)
        return plugin_data

    @staticmethod
    def get_tournament_plugin_data(tournament: Tournament) -> 'FfeTournamentPluginData':
        plugin_data = tournament.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, FfeTournamentPluginData)
        return plugin_data

    @staticmethod
    def get_player_plugin_data(player: Player) -> 'FfePlayerPluginData':
        plugin_data = player.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, FfePlayerPluginData)
        return plugin_data

    @staticmethod
    def ffe_actions_unavailable_message(tournament: Tournament) -> str | None:
        from plugins.ffe.papi_converter import PapiConverter

        pd = FFEUtils.get_tournament_plugin_data(tournament)
        if not pd.ffe_id and not pd.password:
            return _('FFE certification number and password not defined.')
        if not pd.ffe_id:
            return _('FFE certification number not defined.')
        if not pd.password:
            return _('FFE password not defined.')
        return PapiConverter.papi_export_unavailable_message(tournament)


class PlayerFFELicence(IntEnum):
    NONE = 0
    N = 1
    A = 2
    B = 3

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
    def compact_name(self) -> str:
        match self:
            case PlayerFFELicence.NONE:
                return _('None *** FFE licence')
            case PlayerFFELicence.N:
                return _('Expired *** FFE licence')
            case PlayerFFELicence.A:
                return _('A - Competition *** FFE licence')
            case PlayerFFELicence.B:
                return _('B - Leisure *** FFE licence')
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
class FfeEventPluginData(PluginData):
    auto_upload: bool
    auto_upload_delay: int

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            auto_upload=stored_value.get('auto_upload') or False,
            auto_upload_delay=stored_value.get(
                'auto_upload_delay', FFE_DEFAULT_UPLOAD_DELAY
            ),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'auto_upload': self.auto_upload,
            'auto_upload_delay': self.auto_upload_delay,
        }

    @classmethod
    def from_form_data(
        cls, data: dict[str, str], previous_object: Self | None = None
    ) -> Self:
        return cls(
            auto_upload=WebContext.form_data_to_bool(data, 'ffe_auto_upload'),
            auto_upload_delay=WebContext.form_data_to_int(data, 'ffe_auto_upload_delay')
            or FFE_DEFAULT_UPLOAD_DELAY,
        )

    def to_form_data(self) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'ffe_auto_upload': self.auto_upload,
                'ffe_auto_upload_delay': self.auto_upload_delay,
            }
        )


@dataclass
class FfeTournamentPluginData(PluginData):
    ffe_id: int | None
    password: str | None
    auto_upload: bool | None
    last_upload: float | None
    last_rules_upload: float | None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            ffe_id=stored_value.get('ffe_id', None),
            password=stored_value.get('password', None),
            auto_upload=stored_value.get('auto_upload', None),
            last_upload=stored_value.get('last_upload', 0.0),
            last_rules_upload=stored_value.get('last_rules_upload', 0.0),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'ffe_id': self.ffe_id,
            'password': self.password,
            'auto_upload': self.auto_upload,
            'last_upload': self.last_upload,
            'last_rules_upload': self.last_rules_upload,
        }

    @classmethod
    def from_form_data(
        cls, data: dict[str, str], previous_object: Self | None = None
    ) -> Self:
        return cls(
            last_upload=previous_object.last_upload if previous_object else None,
            last_rules_upload=previous_object.last_rules_upload
            if previous_object
            else None,
            ffe_id=WebContext.form_data_to_int(data, 'ffe_id'),
            password=WebContext.form_data_to_str(data, 'ffe_password'),
            auto_upload=WebContext.form_data_to_bool_or_none(data, 'ffe_auto_upload'),
        )

    def to_form_data(self) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'ffe_id': self.ffe_id,
                'ffe_password': self.password,
                'ffe_auto_upload': self.auto_upload,
            }
        )


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
