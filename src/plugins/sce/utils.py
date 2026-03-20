import json
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from logging import Logger
from typing import Any, Self


from common.logger import get_logger
from common.network import NetworkMonitor
from data.event import Event
from data.player import Player
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTournament
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_event_status import (
    SCEEventStatus,
    PublishedSCEEventStatus,
    DraftSCEEventStatus,
    ArchivedSCEEventStatus,
    NoInternetSCEEventStatus,
    InvalidRefreshTokenSCEEventStatus,
    NotFoundSCEEventStatus,
    NotConnectedSCEEventStatus,
    UnexpectedHttpSCEEventStatus,
    NotReachableSCEEventStatus,
)
from plugins.sce.sce_tournament_status import (
    SuccessSCETournamentStatus,
    SCETournamentStatus,
    ModifiedSCETournamentStatus,
    PendingSCETournamentStatus,
    NotStartedSCETournamentStatus,
    NeverUploadedSCETournamentStatus,
    OngoingSCETournamentStatus,
    NetworkFailureSCETournamentStatus,
    UnexpectedHTTPFailureSCETournamentStatus,
    NotFoundFailureSCETournamentStatus,
    AuthFailureSCETournamentStatus,
)
from plugins.utils import PluginData, PluginUtils
from utils import Utils
from utils.entity import EntityManager
from web.urls import build_get_url

logger: Logger = get_logger()

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


@dataclass
class SCETokens:
    access_token: str
    refresh_token: str
    expires_at: datetime


@dataclass
class SCEEventPluginData(PluginData):
    id: str
    slug: str = ''
    organiser_slug: str = ''
    status: str | None = None
    auto_upload: bool = False
    auto_player_sync: bool = False
    tournament_names_by_id: dict[str, str] = field(default_factory=dict)
    last_sync_at: datetime | None = None
    tokens: SCETokens | None = None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        tokens: SCETokens | None = None
        if stored_tokens := stored_value.get('tokens'):
            tokens = SCETokens(
                access_token=stored_tokens.get('access_token'),
                refresh_token=stored_tokens.get('refresh_token'),
                expires_at=SQLiteDatabase.load_datetime_from_database_field(
                    stored_tokens.get('expires_at'),
                ),
            )
        return cls(
            id=stored_value.get('id', ''),
            slug=stored_value.get('slug', ''),
            organiser_slug=stored_value.get('organiser_slug', ''),
            status=stored_value.get('status'),
            auto_upload=stored_value.get('auto_upload', False),
            auto_player_sync=stored_value.get('auto_player_sync', False),
            tournament_names_by_id=stored_value.get('tournament_names_by_id', {}),
            tokens=tokens,
            last_sync_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_sync_at'),
            ),
        )

    def to_stored_value(self) -> dict[str, Any]:
        stored_value: dict[str, Any] = {
            'id': self.id,
            'auto_upload': self.auto_upload,
            'auto_player_sync': self.auto_player_sync,
            'tournament_names_by_id': self.tournament_names_by_id,
            'slug': self.slug,
            'organiser_slug': self.organiser_slug,
            'status': self.status,
            'last_sync_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_sync_at
            ),
        }
        if self.tokens:
            stored_value['tokens'] = {
                'access_token': self.tokens.access_token,
                'refresh_token': self.tokens.refresh_token,
                'expires_at': (
                    SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                        self.tokens.expires_at
                    )
                ),
            }
        return stored_value

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        if previous_object:
            return previous_object
        return cls(id='')

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return {}


@dataclass
class SCETournamentPluginData(PluginData):
    id: str | None = None
    auto_upload: bool = True
    last_upload_at: datetime | None = None
    upload_status: str | None = None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            id=stored_value.get('id'),
            auto_upload=stored_value.get('auto_upload', True),
            last_upload_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload_at'),
            ),
            upload_status=stored_value.get('upload_status'),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'auto_upload': self.auto_upload,
            'last_upload_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_upload_at
            ),
            'upload_status': self.upload_status,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        if previous_object and action != 'clone':
            return previous_object
        return cls()

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return {}


@dataclass
class SCEPlayerPluginData(PluginData):
    id: str | None = None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            id=stored_value.get('id', None),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'id': self.id,
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


class _SCEEventStatusManager(EntityManager[SCEEventStatus]):
    def entity_types(self) -> list[type[SCEEventStatus]]:
        return [
            PublishedSCEEventStatus,
            DraftSCEEventStatus,
            ArchivedSCEEventStatus,
            NoInternetSCEEventStatus,
            InvalidRefreshTokenSCEEventStatus,
            NotFoundSCEEventStatus,
            UnexpectedHttpSCEEventStatus,
            NotConnectedSCEEventStatus,
            NotReachableSCEEventStatus,
        ]


class _SCETournamentStatusManager(EntityManager[SCETournamentStatus]):
    def entity_types(self) -> list[type[SCETournamentStatus]]:
        return [
            NeverUploadedSCETournamentStatus,
            NotStartedSCETournamentStatus,
            SuccessSCETournamentStatus,
            ModifiedSCETournamentStatus,
            PendingSCETournamentStatus,
            OngoingSCETournamentStatus,
            NetworkFailureSCETournamentStatus,
            NotFoundFailureSCETournamentStatus,
            UnexpectedHTTPFailureSCETournamentStatus,
            AuthFailureSCETournamentStatus,
        ]


