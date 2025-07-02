from abc import ABC
from typing import Self

from common.i18n import _
from database.sqlite.event.event_store import (
    StoredDevice,
    StoredAccount,
    LOCALHOST_ID,
    ANY_DEVICE_ID,
    ANONYMOUS_ID,
)
from data.auth.roles import Role


class AuthEntity(ABC):
    """An abstract access entity."""

    def __init__(
        self,
        permissions: dict[int, str | None],
    ):
        self.permissions_by_role: dict[Role, str | None] = {
            Role(role_value): tournament_uniq_ids
            for role_value, tournament_uniq_ids in permissions.items()
        }


class Device(AuthEntity):
    """A data wrapper around a stored device, made of an IP specification."""

    LOCALHOST_IP: str = '127.0.0.1'
    LOCALHOST_NAME: str = 'localhost'
    UNKNOWN_IP: str = '0.0.0.0'

    def __init__(
        self,
        stored_device: StoredDevice,
    ):
        self.stored_device: StoredDevice = stored_device
        super().__init__(self.stored_device.permissions)

    @property
    def id(self) -> int:
        """Returns the device ID."""
        assert self.stored_device.id is not None
        return self.stored_device.id

    @property
    def edit_properties(self) -> bool:
        """Returns True the device is locked (can not be updated or deleted)."""
        return self.stored_device.edit_properties

    @property
    def edit_permissions(self) -> bool:
        """Returns True the permissions of the device can be updated."""
        return self.stored_device.edit_permissions

    @property
    def active(self) -> bool:
        """Returns the device is active."""
        return self.stored_device.active

    @classmethod
    def host_is_localhost(cls, host: str) -> bool:
        """Returns True the host is the server itself."""
        return host in [
            cls.LOCALHOST_IP,
            cls.LOCALHOST_NAME,
        ]

    @property
    def localhost(self) -> bool:
        """Returns True the device is the server itself."""
        return self.stored_device.id == LOCALHOST_ID

    @property
    def unknown(self) -> bool:
        """Returns True the device represent any client."""
        return self.stored_device.id == ANY_DEVICE_ID

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

    def matches(
        self,
        host: str,
    ) -> bool:
        """Returns True if the given host matches, False otherwise."""
        if self.localhost:
            return self.host_is_localhost(host)
        elif self.unknown:
            return True
        else:
            assert self.stored_device.ip is not None
            return host == self.stored_device.ip

    def __repr__(self) -> str:
        return f'Device(id={self.id}, ip={self.ip})'

    # devices are stored at event-level, methods localhost_device')
    # and unknown_device() provide event-free instances that can
    # be used when no events are available (welcome page, ...)

    @classmethod
    def localhost_device(cls) -> Self:
        return cls(StoredDevice.localhost_stored_device())

    @classmethod
    def unknown_device(cls) -> Self:
        return cls(StoredDevice.unknown_stored_device())


class Account(AuthEntity):
    """A data wrapper around a stored account.
    The class that represents an account, made of credentials (username and password)."""

    def __init__(
        self,
        stored_account: StoredAccount,
    ):
        self.stored_account: StoredAccount = stored_account
        super().__init__(self.stored_account.permissions)

    @property
    def id(self) -> int:
        """Returns the account ID."""
        assert self.stored_account.id is not None
        return self.stored_account.id

    @property
    def edit_properties(self) -> bool:
        """Returns True the account is locked (can not be updated or deleted)."""
        return self.stored_account.edit_properties

    @property
    def edit_permissions(self) -> bool:
        """Returns True the permissions of the account can be updated."""
        return self.stored_account.edit_permissions

    @property
    def active(self) -> bool:
        """Returns the account is active."""
        return self.stored_account.active

    @property
    def anonymous(self) -> bool:
        """Returns True the client represent any account."""
        return self.stored_account.id == ANONYMOUS_ID

    @property
    def username(self) -> str | None:
        """Returns the username of the account."""
        if self.anonymous:
            return None
        return self.stored_account.username

    @property
    def password(self) -> str | None:
        """Returns the password of the account."""
        if self.anonymous:
            return None
        return self.stored_account.password

    def matches(
        self,
        account: Self | None,
    ) -> bool:
        """Returns True if the given account matches, False otherwise."""
        if self.anonymous:
            return True
        elif account is None:
            return False
        else:
            return self.id == account.id

    def __repr__(self) -> str:
        return f'Account(id={self.id}, username={self.username})'

    # Accounts are stored at event-level, this provides an event-free
    # instance that can be used when no events are available (welcome page, ...)

    @classmethod
    def anonymous_account(cls) -> Self:
        return cls(StoredAccount.anonymous_stored_account())
