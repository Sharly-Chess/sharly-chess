import re
from abc import ABC
from typing import Self

from database.sqlite.event.event_store import (
    StoredComputer,
    StoredUser,
    LOCALHOST_ID,
    ANY_COMPUTER_ID,
    ANY_USER_ID,
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


class Computer(AuthEntity):
    """A data wrapper around a stored computer, made of an IP specification."""

    LOCALHOST_IP: str = '127.0.0.1'
    LOCALHOST_NAME: str = 'localhost'
    ANY_IP: str = '0.0.0.0'

    def __init__(
        self,
        stored_computer: StoredComputer,
    ):
        self.stored_computer: StoredComputer = stored_computer
        super().__init__(self.stored_computer.permissions)

    @property
    def id(self) -> int:
        """Returns the computer ID."""
        assert self.stored_computer.id is not None
        return self.stored_computer.id

    @property
    def edit_properties(self) -> bool:
        """Returns True the computer is locked (can not be updated or deleted)."""
        return self.stored_computer.edit_properties

    @property
    def edit_permissions(self) -> bool:
        """Returns True the permissions of the computer can be updated."""
        return self.stored_computer.edit_permissions

    @property
    def active(self) -> bool:
        """Returns the computer is active."""
        return self.stored_computer.active

    @classmethod
    def host_is_localhost(cls, host: str) -> bool:
        """Returns True the host is the server itself."""
        return host in [
            cls.LOCALHOST_IP,
            cls.LOCALHOST_NAME,
        ]

    @property
    def is_localhost(self) -> bool:
        """Returns True the computer is the server itself."""
        return self.stored_computer.id == LOCALHOST_ID

    @property
    def is_any(self) -> bool:
        """Returns True the computer represent any client."""
        return self.stored_computer.id == ANY_COMPUTER_ID

    @property
    def ip(self) -> str:
        """Returns the host address of the computer."""
        if self.is_localhost:
            return self.LOCALHOST_IP
        if self.is_any:
            return self.ANY_IP
        assert self.stored_computer.ip is not None
        return self.stored_computer.ip

    def matches(
        self,
        host: str,
    ) -> bool:
        """Returns True if the given host matches, False otherwise."""
        if self.is_localhost:
            return self.host_is_localhost(host)
        elif self.is_any:
            return True
        else:
            assert self.stored_computer.ip is not None
            return host in (ip for ip in re.split(', ;', self.stored_computer.ip) if ip)


class User(AuthEntity):
    """A data wrapper around a stored user.
    The class that represents a user, made of credentials (username and password)."""

    def __init__(
        self,
        stored_user: StoredUser,
    ):
        self.stored_user: StoredUser = stored_user
        super().__init__(self.stored_user.permissions)

    @property
    def id(self) -> int:
        """Returns the user ID."""
        assert self.stored_user.id is not None
        return self.stored_user.id

    @property
    def edit_properties(self) -> bool:
        """Returns True the user is locked (can not be updated or deleted)."""
        return self.stored_user.edit_properties

    @property
    def edit_permissions(self) -> bool:
        """Returns True the permissions of the user can be updated."""
        return self.stored_user.edit_permissions

    @property
    def active(self) -> bool:
        """Returns the user is active."""
        return self.stored_user.active

    @property
    def is_any(self) -> bool:
        """Returns True the client represent any client."""
        return self.stored_user.id == ANY_USER_ID

    @property
    def username(self) -> str | None:
        """Returns the username of the client."""
        if self.is_any:
            return None
        return self.stored_user.username

    @property
    def password(self) -> str | None:
        """Returns the password of the client."""
        if self.is_any:
            return None
        return self.stored_user.password

    def matches(
        self,
        user: Self | None,
    ) -> bool:
        """Returns True if the given client matches, False otherwise."""
        if self.is_any:
            return True
        elif user is None:
            return False
        else:
            return self.id == user.id
