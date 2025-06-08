import weakref
from _weakref import ReferenceType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data.event import Event

from database.sqlite.event.event_store import StoredClient
from roles.client import Client


class PermissionManager:
    def __init__(
        self,
        event: 'Event',
        stored_clients: list[StoredClient],
    ):
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)
        self.clients_by_id: dict[int, Client] = {
            stored_client.id: Client(self.event, stored_client=stored_client)
            for stored_client in stored_clients
        }

    @property
    def event(self) -> 'Event':
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event
