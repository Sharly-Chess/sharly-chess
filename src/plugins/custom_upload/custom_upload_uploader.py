import socket
import time
import urllib
from datetime import datetime
from functools import partial
from io import BytesIO
from pathlib import Path
from threading import Thread, Timer

import paramiko.client
from httpx import Client
from paramiko.sftp_client import SFTPClient
from paramiko.ssh_exception import (
    BadHostKeyException,
    AuthenticationException,
    SSHException,
    NoValidConnectionsError,
)

from common.i18n import set_locale
from common.i18n.utils import parse_jinja_template
from common.logger import get_logger
from common.network import NetworkMonitor
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from plugins.custom_upload import PLUGIN_NAME
from plugins.custom_upload.custom_upload_status import (
    UnexpectedFailureCustomUploadStatus,
    TargetLocationNotFoundCustomUploadStatus,
)
from plugins.custom_upload.utils import (
    CustomUploadUtils,
    CustomUploadTournamentPluginData,
    CustomUploadEventPluginData,
)
from plugins.utils import PluginUtils
from utils import Utils
from web.channels import channels_plugin
from web.controllers.admin.event_documents_controller import EventDocumentsController

logger = get_logger()
get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class CustomUploadUploader:
    timeout_threads: dict[str, Timer] = {}
    queued_result_ids: set[str] = set()
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
        return key in cls.queued_result_ids

    @classmethod
    def remove_scheduled_upload(cls, tournament: Tournament):
        key = cls.tournament_result_id(tournament)
        thread = cls.timeout_threads.get(key)
        if thread and thread.is_alive():
            thread.cancel()

    @classmethod
    def custom_last_upload(cls, tournament: Tournament) -> datetime | None:
        plugin_data = CustomUploadUtils.get_tournament_plugin_data(tournament)
        return plugin_data.last_upload_at

    @classmethod
    def custom_upload_needed(cls, tournament: Tournament) -> bool:
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
        """Connection attempt to the FTP server.
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
        http_client: Client,
    ):
        """Upload a tournament to a custom location."""

        result_id: str = cls.result_id(event_uniq_id, tournament_id)
        cls.ongoing_result_ids.add(result_id)
        cls.queued_result_ids.discard(result_id)

        # NOTE (Molrn) Ensures a minimum time for the thread
        # This prevents flashing and situations where both requests
        # triggered by the `upload-event` web socket are treated as one
        time.sleep(0.5)

        # We refetch the latest event and tournament
        loader = EventLoader()
        if event_uniq_id not in loader.event_uniq_ids:
            # The event has been deleted
            return
        event = loader.load_event(event_uniq_id)

        tournament = event.tournaments_by_id.get(tournament_id, None)
        if not tournament:
            # The tournament has been deleted
            return

        if CustomUploadUtils.custom_upload_configuration_verification_message(
            tournament
        ):
            # Skip this tournament if configuration is invalid
            return

        if not NetworkMonitor.connected():
            # The network is offline, we can't upload
            cls.publish_upload_event()
            return

        logger.info('Uploading tournament [%s]...', tournament.name)

        tournament_plugin_data = CustomUploadUtils.get_tournament_plugin_data(
            tournament
        )

        try:
            temporary_files = cls._generate_documents_in_memory(
                event, tournament_plugin_data, http_client
            )
        except Exception:
            logger.exception('Error uploading tournament [%s]', tournament.name)
            return

        with paramiko.SSHClient() as ftp_client:
            ftp_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            cls._ftp_upload(
                CustomUploadUtils.get_event_plugin_data(tournament.event),
                tournament_plugin_data,
                tournament,
                result_id,
                ftp_client,
                temporary_files,
            )

    @classmethod
    def _ftp_upload(
        cls,
        event_plugin_data: CustomUploadEventPluginData,
        tournament_plugin_data: CustomUploadTournamentPluginData,
        tournament: Tournament,
        result_id: str,
        ftp_client: paramiko.SSHClient,
        temporary_files: list[tuple[BytesIO, str]],
    ):
        failure_status = None

        host = event_plugin_data.ftp_host
        username = event_plugin_data.ftp_username
        password = event_plugin_data.ftp_password

        try:
            ftp_client.connect(host, username=username, password=password)
            sftp_client = ftp_client.open_sftp()

            server_path = tournament_plugin_data.server_path
            if not server_path:
                server_path = ''

            target_path = Path('/') / Path(server_path)
            if not CustomUploadUploader._does_remote_path_exist(
                sftp_client, target_path.as_posix()
            ):
                logger.error(
                    'Error uploading tournament [%s]: path "%s" doesn\'t target a valid location',
                    tournament.name,
                    target_path,
                )
                failure_status = TargetLocationNotFoundCustomUploadStatus()
                return

            for (
                temporary_document_file,
                file_name,
            ) in temporary_files:
                sftp_client.putfo(
                    temporary_document_file,
                    (target_path / file_name).as_posix(),
                )
                logger.info('Uploaded document file [%s]', file_name)
                temporary_document_file.close()
            sftp_client.close()
        except Exception:
            logger.exception('Error uploading tournament [%s]', tournament.name)
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

    @classmethod
    def _generate_documents_in_memory(
        cls,
        event: Event,
        tournament_plugin_data: CustomUploadTournamentPluginData,
        http_client: Client,
    ) -> list[tuple[BytesIO, str]]:
        temporary_files_with_name: list[tuple[BytesIO, str]] = []
        for document_url in tournament_plugin_data.document_urls:
            document_url_resource_part = document_url.split('/')[-1]
            document_id, document_options = document_url_resource_part.split('?')
            decoded_document_options = document_options.replace('options=', '')
            decoded_document_options = urllib.parse.unquote(decoded_document_options)
            document_htmx_template = EventDocumentsController.document_view(
                http_client,
                event,
                document_id,
                decoded_document_options,
            )
            html_content = parse_jinja_template(
                document_htmx_template.template_name, document_htmx_template.context
            )
            temporary_document_file = BytesIO(html_content.encode())
            file_name = f'{"_".join(event.name.split())}_{document_id}_{decoded_document_options}.html'
            temporary_files_with_name.append((temporary_document_file, file_name))
        return temporary_files_with_name

    @classmethod
    def schedule_upload(cls, tournament, http_client: Client):
        """Schedule the upload of a tournament."""
        if CustomUploadUtils.custom_upload_configuration_verification_message(
            tournament
        ):
            return

        result_id = cls.result_id(tournament.event.uniq_id, tournament.id)

        def _run():
            set_locale(SharlyChessConfig().locale)
            cls.upload_tournament(tournament.event.uniq_id, tournament.id, http_client)

        timer = Timer(0.1, _run)
        cls.timeout_threads[result_id] = timer
        timer.start()

    @classmethod
    def upload_event_tournaments(
        cls, tournaments: list[Tournament], http_client: Client
    ):
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

        if not updated_tournaments:
            return

        for tournament in updated_tournaments:
            cls.queued_result_ids.add(cls.tournament_result_id(tournament))

        def _run():
            set_locale(SharlyChessConfig().locale)
            for tournament in updated_tournaments:
                cls.upload_tournament(event_uniq_id, tournament.id, http_client)

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
