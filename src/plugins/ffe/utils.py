import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from functools import partial
from typing import Self, Any

from common.i18n import _
from data.account import Account
from data.event import Event
from data.player import Player
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_upload_status import (
    FFEUploadStatus,
    NeverUploadedFFEUploadStatus,
    FailureFFEUploadStatus,
    NetworkFailureFFEUploadStatus,
    UnexpectedFailureFFEUploadStatus,
    ModifiedFFEUploadStatus,
    UpToDateFFEUploadStatus,
    OngoingFFEUploadStatus,
    PendingFFEUploadStatus,
    NotConfiguredFFEUploadStatus,
    IncompatibleFFEUploadStatus,
    NotReachableFFEUploadStatus,
    AuthFailureFFEUploadStatus,
    FinishedFailureFFEUploadStatus,
    PapiConversionFailureFFEUploadStatus,
)
from plugins.utils import PluginUtils, PluginData, AccountPluginData
from utils.date_time import format_datetime
from utils.entity import EntityManager
from utils.enum import FormAction
from web.controllers.base_controller import WebContext

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)

FFE_UPLOAD_DELAY = 3
FFE_EPOCH = datetime(2000, 1, 1)

# The FFE league names.
FFE_LEAGUES: dict[str, str] = {
    'ARA': 'Auvergne-Rhône-Alpes',
    'BFC': 'Bourgogne-Franche-Comté',
    'BRE': 'Bretagne',
    'CRS': 'Corse',
    'CVL': 'Centre-Val de Loire',
    'EST': 'Grand-Est',
    'GUA': 'Guadeloupe',
    'GUY': 'Guyane',
    'HDF': 'Hauts-de-France',
    'IDF': 'Île-de-France',
    'MAR': 'Martinique',
    'NAQ': 'Nouvelle-Aquitaine',
    'NCA': 'Nouvelle-Calédonie',
    'NOR': 'Normandie',
    'OCC': 'Occitanie',
    'PAC': "Provence-Alpes-Côte d'azur",
    'PDL': 'Pays de la Loire',
    'POL': 'Saint-Pierre-et-Miquelon',
    'REU': 'Réunion',
}


class FFEUtils:
    @classmethod
    def resolve_auto_upload(cls, tournament: Tournament) -> bool:
        if not cls.get_event_plugin_data(tournament.event).auto_upload:
            return False
        return cls.get_tournament_plugin_data(tournament).auto_upload

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
    def get_account_plugin_data(account: Account) -> 'FfeAccountPluginData':
        plugin_data = account.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, FfeAccountPluginData)
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

    @staticmethod
    def update_tournament_plugin_data(
        tournament: Tournament,
        plugin_data: 'FfeTournamentPluginData',
    ):
        tournament.stored_tournament.plugin_data[PLUGIN_NAME] = (
            plugin_data.to_stored_value()
        )
        tournament.plugin_data[PLUGIN_NAME] = plugin_data
        with EventDatabase(tournament.event.uniq_id, write=True) as database:
            database.execute(
                'UPDATE tournament SET plugin_data = '
                f"json_set(plugin_data,'$.{PLUGIN_NAME}', json(?)) WHERE id = ?",
                (json.dumps(plugin_data.to_stored_value()), tournament.id),
            )

    @staticmethod
    def update_event_plugin_data(
        event: Event,
        plugin_data: 'FfeEventPluginData',
    ):
        event.stored_event.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
        event.plugin_data[PLUGIN_NAME] = plugin_data
        with EventDatabase(event.uniq_id, True) as database:
            database.execute(
                'UPDATE info SET plugin_data = '
                f"json_set(plugin_data,'$.{PLUGIN_NAME}', json(?))",
                (json.dumps(plugin_data.to_stored_value()),),
            )

    @classmethod
    def tournament_url(cls, ffe_id: int) -> str:
        return f'https://echecs.asso.fr/FicheTournoi.aspx?Ref={ffe_id}'

    @classmethod
    def resolve_tournament_upload_statuses(
        cls, tournament: Tournament
    ) -> list[FFEUploadStatus]:
        from plugins.ffe.ffe_background_uploader import FfeBackgroundUploader
        from plugins.ffe.papi_converter import PapiConverter

        plugin_data = cls.get_tournament_plugin_data(tournament)

        if not plugin_data.ffe_id or not plugin_data.password:
            return [NotConfiguredFFEUploadStatus()]

        statuses: list[FFEUploadStatus] = []

        # Last upload failure
        if plugin_data.upload_failure_id:
            status = FFEUploadFailureStatusManager().get_object(
                plugin_data.upload_failure_id
            )
            statuses.append(status)

        if PapiConverter.papi_export_unavailable_message(tournament):
            statuses.append(IncompatibleFFEUploadStatus())

        is_modified = FfeBackgroundUploader.ffe_upload_needed(tournament)
        # Current data status
        if not plugin_data.last_upload_at:
            statuses.append(NeverUploadedFFEUploadStatus())
        elif is_modified:
            statuses.append(ModifiedFFEUploadStatus())
        else:
            statuses.append(UpToDateFFEUploadStatus())

        # Next upload status
        if FfeBackgroundUploader.is_upload_ongoing(tournament):
            statuses.append(OngoingFFEUploadStatus())
        elif FfeBackgroundUploader.is_upload_queued(tournament) or (
            FfeBackgroundUploader.is_upload_scheduled(tournament) and is_modified
        ):
            statuses.append(PendingFFEUploadStatus())
        return statuses


