"""What this computer is known by to the relay that carries remote access.

The relay recognises the computer by the key pair the computer is recognised by
everywhere else: one computer, one key, whose private half is generated on it
and never leaves.  What belongs to remote access alone is the identifier the
control plane answers with once the public half has been registered, and that
is all this holds.
"""

from dataclasses import dataclass
from io import StringIO

import paramiko

from common.computer_identity import ComputerIdentity, computer_identity
from database.sqlite.config.config_database import ConfigDatabase


@dataclass(frozen=True)
class RemoteInstall:
    """The computer, as the control plane knows it."""

    identity: ComputerIdentity
    #: None until the control plane has been told about the public half.
    install_id: str | None

    @property
    def public_key(self) -> str:
        return self.identity.public_key

    @property
    def is_registered(self) -> bool:
        return self.install_id is not None

    def signing_key(self) -> paramiko.PKey:
        """The key in the form the SSH client wants it."""
        return paramiko.Ed25519Key.from_private_key(StringIO(self.identity.private_key))


def remote_install() -> RemoteInstall:
    """The computer, with whatever the control plane has called it so far."""
    with ConfigDatabase() as database:
        install_id = database.load_stored_config().remote_install_id
    return RemoteInstall(identity=computer_identity(), install_id=install_id)


def set_install_id(install_id: str) -> RemoteInstall:
    """Records what the control plane calls this computer."""
    with ConfigDatabase(write=True) as database:
        database.update_remote_install_id(install_id)
    return RemoteInstall(identity=computer_identity(), install_id=install_id)


def forget_remote_install() -> None:
    """Discards the identifier, so that the next use registers the computer
    again.

    The key is kept: it belongs to the computer rather than to remote access,
    and other things are recognised by it.  Registering it again is refused once
    it has been disowned, which is what makes a lost laptop stay lost.
    """
    with ConfigDatabase(write=True) as database:
        database.update_remote_install_id(None)
