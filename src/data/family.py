import functools
import weakref
from datetime import datetime
from functools import cached_property
from math import ceil
from typing import TYPE_CHECKING, Optional
from _weakref import ReferenceType

from common.i18n import _
from data.screen import Screen
from data.screen_set import format_range

from database.sqlite.event.event_store import StoredFamily

if TYPE_CHECKING:
    from data.event import Event
    from data.tournament import Tournament
    from data.timer import Timer
    from data.screen_types import ScreenType


class Family:
    """A data wrapper around a StoredFamily."""

    def __init__(
        self,
        event: 'Event',
        stored_family: StoredFamily,
    ):
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)
        self.stored_family: StoredFamily = stored_family
        self._calculated_first: int = 0
        self._calculated_last: int = 0
        self._calculated_number: int = 0
        self._calculated_parts: int = 1
        self.error: str | None = None

        # http://rednafi.com/python/lru_cache_on_methods/
        self._calculate_and_cache_screens = functools.lru_cache()(
            self._calculate_screens
        )

    @property
    def event(self) -> 'Event':
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event

    @property
    def id(self) -> int:
        assert self.stored_family.id is not None, 'Family id is not set.'
        return self.stored_family.id

    @property
    def type(self) -> str:
        """The family's type id (a built-in id or a plugin-defined one), kept
        as a plain string (see ``Screen.type``)."""
        return self.stored_family.type

    @property
    def screen_type(self) -> 'ScreenType':
        """The screen-type entity for this family, resolved through the
        manager (so a plugin-defined type is honoured)."""
        from data.screen_types import ScreenTypeManager

        return ScreenTypeManager(self.event).get_object(self.type)

    @property
    def public(self) -> bool:
        return self.stored_family.public

    @property
    def uniq_id(self) -> str:
        return self.stored_family.uniq_id

    @property
    def name(self) -> str:
        name: str = (
            self.stored_family.name if self.stored_family.name else _('%t (%f to %l)')
        )
        return name.replace('%t', self.tournament.name)

    def resolve_label(self, template: str, abbreviated: bool = False) -> str:
        """Substitute the tokens %t (tournament), %f/%l (first/last of the
        family's overall range) and %r (the first–last range) in a label
        template. ``abbreviated`` shortens player names (menu navigation)."""
        text = template.replace('%t', self.tournament.name)
        if '%f' not in text and '%l' not in text and '%r' not in text:
            return text
        screens = list(self.screens_by_uniq_id.values())
        if not screens:
            first = last = '-'
        else:
            first = screens[0].sorted_screen_sets[0].range_bounds(abbreviated)[0]
            last = screens[-1].sorted_screen_sets[0].range_bounds(abbreviated)[1]
        text = text.replace('%r', format_range(first, last))
        return text.replace('%f', first).replace('%l', last)

    @property
    def label_template(self) -> str:
        """The family name as a label template: the range ``(%f - %l)`` is
        appended when the name carries neither ``%f`` nor ``%l`` (so a family
        always shows its range), otherwise the name is used as is."""
        name = self.name
        if '%f' in name or '%l' in name:
            return name
        return f'{name} (%r)'

    @property
    def display_name(self) -> str:
        """The family's full name for admin display (cards, menu details)."""
        return self.resolve_label(self.label_template, abbreviated=False)

    @property
    def nav_label(self) -> str:
        """The family's compact name for the navigation menu."""
        return self.resolve_label(self.label_template, abbreviated=True)

    def _menu_label_template(self, with_tournament: bool = False) -> str:
        """The menu-label template: the range ``%f - %l`` is appended to the
        custom menu text (or used alone when there is none), unless the user
        already placed a ``%f``/``%l`` token themselves. When automatic (no
        custom text) and ``with_tournament``, the tournament name is prefixed
        to disambiguate families of different tournaments. A single-screen
        family has no meaningful range, so the range is not appended (the
        tournament name is used when automatic)."""
        text = self.menu_text or ''
        if '%f' in text or '%l' in text:
            return text
        if len(self.screens_by_uniq_id) <= 1:
            return text or '%t'
        if not text and with_tournament:
            text = '%t'
        return f'{text} %r'.strip()

    def menu_label(self, with_tournament: bool = False) -> str:
        """The family's menu label (full), with its tokens resolved."""
        return self.resolve_label(
            self._menu_label_template(with_tournament), abbreviated=False
        )

    def nav_menu_label(self, with_tournament: bool = False) -> str:
        """The family's menu label for the navigation menu (abbreviated)."""
        return self.resolve_label(
            self._menu_label_template(with_tournament), abbreviated=True
        )

    @property
    def in_multi_family_menu(self) -> bool:
        """Whether the menu this family belongs to covers more than one
        family."""
        for menu in self.event.sorted_menus:
            families = menu.covered_families
            if any(family.id == self.id for family in families):
                return len(families) > 1
        return False

    @property
    def tournament_id(self) -> int:
        return self.stored_family.tournament_id

    @property
    def tournament(self) -> 'Tournament':
        return self.event.tournaments_by_id[self.tournament_id]

    @property
    def shows_team_matches(self) -> bool:
        """Whether boards/input screens of this family show team-match
        blocks: only team-vs-team pairing systems have match envelopes —
        flat fixed-table systems (e.g. Molter) keep the individual board
        list even in a team event."""
        return (
            self.tournament.is_team_tournament
            and self.tournament.pairing_system.paired_by_team
        )

    @property
    def columns(self) -> int:
        return self.stored_family.columns or 1

    @property
    def font_size(self) -> int:
        return self.stored_family.font_size or 100

    @property
    def menu_text(self) -> str:
        return self.stored_family.menu_text

    @property
    def timer_id(self) -> int | None:
        return self.stored_family.timer_id

    @property
    def timer(self) -> Optional['Timer']:
        return self.event.timers_by_id[self.timer_id] if self.timer_id else None

    @property
    def input_exit_button(self) -> bool:
        exit_button = self.stored_family.input_exit_button
        assert exit_button is not None
        return exit_button

    @property
    def players_show_unpaired(self) -> bool:
        show_unpaired = self.stored_family.players_show_unpaired
        assert show_unpaired is not None
        return show_unpaired

    @property
    def icon_str(self) -> str:
        return self.screen_type.icon_str

    @property
    def type_str(self) -> str:
        return self.screen_type.family_type_str(self)

    @property
    def first(self) -> int | None:
        return self.stored_family.first

    @property
    def last(self) -> int | None:
        return self.stored_family.last

    @property
    def parts(self) -> int | None:
        return self.stored_family.parts

    @property
    def number(self) -> int | None:
        return self.stored_family.number

    @property
    def message_default(self) -> bool:
        return self.stored_family.message_default

    @property
    def message_text(self) -> str | None:
        return (
            self.event.message_text
            if self.message_default
            else self.stored_family.message_text
        )

    @property
    def last_update(self) -> datetime:
        return self.stored_family.last_update

    def _calculate_screens(self) -> bool:
        item_range = self.screen_type.family_item_range(self)
        self._calculated_first = item_range.first
        self._calculated_last = item_range.last
        cut_items_number: int = item_range.item_count
        if cut_items_number:
            # OK now we know the number of items and the number of the first item to take
            # Let's go for the number of items by part and the number of parts
            if self.number:
                if item_range.players_instead_of_boards:
                    self._calculated_number = self.number * 2
                elif item_range.number_per_column:
                    # In team mode ``number`` counts matches per COLUMN
                    # (easier to reason about than display rows, since a
                    # match spans several rows) — scale to a per-screen
                    # item count.
                    self._calculated_number = self.number * self.columns
                else:
                    self._calculated_number = self.number
            elif self.parts:
                self._calculated_number = ceil(cut_items_number / self.parts)
            else:
                self._calculated_number = cut_items_number
            divisor: int = (
                self.columns * 2
                if item_range.players_instead_of_boards
                else self.columns
            )
            # ensure that the number of items is divisible by the number of columns
            if self._calculated_number % divisor != 0:
                self._calculated_number = min(
                    (self._calculated_number // divisor + 1) * divisor, cut_items_number
                )
            # recalculate the number of parts
            # (because the number of items by part may increase to fit the number of columns)
            self._calculated_parts = ceil(cut_items_number / self._calculated_number)
        return True

    @cached_property
    def screens_by_uniq_id(self) -> dict[str, Screen]:
        screens_by_uniq_id: dict[str, Screen] = {}
        if self._calculate_and_cache_screens():
            for family_index in range(1, self.calculated_parts + 1):
                screen: Screen = Screen(
                    self.event, family=self, family_part=family_index
                )
                screens_by_uniq_id[screen.uniq_id] = screen
        return screens_by_uniq_id

    @cached_property
    def calculated_first_screen_id(self) -> str:
        return next(iter(self.screens_by_uniq_id.keys()))

    @cached_property
    def calculated_first(self) -> int:
        self._calculate_and_cache_screens()
        return self._calculated_first

    @cached_property
    def calculated_last(self) -> int:
        self._calculate_and_cache_screens()
        return self._calculated_last

    @cached_property
    def calculated_number(self) -> int:
        self._calculate_and_cache_screens()
        return self._calculated_number

    @cached_property
    def calculated_parts(self) -> int:
        self._calculate_and_cache_screens()
        return self._calculated_parts

    @property
    def numbers_str(self) -> str:
        strings, offset = self.screen_type.family_number_strings(self)
        first = self.first + offset if self.first is not None else None
        last = self.last + offset if self.last is not None else None
        match (self.first, self.last, self.number, self.parts):
            case (None, None, None, None):
                return strings['all']
            case (f, None, None, None) if f is not None:
                return strings['from'].format(first=first)
            case (None, l, None, None) if l is not None:
                return strings['to'].format(last=last)
            case (f, l, None, None) if f is not None and l is not None:
                return strings['range'].format(first=first, last=last)
            case (None, None, number, None) if number is not None:
                return strings['number'].format(number=number)
            case (f, None, number, None) if f is not None and number is not None:
                return strings['number_from'].format(first=first, number=number)
            case (None, l, number, None) if l is not None and number is not None:
                return strings['number_to'].format(last=last, number=number)
            case (f, l, number, None) if (
                f is not None and l is not None and number is not None
            ):
                return strings['number_range'].format(
                    first=first, last=last, number=number
                )
            case (None, None, None, parts) if parts is not None:
                return strings['parts'].format(parts=parts)
            case (f, None, None, parts) if f is not None and parts is not None:
                return strings['parts_from'].format(first=first, parts=parts)
            case (None, l, None, parts) if l is not None and parts is not None:
                return strings['parts_to'].format(last=last, parts=parts)
            case (f, l, None, parts) if (
                f is not None and l is not None and parts is not None
            ):
                return strings['parts_range'].format(
                    first=first, last=last, parts=parts
                )
            case _:
                raise ValueError(
                    f'first={self.first}, last={self.last}, parts={self.parts}, number={self.number}'
                )

    def __str__(self):
        return f'Tournament {self.tournament.name} ({self.numbers_str})'