class FFEUploadFailureStatusManager(EntityManager[FailureFFEUploadStatus]):
    def entity_types(self) -> list[type[FailureFFEUploadStatus]]:
        return [
            NetworkFailureFFEUploadStatus,
            UnexpectedFailureFFEUploadStatus,
            NotReachableFFEUploadStatus,
            AuthFailureFFEUploadStatus,
            FinishedFailureFFEUploadStatus,
            PapiConversionFailureFFEUploadStatus,
        ]


class PlayerFFELicence(StrEnum):
    NONE = ''
    N = 'N'
    B = 'B'
    A = 'A'

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
                return _('N - Expired *** FFE licence')
            case PlayerFFELicence.A:
                return _('A - Competition *** FFE licence')
            case PlayerFFELicence.B:
                return _('B - Leisure *** FFE licence')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def short_name(self) -> str:
        if self == PlayerFFELicence.NONE:
            return '-'
        return self.value

    @staticmethod
    def validate(string: str) -> bool:
        """Returns True if the string is a correct licence number."""
        return bool(re.match(r'^[A-Z][A-Z\d]\d{4}$', string))

    @property
    def sort_index(self) -> int:
        return _LICENCE_SORT_INDEX[self]


_LICENCE_SORT_INDEX = {
    PlayerFFELicence.NONE: 0,
    PlayerFFELicence.N: 1,
    PlayerFFELicence.B: 2,
    PlayerFFELicence.A: 3,
}


class FFEArbiterTitle(StrEnum):
    NONE = ''
    AS = 'AS'
    AFJ = 'AFJ'
    AFC = 'AFC'
    AFO1 = 'AFO1'
    AFO2 = 'AFO2'
    AFE1 = 'AFE1'
    AFE2 = 'AFE2'

    @classmethod
    def from_html(cls, html_arbiter_string: str) -> 'FFEArbiterTitle':
        match html_arbiter_string:
            case 'Arbitre Jeune':
                return cls.AFJ
            case 'Arbitre Club':
                return cls.AFC
            case 'Arbitre Open 1':
                return cls.AFO1
            case 'Arbitre Open 2':
                return cls.AFO2
            case 'Arbitre Elite 1':
                return cls.AFE1
            case 'Arbitre Elite 2':
                return cls.AFE2
            case _:
                return cls.NONE

    @property
    def name(self) -> str:
        match self:
            case FFEArbiterTitle.NONE:
                return '-'
            case FFEArbiterTitle.AS:
                return _('Trainee Arbiter')
            case FFEArbiterTitle.AFJ:
                return _('Young Arbiter')
            case FFEArbiterTitle.AFC:
                return _('Club Arbiter')
            case FFEArbiterTitle.AFO1:
                return _('Open Arbiter (level 1)')
            case FFEArbiterTitle.AFO2:
                return _('Open Arbiter (level 2)')
            case FFEArbiterTitle.AFE1:
                return _('Elite Arbiter (level 1)')
            case FFEArbiterTitle.AFE2:
                return _('Elite Arbiter (level 2)')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def short_name(self) -> str:
        return self.value


