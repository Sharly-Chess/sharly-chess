import ftplib
import re
import time
from datetime import datetime
from ftplib import error_perm
from io import BytesIO
from pathlib import PurePosixPath
from threading import Thread, Timer

import paramiko.client
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
from data.access_levels.client import Client
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from plugins.custom_upload.custom_upload_status import (
    AuthenticationFailureCustomUploadStatus,
    ConnectionFailureCustomUploadStatus,
    UnexpectedFailureCustomUploadStatus,
    TargetLocationNotFoundCustomUploadStatus,
    FailureCustomUploadStatus,
)
from plugins.custom_upload.utils import (
    CustomUploadUtils,
    CustomUploadTournamentPluginData,
    TransferProtocol,
)
from utils import Utils
from web.channels import channels_plugin
from web.controllers.admin.event_documents_controller import EventDocumentsController

logger = get_logger()


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

    @staticmethod
    def normalize_server_path(server_path: str | None) -> str:
        """Clean a user-provided server path. A leading slash is optional: with
        one the path is absolute from the server root, without one it is relative
        to the FTP/SFTP login directory. Empty resolves to the login directory."""
        path = (server_path or '').strip()
        if not path:
            return '.'
        return PurePosixPath(path).as_posix()

    @classmethod
    def test_file_transfer_connection(
        cls,
        host: str,
        username: str,
        password: str,
        target_path: str,
        protocol: TransferProtocol,
        port: int,
    ) -> None:
        """Connection attempt to the FTP/SFTP server.
        Throws ConnectionError exception if the connection doesn't succeed.
        Throws FileNotFoundError exception if the target path can't be found."""

        target_path = cls.normalize_server_path(target_path)
        logger.info('Testing connection for [%s]...', host)
        match protocol:
            case TransferProtocol.SFTP:
                logger.info('Connection attempt via SFTP.')
                cls._sftp_auth_check(host, username, password, port, target_path)
            case TransferProtocol.FTP:
                logger.info('Connection attempt via FTP.')
                cls._ftp_auth_check(host, username, password, port, target_path)
            case TransferProtocol.FTPS:
                logger.info('Connection attempt via FTPS.')
                cls._ftps_auth_check(host, username, password, port, target_path)
        logger.info('Connection succeeded.')

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

        try:
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
                return

            logger.info('Uploading tournament [%s]...', tournament.name)

            event_plugin_data = CustomUploadUtils.get_event_plugin_data(
                tournament.event
            )
            tournament_plugin_data = CustomUploadUtils.get_tournament_plugin_data(
                tournament
            )

            try:
                temporary_files = cls._generate_documents_in_memory(
                    event, tournament_plugin_data, http_client
                )
            except Exception:
                logger.exception('Error uploading tournament [%s]', tournament.name)
                tournament_plugin_data.upload_failure_id = (
                    UnexpectedFailureCustomUploadStatus().id
                )
                tournament_plugin_data.last_upload_attempt_at = datetime.now()
                CustomUploadUtils.update_tournament_plugin_data(
                    tournament, tournament_plugin_data
                )
                return

            host = event_plugin_data.ftp_host
            username = event_plugin_data.ftp_username
            password = event_plugin_data.ftp_password or ''
            transfer_protocol = event_plugin_data.transfer_protocol
            port = event_plugin_data.transfer_port

            if not host or not username:
                # Host or username is missing, we can't upload
                return

            server_path = tournament_plugin_data.server_path
            if not server_path:
                server_path = event_plugin_data.default_server_path

            target_path = cls.normalize_server_path(server_path)

            if event_plugin_data.transfer_protocol == TransferProtocol.SFTP:
                cls._sftp_upload(
                    host,
                    username,
                    password,
                    port,
                    target_path,
                    tournament_plugin_data,
                    tournament,
                    result_id,
                    temporary_files,
                )
            else:
                cls._ftp_upload(
                    host,
                    username,
                    password,
                    port,
                    transfer_protocol == TransferProtocol.FTPS,
                    target_path,
                    tournament_plugin_data,
                    tournament,
                    result_id,
                    temporary_files,
                )
        finally:
            cls.ongoing_result_ids.discard(result_id)
            cls.publish_upload_event()

    @classmethod
    def _sftp_upload(
        cls,
        host: str,
        username: str,
        password: str,
        port: int,
        target_path: str,
        tournament_plugin_data: CustomUploadTournamentPluginData,
        tournament: Tournament,
        result_id: str,
        temporary_files: list[tuple[BytesIO, str]],
    ):
        failure_status: FailureCustomUploadStatus | None = None

        with paramiko.SSHClient() as ssh_client:
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            sftp_client: SFTPClient | None = None
            try:
                ssh_client.connect(
                    host, username=username, password=password, port=port
                )
                sftp_client = ssh_client.open_sftp()

                if not CustomUploadUploader._does_remote_path_exist_sftp(
                    sftp_client, target_path
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
                        (PurePosixPath(target_path) / file_name).as_posix(),
                    )
                    logger.info('Uploaded document file [%s]', file_name)
            except AuthenticationException:
                logger.warning(
                    'Authentication failed on [%s] for tournament [%s]',
                    host,
                    tournament.name,
                )
                failure_status = AuthenticationFailureCustomUploadStatus()
            except (SSHException, EOFError, OSError):
                logger.warning(
                    'Could not connect to [%s] to upload tournament [%s]',
                    host,
                    tournament.name,
                )
                failure_status = ConnectionFailureCustomUploadStatus()
            except Exception:
                logger.exception('Error uploading tournament [%s]', tournament.name)
                failure_status = UnexpectedFailureCustomUploadStatus()
            finally:
                if sftp_client is not None:
                    sftp_client.close()
                for temporary_document_file, _ in temporary_files:
                    temporary_document_file.close()
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
    def _ftp_upload(
        cls,
        host: str,
        username: str,
        password: str,
        port: int,
        tls_enabled: bool,
        target_path: str,
        tournament_plugin_data: CustomUploadTournamentPluginData,
        tournament: Tournament,
        result_id: str,
        temporary_files: list[tuple[BytesIO, str]],
    ):
        try:
            ftp_client_type: type[ftplib.FTP] = ftplib.FTP
            if tls_enabled:
                ftp_client_type = ftplib.FTP_TLS

            with ftp_client_type() as ftp_client:
                ftp_client.connect(host, port, timeout=5)
                ftp_client.login(username, password)

                if not CustomUploadUploader._does_remote_path_exist_ftp(
                    ftp_client, target_path
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
                    ftp_client.storbinary(
                        f'STOR {file_name}',
                        temporary_document_file,
                    )
                    logger.info('Uploaded document file [%s]', file_name)
        except ftplib.all_errors:
            logger.warning(
                'Could not connect to [%s] to upload tournament [%s]',
                host,
                tournament.name,
            )
            failure_status = ConnectionFailureCustomUploadStatus()
        except Exception:
            logger.exception('Error uploading tournament [%s]', tournament.name)
            failure_status = UnexpectedFailureCustomUploadStatus()
        finally:
            for temporary_document_file, _ in temporary_files:
                temporary_document_file.close()
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
        for configured_document in tournament_plugin_data.documents:
            document_htmx_template = EventDocumentsController.document_view(
                http_client,
                event,
                configured_document.document_id,
                configured_document.options or None,
            )
            html_content = parse_jinja_template(
                document_htmx_template.template_name, document_htmx_template.context
            )
            temporary_document_file = BytesIO(html_content.encode())
            options_suffix = re.sub(
                r'[^A-Za-z0-9]+', '_', configured_document.options
            ).strip('_')
            file_name = (
                f'{"_".join(event.name.split())}_{configured_document.document_id}'
            )
            if options_suffix:
                file_name += f'_{options_suffix}'
            file_name += '.html'
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
        """Upload all eligible tournaments for an event in a background thread."""
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
    def _does_remote_path_exist_sftp(sftp_client: SFTPClient, remote_path: str) -> bool:
        try:
            sftp_client.stat(remote_path)
        except FileNotFoundError:
            return False
        return True

    @staticmethod
    def _does_remote_path_exist_ftp(ftp_client: ftplib.FTP, remote_path: str) -> bool:
        try:
            ftp_client.cwd(remote_path)
        except error_perm:
            return False
        return True

    @staticmethod
    def _sftp_auth_check(
        host: str, username: str, password: str, port: int, target_path: str
    ) -> None:
        with paramiko.SSHClient() as client:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(
                    host, username=username, password=password, port=port, timeout=5
                )
                sftp_client = client.open_sftp()
            except AuthenticationException:
                raise PermissionError(f'Authentication failed for {host}')
            except (
                BadHostKeyException,
                NoValidConnectionsError,
                SSHException,
                OSError,
                TimeoutError,
            ):
                raise ConnectionError(f'Cannot connect to {host}')

            if not CustomUploadUploader._does_remote_path_exist_sftp(
                sftp_client, target_path
            ):
                raise FileNotFoundError(f'Remote path not found: {target_path}')

    @staticmethod
    def _ftp_auth_check(
        host: str, username: str, password: str, port: int, target_path: str
    ) -> None:
        with ftplib.FTP() as ftp_client:
            CustomUploadUploader._ftplib_auth_check(
                host, username, password, port, target_path, ftp_client
            )

    @staticmethod
    def _ftps_auth_check(
        host: str, username: str, password: str, port: int, target_path: str
    ) -> None:
        with ftplib.FTP_TLS() as ftp_client:
            CustomUploadUploader._ftplib_auth_check(
                host, username, password, port, target_path, ftp_client
            )

    @staticmethod
    def _ftplib_auth_check(
        host: str,
        username: str,
        password: str,
        port: int,
        target_path: str,
        ftp_client: ftplib.FTP,
    ):
        try:
            ftp_client.connect(host, port, timeout=5)
            ftp_client.login(username, password)
            if not CustomUploadUploader._does_remote_path_exist_ftp(
                ftp_client, target_path
            ):
                raise FileNotFoundError(f'Remote path not found: {target_path}')
        except FileNotFoundError:
            raise
        except ftplib.error_perm:
            raise PermissionError(f'Authentication failed for {host}')
        except ftplib.all_errors:
            raise ConnectionError(f'Cannot connect to {host}')
