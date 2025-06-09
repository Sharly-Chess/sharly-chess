import re
import weakref
from _weakref import ReferenceType
from abc import ABC
from typing import TYPE_CHECKING, Self

from database.sqlite.event.event_store import (
    StoredComputer,
    StoredUser,
    LOCALHOST_ID,
    ANY_COMPUTER_ID,
    ANY_USER_ID,
)
from data.auth.permissions import ComputerPermission, UserPermission

if TYPE_CHECKING:
    from data.event import Event


class Entity(ABC):
    """An abstract entity."""

    def __init__(
        self,
        event: 'Event',
    ):
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)

    @property
    def event(self) -> 'Event':
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event


class Computer(Entity):
    """A data wrapper around a stored computer, made of an IP specification."""

    LOCALHOST_IP: str = '127.0.0.1'
    LOCALHOST_NAME: str = 'localhost'
    ANY_IP: str = '0.0.0.0'

    def __init__(
        self,
        event: 'Event',
        stored_computer: StoredComputer,
    ):
        super().__init__(event)
        self.stored_computer: StoredComputer = stored_computer
        self.permissions_by_id: dict[int, ComputerPermission] = {
            stored_computer_permission.id: ComputerPermission(
                self,
                stored_computer_permission=stored_computer_permission,
            )
            for stored_computer_permission in self.stored_computer.stored_permissions
            if stored_computer_permission.id
        }

    @property
    def id(self) -> int:
        """Returns the computer ID."""
        assert self.stored_computer.id is not None
        return self.stored_computer.id

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
    def locked(self) -> bool:
        """Returns True the computer is locked (can not be updated or deleted)."""
        return self.stored_computer.locked

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
            return host in (ip for ip in re.split(', ;', self.stored_computer.ip) if ip)


class User(Entity):
    """A data wrapper around a stored user.
    The class that represents a user, made of credentials (username and password)."""

    def __init__(
        self,
        event: 'Event',
        stored_user: StoredUser,
    ):
        super().__init__(event)
        self.stored_user: StoredUser = stored_user
        self.permissions_by_id: dict[int, UserPermission] = {
            stored_user_permission.id: UserPermission(
                self, stored_user_permission=stored_user_permission
            )
            for stored_user_permission in self.stored_user.stored_user_permissions
            if stored_user_permission.id
        }

    @property
    def id(self) -> int:
        """Returns the user ID."""
        assert self.stored_user.id is not None
        return self.stored_user.id

    @property
    def is_any(self) -> bool:
        """Returns True the client represent any client."""
        return self.stored_user.id == ANY_USER_ID

    @property
    def locked(self) -> bool:
        """Returns True the client is locked (can not be updated or deleted)."""
        return self.is_any

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