@dataclass
class FfeEventPluginData(PluginData):
    auto_upload: bool = True

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            auto_upload=stored_value.get('auto_upload', False),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'auto_upload': self.auto_upload,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        if previous_object:
            return previous_object
        return cls()

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return {}


@dataclass
class FfeTournamentPluginData(PluginData):
    ffe_id: int | None = None
    password: str | None = None
    auto_upload: bool = False
    last_upload_at: datetime | None = None
    last_upload_attempt_at: datetime | None = None
    upload_failure_id: str | None = None

    @property
    def last_upload_at_str(self) -> str:
        if not self.last_upload_at:
            return '-'
        return format_datetime(self.last_upload_at)

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            ffe_id=stored_value.get('ffe_id', None),
            password=stored_value.get('password', None),
            auto_upload=stored_value.get('auto_upload', False),
            last_upload_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload')
            ),
            last_upload_attempt_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload_attempt_at')
            ),
            upload_failure_id=stored_value.get('upload_failure_id'),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'ffe_id': self.ffe_id,
            'password': self.password,
            'auto_upload': self.auto_upload,
            'last_upload': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_upload_at
            ),
            'last_upload_attempt_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_upload_attempt_at
            ),
            'upload_failure_id': self.upload_failure_id,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        plugin_data = cls(
            ffe_id=WebContext.form_data_to_int(data, 'ffe_id'),
            password=WebContext.form_data_to_str(data, 'ffe_password'),
        )
        if previous_object:
            if action != 'clone':
                plugin_data.last_upload_at = previous_object.last_upload_at
                plugin_data.last_upload_attempt_at = (
                    previous_object.last_upload_attempt_at
                )
                plugin_data.upload_failure_id = previous_object.upload_failure_id
            plugin_data.auto_upload = previous_object.auto_upload
        return plugin_data

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'ffe_id': self.ffe_id if action != 'clone' else '',
                'ffe_password': self.password if action != 'clone' else '',
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
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        return cls(
            ffe_id=WebContext.form_data_to_int(data, 'ffe_id'),
            ffe_licence=PlayerFFELicence(
                WebContext.form_data_to_str(data, 'ffe_licence')
                or PlayerFFELicence.NONE
            ),
            ffe_licence_number=WebContext.form_data_to_str(data, 'ffe_licence_number'),
            league=WebContext.form_data_to_str(data, 'ffe_league'),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        if action == FormAction.REPLACE:
            return {}
        return WebContext.values_dict_to_form_data(
            {
                'ffe_id': self.ffe_id,
                'ffe_licence': self.ffe_licence.value,
                'ffe_licence_number': self.ffe_licence_number,
                'ffe_league': self.league,
            }
        )


@dataclass
class FfeAccountPluginData(AccountPluginData):
    ffe_licence_number: str | None
    ffe_arbiter_title: FFEArbiterTitle

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            ffe_licence_number=stored_value.get('ffe_licence_number', None),
            ffe_arbiter_title=FFEArbiterTitle(
                stored_value.get('ffe_arbiter_title', FFEArbiterTitle.NONE)
            ),
        )

    @classmethod
    def from_stored_player(cls, stored_player: StoredPlayer) -> Self:
        return cls(
            ffe_licence_number=stored_player.plugin_data.get(PLUGIN_NAME, {}).get(
                'ffe_licence_number', None
            ),
            ffe_arbiter_title=FFEArbiterTitle(
                stored_player.transient_arbiter_titles.get('ffe')
                or FFEArbiterTitle.NONE
            ),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'ffe_arbiter_title': self.ffe_arbiter_title.value,
            'ffe_licence_number': self.ffe_licence_number,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        return cls(
            ffe_licence_number=WebContext.form_data_to_str(data, 'ffe_licence_number'),
            ffe_arbiter_title=FFEArbiterTitle(
                WebContext.form_data_to_str(data, 'ffe_arbiter_title')
                or FFEArbiterTitle.NONE
            ),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'ffe_licence_number': self.ffe_licence_number,
                'ffe_arbiter_title': self.ffe_arbiter_title.value,
            }
        )
