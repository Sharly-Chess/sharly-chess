import builtins
import weakref
from collections.abc import Collection
from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING
from _weakref import ReferenceType

from common.background import inline_image_url
from common.i18n import _
from common.logger import get_logger
from data.screens.screen_set import ScreenSet, format_range
from data.screens.timer import Timer
from plugins.manager import plugin_manager
from plugins.utils import PluginData

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredScreen

if TYPE_CHECKING:
    from data.event import Event
    from data.screens.display_controller import DisplayController
    from data.screens.family import Family
    from data.screens.screen_types import ScreenType


logger = get_logger()


class Screen:
    """A data wrapper around a stored screen."""

    def __init__(
        self,
        event: Event,
        stored_screen: StoredScreen | None = None,
        family: Family | None = None,
        family_part: int | None = None,
    ):
        if stored_screen is None:
            assert family is not None and family_part is not None, (
                f'screen={stored_screen}, family={family}, family_part={family_part}'
            )
        else:
            assert family is None and family_part is None, (
                f'screen={stored_screen}, family={family}, family_part={family_part}'
            )
        self._event_ref: ReferenceType[Event] = weakref.ref(event)
        self.stored_screen: StoredScreen | None = stored_screen
        self._family_ref: ReferenceType[Family] | None = (
            weakref.ref(family) if family else None
        )
        self.family_part: int | None = family_part

    @property
    def event(self) -> Event:
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event

    @property
    def family(self) -> Family | None:
        return self._family_ref() if self._family_ref else None

    @cached_property
    def screen_sets_by_id(self) -> dict[int | None, ScreenSet]:
        if not self.screen_type.has_screen_sets:
            return {}
        if self.stored_screen:
            return {
                stored_screen_set.id: ScreenSet(
                    self, stored_screen_set=stored_screen_set
                )
                for stored_screen_set in self.stored_screen.stored_screen_sets
            }
        return {
            self.id: ScreenSet(self, family=self.family, family_part=self.family_part)
        }

    @property
    def screen_sets(self) -> Collection[ScreenSet]:
        return self.screen_sets_by_id.values()

    @property
    def id(self) -> int:
        return (
            self.stored_screen.id
            if self.stored_screen and self.stored_screen.id
            else -1
        )

    @property
    def family_id(self) -> int | None:
        return self.family.id if self.family else None

    @property
    def type(self) -> str:
        """The screen's type id (a built-in id or a plugin-defined one). Use
        ``screen_type`` for behaviour/metadata; this is the raw id stored on
        the screen (or family)."""
        if self.stored_screen:
            return self.stored_screen.type
        if self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        return self.family.type

    @property
    def screen_type(self) -> ScreenType:
        """The screen-type entity for this screen, resolved through the
        manager (so a plugin-defined type is honoured)."""
        from data.screens.manager import ScreenTypeManager

        return ScreenTypeManager(self.event).get_object(self.type)

    @property
    def public(self) -> bool:
        if self.stored_screen:
            return self.stored_screen.public
        if self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        return self.family.public

    @property
    def uniq_id(self) -> str:
        if self.stored_screen:
            return self.stored_screen.uniq_id
        if self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        return f'{self.family.uniq_id}:{self.family_part:03}'

    @property
    def is_paged(self) -> bool:
        return False

    @property
    def collection_item_id(self) -> str:
        return str(self.id)

    @property
    def name(self) -> str:
        """The stored name or, when none is set, the automatic one."""
        if self.stored_screen and self.stored_screen.name:
            return self.stored_screen.name
        return self.screen_type.default_screen_name(self)

    @property
    def display_controllers(self) -> list[DisplayController]:
        """The display controllers this screen is set up for."""
        if self.stored_screen is None:
            return []
        return [
            display_controller
            for display_controller in self.event.sorted_display_controllers
            if self.stored_screen.id
            in display_controller.stored_display_controller.item_screen_ids
        ]

    @property
    def page_display_controllers(self) -> list[DisplayController]:
        """The display controllers held on this page of a multi-screen."""
        if self.family is None or self.family_part is None:
            return []
        return [
            display_controller
            for display_controller in self.event.sorted_display_controllers
            if display_controller.shows_family_page(self.family, self.family_part)
        ]

    @property
    def columns(self) -> int:
        if self.stored_screen:
            return self.stored_screen.columns or 1
        if self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        return self.family.columns

    @property
    def font_size(self) -> int | None:
        if self.stored_screen:
            return self.stored_screen.font_size
        if self.family:
            return self.family.font_size
        return None

    @property
    def menu_text(self) -> str | None:
        if self.stored_screen:
            return self.stored_screen.menu_text
        if self.family:
            return self.family.menu_text
        return None

    @staticmethod
    def default_boards_screen_menu_text(
        single_tournament: bool, first_last: bool, team_matches: bool = False
    ) -> str:
        if team_matches:
            if single_tournament:
                if first_last:
                    return _('Matches %f-%l')
                return _('By match')
            if first_last:
                return _('%t [Matches %f-%l]')
            return _('%t (by match)')
        if single_tournament:
            if first_last:
                return _('Boards %f-%l')
            return _('By board')
        if first_last:
            return _('%t [Boards %f-%l]')
        return _('%t (by board)')

    @staticmethod
    def default_players_screen_menu_text(
        single_tournament: bool, first_last: bool
    ) -> str:
        if single_tournament:
            if first_last:
                return '%f-%l'
            return _('By player')
        if first_last:
            return '%t [%f-%l]'
        return _('%t (by player)')

    @staticmethod
    def default_check_in_screen_menu_text(
        single_tournament: bool, first_last: bool
    ) -> str:
        if single_tournament:
            if first_last:
                return '%f-%l'
            return _('Check-in')
        if first_last:
            return '%t [%f-%l]'
        return _('%t (check-in)')

    @staticmethod
    def default_ranking_screen_menu_text(
        single_tournament: bool,
        first_last: bool,
        crosstable: bool,
    ) -> str:
        if single_tournament:
            if first_last:
                if crosstable:
                    return _('Crosstable %f-%l')
                return _('Ranking %f-%l')
            if crosstable:
                return _('Crosstable')
            return _('Ranking')
        if first_last:
            if crosstable:
                return '%t crosstable [%f-%l]'
            return '%t ranking [%f-%l]'
        if crosstable:
            return '%t crosstable'
        return _('%t ranking')

    def _resolve_menu_label(self, template: str) -> str:
        """Substitute %t (tournament), %f/%l (this screen's first/last, with
        abbreviated player names) and %r (the first–last range) in a menu
        label template."""
        if not self.sorted_screen_sets:
            return template
        screen_set = self.sorted_screen_sets[0]
        text = template.replace('%t', screen_set.tournament.name)
        if '%f' in text or '%l' in text or '%r' in text:
            first, last = screen_set.range_bounds(abbreviated=True)
            text = text.replace('%r', format_range(first, last))
            text = text.replace('%f', first).replace('%l', last)
        return text

    @property
    def menu_entry_label(self) -> str:
        """The label shown for this screen in menus: the custom menu text
        (tokens resolved) if set; for a family-generated screen its own range
        with abbreviated player names (compact submenu items); otherwise the
        screen name (which, when automatic, is the screen's tournament
        name(s))."""
        if self.menu_text:
            return self._resolve_menu_label(self.menu_text)
        if self.family is not None:
            return self._resolve_menu_label(self.family.label_template)
        return self.name

    @property
    def menu_range_label(self) -> str:
        """This screen's range alone (``%f - %l`` with abbreviated player
        names). Used for the items of a family submenu."""
        if not self.sorted_screen_sets:
            return ''
        first, last = self.sorted_screen_sets[0].range_bounds(abbreviated=True)
        return format_range(first, last)

    @property
    def range_label(self) -> str:
        """This screen's range alone, with full names."""
        if not self.sorted_screen_sets:
            return ''
        first, last = self.sorted_screen_sets[0].range_bounds(abbreviated=False)
        return format_range(first, last)

    @property
    def timer(self) -> Timer | None:
        timer_id: int | None
        if self.stored_screen:
            timer_id = self.stored_screen.timer_id
        elif self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        else:
            timer_id = self.family.timer_id

        return self.event.timers_by_id[timer_id] if timer_id else None

    def set_timer(self, timer_id: int | None) -> None:
        assert self.stored_screen is not None
        with EventDatabase(self.event.uniq_id, True) as database:
            database.set_stored_screen_timer_id(self.id, timer_id)
        self.stored_screen.timer_id = timer_id

    @cached_property
    def screen_sets_by_uniq_id(self) -> dict[str, ScreenSet]:
        return {screen_set.uniq_id: screen_set for screen_set in self.screen_sets}

    @cached_property
    def sorted_screen_sets(self) -> list[ScreenSet]:
        return sorted(
            self.screen_sets,
            key=lambda screen_set: screen_set.order or 0,
        )

    @property
    def accepts_input(self) -> bool:
        """Whether results can be entered, or players checked in, on this
        screen."""
        if not self.screen_type.input_option:
            return False
        if self.stored_screen:
            return self.stored_screen.accepts_input
        if self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        return self.family.accepts_input

    @property
    def allowed_in_rotators(self) -> bool:
        """Whether the screen can go through a rotator: not while someone may
        be using it."""
        return not self.accepts_input

    @property
    def input_exit_button(self) -> bool:
        if self.stored_screen:
            return bool(self.stored_screen.input_exit_button)
        if self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        return self.family.input_exit_button

    @property
    def icon_str(self) -> str:
        return self.screen_type.icon_str

    @property
    def type_str(self) -> str:
        return self.screen_type.type_str(self)

    @property
    def last_update(self) -> datetime:
        if self.stored_screen:
            return self.stored_screen.last_update
        if self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        return self.family.last_update

    @property
    def background_image(self) -> str:
        if self.stored_screen and self.stored_screen.background_image:
            return self.stored_screen.background_image
        return ''

    @cached_property
    def background_url(self) -> str:
        return inline_image_url(self.background_image)

    @property
    def background_color(self) -> str:
        if self.stored_screen and self.stored_screen.background_color:
            return self.stored_screen.background_color
        return self.event.background_color

    @property
    def message_default(self) -> bool:
        if self.stored_screen:
            return self.stored_screen.message_default
        if self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        return self.family.message_default

    @property
    def message_text(self) -> str | None:
        if self.message_default:
            return self.event.message_text
        if self.stored_screen:
            return self.stored_screen.message_text
        if self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        return self.family.message_text

    @staticmethod
    def plugin_data_class_by_plugin_id() -> dict[str, builtins.type[PluginData]]:
        return dict(plugin_manager.hook.get_screen_plugin_data_class())

    @cached_property
    def plugin_data(self) -> dict[str, PluginData]:
        stored_plugin_data = (
            self.stored_screen.plugin_data if self.stored_screen else {}
        )
        return {
            plugin_id: plugin_data_class.from_stored_value(
                stored_plugin_data.get(plugin_id, {})
            )
            for plugin_id, plugin_data_class in self.plugin_data_class_by_plugin_id().items()
        }
