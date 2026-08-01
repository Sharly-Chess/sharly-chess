import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
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

DEFAULT_FTP_PORT = 21
DEFAULT_SFTP_PORT = 22


class TransferProtocol(StrEnum):
    SFTP = 'SFTP'
    FTPS = 'FTPS'
    FTP = 'FTP'

    @classmethod
    def parse(cls, value: str | None) -> 'TransferProtocol':
        try:
            return cls(value or '')
        except ValueError:
            return cls.SFTP

    @classmethod
    def form_options(cls) -> dict[str, str]:
        return {
            WebContext.value_to_form_data(protocol.value): protocol.name
            for protocol in cls
        }

    @property
    def name(self) -> str:
        match self:
            case TransferProtocol.SFTP:
                return _('SFTP (FTP over SSH)')
            case TransferProtocol.FTPS:
                return _('FTPS (FTP with TLS/SSL)')
            case TransferProtocol.FTP:
                return _('FTP (unsecured)')
            case _:
                raise ValueError(f'Unknown value: {self}')

    @property
    def default_port(self) -> int:
        match self:
            case TransferProtocol.SFTP:
                return DEFAULT_SFTP_PORT
            case TransferProtocol.FTPS | TransferProtocol.FTP:
                return DEFAULT_FTP_PORT
            case _:
                raise ValueError(f'Unknown value: {self}')


