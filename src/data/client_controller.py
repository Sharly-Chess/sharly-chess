from typing import TYPE_CHECKING
import weakref
from _weakref import ReferenceType

from common.i18n import _
from database.sqlite.event.event_store import StoredClientController

if TYPE_CHECKING:
    from data.event import Event


class ClientController:
    """A data wrapper around a stored client controller."""

    def __init__(
        self,
        event: 'Event',
        stored_client_controller: StoredClientController,
    ):
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)
        self.stored_client_controller: StoredClientController = stored_client_controller
        self._screen_id: int | None = None
        self._family_id: int | None = None
        self._rotator_id: int | None = None

    @property
    def event(self) -> 'Event':
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event

    @property
    def id(self) -> int:
        assert self.stored_client_controller.id is not None
        return self.stored_client_controller.id

    @property
    def public(self) -> bool:
        return self.stored_client_controller.public

    @property
    def uniq_id(self) -> str:
        return self.stored_client_controller.uniq_id

    @property
    def name(self) -> str:
        name: str = (
            self.stored_client_controller.name
            if self.stored_client_controller.name
            else _('Client controller')
        )
        return name

    @property
    def screen_id(self) -> int | None:
        return self._screen_id

    @screen_id.setter
    def screen_id(self, new_id):
        self._screen_id = new_id
        self._family_id = None
        self._rotator_id = None

    @property
    def family_id(self) -> int | None:
        return self._family_id

    @family_id.setter
    def family_id(self, new_id):
        self._family_id = new_id
        self._screen_id = None
        self._rotator_id = None

    @property
    def rotator_id(self) -> int | None:
        return self._rotator_id

    @rotator_id.setter
    def rotator_id(self, new_id):
        self._rotator_id = new_id
        self._screen_id = None
        self._family_id = None
