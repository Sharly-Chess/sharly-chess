from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Self

from common.i18n import _
from data.tournament import Tournament
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.custom_upload import PLUGIN_NAME
from plugins.utils import PluginData
from utils.enum import FormAction
from web.controllers.base_controller import WebContext


class CustomUploadUtils:
    @staticmethod
    def get_tournament_plugin_data(
        tournament: Tournament,
    ) -> 'CustomUploadTournamentPluginData':
        plugin_data = tournament.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, CustomUploadTournamentPluginData)
        return plugin_data

    @staticmethod
    def custom_upload_configuration_verification_message(
        tournament: Tournament,
    ) -> str | None:
        plugin_data = CustomUploadUtils.get_tournament_plugin_data(tournament)
        if not plugin_data.ftp_host:
            return _('FTP host is not defined.')
        if not plugin_data.ftp_username or not plugin_data.ftp_password:
            return _('FTP credentials are not defined.')
        return None


@dataclass
class CustomUploadTournamentPluginData(PluginData):
    ftp_host: str | None = None
    server_path: str | None = None
    ftp_username: str | None = None
    ftp_password: str | None = None
    last_upload: datetime | None = None
    document_urls: list[str] = field(default_factory=list)

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            ftp_host=stored_value.get('ftp_host', None),
            server_path=stored_value.get('server_path', None),
            ftp_username=stored_value.get('ftp_username', None),
            ftp_password=stored_value.get('ftp_password', None),
            last_upload=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload')
            ),
            document_urls=stored_value.get('document_urls', []),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'ftp_host': self.ftp_host,
            'server_path': self.server_path,
            'ftp_username': self.ftp_username,
            'ftp_password': self.ftp_password,
            'document_urls': self.document_urls,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        last_upload: datetime | None = None
        document_urls: list[str] | None = []
        if previous_object and action != FormAction.CLONE:
            last_upload = previous_object.last_upload

        # If action is UPDATE, it means form is for updating FTP configuration only
        # Document URLs should then stay as they are
        if action == FormAction.UPDATE:
            document_urls = previous_object.document_urls
        if action == 'edit_documents':
            document_urls = [
                value.strip()
                for key, value in data.items()
                if key.startswith('document_url_')
            ]
        return cls(
            ftp_host=WebContext.form_data_to_str(data, 'ftp_host'),
            server_path=WebContext.form_data_to_str(data, 'server_path'),
            last_upload=last_upload,
            ftp_username=WebContext.form_data_to_str(data, 'ftp_username'),
            ftp_password=WebContext.form_data_to_str(data, 'ftp_password'),
            document_urls=document_urls,
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        form_data = {}
        if action != 'edit_documents':
            form_data.update(
                {
                    'ftp_host': self.ftp_host,
                    'server_path': self.server_path,
                    'ftp_username': self.ftp_username,
                    'ftp_password': self.ftp_password,
                }
            )
        for index, document_url in enumerate(self.document_urls):
            form_data[f'document_url_{index}'] = document_url

        return WebContext.values_dict_to_form_data(form_data)
