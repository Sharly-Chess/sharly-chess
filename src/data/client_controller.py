from typing import TYPE_CHECKING
import weakref
from _weakref import ReferenceType

from common.i18n import _
from common.papi_web_config import PapiWebConfig
from data.rotator import Rotator
from data.screen import Screen
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
        return self.stored_client_controller.screen_id

    @screen_id.setter
    def screen_id(self, new_id):
        self.stored_client_controller.screen_id = new_id
        self.stored_client_controller.rotator_id = None

    @property
    def rotator_id(self) -> int | None:
        return self.stored_client_controller.rotator_id

    @rotator_id.setter
    def rotator_id(self, new_id):
        self.stored_client_controller.rotator_id = new_id
        self.stored_client_controller.screen_id = None

    @property
    def assigned_object(self) -> Screen | Rotator | None:
        try:
            if self.screen_id:
                return self.event.basic_screens_by_id[self.screen_id]
            if self.rotator_id:
                return self.event.rotators_by_id[self.rotator_id]
        except KeyError:
            return None
        return None

    @property
    def assigned_type(self) -> str | None:
        object = self.assigned_object
        if object is None:
            return None
        if isinstance(object, Screen):
            return 'screen'
        if isinstance(object, Rotator):
            return 'rotator'
        raise ValueError(f'type=[{type(object)}]')

    @property
    def assigned_description(
        self,
    ) -> str | None:
        assigned_object = self.assigned_object
        if assigned_object is None:
            return None

        assert assigned_object.uniq_id is not None
        if self.assigned_type == 'screen':
            return _('Currently displaying screen: {uniq_id}').format(
                uniq_id=assigned_object.uniq_id
            )
        elif self.assigned_type == 'rotator':
            return _('Currently displaying rotator: {uniq_id}').format(
                uniq_id=assigned_object.uniq_id
            )
        else:
            return None

    @property
    def screen(self) -> Screen | None:
        try:
            if self.screen_id:
                return self.event.basic_screens_by_id[self.screen_id]
            if self.rotator_id:
                rotator: Rotator | None = self.event.rotators_by_id[self.rotator_id]
                if rotator and rotator.rotating_screens:
                    return self.event.rotators_by_id[self.rotator_id].rotating_screens[
                        0
                    ]
        except KeyError:
            return None
        return None

    @property
    def rotator(self) -> Rotator | None:
        if self.rotator_id:
            return self.event.rotators_by_id[self.rotator_id]
        return None

    @property
    def delay(self) -> int:
        if self.rotator_id:
            rotator: Rotator | None = self.event.rotators_by_id[self.rotator_id]
            if rotator:
                return rotator.delay
        return PapiWebConfig.user_screen_update_delay
