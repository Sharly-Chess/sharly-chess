from abc import ABC, abstractmethod

from common.i18n import _
from data.auth.managers import RoleManager
from database.sqlite.event.event_store import (
    StoredDevice,
    StoredAccount,
    StoredAccess,
)
from data.auth.roles import Role, AdministrationRole


class AuthEntity[T: StoredAccess](ABC):
    """An abstract access entity."""

    def __init__(self, stored_access: T):
        self._stored_access = stored_access

    @property
    def id(self) -> int:
        assert self._stored_access.id is not None
        return self._stored_access.id

    @property
    @abstractmethod
    def edit_properties(self) -> bool:
        """Returns False if the device is locked (can not be updated or deleted)."""

    @property
    @abstractmethod
    def edit_permissions(self) -> bool:
        """Returns True if the permissions of the device can be updated."""

    @property
    def active(self) -> bool:
        return self._stored_access.active

    @property
    def roles(self) -> list[Role]:
        return [
            RoleManager.get_object(role_id) for role_id in self._stored_access.roles
        ]

    @property
    def tournament_ids(self) -> set[int] | None:
        if self._stored_access.tournament_ids is None:
            return None
        return set(self._stored_access.tournament_ids)


class Device(AuthEntity[StoredDevice]):
    """A data wrapper around a stored device, made of an IP specification."""

    LOCALHOST_IP: str = '127.0.0.1'
    LOCALHOST_NAME: str = 'localhost'
    LOCALHOST_ID: int = 1
    ANY_DEVICE_ID: int = 2
    UNKNOWN_IP: str = '0.0.0.0'

    def __init__(self, stored_device: StoredDevice):
        super().__init__(stored_device)
        self.stored_device = stored_device

    @property
    def edit_properties(self) -> bool:
        return not self.localhost and not self.unknown

    @property
    def edit_permissions(self) -> bool:
        return not self.localhost

    @classmethod
    def host_is_localhost(cls, host: str) -> bool:
        """Returns True the host is the server itself."""
        return host in [
            cls.LOCALHOST_IP,
            cls.LOCALHOST_NAME,
        ]

    @property
    def localhost(self) -> bool:
        """Returns True if the device is the server itself."""
        return self.id == self.LOCALHOST_ID

    @property
    def unknown(self) -> bool:
        """Returns True if the device represents any client."""
        return self.id == self.ANY_DEVICE_ID

    @property
    def ip(self) -> str:
        """Returns the host address of the device."""
        if self.localhost:
            return '{ip} ({name})'.format(
                ip=self.LOCALHOST_IP,
                name=_('server'),
            )
        if self.unknown:
            return '{ip} ({name})'.format(
                ip=self.UNKNOWN_IP,
                name=_('unknown'),
            )
        assert self.stored_device.ip is not None
        return self.stored_device.ip

    def __repr__(self) -> str:
        return f'Device(id={self.id}, ip={self.ip})'

    # devices are stored at event-level, methods localhost_device()
    # and unknown_device() provide event-free instances that can
    # be used when no events are available (welcome page, ...)

    @classmethod
    def localhost_device(cls) -> 'Device':
        return cls(
            StoredDevice(
                id=cls.LOCALHOST_ID,
                active=True,
                roles=[AdministrationRole.static_id()],
                tournament_ids=None,
                ip=None,
            )
        )

    @classmethod
    def unknown_device(cls) -> 'Device':
        return cls(
            StoredDevice(
                id=cls.ANY_DEVICE_ID,
                active=True,
                roles=[],
                tournament_ids=None,
                ip=None,
            )
        )


class Account(AuthEntity[StoredAccount]):
    """A data wrapper around a stored account.
    The class that represents an account, made of credentials (username and password)."""

    ANONYMOUS_ID: int = 1

    def __init__(self, stored_account: StoredAccount):
        super().__init__(stored_account)
        self.stored_account = stored_account

    @property
    def edit_properties(self) -> bool:
        return not self.anonymous

    @property
    def edit_permissions(self) -> bool:
        return True

    @property
    def anonymous(self) -> bool:
        """Returns True the client represent any account."""
        return self.id == self.ANONYMOUS_ID

    @property
    def username(self) -> str | None:
        """Returns the username of the account."""
        return self.stored_account.username

    @property
    def password_hash(self) -> str | None:
        """Returns the password hash of the account."""
        return self.stored_account.password_hash

    def update_password(self, new_hash: str):
        self.stored_account.password_hash = new_hash

    def __repr__(self) -> str:
        return f'Account(id={self.id}, username={self.username})'

    # Accounts are stored at event-level, this provides an event-free
    # instance that can be used when no events are available (welcome page, ...)

    @classmethod
    def anonymous_account(cls) -> 'Account':
        return cls(
            StoredAccount(
                id=cls.ANONYMOUS_ID,
                active=True,
                roles=[],
                tournament_ids=None,
                username=None,
                password_hash=None,
            )
        )
