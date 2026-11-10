import base64
from pathlib import Path
from threading import Lock

import paramiko
from paramiko.pkey import PKey
from paramiko.ssh_exception import BadHostKeyException

from common import DATA_DIR

KNOWN_HOSTS_FILE: Path = DATA_DIR / 'known_hosts'


class UntrustedHostKeyError(Exception):
    """The SFTP server presented a host key that is not trusted: either the
    server is unknown, or its key differs from the one trusted before. The
    connection is dropped before any credential is sent."""

    def __init__(
        self, host: str, port: int, key: PKey, trusted_key: PKey | None = None
    ):
        self.host = host
        self.port = port
        self.key = key
        self.trusted_key = trusted_key
        super().__init__(
            f'Host key {key.fingerprint} of [{host}:{port}] is '
            + ('different from the trusted one' if trusted_key else 'not trusted')
        )

    @property
    def changed(self) -> bool:
        return self.trusted_key is not None

    @property
    def fingerprint(self) -> str:
        return self.key.fingerprint

    @property
    def encoded_key(self) -> str:
        return SFTPHostKeys.encode_key(self.key)


class SFTPHostKeys:
    """The SFTP server keys the user has trusted, stored in a known_hosts file
    of the data folder."""

    _lock = Lock()

    @staticmethod
    def encode_key(key: PKey) -> str:
        return f'{key.get_name()} {key.get_base64()}'

    @staticmethod
    def decode_key(encoded_key: str) -> PKey | None:
        try:
            key_type, blob = encoded_key.split(' ', 1)
            return PKey.from_type_string(key_type, base64.b64decode(blob))
        except Exception:
            return None

    @staticmethod
    def host_key_name(host: str, port: int) -> str:
        return host if port == 22 else f'[{host}]:{port}'

    @classmethod
    def trust(cls, host: str, port: int, key: PKey) -> None:
        """Trust the key for the server, replacing any key trusted before."""
        name = cls.host_key_name(host, port)
        with cls._lock:
            host_keys = paramiko.HostKeys()
            if KNOWN_HOSTS_FILE.exists():
                host_keys.load(str(KNOWN_HOSTS_FILE))
            if name in host_keys:
                del host_keys[name]
            host_keys.add(name, key.get_name(), key)
            KNOWN_HOSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            host_keys.save(str(KNOWN_HOSTS_FILE))

    @classmethod
    def connect(
        cls,
        client: paramiko.SSHClient,
        host: str,
        port: int,
        username: str,
        password: str,
        accepted_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Connect the client, authenticating the server with the trusted keys.

        ``accepted_key`` is a key the user has just accepted, as given by
        ``UntrustedHostKeyError.encoded_key``: when the server presents it, it
        becomes the trusted key of the server. Raises ``UntrustedHostKeyError``
        when the server presents any other key that is not trusted."""
        name = cls.host_key_name(host, port)
        with cls._lock:
            if KNOWN_HOSTS_FILE.exists():
                client.load_host_keys(str(KNOWN_HOSTS_FILE))
        host_keys = client.get_host_keys()
        trusted_keys = host_keys.lookup(name)
        accepted = cls.decode_key(accepted_key) if accepted_key else None
        if accepted is not None and trusted_keys is not None:
            del host_keys[name]
        client.set_missing_host_key_policy(
            _TrustOnFirstUsePolicy(
                host,
                port,
                accepted,
                next(iter(trusted_keys.values())) if trusted_keys else None,
            )
        )
        try:
            client.connect(
                host,
                username=username,
                password=password,
                port=port,
                timeout=timeout,
                allow_agent=False,
                look_for_keys=False,
            )
        except BadHostKeyException as error:
            raise UntrustedHostKeyError(
                host, port, error.key, error.expected_key
            ) from error


class _TrustOnFirstUsePolicy(paramiko.MissingHostKeyPolicy):
    """Accepts the server key only if it is already trusted or is the one the
    user has just accepted."""

    def __init__(
        self,
        host: str,
        port: int,
        accepted: PKey | None,
        trusted_key: PKey | None,
    ):
        self.host = host
        self.port = port
        self.accepted = accepted
        self.trusted_key = trusted_key

    def missing_host_key(
        self, client: paramiko.SSHClient, hostname: str, key: PKey
    ) -> None:
        if key == self.trusted_key:
            return
        if self.accepted is not None and key == self.accepted:
            SFTPHostKeys.trust(self.host, self.port, key)
            return
        raise UntrustedHostKeyError(self.host, self.port, key, self.trusted_key)
