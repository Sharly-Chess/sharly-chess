from typing import TYPE_CHECKING
import weakref
from _weakref import ReferenceType

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.screens.family import Family
from data.screens.menu import Menu
from data.screens.rotator import Rotator
from data.screens.screen import Screen
from database.sqlite.event.event_store import StoredDisplayController

if TYPE_CHECKING:
    from data.event import Event


class DisplayController:
    """A data wrapper around a stored display controller."""

    def __init__(
        self,
        event: Event,
        stored_display_controller: StoredDisplayController,
    ):
        self._event_ref: ReferenceType[Event] = weakref.ref(event)
        self.stored_display_controller: StoredDisplayController = (
            stored_display_controller
        )

    @property
    def event(self) -> Event:
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event

    @property
    def id(self) -> int:
        assert self.stored_display_controller.id is not None
        return self.stored_display_controller.id

    @property
    def public(self) -> bool:
        return self.stored_display_controller.public

    @property
    def name(self) -> str:
        return self.stored_display_controller.name

    @property
    def screen_id(self) -> int | None:
        return self.stored_display_controller.screen_id

    @screen_id.setter
    def screen_id(self, new_id: int | None) -> None:
        self._show(screen_id=new_id)

    @property
    def rotator_id(self) -> int | None:
        return self.stored_display_controller.rotator_id

    @rotator_id.setter
    def rotator_id(self, new_id: int | None) -> None:
        self._show(rotator_id=new_id)

    @property
    def family_id(self) -> int | None:
        return self.stored_display_controller.family_id

    @family_id.setter
    def family_id(self, new_id: int | None) -> None:
        self._show(family_id=new_id)

    @property
    def family_page(self) -> int | None:
        """The page of the multi-screen the controller is held on, counted from
        1; None when it goes through all the pages in turn."""
        return self.stored_display_controller.family_page

    def show_family_page(self, family_id: int, page: int) -> None:
        self._show(family_id=family_id, family_page=page)

    def shows_family_page(self, family: Family, page: int) -> bool:
        return self.family_id == family.id and self.family_page == page

    @property
    def menu_id(self) -> int | None:
        return self.stored_display_controller.menu_id

    @menu_id.setter
    def menu_id(self, new_id: int | None) -> None:
        self._show(menu_id=new_id)

    def _show(
        self,
        screen_id: int | None = None,
        rotator_id: int | None = None,
        family_id: int | None = None,
        family_page: int | None = None,
        menu_id: int | None = None,
    ) -> None:
        self.stored_display_controller.screen_id = screen_id
        self.stored_display_controller.rotator_id = rotator_id
        self.stored_display_controller.family_id = family_id
        self.stored_display_controller.family_page = family_page
        self.stored_display_controller.menu_id = menu_id

    @property
    def item_screens(self) -> list[Screen]:
        """The single screens set up for this controller."""
        screen_ids = self.stored_display_controller.item_screen_ids
        return [
            screen
            for screen in self.event.sorted_basic_screens
            if screen.id in screen_ids
        ]

    @property
    def item_families(self) -> list[Family]:
        """The multi-screens set up for this controller."""
        family_ids = self.stored_display_controller.item_family_ids
        return [family for family in self._families if family.id in family_ids]

    @property
    def other_families(self) -> list[Family]:
        """The multi-screens not set up for this controller."""
        family_ids = self.stored_display_controller.item_family_ids
        return [family for family in self._families if family.id not in family_ids]

    @property
    def _families(self) -> list[Family]:
        return sorted(
            self.event.families_by_id.values(),
            key=lambda family: family.display_name,
        )

    @property
    def item_rotators(self) -> list[Rotator]:
        """The rotators set up for this controller."""
        rotator_ids = self.stored_display_controller.item_rotator_ids
        return [
            rotator
            for rotator in self.event.sorted_rotators
            if rotator.id in rotator_ids
        ]

    @property
    def other_rotators(self) -> list[Rotator]:
        """The rotators not set up for this controller."""
        rotator_ids = self.stored_display_controller.item_rotator_ids
        return [
            rotator
            for rotator in self.event.sorted_rotators
            if rotator.id not in rotator_ids
        ]

    @property
    def item_menus(self) -> list[Menu]:
        """The menus set up for this controller."""
        menu_ids = self.stored_display_controller.item_menu_ids
        return [menu for menu in self.event.sorted_menus if menu.id in menu_ids]

    @property
    def other_menus(self) -> list[Menu]:
        """The menus not set up for this controller."""
        menu_ids = self.stored_display_controller.item_menu_ids
        return [menu for menu in self.event.sorted_menus if menu.id not in menu_ids]

    @property
    def other_screens(self) -> list[Screen]:
        """The single screens not set up for this controller, by screen type."""
        screen_ids = self.stored_display_controller.item_screen_ids
        return sorted(
            (
                screen
                for screen in self.event.sorted_basic_screens
                if screen.id not in screen_ids
            ),
            key=lambda screen: screen.type,
        )

    @property
    def assigned_object(self) -> Screen | Rotator | Family | Menu | None:
        if self.screen_id:
            return self.event.basic_screens_by_id.get(self.screen_id)
        if self.rotator_id:
            return self.event.rotators_by_id.get(self.rotator_id)
        if self.family_id:
            return self.event.families_by_id.get(self.family_id)
        if self.menu_id:
            return self.event.menus_by_id.get(self.menu_id)
        return None

    @property
    def assigned_type(self) -> str | None:
        obj = self.assigned_object
        if obj is None:
            return None
        if isinstance(obj, Screen):
            return 'screen'
        if isinstance(obj, Rotator):
            return 'rotator'
        if isinstance(obj, Family):
            return 'family'
        if isinstance(obj, Menu):
            return 'menu'
        raise ValueError(f'type=[{type(obj)}]')

    @property
    def assignment_key(self) -> str:
        """Identifies what the controller is showing, so that a device can tell
        when something else has been sent."""
        obj = self.assigned_object
        if obj is None:
            return ''
        if self.family and self.family_page:
            return f'family:{obj.id}:{self.family_page}'
        return f'{self.assigned_type}:{obj.id}'

    @property
    def assigned_name(self) -> str | None:
        obj = self.assigned_object
        if isinstance(obj, Family):
            if self.family_page:
                return _('{name}, page {page}').format(
                    name=obj.display_name, page=self.family_page
                )
            return obj.display_name
        return obj.name if obj else None

    @property
    def screens(self) -> list[Screen]:
        """The screens shown by this controller, in the order they are shown."""
        obj = self.assigned_object
        if isinstance(obj, Screen):
            return [obj]
        if isinstance(obj, Rotator):
            return obj.rotating_screens
        if isinstance(obj, Family):
            pages = list(obj.screens_by_uniq_id.values())
            if self.family_page:
                return pages[self.family_page - 1 : self.family_page]
            return pages
        if isinstance(obj, Menu):
            return obj.resolved_screens()
        return []

    def screens_for(self, include_private: bool) -> list[Screen]:
        """The screens a viewer can reach: a menu only offers a viewer the
        screens they may see."""
        if menu := self.menu:
            return menu.screens_for(include_private)
        return self.screens

    @property
    def cycles(self) -> bool:
        """Whether the controller moves on to its next screen by itself."""
        if self.rotator:
            return True
        return bool(self.family) and len(self.screens) > 1

    @property
    def screen(self) -> Screen | None:
        screens = self.screens
        return screens[0] if screens else None

    @property
    def rotator(self) -> Rotator | None:
        obj = self.assigned_object
        return obj if isinstance(obj, Rotator) else None

    @property
    def family(self) -> Family | None:
        obj = self.assigned_object
        return obj if isinstance(obj, Family) else None

    @property
    def menu(self) -> Menu | None:
        obj = self.assigned_object
        return obj if isinstance(obj, Menu) else None

    @property
    def delay(self) -> int:
        if rotator := self.rotator:
            return rotator.delay
        if (family := self.family) and not self.family_page:
            return family.page_delay or SharlyChessConfig.default_rotator_delay
        return SharlyChessConfig.user_screen_update_delay

    def delay_for(self, screen: Screen) -> int:
        """How long *screen*, shown now, stays before the next one."""
        if rotator := self.rotator:
            return rotator.delay_for(screen)
        return self.delay
