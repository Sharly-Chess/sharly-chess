import weakref
from _weakref import ReferenceType
from abc import abstractmethod
from fnmatch import fnmatch
from typing import TYPE_CHECKING

from data.tournament import Tournament
from database.sqlite.event.event_store import (
    StoredComputerPermission,
    StoredUserPermission,
)
from data.auth.roles import Role

if TYPE_CHECKING:
    from data.event import Event
    from data.auth.entities import Computer, User


class Permission:
    """An abstract permission."""

    @property
    @abstractmethod
    def event(self) -> 'Event':
        """Return the event of the permission."""

    @property
    @abstractmethod
    def active(self) -> bool:
        """Returns True if the permission is active, False otherwise."""

    @property
    @abstractmethod
    def role(self) -> Role:
        """Returns the role of the permission."""

    @property
    @abstractmethod
    def tournament_uniq_ids(self) -> str | None:
        """Returns the tournament unique IDs the permission applies to (if None, applies to all the tournaments)."""

    def tournament_matches(self, tournament: Tournament) -> bool:
        """Returns True if the given tournament matches the permission."""
        if self.tournament_uniq_ids is None:
            return True
        for tournament_pattern in self.tournament_uniq_ids.split(','):
            if '*' in tournament_pattern:
                if fnmatch(tournament.uniq_id, tournament_pattern):
                    return True
            elif tournament.uniq_id == tournament_pattern:
                return True
        return False


class ComputerPermission(Permission):
    """A data wrapper around a stored computer permission.
    The class that represents a computer permission,
    i.e. a role given to a computer (identified by its IP address)."""

    def __init__(
        self,
        computer: 'Computer',
        stored_computer_permission: StoredComputerPermission,
    ):
        self._computer_ref: 'ReferenceType[Computer]' = weakref.ref(computer)
        self.stored_computer_permission: StoredComputerPermission = (
            stored_computer_permission
        )

    @property
    def computer(self) -> 'Computer':
        computer = self._computer_ref()
        if computer is None:
            raise RuntimeError('Computer reference has been garbage collected')
        return computer

    @property
    def event(self) -> 'Event':
        return self.computer.event

    @property
    def active(self) -> bool:
        """Returns True if the permission is active, False otherwise."""
        return self.stored_computer_permission.active

    @property
    def role(self) -> Role:
        """Returns the role given to the computer of the permission."""
        return Role(self.stored_computer_permission.role_id)

    @property
    def tournament_uniq_ids(self) -> str | None:
        """Returns the tournament unique IDs the permission applies to (if None, applies to all the tournaments)."""
        return self.stored_computer_permission.tournament_uniq_ids


class UserPermission(Permission):
    """A data wrapper around a stored user permission.
    The class that represents a user permission, i.e. a role given to a user."""

    def __init__(
        self,
        user: 'User',
        stored_user_permission: StoredUserPermission,
    ):
        self._user_ref: 'ReferenceType[User]' = weakref.ref(user)
        self.stored_user_permission: StoredUserPermission = stored_user_permission

    @property
    def user(self) -> 'User':
        user = self._user_ref()
        if user is None:
            raise RuntimeError('User reference has been garbage collected')
        return user

    @property
    def event(self) -> 'Event':
        return self.user.event

    @property
    def active(self) -> bool:
        """Returns True if the permission is active, False otherwise."""
        return self.stored_user_permission.active

    @property
    def role(self) -> Role:
        """Returns the role given to the user of the permission."""
        return Role(self.stored_user_permission.role_id)
