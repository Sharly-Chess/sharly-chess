from typing import TYPE_CHECKING
import weakref
from _weakref import ReferenceType

from common.sharly_chess_config import SharlyChessConfig
from data.family import Family
from data.screen import Screen
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredRotator, StoredRotatingScreen

if TYPE_CHECKING:
    from data.event import Event


ROTATOR_DEFAULT_DELAY: int = 15


class RotatingScreen:
    def __init__(
        self,
        event: 'Event',
        stored_rotating_screen: StoredRotatingScreen,
    ):
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)
        self.stored_rotating_screen = stored_rotating_screen

    @property
    def event(self) -> 'Event':
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event

    @property
    def rotator(self) -> 'Rotator':
        return self.event.rotators_by_id[self.stored_rotating_screen.rotator_id]

    @property
    def screen(self) -> Screen | None:
        if screen_id := self.stored_rotating_screen.screen_id:
            return self.event.basic_screens_by_id[screen_id]
        return None

    @property
    def family(self) -> Family | None:
        if family_id := self.stored_rotating_screen.family_id:
            return self.event.families_by_id[family_id]
        return None

    @property
    def index(self) -> int:
        return self.stored_rotating_screen.index

    @property
    def form_id(self) -> str:
        if self.screen:
            return f'screen:{self.screen.id}'
        if self.family:
            return f'family:{self.family.id}'
        raise ValueError('Screen or family supposed to be set')


class Rotator:
    """A data wrapper around a stored rotator."""

    def __init__(
        self,
        event: 'Event',
        stored_rotator: StoredRotator,
    ):
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)
        self.stored_rotator = stored_rotator
        self.rotating_screen_objects = [
            RotatingScreen(event, stored_rotating_screen)
            for stored_rotating_screen in self.stored_rotating_screens
        ]

    @property
    def event(self) -> 'Event':
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event

    @property
    def id(self) -> int:
        assert self.stored_rotator.id is not None
        return self.stored_rotator.id

    @property
    def public(self) -> bool:
        return self.stored_rotator.public

    @property
    def uniq_id(self) -> str:
        # TODO (Molrn) replace all the uniq_id usages by the name
        return self.name

    @property
    def name(self) -> str:
        return self.stored_rotator.name

    @property
    def delay(self) -> int:
        return (
            self.stored_rotator.delay
            if self.stored_rotator.delay is not None
            else SharlyChessConfig.default_rotator_delay
        )

    @property
    def message_default(self) -> bool:
        return self.stored_rotator.message_default

    @property
    def message_text(self) -> str | None:
        return (
            self.event.message_text
            if self.message_default
            else self.stored_rotator.message_text
        )

    @property
    def stored_rotating_screens(self) -> list[StoredRotatingScreen]:
        return self.stored_rotator.stored_rotating_screens

    @property
    def screens(self) -> list[Screen]:
        return [
            rotating_screen.screen
            for rotating_screen in self.rotating_screen_objects
            if rotating_screen.screen
        ]

    @property
    def families(self) -> list[Family]:
        return [
            rotating_screen.family
            for rotating_screen in self.rotating_screen_objects
            if rotating_screen.family
        ]

    @property
    def rotating_screens(self) -> list[Screen]:
        rotating_screens: list[Screen] = []
        for rotating_screen in self.rotating_screen_objects:
            if rotating_screen.screen:
                rotating_screens.append(rotating_screen.screen)
            elif rotating_screen.family:
                for screen in rotating_screen.family.screens_by_uniq_id.values():
                    rotating_screens.append(screen)
        return rotating_screens

    def delete_rotating_screen(self, index: int):
        if not 0 <= index < len(self.rotating_screen_objects):
            raise ValueError(f'Invalid index for rotator [{self.id}].')
        self.rotating_screen_objects.pop(index)
        with EventDatabase(self.event.uniq_id, True) as database:
            database.delete_stored_rotating_screen(self.id, index)
            self._set_rotating_screens_indexes(database)

    def reorder_rotating_screens(self, ordered_form_ids: list[str]):
        if len(ordered_form_ids) != len(self.rotating_screen_objects):
            raise ValueError(f'{ordered_form_ids=}')
        if len(ordered_form_ids) != len(set(ordered_form_ids)):
            raise ValueError(f'Duplicate in {ordered_form_ids=}')
        rotating_screens: list[RotatingScreen] = []
        for form_id in ordered_form_ids:
            rotating_screen = next(
                (
                    rotating_screen
                    for rotating_screen in self.rotating_screen_objects
                    if rotating_screen.form_id == form_id
                ),
                None,
            )
            if not rotating_screen:
                raise ValueError(f'Unknown {form_id=} for rotator {self.id}')
            rotating_screens.append(rotating_screen)
        self.rotating_screen_objects = rotating_screens
        with EventDatabase(self.event.uniq_id, True) as database:
            self._set_rotating_screens_indexes(database)

    def _set_rotating_screens_indexes(self, database: EventDatabase):
        for index, rotating_screen in enumerate(self.rotating_screen_objects):
            rotating_screen.stored_rotating_screen.index = index
            database.update_stored_rotating_screen(
                rotating_screen.stored_rotating_screen
            )

    def add_rotating_screens(self, screen_ids: list[int], family_ids: list[int]):
        stored_rotating_screens: list[StoredRotatingScreen] = []
        for screen_id in screen_ids:
            if screen_id not in self.event.basic_screens_by_id:
                raise ValueError(f'Unknown screen ID [{screen_id}]')
            stored_rotating_screens.append(
                StoredRotatingScreen(self.id, screen_id=screen_id)
            )
        for family_id in family_ids:
            if family_id not in self.event.families_by_id:
                raise ValueError(f'Unknown family ID [{family_id}]')
            stored_rotating_screens.append(
                StoredRotatingScreen(self.id, family_id=family_id)
            )
        with EventDatabase(self.event.uniq_id, True) as database:
            for stored_rotating_screen in stored_rotating_screens:
                stored_rotating_screen.index = len(self.rotating_screen_objects)
                database.add_stored_rotating_screen(stored_rotating_screen)
                self.rotating_screen_objects.append(
                    RotatingScreen(self.event, stored_rotating_screen)
                )
