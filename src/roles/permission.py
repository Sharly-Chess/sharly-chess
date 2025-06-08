import weakref
from _weakref import ReferenceType
from typing import TYPE_CHECKING

from data.tournament import Tournament
from database.sqlite.event.event_store import StoredPermission
from roles.role import Role

if TYPE_CHECKING:
    from data.event import Event
    from roles.client import Client


class Permission:
    """A data wrapper around a stored permission.
    The class that represents a permission, i.e. a role given to client."""

    def __init__(
        self,
        client: 'Client',
        stored_permission: StoredPermission,
    ):
        self._client_ref: 'ReferenceType[Client]' = weakref.ref(client)
        self.stored_permission: StoredPermission = stored_permission

    @property
    def client(self) -> 'Client':
        client = self._client_ref()
        if client is None:
            raise RuntimeError('Client reference has been garbage collected')
        return client

    @property
    def event(self) -> 'Event':
        return self.client.event

    @property
    def locked(self) -> bool:
        """Returns True if the permission is locked (can not be updated or deleted)."""
        return self.stored_permission.locked

    @property
    def role(self) -> Role:
        """Returns the role given to the client of the permission."""
        return Role(self.stored_permission.role_id)

    @property
    def tournament(self) -> Tournament | None:
        """Returns the tournament the permission applies to (if None, applies to all the tournaments)."""
        if self.stored_permission.tournament_id is None:
            return None
        else:
            return self.event.tournaments_by_id[self.stored_permission.tournament_id]
