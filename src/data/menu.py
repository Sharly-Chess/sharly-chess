from operator import attrgetter
from typing import TYPE_CHECKING
import weakref
from _weakref import ReferenceType

from data.family import Family
from data.screen import Screen
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredMenu, StoredMenuItem
from utils.enum import ScreenType

if TYPE_CHECKING:
    from data.event import Event


class MenuNavEntry:
    """A single entry in a screen's navigation bar: either one screen, or a
    family shown as one item opening a submenu of its screens."""

    def __init__(self, screens: list[Screen], family: Family | None = None):
        self.screens = screens
        self.family = family

    @property
    def is_family(self) -> bool:
        return self.family is not None

    @property
    def screen(self) -> Screen:
        return self.screens[0]

    @property
    def label(self) -> str:
        if self.family is not None:
            return self.family.menu_text or self.family.name
        return self.screens[0].menu_entry_label


def group_menu_nav_entries(screens: list[Screen]) -> list['MenuNavEntry']:
    """Group screens into navigation entries, collapsing each family's
    screens (kept in first-appearance order) into a single entry."""
    entries: list[MenuNavEntry] = []
    family_entry_by_id: dict[int, MenuNavEntry] = {}
    for screen in screens:
        family = screen.family
        if family is None:
            entries.append(MenuNavEntry([screen]))
            continue
        entry = family_entry_by_id.get(family.id)
        if entry is None:
            entry = MenuNavEntry([], family)
            family_entry_by_id[family.id] = entry
            entries.append(entry)
        entry.screens.append(screen)
    # A menu that is just one family needs no submenu: show its screens
    # directly as the top-level menu.
    if len(entries) == 1 and entries[0].is_family:
        return [MenuNavEntry([screen]) for screen in entries[0].screens]
    return entries


class MenuItem:
    def __init__(
        self,
        event: 'Event',
        stored_menu_item: StoredMenuItem,
    ):
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)
        self.stored_menu_item = stored_menu_item

    @property
    def event(self) -> 'Event':
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event

    @property
    def id(self) -> int:
        assert self.stored_menu_item.id is not None
        return self.stored_menu_item.id

    @property
    def menu(self) -> 'Menu':
        return self.event.menus_by_id[self.stored_menu_item.menu_id]

    @property
    def screen(self) -> Screen | None:
        if screen_id := self.stored_menu_item.screen_id:
            return self.event.basic_screens_by_id[screen_id]
        return None

    @property
    def family(self) -> Family | None:
        if family_id := self.stored_menu_item.family_id:
            return self.event.families_by_id[family_id]
        return None

    @property
    def screen_type(self) -> ScreenType | None:
        if self.stored_menu_item.screen_type:
            return ScreenType(self.stored_menu_item.screen_type)
        return None

    @property
    def index(self) -> int:
        return self.stored_menu_item.index

    @property
    def screens(self) -> list[Screen]:
        """The screens this item resolves to: a single screen, a family's
        screens, or every event screen of the item's screen type."""
        if screen := self.screen:
            return [screen]
        if family := self.family:
            return list(family.screens_by_uniq_id.values())
        if screen_type := self.screen_type:
            return self.event.sorted_screens_by_screen_type[screen_type]
        return []


class Menu:
    """A data wrapper around a stored menu."""

    def __init__(
        self,
        event: 'Event',
        stored_menu: StoredMenu,
    ):
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)
        self.stored_menu = stored_menu
        self.menu_items_by_id = self._get_menu_items_by_id()

    @property
    def event(self) -> 'Event':
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event

    @property
    def id(self) -> int:
        assert self.stored_menu.id is not None
        return self.stored_menu.id

    @property
    def default_type(self) -> ScreenType | None:
        if self.stored_menu.default_type:
            return ScreenType(self.stored_menu.default_type)
        return None

    @property
    def name(self) -> str:
        """The stored name, or — for a seeded default menu with no stored
        name — the translatable label of its screen type."""
        if self.stored_menu.name:
            return self.stored_menu.name
        if default_type := self.default_type:
            return default_type.name
        return ''

    @property
    def stored_menu_items(self) -> list[StoredMenuItem]:
        return self.stored_menu.stored_menu_items

    @property
    def sorted_menu_items(self) -> list[MenuItem]:
        return sorted(self.menu_items_by_id.values(), key=attrgetter('index'))

    @property
    def screens(self) -> list[Screen]:
        return [item.screen for item in self.sorted_menu_items if item.screen]

    @property
    def families(self) -> list[Family]:
        return [item.family for item in self.sorted_menu_items if item.family]

    @property
    def screen_types(self) -> list[ScreenType]:
        return [item.screen_type for item in self.sorted_menu_items if item.screen_type]

    @property
    def first_screen(self) -> Screen | None:
        """The first screen the menu points to, used to open the menu."""
        screens = self.resolved_screens()
        return screens[0] if screens else None

    def resolved_screens(self) -> list[Screen]:
        """Every screen this menu points to, in item order, de-duplicated:
        individual screens, each family's screens and every screen of any
        included screen type."""
        screens: list[Screen] = []
        seen: set[str] = set()
        for item in self.sorted_menu_items:
            for screen in item.screens:
                if screen.uniq_id not in seen:
                    seen.add(screen.uniq_id)
                    screens.append(screen)
        return screens

    def _get_menu_items_by_id(self) -> dict[int, MenuItem]:
        menu_items_by_id = {}
        for stored_menu_item in self.stored_menu.stored_menu_items:
            assert stored_menu_item.id is not None
            menu_items_by_id[stored_menu_item.id] = MenuItem(
                self.event, stored_menu_item
            )
        return menu_items_by_id

    def delete_menu_item(self, menu_item_id: int):
        if menu_item_id not in self.menu_items_by_id:
            raise ValueError(
                f'Menu item [{menu_item_id}] not part of menu [{self.id}].'
            )
        with EventDatabase(self.event.uniq_id, True) as database:
            database.delete_stored_menu_item(menu_item_id)
            del self.menu_items_by_id[menu_item_id]
            ordered_ids = [item.id for item in self.sorted_menu_items]
            self._set_menu_item_indexes(database, ordered_ids)

    def reorder_menu_items(self, ordered_ids: list[int]):
        if len(ordered_ids) != len(self.menu_items_by_id):
            raise ValueError(f'{ordered_ids=}')
        for menu_item in self.menu_items_by_id.values():
            if menu_item.id not in ordered_ids:
                raise ValueError(f'Menu item {menu_item.id} missing for menu {self.id}')
        with EventDatabase(self.event.uniq_id, True) as database:
            self._set_menu_item_indexes(database, ordered_ids)

    def _set_menu_item_indexes(self, database: EventDatabase, ordered_ids: list[int]):
        for index, menu_item_id in enumerate(ordered_ids):
            stored_menu_item = self.menu_items_by_id[menu_item_id].stored_menu_item
            stored_menu_item.index = index
            database.update_stored_menu_item(stored_menu_item)

    def add_menu_item(
        self,
        screen_id: int | None = None,
        family_id: int | None = None,
        screen_type: ScreenType | None = None,
    ):
        stored_menu_item = StoredMenuItem(
            id=None,
            menu_id=self.id,
            screen_id=screen_id,
            family_id=family_id,
            screen_type=screen_type.value if screen_type else None,
            index=len(self.stored_menu_items),
        )
        with EventDatabase(self.event.uniq_id, True) as database:
            new_id = database.add_stored_menu_item(stored_menu_item)
            stored_menu_item.id = new_id
            self.menu_items_by_id[new_id] = MenuItem(self.event, stored_menu_item)
