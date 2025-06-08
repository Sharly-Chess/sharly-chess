import weakref
from _weakref import ReferenceType
from typing import TYPE_CHECKING

from common.i18n import _
from database.sqlite.event.event_store import (
    StoredClient,
    CLIENT_LOCALHOST_ID,
    CLIENT_ANY_ID,
)
from roles.permission import Permission

if TYPE_CHECKING:
    from data.event import Event


class Client:
    """A data wrapper around a stored client.
    The class that represents a client, made of
    credentials (name and password) and origin (IP address)."""

    def __init__(
        self,
        event: 'Event',
        stored_client: StoredClient,
    ):
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)
        self.stored_client: StoredClient = stored_client
        self._permissions_by_id: dict[int, Permission] = {
            stored_permission.id: Permission(self, stored_permission=stored_permission)
            for stored_permission in self.stored_client.stored_permissions
        }

    @property
    def event(self) -> 'Event':
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event

    @property
    def is_localhost(self) -> bool:
        """Returns True the client is the server itself."""
        return self.stored_client.id == CLIENT_LOCALHOST_ID

    @property
    def is_any(self) -> bool:
        """Returns True the client represent any client."""
        return self.stored_client.id == CLIENT_ANY_ID

    @property
    def locked(self) -> bool:
        """Returns True the client is locked (can not be updated or deleted)."""
        return self.is_localhost or self.is_any

    @property
    def name(self) -> str:
        """Returns the name of the client."""
        if self.is_localhost:
            return _('The server')
        if self.is_any:
            return _('Any anonymous client')
        return self.stored_client.name or ''

    @property
    def username(self) -> str | None:
        """Returns the username of the client."""
        if self.is_localhost:
            return None
        if self.is_any:
            return None
        return self.stored_client.username

    @property
    def password(self) -> str | None:
        """Returns the password of the client."""
        if self.is_localhost:
            return None
        if self.is_any:
            return None
        return self.stored_client.password

    @property
    def ip(self) -> str | None:
        """Returns the IP address of the client."""
        if self.is_localhost:
            return '127.0.0.1'
        if self.is_any:
            return '0.0.0.0'
        return self.stored_client.ip

    @property
    def order(self) -> int:
        """Returns the order of the client."""
        return self.stored_client.order