class CustomUploadUtils:
    @staticmethod
    def sanitize_server_path(server_path: str | None) -> str:
        """Clean a user-provided server path. Leading/trailing slashes
        and invalid parts are removed, path is always relative to the
        login directory."""
        # remove leading and trailing slashes
        path = f'{(server_path or "").strip(" /")}'
        # remove empty and invalid parts
        path_parts: list[str] = []
        for path_part in path.split('/'):
            sanitized_part: str = path_part.strip()
            if sanitized_part not in ('', '..', '.'):
                path_parts.append(path_part)
        return '/'.join(path_parts)

    @staticmethod
    def sanitize_filename(filename: str | None) -> str:
        """Clean a user-provided filename. Slashes are removed."""
        # remove all slashes
        return f'{(filename or "").replace("/", "")}'

    @staticmethod
    def get_event_plugin_data(event: Event) -> 'CustomUploadEventPluginData':
        plugin_data = event.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, CustomUploadEventPluginData)
        return plugin_data

    @staticmethod
    def event_connection_message(event: Event) -> str | None:
        """Return a message describing why the connection can't be used, or
        ``None`` when host and credentials are set."""
        event_plugin_data = CustomUploadUtils.get_event_plugin_data(event)
        if not event_plugin_data.ftp_host:
            return _('FTP host is not defined')
        if not event_plugin_data.ftp_username:
            return _('FTP credentials are not defined')
        return None

    @staticmethod
    def get_document(event: Event, document_id: str) -> 'ConfiguredDocument | None':
        for document in CustomUploadUtils.get_event_plugin_data(event).documents:
            if document.id == document_id:
                return document
        return None

    @staticmethod
    def document_tournaments(
        event: Event, document: 'ConfiguredDocument'
    ) -> list[Tournament]:
        """The tournament(s) targeted by a document, resolved from the
        ``tournament``/``tournaments`` values stored in its options."""
        tournaments: list[Tournament] = []
        for tournament_id in document.tournament_ids():
            tournament = event.tournaments_by_id.get(tournament_id)
            if tournament:
                tournaments.append(tournament)
        return tournaments

    @staticmethod
    def tournament_server_paths(event: Event, tournament: Tournament) -> list[str]:
        """Distinct server paths of the documents targeting a tournament,
        falling back to the event default path."""
        event_data = CustomUploadUtils.get_event_plugin_data(event)
        paths: list[str] = []
        for document in event_data.documents:
            if tournament.id in document.tournament_ids():
                path = document.server_path or event_data.default_server_path or ''
                if path not in paths:
                    paths.append(path)
        return paths

    @staticmethod
    def document_name(event: Event, document: 'ConfiguredDocument') -> str:
        from data.print_documents import PrintDocumentManager

        try:
            return (
                PrintDocumentManager(event).get_type(document.document_id).static_name()
            )
        except KeyError:
            return document.document_id

    @staticmethod
    def save_event_plugin_data(
        event: Event, plugin_data: 'CustomUploadEventPluginData'
    ):
        event.stored_event.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
        event.plugin_data[PLUGIN_NAME] = plugin_data
        with EventDatabase(event.uniq_id, write=True) as database:
            database.update_stored_event(event.stored_event)

    @classmethod
    def update_document_state(cls, event_uniq_id: str, document: 'ConfiguredDocument'):
        """Persist the upload state of a single document, reloading the event's
        plugin data first so concurrent uploads of other documents aren't lost."""
        with EventDatabase(event_uniq_id, write=True) as database:
            stored_event = database.load_stored_event()
            event_data = CustomUploadEventPluginData.from_stored_value(
                stored_event.plugin_data.get(PLUGIN_NAME, {})
            )
            for index, existing in enumerate(event_data.documents):
                if existing.id == document.id:
                    event_data.documents[index] = document
                    break
            stored_event.plugin_data[PLUGIN_NAME] = event_data.to_stored_value()
            database.update_stored_event(stored_event)

    @classmethod
    def resolve_document_upload_statuses(
        cls, event: Event, document: 'ConfiguredDocument'
    ) -> list[CustomUploadStatus]:
        from plugins.custom_upload.custom_upload_uploader import CustomUploadUploader

        if cls.event_connection_message(event):
            return [NotConfiguredCustomUploadStatus()]

        statuses: list[CustomUploadStatus] = []

        # Last upload failure
        if document.upload_failure_id:
            statuses.append(
                CustomUploadFailureStatusManager().get_object(
                    document.upload_failure_id
                )
            )

        is_modified = CustomUploadUploader.custom_upload_needed(event, document)
        # Current data status
        if not document.last_upload_at:
            statuses.append(NeverUploadedCustomUploadStatus())
        elif is_modified:
            statuses.append(ModifiedCustomUploadStatus())
        else:
            statuses.append(UpToDateCustomUploadStatus())

        # Next upload status
        if CustomUploadUploader.is_upload_ongoing(event.uniq_id, document.id):
            statuses.append(OngoingCustomUploadStatus())
        elif CustomUploadUploader.is_upload_queued(
            event.uniq_id, document.id
        ) or CustomUploadUploader.is_upload_scheduled(event.uniq_id, document.id):
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
    `id=value|id=value` options string consumed by the document-view endpoint.
    ``server_path`` overrides the event default server path, ``target_filename``
    the name of the document on the server. ``id`` is a stable handle used to
    track the document's upload state across background threads."""

    document_id: str
    options: str = ''
    target_filename: str = ''
    server_path: str | None = None
    auto_upload: bool = False
    id: str = field(default_factory=lambda: secrets.token_hex(8))
    last_upload_at: datetime | None = None
    last_upload_attempt_at: datetime | None = None
    upload_failure_id: str | None = None

    @property
    def last_upload_at_str(self) -> str:
        if not self.last_upload_at:
            return '-'
        return format_datetime(self.last_upload_at)

    def tournament_ids(self) -> list[int]:
        """Tournament id(s) this document targets, parsed from the
        ``tournament``/``tournaments`` values in its options string."""
        tournament_ids: list[int] = []
        for part in self.options.split('|'):
            if '=' not in part:
                continue
            key, value = part.split('=', 1)
            raw_ids: list[str] = []
            if key == 'tournament' and value:
                raw_ids = [value]
            elif key == 'tournaments' and value:
                raw_ids = value.split(';')
            for raw_id in raw_ids:
                try:
                    tournament_ids.append(int(raw_id))
                except ValueError:
                    continue
        return tournament_ids

    def upload_filename(
        self,
        event: Event,
    ) -> str:
        file_name: str = self.target_filename
        if not file_name:
            file_name = (
                f'e={event.uniq_id}|d={re.sub(r"[^A-Za-z0-9]+", "_", self.document_id)}'
            )
            tournament_ids: list[int] = self.tournament_ids()
            if len(tournament_ids) not in (0, len(event.tournaments)):
                file_name += f'|t={",".join(map(str, tournament_ids))}'
            for option in self.options.split('|'):
                if option:
                    option_name, option_value = option.split('=', maxsplit=2)
                    option_name = re.sub(r'[^A-Za-z0-9]+', '_', option_name).strip('_')
                    if option_name in ('tournament', 'tournaments'):
                        continue
                    file_name += f'|{option_name}={re.sub(r"[^A-Za-z0-9]+", "_", option_value).strip("_")}'
        if Path(file_name).suffix.lower() not in ('htm', 'html'):
            file_name += '.html'
        return file_name

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> 'ConfiguredDocument':
        return cls(
            document_id=stored_value['document_id'],
            options=stored_value.get('options', ''),
            target_filename=stored_value.get('target_filename', ''),
            server_path=stored_value.get('server_path'),
            auto_upload=stored_value.get('auto_upload', False),
            id=stored_value.get('id') or secrets.token_hex(8),
            last_upload_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload_at')
            ),
            last_upload_attempt_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload_attempt_at')
            ),
            upload_failure_id=stored_value.get('upload_failure_id'),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'document_id': self.document_id,
            'options': self.options,
            'target_filename': self.target_filename,
            'server_path': self.server_path,
            'auto_upload': self.auto_upload,
            'id': self.id,
            'last_upload_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_upload_at
            ),
            'last_upload_attempt_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_upload_attempt_at
            ),
            'upload_failure_id': self.upload_failure_id,
        }