class SCEUtils:
    @staticmethod
    def get_event_plugin_data(event: Event) -> SCEEventPluginData:
        plugin_data = event.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, SCEEventPluginData)
        return plugin_data

    @staticmethod
    def get_tournament_plugin_data(tournament: Tournament) -> SCETournamentPluginData:
        plugin_data = tournament.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, SCETournamentPluginData)
        return plugin_data

    @staticmethod
    def get_player_plugin_data(player: Player) -> SCEPlayerPluginData:
        plugin_data = player.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, SCEPlayerPluginData)
        return plugin_data

    @staticmethod
    def update_event_plugin_data(
        event: Event,
        plugin_data: SCEEventPluginData,
        write: bool = True,
        write_stored_object: bool = False,
    ):
        event.stored_event.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
        event.plugin_data[PLUGIN_NAME] = plugin_data
        if write:
            with EventDatabase(event.uniq_id, True) as database:
                if write_stored_object:
                    database.update_stored_event(event.stored_event)
                else:
                    database.execute(
                        "UPDATE info SET plugin_data = json_set(plugin_data,'$.sce', json(?))",
                        (json.dumps(plugin_data.to_stored_value()),),
                    )

    @staticmethod
    def update_tournament_plugin_data(
        tournament: Tournament,
        plugin_data: SCETournamentPluginData,
        write: bool = True,
        write_stored_object: bool = False,
    ):
        tournament.stored_tournament.plugin_data[PLUGIN_NAME] = (
            plugin_data.to_stored_value()
        )
        tournament.plugin_data[PLUGIN_NAME] = plugin_data
        if write:
            with EventDatabase(tournament.event.uniq_id, write=True) as database:
                if write_stored_object:
                    database.update_stored_tournament(tournament.stored_tournament)
                else:
                    database.execute(
                        'UPDATE tournament SET plugin_data = '
                        "json_set(plugin_data,'$.sce', json(?)) WHERE id = ?",
                        (json.dumps(plugin_data.to_stored_value()), tournament.id),
                    )

    @classmethod
    def resolve_tournament_upload_statuses(
        cls, tournament: Tournament
    ) -> list[SCETournamentStatus]:
        from plugins.sce.sce_background_uploader import is_upload_ongoing

        is_ongoing = is_upload_ongoing(tournament)
        if not tournament.started:
            return [NotStartedSCETournamentStatus()]
        if is_ongoing:
            return [OngoingSCETournamentStatus()]

        event_plugin_data = cls.get_event_plugin_data(tournament.event)
        plugin_data = cls.get_tournament_plugin_data(tournament)
        statuses: list[SCETournamentStatus] = []
        last_upload = plugin_data.last_upload_at
        is_modified = cls.tournament_modified_since_last_upload(tournament)
        if plugin_data.upload_status:
            statuses.append(
                _SCETournamentStatusManager().get_object(plugin_data.upload_status)
            )
        if not last_upload:
            statuses.append(NeverUploadedSCETournamentStatus())
        elif is_modified:
            statuses.append(ModifiedSCETournamentStatus())
        if event_plugin_data.auto_upload and plugin_data.auto_upload and is_modified:
            statuses.append(PendingSCETournamentStatus())
        return statuses

    @classmethod
    def resolve_event_status(cls, event: Event) -> SCEEventStatus:
        plugin_data = cls.get_event_plugin_data(event)
        if not plugin_data.id or not plugin_data.status:
            return NotConnectedSCEEventStatus()
        if not NetworkMonitor.connected():
            return NoInternetSCEEventStatus()
        if not plugin_data.tokens:
            return InvalidRefreshTokenSCEEventStatus()

        return _SCEEventStatusManager().get_object(plugin_data.status)

    @classmethod
    def tournament_modified_since_last_upload(
        cls, tournament: Tournament | StoredTournament
    ) -> bool:
        last_upload = cls.get_tournament_last_upload(tournament)
        return not last_upload or Utils.tournament_results_modified_since(
            tournament, last_upload
        )

    @classmethod
    def get_tournament_last_upload(
        cls, tournament: Tournament | StoredTournament
    ) -> datetime | None:
        if isinstance(tournament, Tournament):
            plugin_data = cls.get_tournament_plugin_data(tournament)
        else:
            plugin_data = SCETournamentPluginData.from_stored_value(
                tournament.plugin_data.get(PLUGIN_NAME, {})
            )
        return plugin_data.last_upload_at

    @classmethod
    def event_url(cls, event: Event) -> str:
        from plugins.sce.sce_session import SCE_BASE_URL

        pd = cls.get_event_plugin_data(event)
        return build_get_url(
            SCE_BASE_URL, f'/organizer/{pd.organiser_slug}/events/{pd.id}'
        )

    @classmethod
    def tournament_url(cls, tournament: Tournament) -> str:
        from plugins.sce.sce_session import SCE_BASE_URL

        pd = cls.get_event_plugin_data(tournament.event)
        tournament_id = cls.get_tournament_plugin_data(tournament).id
        return build_get_url(
            SCE_BASE_URL,
            f'/organizer/{pd.organiser_slug}/events/'
            f'{pd.id}/tournaments/{tournament_id}',
        )
