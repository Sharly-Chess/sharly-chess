import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from common.i18n import _
from data.event import Event
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.custom_upload import PLUGIN_NAME
from plugins.custom_upload.custom_upload_status import (
    CustomUploadStatus,
    NotConfiguredCustomUploadStatus,
    NeverUploadedCustomUploadStatus,
    UpToDateCustomUploadStatus,
    FailureCustomUploadStatus,
    UnexpectedFailureCustomUploadStatus,
    ModifiedCustomUploadStatus,
    OngoingCustomUploadStatus,
    AuthenticationFailureCustomUploadStatus,
    ConnectionFailureCustomUploadStatus,
    TargetLocationNotFoundCustomUploadStatus,
    PendingCustomUploadStatus,
)
from plugins.utils import PluginData
from utils.date_time import format_datetime
from utils.entity import EntityManager
from utils.enum import FormAction
from web.controllers.base_controller import WebContext


class TransferProtocol(StrEnum):
    SFTP = 'SFTP'
    FTP = 'FTP'

    @classmethod
    def parse(cls, value: str | None) -> 'TransferProtocol':
        try:
            return cls(value)
        except ValueError:
            return cls.SFTP


class CustomUploadUtils:
    @staticmethod
    def get_tournament_plugin_data(
        tournament: Tournament,
    ) -> 'CustomUploadTournamentPluginData':
        plugin_data = tournament.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, CustomUploadTournamentPluginData)
        return plugin_data

    @staticmethod
    def get_event_plugin_data(event: Event) -> 'CustomUploadEventPluginData':
        plugin_data = event.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, CustomUploadEventPluginData)
        return plugin_data

    @staticmethod
    def custom_upload_configuration_verification_message(
        tournament: Tournament,
    ) -> str | None:
        event_plugin_data = CustomUploadUtils.get_event_plugin_data(tournament.event)
        tournament_plugin_data = CustomUploadUtils.get_tournament_plugin_data(
            tournament
        )
        if not event_plugin_data.ftp_host:
            return _('FTP host is not defined')
        if not event_plugin_data.ftp_username:
            return _('FTP credentials are not defined')
        if not tournament_plugin_data.documents:
            return _('No configured documents')
        return None

    @staticmethod
    def update_tournament_plugin_data(
        tournament: Tournament,
        plugin_data: 'CustomUploadTournamentPluginData',
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

    @classmethod
    def resolve_tournament_upload_statuses(
        cls, tournament: Tournament
    ) -> list[CustomUploadStatus]:
        from plugins.custom_upload.custom_upload_uploader import CustomUploadUploader

        custom_upload_event_plugin_data = cls.get_event_plugin_data(tournament.event)

        if (
            not custom_upload_event_plugin_data.ftp_host
            or not custom_upload_event_plugin_data.ftp_username
        ):
            return [NotConfiguredCustomUploadStatus()]

        custom_upload_tournament_plugin_data = cls.get_tournament_plugin_data(
            tournament
        )
        statuses: list[CustomUploadStatus] = []

        # Last upload failure
        if custom_upload_tournament_plugin_data.upload_failure_id:
            status = CustomUploadFailureStatusManager().get_object(
                custom_upload_tournament_plugin_data.upload_failure_id
            )
            statuses.append(status)

        is_modified = CustomUploadUploader.custom_upload_needed(tournament)
        # Current data status
        if not custom_upload_tournament_plugin_data.last_upload_at:
            statuses.append(NeverUploadedCustomUploadStatus())
        elif is_modified:
            statuses.append(ModifiedCustomUploadStatus())
        else:
            statuses.append(UpToDateCustomUploadStatus())

        # Next upload status
        if CustomUploadUploader.is_upload_ongoing(tournament):
            statuses.append(OngoingCustomUploadStatus())
        elif CustomUploadUploader.is_upload_queued(
            tournament
        ) or CustomUploadUploader.is_upload_scheduled(tournament):
            statuses.append(PendingCustomUploadStatus())
        return statuses


class CustomUploadFailureStatusManager(EntityManager[FailureCustomUploadStatus]):
    def entity_types(self) -> list[type[FailureCustomUploadStatus]]:
        return [
            AuthenticationFailureCustomUploadStatus,
            ConnectionFailureCustomUploadStatus,
            TargetLocationNotFoundCustomUploadStatus,
            UnexpectedFailureCustomUploadStatus,
        ]


@dataclass
class ConfiguredDocument:
    """A document configured for upload: a print-document id and the
    `id=value|id=value` options string consumed by the document-view endpoint."""

    document_id: str
    options: str = ''


@dataclass
class CustomUploadTournamentPluginData(PluginData):
    server_path: str | None = None
    last_upload_at: datetime | None = None
    last_upload_attempt_at: datetime | None = None
    upload_failure_id: str | None = None
    documents: list[ConfiguredDocument] = field(default_factory=list)

    @property
    def last_upload_at_str(self) -> str:
        if not self.last_upload_at:
            return '-'
        return format_datetime(self.last_upload_at)

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            server_path=stored_value.get('server_path', None),
            last_upload_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload_at')
            ),
            last_upload_attempt_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload_attempt_at')
            ),
            upload_failure_id=stored_value.get('upload_failure_id'),
            documents=[
                ConfiguredDocument(
                    document_id=document['document_id'],
                    options=document.get('options', ''),
                )
                for document in stored_value.get('documents', [])
            ],
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'server_path': self.server_path,
            'last_upload_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_upload_at
            ),
            'last_upload_attempt_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_upload_attempt_at
            ),
            'upload_failure_id': self.upload_failure_id,
            'documents': [
                {'document_id': document.document_id, 'options': document.options}
                for document in self.documents
            ],
        }

    @staticmethod
    def documents_from_form_data(data: dict[str, str]) -> list[ConfiguredDocument]:
        """Rebuild the configured documents from the ``document_{i}_id`` /
        ``document_{i}_options`` hidden fields carried by the configuration form."""
        indices = sorted(
            {
                int(match.group(1))
                for key in data
                if (match := re.fullmatch(r'document_(\d+)_id', key))
            }
        )
        documents: list[ConfiguredDocument] = []
        for index in indices:
            document_id = (data.get(f'document_{index}_id') or '').strip()
            if not document_id:
                continue
            documents.append(
                ConfiguredDocument(
                    document_id=document_id,
                    options=data.get(f'document_{index}_options') or '',
                )
            )
        return documents

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        if action == FormAction.UPDATE and previous_object:
            return previous_object
        last_upload_at: datetime | None = None
        last_upload_attempt_at: datetime | None = None
        upload_failure_id: str | None = None
        if previous_object and action != FormAction.CLONE:
            last_upload_at = previous_object.last_upload_at
            last_upload_attempt_at = previous_object.last_upload_attempt_at
            upload_failure_id = previous_object.upload_failure_id

        return cls(
            server_path=WebContext.form_data_to_str(data, 'server_path'),
            last_upload_at=last_upload_at,
            last_upload_attempt_at=last_upload_attempt_at,
            upload_failure_id=upload_failure_id,
            documents=cls.documents_from_form_data(data),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        form_data = {
            'server_path': self.server_path,
        }
        for index, document in enumerate(self.documents):
            form_data[f'document_{index}_id'] = document.document_id
            form_data[f'document_{index}_options'] = document.options

        return WebContext.values_dict_to_form_data(form_data)


@dataclass
class CustomUploadEventPluginData(PluginData):
    ftp_host: str | None = None
    default_server_path: str | None = None
    ftp_username: str | None = None
    ftp_password: str | None = None
    transfer_protocol: TransferProtocol = TransferProtocol.SFTP

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            ftp_host=stored_value.get('ftp_host', None),
            default_server_path=stored_value.get('default_server_path', None),
            ftp_username=stored_value.get('ftp_username', None),
            ftp_password=stored_value.get('ftp_password', None),
            transfer_protocol=TransferProtocol.parse(
                stored_value.get('transfer_protocol')
            ),
        )

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        if action == FormAction.UPDATE and previous_object:
            return previous_object
        return cls(
            ftp_host=WebContext.form_data_to_str(data, 'ftp_host'),
            default_server_path=WebContext.form_data_to_str(
                data, 'default_server_path'
            ),
            ftp_username=WebContext.form_data_to_str(data, 'ftp_username'),
            ftp_password=WebContext.form_data_to_str(data, 'ftp_password'),
            transfer_protocol=TransferProtocol.parse(
                WebContext.form_data_to_str(data, 'transfer_protocol')
            ),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'ftp_host': self.ftp_host,
            'default_server_path': self.default_server_path,
            'ftp_username': self.ftp_username,
            'ftp_password': self.ftp_password,
            'transfer_protocol': self.transfer_protocol.value,
        }

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        form_data = {
            'ftp_host': self.ftp_host,
            'default_server_path': self.default_server_path,
            'ftp_username': self.ftp_username,
            'ftp_password': self.ftp_password,
            'transfer_protocol': self.transfer_protocol.value,
        }

        return WebContext.values_dict_to_form_data(form_data)
