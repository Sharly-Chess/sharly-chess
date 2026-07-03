from operator import attrgetter
from typing import TYPE_CHECKING
import weakref
from _weakref import ReferenceType

from common.i18n import _
from data.family import Family
from data.screen import Screen
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredMenu, StoredMenuItem
from utils.enum import ScreenType

if TYPE_CHECKING:
    from data.event import Event


class MenuNavEntry:
    """A single entry in a screen's navigation bar: one screen."""

    def __init__(self, screen: Screen):
        self.screen = screen

    @property
    def label(self) -> str:
        return self.screen.menu_entry_label


def group_menu_nav_entries(screens: list[Screen]) -> list['MenuNavEntry']:
    """Build the navigation entries: one entry per screen. A family's screens
    are expanded inline as top-level entries rather than collapsed into a
    submenu."""
    return [MenuNavEntry(screen) for screen in screens]


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
            # All screens of this type (basic and family-generated), ordered by
            # uniq_id. Sorting by name is avoided on purpose: Screen.name for a
            # ranking screen needs precomputed player ranks, which the menu
            # resolution must not depend on.
            return sorted(
                (
                    screen
                    for screen in self.event.screens_by_uniq_id.values()
                    if screen.type == screen_type
                ),
                key=lambda screen: screen.uniq_id,
            )
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
        """The stored name, or — when none is set — an automatic name: the
        seeded default's screen type label, otherwise the distinct screen
        types the menu covers, joined by ' / '."""
        if self.stored_menu.name:
            return self.stored_menu.name
        if default_type := self.default_type:
            return default_type.name
        screen_types: list[ScreenType] = []
        for screen in self.resolved_screens():
            if screen.type not in screen_types:
                screen_types.append(screen.type)
        if screen_types:
            return ' / '.join(screen_type.name for screen_type in screen_types)
        return _('Menu')

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
    def covered_basic_screens(self) -> list[Screen]:
        """All basic screens the menu claims: those added individually plus
        every basic screen of an included screen type."""
        screens: dict[str, Screen] = {screen.uniq_id: screen for screen in self.screens}
        for screen_type in self.screen_types:
            for screen in self.event.sorted_basic_screens_by_screen_type[screen_type]:
                screens[screen.uniq_id] = screen
        return list(screens.values())

    @property
    def covered_families(self) -> list[Family]:
        """All families the menu claims: those added individually plus every
        family of an included screen type."""
        families: dict[int, Family] = {family.id: family for family in self.families}
        for screen_type in self.screen_types:
            for family in self.event.families_by_screen_type.get(screen_type, []):
                families[family.id] = family
        return list(families.values())

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
