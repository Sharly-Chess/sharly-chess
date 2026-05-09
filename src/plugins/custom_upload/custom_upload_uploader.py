import urllib
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from functools import partial
from io import BytesIO
from pathlib import Path
from threading import Thread

import paramiko.client

from common.i18n import _, set_locale
from common.i18n.utils import parse_jinja_template
from common.logger import get_logger
from common.network import NetworkMonitor
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredTournament
from plugins.custom_upload import PLUGIN_NAME
from plugins.custom_upload.utils import (
    CustomUploadUtils,
    CustomUploadTournamentPluginData,
)
from plugins.utils import PluginUtils
from web.channels import channels_plugin
from web.controllers.admin.event_documents_controller import EventDocumentsController

logger = get_logger()
get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class CustomUploadStatus(IntEnum):
    NEVER = 0
    UPLOADED = 1
    CHANGED = 2
    PENDING = 3
    IN_PROGRESS = 4
    SUCCESS = 5
    INFO = 6
    ERROR = 7
    SETTINGS_ERROR = 8


@dataclass
class CustomUploadResult:
    status: CustomUploadStatus
    message: str


class CustomUploadUploader:
    uploading_event: bool = False
    upload_status_messages: dict[str, CustomUploadResult] = {}

    @classmethod
    def result_id(cls, event_uniq_id: str, tournament_id: int) -> str:
        return f'{event_uniq_id}:{tournament_id}'

    @classmethod
    def get_updated_tournament_upload_result(
        cls, tournament: Tournament
    ) -> CustomUploadResult:
        result_id = cls.result_id(tournament.event.uniq_id, tournament.id)
        result = cls.upload_status_messages.get(result_id, None)

        # Clear the message if it is a SETTINGS_ERROR, and refresh it later...
        if result and result.status == CustomUploadStatus.SETTINGS_ERROR:
            result = None

        # Default status when we don't have a result
        if result is None:
            if cls.custom_last_upload(tournament):
                result = CustomUploadResult(
                    CustomUploadStatus.UPLOADED,
                    _('Tournament previously uploaded.'),
                )
            else:
                result = CustomUploadResult(
                    CustomUploadStatus.NEVER,
                    _('Tournament not yet uploaded.'),
                )
            cls.upload_status_messages[result_id] = result

        if unavailable_message := (
            CustomUploadUtils.custom_upload_configuration_verification_message(
                tournament
            )
        ):
            result = CustomUploadResult(
                CustomUploadStatus.SETTINGS_ERROR, unavailable_message
            )
            cls.upload_status_messages[result_id] = result
        elif result.status != CustomUploadStatus.NEVER and cls.custom_upload_needed(
            tournament
        ):
            # For manual updates tell the user that the tournament has been modified
            result = CustomUploadResult(
                CustomUploadStatus.INFO,
                _('Modified since last upload'),
            )
            cls.upload_status_messages[result_id] = result
        return result

    @classmethod
    def update_eligible_tournaments(
        cls, tournaments: list[Tournament]
    ) -> list[Tournament]:
        eligible_tournaments: list[Tournament] = []
        for tournament in tournaments:
            result = cls.get_updated_tournament_upload_result(tournament)
            if result.status == CustomUploadStatus.SETTINGS_ERROR:
                # Skip this tournament if we have a SETTINGS_ERROR
                continue

            eligible_tournaments.append(tournament)
        return eligible_tournaments

    @classmethod
    def custom_last_upload(
        cls, tournament: Tournament | StoredTournament
    ) -> datetime | None:
        plugin_data: CustomUploadTournamentPluginData
        if isinstance(tournament, Tournament):
            plugin_data = CustomUploadUtils.get_tournament_plugin_data(tournament)
        else:
            raw_plugin_data = tournament.plugin_data.get(PLUGIN_NAME, {})
            plugin_data = raw_plugin_data

        return plugin_data.last_upload_at

    @classmethod
    def custom_upload_needed(cls, tournament: Tournament | StoredTournament) -> bool:
        return (cls.custom_last_upload(tournament) or datetime.min) < max(
            tournament.last_update or datetime.min,
            tournament.last_player_update or datetime.min,
            tournament.last_pairing_update or datetime.min,
        )

    @classmethod
    def publish_upload_event(cls):
        if channels_plugin:
            channels_plugin.publish(
                {
                    'event': 'upload-event',
                    'data': '',
                },
                ['ws'],
            )

    @classmethod
    def upload_tournament(
        cls,
        event_uniq_id: str,
        tournament_id: int,
        force: bool,
    ) -> CustomUploadResult | None:
        """Upload a tournament to custom website."""

        # We refetch the latest event and tournament
        loader = EventLoader()
        if event_uniq_id not in loader.event_uniq_ids:
            # The event has been deleted
            return None
        event = loader.load_event(event_uniq_id)

        tournament = event.tournaments_by_id.get(tournament_id, None)
        if not tournament:
            # The tournament has been deleted
            return None

        current_result = cls.get_updated_tournament_upload_result(tournament)
        if current_result.status == CustomUploadStatus.SETTINGS_ERROR:
            # Skip this tournament if we now have a SETTINGS_ERROR
            return current_result

        result_id = cls.result_id(tournament.event.uniq_id, tournament.id)
        if not force and current_result.status != CustomUploadStatus.NEVER:
            cls.upload_status_messages[result_id] = CustomUploadResult(
                CustomUploadStatus.CHANGED,
                _('Modified since last upload'),
            )
            return cls.upload_status_messages[result_id]

        if not NetworkMonitor.connected():
            # The network is offline, we can't upload
            cls.upload_status_messages[result_id] = CustomUploadResult(
                CustomUploadStatus.ERROR,
                _('Modified, but no internet connection'),
            )
            cls.publish_upload_event()
            return cls.upload_status_messages[result_id]

        cls.upload_status_messages[result_id] = CustomUploadResult(
            CustomUploadStatus.IN_PROGRESS,
            _('Uploading tournament…'),
        )

        logger.info('Uploading tournament [%s]...', tournament.name)

        tournament_plugin_data = CustomUploadUtils.get_tournament_plugin_data(
            tournament
        )

        temporary_files_with_destination = cls._generate_documents_in_memory(
            event, tournament_plugin_data
        )

        with paramiko.SSHClient() as client:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            host = tournament_plugin_data.ftp_host
            username = tournament_plugin_data.ftp_username
            password = tournament_plugin_data.ftp_password
            try:
                client.connect(host, username=username, password=password)
                sftp_client = client.open_sftp()
                for (
                    temporary_document_file,
                    file_name,
                ) in temporary_files_with_destination:
                    sftp_client.putfo(
                        temporary_document_file,
                        (
                            Path(tournament_plugin_data.server_path) / file_name
                        ).as_posix(),
                    )
                    logger.info('Uploaded document file [%s]', file_name)
                    temporary_document_file.close()
                sftp_client.close()
            except Exception as e:
                logger.error(
                    'Error uploading tournament [%s]: [%s]', tournament.name, e
                )
                cls.upload_status_messages[result_id] = CustomUploadResult(
                    CustomUploadStatus.ERROR,
                    _('Error uploading tournament'),
                )
            finally:
                # TODO: update last upload date only in case of success
                now = datetime.now()
                tournament_plugin_data.last_upload_at = now
                CustomUploadUtils.update_tournament_plugin_data(
                    tournament, tournament_plugin_data
                )
                cls.publish_upload_event()

        return cls.upload_status_messages[result_id]

    @classmethod
    def _generate_documents_in_memory(
        cls, event: Event, tournament_plugin_data: CustomUploadTournamentPluginData
    ) -> list[tuple[BytesIO, str]]:
        temporary_files_with_name: list[tuple[BytesIO, str]] = []
        for document_url in tournament_plugin_data.document_urls:
            document_url_resource_part = document_url.split('/')[-1]
            document_id, document_options = document_url_resource_part.split('?')
            decoded_document_options = document_options.replace('options=', '')
            decoded_document_options = urllib.parse.unquote(decoded_document_options)
            document_htmx_template = EventDocumentsController.document_view(
                event=event,
                document=document_id,
                options=decoded_document_options,
            )
            html_content = parse_jinja_template(
                document_htmx_template.template_name, document_htmx_template.context
            )
            temporary_document_file = BytesIO(html_content.encode())
            file_name = f'{"_".join(event.name.split())}_{document_id}_{decoded_document_options}.html'
            temporary_files_with_name.append((temporary_document_file, file_name))
        return temporary_files_with_name

    @classmethod
    def upload_event_tournaments(cls, tournaments: list[Tournament]):
        if cls.uploading_event:
            return
        cls.uploading_event = True

        tournaments = cls.update_eligible_tournaments(tournaments)
        updated_tournaments: list[tuple[str, int]] = []
        for tournament in tournaments:
            if cls.ffe_upload_needed(tournament):
                updated_tournaments.append((tournament.event.uniq_id, tournament.id))
            else:
                cls.upload_status_messages[
                    cls.result_id(tournament.event.uniq_id, tournament.id)
                ] = CustomUploadResult(
                    CustomUploadStatus.INFO,
                    _('Tournament not modified since last upload'),
                )

        if not updated_tournaments:
            cls.uploading_event = False
            return

        for event_uuid, tournament_id in updated_tournaments:
            if not NetworkMonitor.connected():
                # The network is offline, we can't upload
                cls.upload_status_messages[cls.result_id(event_uuid, tournament_id)] = (
                    CustomUploadResult(
                        CustomUploadStatus.INFO,
                        _('No internet connection'),
                    )
                )
            else:
                cls.upload_status_messages[cls.result_id(event_uuid, tournament_id)] = (
                    CustomUploadResult(
                        CustomUploadStatus.IN_PROGRESS, _('Uploading tournament…')
                    )
                )

        def _upload_tournaments(cls_: CustomUploadUploader) -> None:
            try:
                # Set the locale (called in a new thread)
                set_locale(SharlyChessConfig().locale)
                for event_uuid_, tournament_id_ in updated_tournaments:
                    scheduled_upload = cls_.timeout_threads.get(
                        cls_.result_id(event_uuid_, tournament_id_)
                    )
                    if scheduled_upload and scheduled_upload.is_alive():
                        # Cancel the scheduled upload
                        scheduled_upload.cancel()
                        cls_.timeout_threads.pop(
                            cls_.result_id(event_uuid_, tournament_id_), None
                        )
                    cls_.upload_tournament(event_uuid_, tournament_id_, True)

            finally:
                cls.uploading_event = False

        uploader = Thread(target=_upload_tournaments, args=(cls,))
        uploader.start()

    @classmethod
    def schedule_upload(cls, tournament: Tournament, force=False) -> None:
        """Schedule the upload of a tournament that has been modified."""
        result = cls.get_updated_tournament_upload_result(tournament)
        if result.status == CustomUploadStatus.SETTINGS_ERROR:
            # Skip this tournament if we have a SETTINGS_ERROR
            return
        result_id = cls.result_id(tournament.event.uniq_id, tournament.id)
        if force:
            cls.upload_status_messages[result_id] = CustomUploadResult(
                CustomUploadStatus.IN_PROGRESS,
                _('Uploading tournament…'),
            )

        cls.upload_tournament(tournament.event.uniq_id, tournament.id, force)
