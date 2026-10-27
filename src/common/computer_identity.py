"""What this computer is recognised by.

The key pair belongs to the computer rather than to any event, so services the
computer connects to can tell it apart from a copy of its events running on
another one. The private half is generated here and never leaves the computer.
"""

import hashlib
from dataclasses import dataclass
from threading import Lock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from database.sqlite.config.config_database import ConfigDatabase

_lock = Lock()


@dataclass(frozen=True)
class ComputerIdentity:
    private_key: str
    public_key: str

    @property
    def device_id(self) -> str:
        """A short name for the computer, derived from its public key."""
        return hashlib.sha256(self.public_key.encode()).hexdigest()[:32]


def _generate_key_pair() -> tuple[str, str]:
    """A new key, written the way OpenSSH writes one.

    Ed25519 because it is short enough to send about without ceremony, and
    there is no key size to choose badly.
    """
    private_key = Ed25519PrivateKey.generate()
    private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )
        .decode()
    )
    return private, public


def computer_identity() -> ComputerIdentity:
    """The computer's identity, given one the first time it is asked for.

    It is generated once and kept: a new one would make everything issued to
    this computer look as if it came from another.
    """
    with _lock:
        with ConfigDatabase() as database:
            stored_config = database.load_stored_config()
        if stored_config.computer_private_key and stored_config.computer_public_key:
            return ComputerIdentity(
                private_key=stored_config.computer_private_key,
                public_key=stored_config.computer_public_key,
            )
        private_key, public_key = _generate_key_pair()
        with ConfigDatabase(write=True) as database:
            database.update_computer_keys(private_key, public_key)
        return ComputerIdentity(private_key=private_key, public_key=public_key)
