import socket
import time
import urllib
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from functools import partial
from io import BytesIO
from pathlib import Path
from threading import Thread, Timer

import paramiko.client
from paramiko.sftp_client import SFTPClient
from paramiko.ssh_exception import (
    BadHostKeyException,
    AuthenticationException,
    SSHException,
    NoValidConnectionsError,
)

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
from plugins.custom_upload.custom_upload_status import (
    UnexpectedFailureCustomUploadStatus,
    TargetLocationNotFoundCustomUploadStatus,
)
from plugins.custom_upload.utils import (
    CustomUploadUtils,
    CustomUploadTournamentPluginData,
)
from plugins.utils import PluginUtils
from utils import Utils
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
    upload_status_messages: dict[str, CustomUploadResult] = {}
    timeout_threads: dict[str, Timer] = {}
    group_upload_wait_queue: set[str] = set()
    ongoing_result_ids: set[str] = set()

    @classmethod
    def result_id(cls, event_uniq_id: str, tournament_id: int) -> str:
        return f'{event_uniq_id}:{tournament_id}'

    @classmethod
    def tournament_result_id(cls, tournament: Tournament) -> str:
        return cls.result_id(tournament.event.uniq_id, tournament.id)

    @classmethod
    def is_upload_ongoing(cls, tournament: Tournament) -> bool:
        """Return True if a background upload is currently running for this tournament."""
        key = cls.tournament_result_id(tournament)
        return key in cls.ongoing_result_ids

    @classmethod
    def is_upload_scheduled(cls, tournament: Tournament) -> bool:
        """Return True if a background upload is scheduled for this tournament."""
        key = cls.tournament_result_id(tournament)
        thread = cls.timeout_threads.get(key)
        return bool(thread and thread.is_alive())

    @classmethod
    def is_upload_queued(cls, tournament: Tournament) -> bool:
        """Return True if a background upload is queued for this tournament."""
        key = cls.tournament_result_id(tournament)
        return key in cls.group_upload_wait_queue

    @classmethod
    def remove_scheduled_upload(cls, tournament: Tournament):
        key = cls.tournament_result_id(tournament)
        thread = cls.timeout_threads.get(key)
        if thread and thread.is_alive():
            thread.cancel()

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
        last_upload = cls.custom_last_upload(tournament)
        return not last_upload or Utils.tournament_results_modified_since(
            tournament, last_upload
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
    def test_ftp(cls, ftp_host: str, ftp_username: str, ftp_password: str) -> bool:
        """Tries to connect to the FTP server.
        Returns True on success, False if the connection doesn't succeed"""

        logger.info('Testing SSH connection for [%s]...', ftp_host)
        if auth := cls._ftp_auth(ftp_host, ftp_username, ftp_password):
            logger.info('SSH connection succeeded.')
        return auth

    @classmethod
    def upload_tournament(
        cls,
        event_uniq_id: str,
        tournament_id: int,
    ) -> CustomUploadResult | None:
        """Upload a tournament to custom website."""

        result_id: str = cls.result_id(event_uniq_id, tournament_id)
        cls.ongoing_result_ids.add(result_id)
        cls.group_upload_wait_queue.discard(result_id)

        # NOTE (Molrn) Ensures a minimum time for the thread
        # This prevents flashing and situations where both requests
        # triggered by the `upload-event` web socket are treated as one
        time.sleep(0.5)

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
            failure_status = None

            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            host = tournament_plugin_data.ftp_host
            username = tournament_plugin_data.ftp_username
            password = tournament_plugin_data.ftp_password
            try:
                client.connect(host, username=username, password=password)
                sftp_client = client.open_sftp()

                target_path = Path(tournament_plugin_data.server_path)
                if not CustomUploadUploader._does_remote_path_exist(
                    sftp_client, target_path.as_posix()
                ):
                    logger.error(
                        'Error uploading tournament [%s]: path "%s" doesn\'t target a valid location',
                        tournament.name,
                        tournament_plugin_data.server_path,
                    )
                    cls.upload_status_messages[result_id] = CustomUploadResult(
                        CustomUploadStatus.ERROR,
                        _('Error uploading tournament'),
                    )
                    failure_status = TargetLocationNotFoundCustomUploadStatus()
                    return cls.upload_status_messages[result_id]

                for (
                    temporary_document_file,
                    file_name,
                ) in temporary_files_with_destination:
                    sftp_client.putfo(
                        temporary_document_file,
                        (target_path / file_name).as_posix(),
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
                failure_status = UnexpectedFailureCustomUploadStatus()
            finally:
                cls.ongoing_result_ids.discard(result_id)
                now = datetime.now()
                if failure_status:
                    tournament_plugin_data.upload_failure_id = failure_status.id
                else:
                    tournament_plugin_data.upload_failure_id = None
                    tournament_plugin_data.last_upload_at = now
                tournament_plugin_data.last_upload_attempt_at = now
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
    def schedule_upload(cls, tournament):
        """Schedule the upload of a tournament."""
        if CustomUploadUtils.custom_upload_configuration_verification_message(
            tournament
        ):
            return

        result_id = cls.result_id(tournament.event.uniq_id, tournament.id)
        timer = Timer(
            0.1,
            cls.upload_tournament,
            args=(tournament.event.uniq_id, tournament.id),
        )
        cls.timeout_threads[result_id] = timer
        timer.start()

    @classmethod
    def upload_event_tournaments(cls, tournaments: list[Tournament]):
        """Upload all eligible SCE tournaments for an event in a background thread."""
        eligible_tournaments = [
            tournament
            for tournament in tournaments
            if not CustomUploadUtils.custom_upload_configuration_verification_message(
                tournament
            )
            and cls.tournament_result_id(tournament) not in cls.ongoing_result_ids
        ]
        if not eligible_tournaments:
            return

        event_uniq_id = eligible_tournaments[0].event.uniq_id
        updated_tournaments: list[Tournament] = []
        for tournament in eligible_tournaments:
            if cls.custom_upload_needed(tournament):
                updated_tournaments.append(tournament)
            else:
                cls.upload_status_messages[
                    cls.result_id(event_uniq_id, tournament.id)
                ] = CustomUploadResult(
                    CustomUploadStatus.INFO,
                    _('Tournament not modified since last upload'),
                )
        if not updated_tournaments:
            return

        for tournament in updated_tournaments:
            cls.group_upload_wait_queue.add(cls.tournament_result_id(tournament))

        def _run():
            set_locale(SharlyChessConfig().locale)
            for tournament in updated_tournaments:
                cls.upload_tournament(event_uniq_id, tournament.id)

        Thread(target=_run, daemon=True).start()

    @staticmethod
    def _does_remote_path_exist(sftp_client: SFTPClient, remote_path: str):
        try:
            sftp_client.stat(remote_path)
        except FileNotFoundError:
            return False
        return True

    @staticmethod
    def _ftp_auth(host: str, username: str, password: str) -> bool:
        with paramiko.SSHClient() as client:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(host, username=username, password=password, timeout=5)
                return True
            except (
                BadHostKeyException,
                AuthenticationException,
                NoValidConnectionsError,
                SSHException,
                socket.error,
                TimeoutError,
            ):
                return False
