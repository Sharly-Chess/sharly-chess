import socket
from io import BytesIO
import threading
from collections.abc import Iterator
from pathlib import Path

import paramiko
import pytest
from paramiko.common import AUTH_FAILED, AUTH_SUCCESSFUL

from plugins.custom_upload import host_keys
from plugins.custom_upload.custom_upload_status import (
    FailureCustomUploadStatus,
    UntrustedServerCustomUploadStatus,
)
from plugins.custom_upload.custom_upload_uploader import CustomUploadUploader
from plugins.custom_upload.host_keys import SFTPHostKeys, UntrustedHostKeyError
from plugins.custom_upload.utils import ConfiguredDocument, TransferProtocol

USERNAME = 'arbiter'
PASSWORD = 's3cret'


class _Server(paramiko.ServerInterface):
    def __init__(self, passwords: list[str]):
        self.passwords = passwords

    def get_allowed_auths(self, username: str) -> str:
        return 'password'

    def check_auth_password(self, username: str, password: str) -> int:
        self.passwords.append(password)
        if username == USERNAME and password == PASSWORD:
            return AUTH_SUCCESSFUL
        return AUTH_FAILED


class SSHServer:
    """An SSH server on a local port, recording the passwords it receives."""

    def __init__(self) -> None:
        self.key: paramiko.PKey = paramiko.RSAKey.generate(2048)
        self.passwords: list[str] = []
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
        transport = paramiko.Transport(connection)
        transport.add_server_key(self.key)
        try:
            transport.start_server(server=_Server(self.passwords))
            transport.join(5)
        except Exception:
            pass
        finally:
            transport.close()

    def close(self) -> None:
        self._socket.close()


@pytest.fixture
def known_hosts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / 'known_hosts'
    monkeypatch.setattr(host_keys, 'KNOWN_HOSTS_FILE', path)
    return path


@pytest.fixture
def server() -> Iterator[SSHServer]:
    ssh_server = SSHServer()
    yield ssh_server
    ssh_server.close()


def _connect(server: SSHServer, accepted_key: str | None = None) -> None:
    with paramiko.SSHClient() as client:
        SFTPHostKeys.connect(
            client,
            '127.0.0.1',
            server.port,
            USERNAME,
            PASSWORD,
            accepted_key=accepted_key,
            timeout=5,
        )


def test_unknown_server_is_rejected_before_the_password_is_sent(
    known_hosts: Path, server: SSHServer
) -> None:
    with pytest.raises(UntrustedHostKeyError) as error:
        _connect(server)
    assert not error.value.changed
    assert error.value.fingerprint == server.key.fingerprint
    assert server.passwords == []
    assert not known_hosts.exists()


def test_accepted_key_is_trusted_and_reused(
    known_hosts: Path, server: SSHServer
) -> None:
    with pytest.raises(UntrustedHostKeyError) as error:
        _connect(server)
    _connect(server, accepted_key=error.value.encoded_key)
    assert server.passwords == [PASSWORD]
    assert f'[127.0.0.1]:{server.port}' in known_hosts.read_text()

    _connect(server)
    assert server.passwords == [PASSWORD, PASSWORD]


def test_accepting_another_key_does_not_trust_the_server(
    known_hosts: Path, server: SSHServer
) -> None:
    other_key = SFTPHostKeys.encode_key(paramiko.RSAKey.generate(2048))
    with pytest.raises(UntrustedHostKeyError):
        _connect(server, accepted_key=other_key)
    assert server.passwords == []
    assert not known_hosts.exists()


def test_changed_key_is_rejected_until_accepted_again(
    known_hosts: Path, server: SSHServer
) -> None:
    previous_key = paramiko.RSAKey.generate(2048)
    SFTPHostKeys.trust('127.0.0.1', server.port, previous_key)

    with pytest.raises(UntrustedHostKeyError) as error:
        _connect(server)
    assert error.value.changed
    assert error.value.trusted_key == previous_key
    assert server.passwords == []

    _connect(server, accepted_key=error.value.encoded_key)
    _connect(server)
    assert server.passwords == [PASSWORD, PASSWORD]
    assert previous_key.get_base64() not in known_hosts.read_text()


def test_trusted_key_is_kept_when_another_key_is_accepted(
    known_hosts: Path, server: SSHServer
) -> None:
    SFTPHostKeys.trust('127.0.0.1', server.port, server.key)
    other_key = SFTPHostKeys.encode_key(paramiko.RSAKey.generate(2048))
    _connect(server, accepted_key=other_key)
    assert server.passwords == [PASSWORD]
    assert server.key.get_base64() in known_hosts.read_text()


def test_host_key_name_follows_openssh() -> None:
    assert SFTPHostKeys.host_key_name('example.com', 22) == 'example.com'
    assert SFTPHostKeys.host_key_name('example.com', 2222) == '[example.com]:2222'


def test_upload_to_an_untrusted_server_fails_without_sending_the_password(
    known_hosts: Path, server: SSHServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded: list[FailureCustomUploadStatus | None] = []
    monkeypatch.setattr(
        CustomUploadUploader,
        '_record_upload_result',
        classmethod(
            lambda cls, event_uniq_id, document, status: recorded.append(status)
        ),
    )
    CustomUploadUploader._sftp_upload(
        '127.0.0.1',
        USERNAME,
        PASSWORD,
        server.port,
        TransferProtocol.SFTP,
        'results',
        '',
        'event',
        ConfiguredDocument(id='document', document_id='standings'),
        'event:document',
        BytesIO(b'content'),
        'standings.html',
    )
    assert len(recorded) == 1
    assert isinstance(recorded[0], UntrustedServerCustomUploadStatus)
    assert server.passwords == []
