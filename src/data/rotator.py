from operator import attrgetter
from typing import TYPE_CHECKING, Optional
import weakref
from _weakref import ReferenceType

from common.sharly_chess_config import SharlyChessConfig
from data.family import Family
from data.screen import Screen
from data.timer import Timer
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
    def id(self) -> int:
        assert self.stored_rotating_screen.id is not None
        return self.stored_rotating_screen.id

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
        self.rotating_screens_by_id = self._get_rotating_screens_by_id()

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
    def timer_id(self) -> int | None:
        return self.stored_rotator.timer_id

    @property
    def timer(self) -> Optional['Timer']:
        return self.event.timers_by_id[self.timer_id] if self.timer_id else None

    @property
    def stored_rotating_screens(self) -> list[StoredRotatingScreen]:
        return self.stored_rotator.stored_rotating_screens

    @property
    def screens(self) -> list[Screen]:
        return [
            rotating_screen.screen
            for rotating_screen in self.sorted_rotating_screens
            if rotating_screen.screen
        ]

    @property
    def families(self) -> list[Family]:
        return [
            rotating_screen.family
            for rotating_screen in self.sorted_rotating_screens
            if rotating_screen.family
        ]

    @property
    def sorted_rotating_screens(self) -> list[RotatingScreen]:
        return sorted(self.rotating_screens_by_id.values(), key=attrgetter('index'))

    @property
    def rotating_screens(self) -> list[Screen]:
        rotating_screens: list[Screen] = []
        for rotating_screen in self.sorted_rotating_screens:
            if rotating_screen.screen:
                rotating_screens.append(rotating_screen.screen)
            elif rotating_screen.family:
                for screen in rotating_screen.family.screens_by_uniq_id.values():
                    rotating_screens.append(screen)
        return rotating_screens

    def _get_rotating_screens_by_id(self) -> dict[int, RotatingScreen]:
        rotating_screens_by_id = {}
        for stored_rotating_screen in self.stored_rotator.stored_rotating_screens:
            assert stored_rotating_screen.id is not None
            rotating_screens_by_id[stored_rotating_screen.id] = RotatingScreen(
                self.event, stored_rotating_screen
            )
        return rotating_screens_by_id

    def delete_rotating_screen(self, rotating_screen_id: int):
        if rotating_screen_id not in self.rotating_screens_by_id:
            raise ValueError(
                f'Rotating screen [{rotating_screen_id}] '
                f'not part of rotator [{self.id}].'
            )
        with EventDatabase(self.event.uniq_id, True) as database:
            database.delete_stored_rotating_screen(rotating_screen_id)
            del self.rotating_screens_by_id[rotating_screen_id]
            ordered_ids = [
                rotating_screen.id for rotating_screen in self.sorted_rotating_screens
            ]
            self._set_rotating_screens_indexes(database, ordered_ids)

    def reorder_rotating_screens(self, ordered_ids: list[int]):
        if len(ordered_ids) != len(self.rotating_screens_by_id):
            raise ValueError(f'{ordered_ids=}')
        for rotating_screen in self.rotating_screens_by_id.values():
            if rotating_screen.id not in ordered_ids:
                raise ValueError(
                    f'Rotating screen {rotating_screen.id} missing for rotator {self.id}'
                )
        with EventDatabase(self.event.uniq_id, True) as database:
            self._set_rotating_screens_indexes(database, ordered_ids)

    def _set_rotating_screens_indexes(
        self, database: EventDatabase, ordered_ids: list[int]
    ):
        for index, rotating_screen_id in enumerate(ordered_ids):
            stored_rotating_screen = self.rotating_screens_by_id[
                rotating_screen_id
            ].stored_rotating_screen
            stored_rotating_screen.index = index
            database.update_stored_rotating_screen(stored_rotating_screen)

    def add_rotating_screen(self, object_id: int, is_family: bool):
        stored_rotating_screen = StoredRotatingScreen(
            id=None,
            rotator_id=self.id,
            screen_id=object_id if not is_family else None,
            family_id=object_id if is_family else None,
            index=len(self.stored_rotating_screens),
        )
        with EventDatabase(self.event.uniq_id, True) as database:
            new_id = database.add_stored_rotating_screen(stored_rotating_screen)
            stored_rotating_screen.id = new_id
            self.rotating_screens_by_id[new_id] = RotatingScreen(
                self.event, stored_rotating_screen
            )