@dataclass
class CustomUploadEventPluginData(PluginData):
    ftp_host: str | None = None
    default_server_path: str | None = None
    ftp_username: str | None = None
    ftp_password: str | None = None
    transfer_protocol: TransferProtocol = TransferProtocol.SFTP
    transfer_port: int | None = None
    documents: list[ConfiguredDocument] = field(default_factory=list)

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
            transfer_port=stored_value.get('transfer_port', None),
            documents=[
                ConfiguredDocument.from_stored_value(document)
                for document in stored_value.get('documents', [])
            ],
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
        # The connection form never carries documents; keep the ones already
        # configured on the event (dropped only when creating from scratch).
        documents: list[ConfiguredDocument] = (
            previous_object.documents if previous_object else []
        )
        default_server_path: str = CustomUploadUtils.sanitize_server_path(
            WebContext.form_data_to_str(data, 'default_server_path')
        )
        data['default_server_path'] = default_server_path
        return cls(
            ftp_host=WebContext.form_data_to_str(data, 'ftp_host'),
            default_server_path=default_server_path,
            ftp_username=WebContext.form_data_to_str(data, 'ftp_username'),
            ftp_password=WebContext.form_data_to_str(data, 'ftp_password'),
            transfer_protocol=TransferProtocol.parse(
                WebContext.form_data_to_str(data, 'transfer_protocol')
            ),
            transfer_port=WebContext.form_data_to_int(data, 'transfer_port'),
            documents=documents,
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'ftp_host': self.ftp_host,
            'default_server_path': self.default_server_path,
            'ftp_username': self.ftp_username,
            'ftp_password': self.ftp_password,
            'transfer_protocol': self.transfer_protocol.value,
            'transfer_port': self.transfer_port,
            'documents': [document.to_stored_value() for document in self.documents],
        }

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        form_data = {
            'ftp_host': self.ftp_host,
            'default_server_path': self.default_server_path,
            'ftp_username': self.ftp_username,
            'ftp_password': self.ftp_password,
            'transfer_protocol': self.transfer_protocol.value,
            'transfer_port': self.transfer_port,
        }

        return WebContext.values_dict_to_form_data(form_data)
