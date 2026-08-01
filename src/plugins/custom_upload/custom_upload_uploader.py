import ftplib
import os.path
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
from plugins.custom_upload.custom_upload_status import (
    AuthenticationFailureCustomUploadStatus,
    ConnectionFailureCustomUploadStatus,
    UnexpectedFailureCustomUploadStatus,
    TargetLocationNotFoundCustomUploadStatus,
    FailureCustomUploadStatus,
)
from plugins.custom_upload.utils import (
    ConfiguredDocument,
    CustomUploadUtils,
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
    def result_id(cls, event_uniq_id: str, document_id: str) -> str:
        return f'{event_uniq_id}:{document_id}'

    @classmethod
    def is_upload_ongoing(cls, event_uniq_id: str, document_id: str) -> bool:
        """Return True if a background upload is currently running for this document."""
        return cls.result_id(event_uniq_id, document_id) in cls.ongoing_result_ids

    @classmethod
    def is_upload_scheduled(cls, event_uniq_id: str, document_id: str) -> bool:
        """Return True if a background upload is scheduled for this document."""
        thread = cls.timeout_threads.get(cls.result_id(event_uniq_id, document_id))
        return bool(thread and thread.is_alive())

    @classmethod
    def is_upload_queued(cls, event_uniq_id: str, document_id: str) -> bool:
        """Return True if a background upload is queued for this document."""
        return cls.result_id(event_uniq_id, document_id) in cls.queued_result_ids

    @classmethod
    def custom_upload_needed(cls, event: Event, document: ConfiguredDocument) -> bool:
        """A document must be re-uploaded when it has never been uploaded or when
        the results of one of its tournaments changed since the last upload."""
        last_upload = document.last_upload_at
        if not last_upload:
            return True
        tournaments = CustomUploadUtils.document_tournaments(event, document)
        if not tournaments:
            # No tournament tie (event-wide document): re-upload on any change.
            tournaments = list(event.tournaments_by_id.values())
        return any(
            Utils.tournament_results_modified_since(tournament, last_upload)
            for tournament in tournaments
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
    def test_file_transfer_connection(
        cls,
        host: str,
        username: str,
        password: str,
        target_path: str,
        transfer_protocol: TransferProtocol,
        transfer_port: int,
    ) -> None:
        """Connection attempt to the FTP/SFTP server.
        Throws ConnectionError exception if the connection doesn't succeed.
        Throws FileNotFoundError exception if the target path can't be found."""

        match transfer_protocol:
            case TransferProtocol.SFTP:
                cls._sftp_auth_check(
                    host, username, password, transfer_port, target_path
                )
            case TransferProtocol.FTP:
                cls._ftp_auth_check(
                    host, username, password, transfer_port, target_path
                )
            case TransferProtocol.FTPS:
                cls._ftps_auth_check(
                    host, username, password, transfer_port, target_path
                )

    @classmethod
    def upload_document(
        cls,
        event_uniq_id: str,
        document_id: str,
        http_client: Client,
    ):
        """Upload a single configured document to its custom location."""

        result_id: str = cls.result_id(event_uniq_id, document_id)
        cls.ongoing_result_ids.add(result_id)
        cls.queued_result_ids.discard(result_id)

        try:
            # NOTE (Molrn) Ensures a minimum time for the thread
            # This prevents flashing and situations where both requests
            # triggered by the `upload-event` web socket are treated as one
            time.sleep(0.5)

            # We refetch the latest event and document
            loader = EventLoader()
            if event_uniq_id not in loader.event_uniq_ids:
                # The event has been deleted
                return
            event = loader.load_event(event_uniq_id)

            document = CustomUploadUtils.get_document(event, document_id)
            if not document:
                # The document has been removed
                return

            if CustomUploadUtils.event_connection_message(event):
                # Skip if the connection is not configured
                return

            if not NetworkMonitor.connected():
                # The network is offline, we can't upload
                return

            logger.info('Generating document [%s]...', document.document_id)

            event_plugin_data = CustomUploadUtils.get_event_plugin_data(event)

            try:
                temporary_file, file_name = cls._generate_document_in_memory(
                    event, document, http_client
                )
            except Exception as error:
                logger.exception(
                    'Error while generating document [%s]: %s.',
                    document.document_id,
                    error,
                )
                document.upload_failure_id = UnexpectedFailureCustomUploadStatus().id
                document.last_upload_attempt_at = datetime.now()
                CustomUploadUtils.update_document_state(event_uniq_id, document)
                return

            host = event_plugin_data.ftp_host
            username = event_plugin_data.ftp_username
            password = event_plugin_data.ftp_password or ''
            transfer_protocol = event_plugin_data.transfer_protocol
            port = event_plugin_data.transfer_port

            if not host or not username:
                # Host or username is missing, we can't upload
                return

            target_path = (
                document.server_path or event_plugin_data.default_server_path or ''
            )
            base_target_path = os.path.dirname(target_path)
            port = port or transfer_protocol.default_port

            logger.info(
                'Uploading document [%s] to [%s:********@%s:%d/%s] via [%s]...',
                document.document_id,
                username,
                host,
                port,
                target_path,
                transfer_protocol,
            )
            if transfer_protocol == TransferProtocol.SFTP:
                cls._sftp_upload(
                    host,
                    username,
                    password,
                    port,
                    transfer_protocol,
                    target_path,
                    base_target_path,
                    event_uniq_id,
                    document,
                    result_id,
                    temporary_file,
                    file_name,
                )
            else:
                cls._ftp_upload(
                    host,
                    username,
                    password,
                    port,
                    transfer_protocol,
                    target_path,
                    base_target_path,
                    event_uniq_id,
                    document,
                    result_id,
                    temporary_file,
                    file_name,
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
        transfer_port: int,
        transfer_protocol: TransferProtocol,
        target_path: str,
        base_target_path: str,
        event_uniq_id: str,
        document: ConfiguredDocument,
        result_id: str,
        temporary_file: BytesIO,
        file_name: str,
    ):
        failure_status: FailureCustomUploadStatus | None = None
        error_message: str = f'Uploading document [{document.document_id}] to [{host}:{transfer_port}/{target_path}] via [{transfer_protocol.name}] failed: %s.'

        with paramiko.SSHClient() as ssh_client:
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            sftp_client: SFTPClient | None = None
            try:
                ssh_client.connect(
                    host, username=username, password=password, port=transfer_port
                )
                sftp_client = ssh_client.open_sftp()
                assert sftp_client is not None

                if not CustomUploadUploader._does_remote_path_exist_sftp(
                    sftp_client, base_target_path
                ):
                    logger.error(
                        error_message,
                        f"path [{base_target_path}] doesn't target a valid location",
                    )
                    failure_status = TargetLocationNotFoundCustomUploadStatus()
                    return

                if not CustomUploadUploader._does_remote_path_exist_sftp(
                    sftp_client, target_path
                ):
                    # In this case, it means only subfolder is missing. Let's create it.
                    sftp_client.mkdir(target_path)

                sftp_client.putfo(
                    temporary_file,
                    (PurePosixPath(target_path) / file_name).as_posix(),
                )
                logger.info('Uploaded document file [%s].', file_name)
            except AuthenticationException as error:
                logger.error(
                    error_message,
                    f'Authentication failed [{error}]',
                )
                failure_status = AuthenticationFailureCustomUploadStatus()
            except (SSHException, EOFError, OSError) as error:
                logger.error(
                    error_message,
                    f'Connection failed [{error}]',
                )
                failure_status = ConnectionFailureCustomUploadStatus()
            except Exception as error:
                logger.error(
                    error_message,
                    f'Unexpected exception [{error}]',
                )
                failure_status = UnexpectedFailureCustomUploadStatus()
            finally:
                if sftp_client is not None:
                    sftp_client.close()
                temporary_file.close()
                cls.ongoing_result_ids.discard(result_id)
                cls._record_upload_result(event_uniq_id, document, failure_status)

    @classmethod
    def _ftp_upload(
        cls,
        host: str,
        username: str,
        password: str,
        transfer_port: int,
        transfer_protocol: TransferProtocol,
        target_path: str,
        base_target_path: str,
        event_uniq_id: str,
        document: ConfiguredDocument,
        result_id: str,
        temporary_file: BytesIO,
        file_name: str,
    ):
        failure_status: FailureCustomUploadStatus | None = None
        error_message: str = f'Uploading document [{document.document_id}] to [{host}:{transfer_port}/{target_path}] via [{transfer_protocol.name}] failed: %s.'

        try:
            ftp_client_type: type[ftplib.FTP] = ftplib.FTP
            if transfer_protocol == TransferProtocol.FTPS:
                ftp_client_type = ftplib.FTP_TLS

            with ftp_client_type() as ftp_client:
                ftp_client.connect(host, transfer_port, timeout=5)
                ftp_client.login(username, password)

                if not CustomUploadUploader._does_remote_path_exist_ftp(
                    ftp_client, base_target_path
                ):
                    logger.error(
                        error_message,
                        f"path [{base_target_path}] doesn't target a valid location",
                    )
                    failure_status = TargetLocationNotFoundCustomUploadStatus()
                    return

                if not CustomUploadUploader._does_remote_path_exist_ftp(
                    ftp_client, target_path
                ):
                    # In this case, it means only subfolder is missing. Let's create it.
                    ftp_client.mkd(target_path)

                ftp_client.storbinary(
                    f'STOR {(PurePosixPath(target_path) / file_name).as_posix()}',
                    temporary_file,
                )
                logger.info('Uploaded document file [%s]', file_name)
        except ftplib.error_perm as error:
            logger.error(
                error_message,
                f'Authentication failed [{error}]',
            )
            failure_status = AuthenticationFailureCustomUploadStatus()
        except ftplib.all_errors as error:
            logger.error(
                error_message,
                f'Connection failed [{error}]',
            )
            failure_status = ConnectionFailureCustomUploadStatus()
        except Exception as error:
            logger.error(
                error_message,
                f'Unexpected exception [{error}]',
            )
            failure_status = UnexpectedFailureCustomUploadStatus()
        finally:
            temporary_file.close()
            cls.ongoing_result_ids.discard(result_id)
            cls._record_upload_result(event_uniq_id, document, failure_status)

    @classmethod
    def _record_upload_result(
        cls,
        event_uniq_id: str,
        document: ConfiguredDocument,
        failure_status: FailureCustomUploadStatus | None,
    ):
        now = datetime.now()
        if failure_status:
            document.upload_failure_id = failure_status.id
        else:
            document.upload_failure_id = None
            document.last_upload_at = now
        document.last_upload_attempt_at = now
        CustomUploadUtils.update_document_state(event_uniq_id, document)
        cls.publish_upload_event()

    @classmethod
    def _generate_document_in_memory(
        cls,
        event: Event,
        document: ConfiguredDocument,
        http_client: Client,
    ) -> tuple[BytesIO, str]:
        document_htmx_template = EventDocumentsController.document_view(
            http_client,
            event,
            document.document_id,
            document.options or None,
        )
        html_content = parse_jinja_template(
            document_htmx_template.template_name, document_htmx_template.context
        )
        temporary_file = BytesIO(html_content.encode())

        normalized_filename = document.target_filename.strip()
        file_name: str
        if normalized_filename:
            file_name = normalized_filename
        else:
            options_suffix = re.sub(r'[^A-Za-z0-9]+', '_', document.options).strip('_')
            file_name = f'{"_".join(event.name.split())}_{document.document_id}'
            if options_suffix:
                file_name += f'_{options_suffix}'
        file_name += '.html'
        return temporary_file, file_name

    @classmethod
    def schedule_upload(
        cls, event: Event, document: ConfiguredDocument, http_client: Client
    ):
        """Schedule the upload of a single document."""
        if CustomUploadUtils.event_connection_message(event):
            return

        event_uniq_id = event.uniq_id
        result_id = cls.result_id(event_uniq_id, document.id)

        def _run():
            set_locale(SharlyChessConfig().locale)
            cls.upload_document(event_uniq_id, document.id, http_client)

        timer = Timer(0.1, _run)
        cls.timeout_threads[result_id] = timer
        timer.start()

    @classmethod
    def upload_event_documents(
        cls, event: Event, documents: list[ConfiguredDocument], http_client: Client
    ):
        """Upload all eligible documents of an event in a background thread."""
        if CustomUploadUtils.event_connection_message(event):
            return

        event_uniq_id = event.uniq_id
        updated_documents: list[ConfiguredDocument] = [
            document
            for document in documents
            if cls.result_id(event_uniq_id, document.id) not in cls.ongoing_result_ids
            and cls.custom_upload_needed(event, document)
        ]
        if not updated_documents:
            return

        for document in updated_documents:
            cls.queued_result_ids.add(cls.result_id(event_uniq_id, document.id))

        def _run():
            set_locale(SharlyChessConfig().locale)
            for document in updated_documents:
                cls.upload_document(event_uniq_id, document.id, http_client)

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
            if 'type=dir;' in ftp_client.sendcmd(f'MLST {remote_path}'):
                return True
        except error_perm:
            return False
        return False

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
            except AuthenticationException as error:
                raise PermissionError(error)
            except (
                BadHostKeyException,
                NoValidConnectionsError,
                SSHException,
                OSError,
                TimeoutError,
            ) as error:
                raise ConnectionError(error)

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
        except ftplib.error_perm as error:
            raise PermissionError(error)
        except ftplib.all_errors as error:
            raise ConnectionError(error)
