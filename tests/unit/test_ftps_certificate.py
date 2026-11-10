import datetime
from io import BytesIO
import ipaddress
import socket
import ssl
import threading
from collections.abc import Iterator
from pathlib import Path

import certifi
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from plugins.custom_upload.custom_upload_status import (
    FailureCustomUploadStatus,
    UntrustedServerCustomUploadStatus,
)
from plugins.custom_upload.custom_upload_uploader import (
    CustomUploadUploader,
    UntrustedCertificateError,
)
from plugins.custom_upload.utils import ConfiguredDocument, TransferProtocol

USERNAME = 'arbiter'
PASSWORD = 's3cret'


def _self_signed_certificate(directory: Path) -> tuple[Path, Path]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, '127.0.0.1')])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    certificate_file = directory / 'certificate.pem'
    key_file = directory / 'key.pem'
    certificate_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return certificate_file, key_file


class FTPSServer:
    """An explicit FTPS server, enough for the connection test and an upload;
    records the commands it receives once secured and the files uploaded."""

    def __init__(self, directory: Path):
        self.certificate_file, key_file = _self_signed_certificate(directory)
        self._context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._context.load_cert_chain(self.certificate_file, key_file)
        self.commands: list[str] = []
        self.files: dict[str, bytes] = {}
        self.data_sessions_reused: list[bool] = []
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.bind(('127.0.0.1', 0))
        self._socket.listen()
        self.port: int = self._socket.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                connection, _ = self._socket.accept()
            except OSError:
                return
            threading.Thread(
                target=self._handle, args=(connection,), daemon=True
            ).start()

    def _handle(self, connection: socket.socket) -> None:
        try:
            connection.sendall(b'220 Ready\r\n')
            assert connection.recv(1024).startswith(b'AUTH TLS')
            connection.sendall(b'234 AUTH TLS ok\r\n')
            secured = self._context.wrap_socket(connection, server_side=True)
            data_listener: socket.socket | None = None
            replies = {
                'USER': '331 Password required',
                'PASS': '230 Logged in',
                'PBSZ': '200 PBSZ=0',
                'PROT': '200 Protection set to Private',
                'MLST': '250-Listing\r\n type=dir; /results\r\n250 End',
                'TYPE': '200 Type set',
                'QUIT': '221 Bye',
            }
            for line in secured.makefile('r', encoding='utf-8'):
                command = line.strip()
                self.commands.append(command)
                verb, _, argument = command.partition(' ')
                if verb == 'PASV':
                    data_listener = socket.create_server(('127.0.0.1', 0))
                    port = data_listener.getsockname()[1]
                    reply = f'227 Passive (127,0,0,1,{port >> 8},{port & 255})'
                elif verb == 'STOR' and data_listener is not None:
                    secured.sendall(b'150 Opening data connection\r\n')
                    data_connection, _ = data_listener.accept()
                    with self._context.wrap_socket(
                        data_connection, server_side=True
                    ) as data:
                        self.data_sessions_reused.append(bool(data.session_reused))
                        self.files[argument] = b''.join(
                            iter(lambda: data.recv(4096), b'')
                        )
                        data.unwrap()
                    reply = '226 Transfer complete'
                else:
                    reply = replies.get(verb, '502 Not implemented')
                secured.sendall(f'{reply}\r\n'.encode())
                if verb == 'QUIT':
                    break
        except OSError, AssertionError:
            pass
        finally:
            connection.close()

    def close(self) -> None:
        self._socket.close()


@pytest.fixture
def server(tmp_path: Path) -> Iterator[FTPSServer]:
    ftps_server = FTPSServer(tmp_path)
    yield ftps_server
    ftps_server.close()


def _test_connection(server: FTPSServer) -> None:
    CustomUploadUploader._ftps_auth_check(
        '127.0.0.1', USERNAME, PASSWORD, server.port, '/results'
    )


def test_unverified_certificate_is_rejected_before_the_password_is_sent(
    server: FTPSServer,
) -> None:
    with pytest.raises(UntrustedCertificateError):
        _test_connection(server)
    assert not any(command.startswith('PASS') for command in server.commands)


def test_verified_certificate_is_accepted_and_the_data_connections_protected(
    server: FTPSServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(certifi, 'where', lambda: str(server.certificate_file))
    _test_connection(server)
    assert f'PASS {PASSWORD}' in server.commands
    assert 'PROT P' in server.commands


def _upload(
    server: FTPSServer, monkeypatch: pytest.MonkeyPatch
) -> list[FailureCustomUploadStatus | None]:
    recorded: list[FailureCustomUploadStatus | None] = []
    monkeypatch.setattr(
        CustomUploadUploader,
        '_record_upload_result',
        classmethod(
            lambda cls, event_uniq_id, document, status: recorded.append(status)
        ),
    )
    CustomUploadUploader._ftp_upload(
        '127.0.0.1',
        USERNAME,
        PASSWORD,
        server.port,
        TransferProtocol.FTPS,
        '/results',
        '/results',
        'event',
        ConfiguredDocument(id='document', document_id='standings'),
        'event:document',
        BytesIO(b'content'),
        'standings.html',
    )
    return recorded


def test_upload_with_unverified_certificate_fails_without_sending_the_password(
    server: FTPSServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded = _upload(server, monkeypatch)
    assert len(recorded) == 1
    assert isinstance(recorded[0], UntrustedServerCustomUploadStatus)
    assert not any(command.startswith('PASS') for command in server.commands)


def test_upload_sends_the_file_over_a_resumed_tls_session(
    server: FTPSServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(certifi, 'where', lambda: str(server.certificate_file))
    assert _upload(server, monkeypatch) == [None]
    assert server.files == {'/results/standings.html': b'content'}
    assert server.data_sessions_reused == [True]
