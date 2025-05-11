import functools
import weakref
from functools import cached_property
from math import ceil
from typing import TYPE_CHECKING, Optional
from _weakref import ReferenceType

from common import format_timestamp_date_time
from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.screen import Screen
from utils.enum import ScreenType
from database.sqlite.event.event_store import StoredFamily

if TYPE_CHECKING:
    from data.event import Event
    from data.tournament import Tournament
    from data.timer import Timer


class Family:
    """A data wrapper around a StoredFamily."""

    def __init__(
        self,
        event: 'Event',
        stored_family: StoredFamily,
    ):
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)
        self.stored_family: StoredFamily = stored_family
        self._calculated_first: int | None = None
        self._calculated_last: int | None = None
        self._calculated_number: int | None = None
        self._calculated_parts: int | None = None
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
    def type(self) -> ScreenType:
        return ScreenType(self.stored_family.type)

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

    @property
    def tournament_id(self) -> int:
        return self.stored_family.tournament_id

    @property
    def tournament(self) -> 'Tournament':
        return self.event.tournaments_by_id[self.tournament_id]

    @property
    def columns(self) -> int:
        return self.stored_family.columns or 1

    @property
    def font_size(self) -> int:
        return self.stored_family.font_size or 100

    @property
    def menu_link(self) -> bool:
        return self.stored_family.menu_link

    @property
    def menu_text(self) -> str:
        return self.stored_family.menu_text

    @cached_property
    def menu_label(self) -> str | None:
        if not self.menu_link:
            return None
        if self.menu_text:
            return self.menu_text
        single_tournament: bool = len(self.event.tournaments_by_id) == 1
        text: str
        if (
            self.type
            in [
                ScreenType.INPUT,
                ScreenType.BOARDS,
            ]
            and self.tournament.current_round
        ):
            text = self.menu_text or Screen.default_boards_screen_menu_text(
                single_tournament=single_tournament, first_last=True
            )
        elif self.type in [
            ScreenType.PLAYERS,
            ScreenType.INPUT,
            ScreenType.BOARDS,
        ]:
            text = self.menu_text or Screen.default_players_screen_menu_text(
                single_tournament=single_tournament, first_last=True
            )
        elif self.type == ScreenType.RANKING:
            text = self.menu_text or Screen.default_ranking_screen_menu_text(
                single_tournament=single_tournament,
                first_last=True,
                crosstable=self.ranking_crosstable,
            )
        else:
            text = self.menu_text
        return text.replace('%t', self.tournament.name)

    @property
    def menu(self) -> str:
        return self.stored_family.menu

    @property
    def timer_id(self) -> int | None:
        return self.stored_family.timer_id

    @property
    def timer(self) -> Optional['Timer']:
        return self.event.timers_by_id[self.timer_id] if self.timer_id else None

    @property
    def input_exit_button(self) -> bool:
        if self.stored_family.input_exit_button is None:
            return SharlyChessConfig.default_input_exit_button
        return self.stored_family.input_exit_button

    @property
    def players_show_unpaired(self) -> bool:
        if self.stored_family.players_show_unpaired is None:
            return SharlyChessConfig.default_players_show_unpaired
        return self.stored_family.players_show_unpaired

    @property
    def ranking_crosstable(self) -> bool:
        match self.type:
            case ScreenType.RANKING:
                return self.stored_family.ranking_crosstable
            case _:
                raise ValueError(f'type=[{self.type}]')

    @property
    def ranking_round(self) -> int | None:
        match self.type:
            case ScreenType.RANKING:
                return self.stored_family.ranking_round
            case _:
                raise ValueError(f'type=[{self.type}]')

    @property
    def ranking_min_points(self) -> float | None:
        match self.type:
            case ScreenType.RANKING:
                return self.stored_family.ranking_min_points
            case _:
                raise ValueError(f'type=[{self.type}]')

    @property
    def ranking_max_points(self) -> float | None:
        match self.type:
            case ScreenType.RANKING:
                return self.stored_family.ranking_max_points
            case _:
                raise ValueError(f'type=[{self.type}]')

    @property
    def icon_str(self) -> str:
        return self.type.icon_str

    @property
    def type_str(self) -> str:
        return Screen.screen_type_str(
            self.type,
            self.ranking_crosstable if self.type == ScreenType.RANKING else None,
        )

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
    def last_update(self) -> float | None:
        return self.stored_family.last_update

    @property
    def last_update_str(self) -> str | None:
        return format_timestamp_date_time(self.last_update)

    def _calculate_screens(self) -> bool:
        if not self.tournament.rounds:
            self.error = _(
                'Tournament [{tournament_uniq_id}] can not be read, family ignored.'
            ).format(tournament_uniq_id=self.tournament.uniq_id)
            self.error = (
                str(self.error)
                if self.error
                else _('Tournament can not be read, family ignored.')
            )
            self.event.add_warning(self.error, family=self)
            return False
        players_instead_of_boards: bool
        match ScreenType(self.type):
            case ScreenType.BOARDS | ScreenType.INPUT:
                if self.tournament.current_round:
                    players_instead_of_boards = False
                    total_items_number: int = len(self.tournament.boards or [])
                    if self.first:
                        if self.first > total_items_number:
                            self.error = _(
                                'Tournament [{tournament_uniq_id}] has only [{boards_number}] boards (< [{first}]), family ignored.'
                            ).format(
                                boards_number=total_items_number,
                                tournament_uniq_id=self.tournament.uniq_id,
                                first=self.first,
                            )
                            self.error = (
                                str(self.error)
                                if self.error
                                else _('Invalid board number range.')
                            )
                            self.event.add_warning(self.error, family=self)
                            return False
                        self._calculated_first = self.first
                    else:
                        self._calculated_first = 1
                    if self.last:
                        self._calculated_last = min(self.last, total_items_number)
                    else:
                        self._calculated_last = total_items_number
                    cut_items_number = (
                        self._calculated_last - self._calculated_first + 1
                    )
                else:
                    players_instead_of_boards = True
                    cut_items_number = len(
                        self.tournament.players_by_name_with_unpaired
                    )
                    self._calculated_first = 1
                    self._calculated_last = cut_items_number
            case ScreenType.PLAYERS | ScreenType.RANKING:
                players_instead_of_boards = False
                if ScreenType(self.type) == ScreenType.PLAYERS:
                    if self.tournament.current_round:
                        if self.players_show_unpaired:
                            total_items_number = len(
                                self.tournament.players_by_name_with_unpaired
                            )
                        else:
                            total_items_number = len(
                                self.tournament.players_by_name_without_unpaired
                            )
                    else:
                        total_items_number = len(
                            self.tournament.players_by_name_with_unpaired
                        )
                else:
                    self.tournament.compute_player_ranks(after_round=self.ranking_round)
                    total_items_number = len(
                        [
                            player
                            for player in self.tournament.players_by_rank.values()
                            if (
                                self.ranking_min_points is None
                                or (player.points or 0) >= self.ranking_min_points
                            )
                            and (
                                self.ranking_max_points is None
                                or (player.points or 0) <= self.ranking_max_points
                            )
                        ]
                    )
                if self.first:
                    if self.first > total_items_number:
                        self.error = (
                            str(self.error)
                            if self.error
                            else _('Invalid player number range.')
                        )
                        self.event.add_warning(self.error, family=self)
                        return False
                    self._calculated_first = self.first
                else:
                    self._calculated_first = 1
                if self.last:
                    self._calculated_last = min(self.last, total_items_number)
                else:
                    self._calculated_last = total_items_number
                cut_items_number = self._calculated_last - self._calculated_first + 1
            case _:
                raise ValueError(f'type={self.type}')
        if not cut_items_number:
            self.error = _(
                'Nothing to display for tournament [{tournament_uniq_id}], family ignored.'
            ).format(tournament_uniq_id=self.tournament.uniq_id)
            self.error = (
                str(self.error)
                if self.error
                else _('Tournament can not be read, family ignored.')
            )
            self.event.add_warning(self.error, family=self)
            return False
        # OK now we know the number of items and the number of the first item to take
        # Let's go for the number of items by part and the number of parts
        if self.number:
            if players_instead_of_boards:
                self._calculated_number = self.number * 2
            else:
                self._calculated_number = self.number
        elif self.parts:
            self._calculated_number = ceil(cut_items_number / self.parts)
        else:
            self._calculated_number = cut_items_number
        divisor: int = self.columns * 2 if players_instead_of_boards else self.columns
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
    def calculated_first_screen_id(self) -> str | None:
        return next(iter(self.screens_by_uniq_id.keys()), None)

    @cached_property
    def calculated_first(self) -> int | None:
        self._calculate_and_cache_screens()
        return self._calculated_first

    @cached_property
    def calculated_last(self) -> int | None:
        self._calculate_and_cache_screens()
        return self._calculated_last

    @cached_property
    def calculated_number(self) -> int | None:
        self._calculate_and_cache_screens()
        return self._calculated_number

    @cached_property
    def calculated_parts(self) -> int:
        self._calculate_and_cache_screens()
        return self._calculated_parts or 1

    @property
    def numbers_str(self):
        if self.type in (ScreenType.BOARDS, ScreenType.INPUT):
            match (self.first, self.last, self.number, self.parts):
                case (None, None, None, None):
                    return _('all the boards')
                case (first, None, None, None) if first is not None:
                    return _('boards from #{first} to end').format(first=first)
                case (None, last, None, None) if last is not None:
                    return _('boards from start to #{last}').format(last=last)
                case (first, last, None, None) if (
                    first is not None and last is not None
                ):
                    return _('boards from #{first} to #{last}').format(
                        first=first, last=last
                    )
                case (None, None, number, None) if number is not None:
                    return _('screens of {number} boards').format(number=number)
                case (first, None, number, None) if (
                    first is not None and number is not None
                ):
                    return _('screens of {number} boards from #{first} to end').format(
                        first=first, number=number
                    )
                case (None, last, number, None) if (
                    last is not None and number is not None
                ):
                    return _('screens of {number} boards from start to #{last}').format(
                        last=last, number=number
                    )
                case (first, last, number, None) if (
                    first is not None and last is not None and number is not None
                ):
                    return _(
                        'screens of {number} boards from #{first} to #{last}'
                    ).format(first=first, last=last, number=number)
                case (None, None, None, parts) if parts is not None:
                    return _('boards on {parts} screens').format(parts=parts)
                case (first, None, None, parts) if (
                    first is not None and parts is not None
                ):
                    return _('boards from #{first} to end, on {parts} screens').format(
                        first=first, parts=parts
                    )
                case (None, last, None, parts) if (
                    last is not None and parts is not None
                ):
                    return _('boards from start to #{last}, on {parts} screens').format(
                        last=last, parts=parts
                    )
                case (first, last, None, parts) if (
                    first is not None and last is not None and parts is not None
                ):
                    return _(
                        'boards from #{first} to #{last}, on {parts} screens'
                    ).format(first=first, last=last, parts=parts)
                case _:
                    raise ValueError(
                        f'first={self.first}, last={self.last}, parts={self.parts}, number={self.number}'
                    )
        else:
            match (self.first, self.last, self.number, self.parts):
                case (None, None, None, None):
                    return _('all the players')
                case (first, None, None, None) if first is not None:
                    return _('players from #{first} to end').format(first=first)
                case (None, last, None, None) if last is not None:
                    return _('players from start to #{last}').format(last=last)
                case (first, last, None, None) if (
                    first is not None and last is not None
                ):
                    return _('players from #{first} to #{last}').format(
                        first=first, last=last
                    )
                case (None, None, number, None) if number is not None:
                    return _('screens of {number} players').format(number=number)
                case (first, None, number, None) if (
                    first is not None and number is not None
                ):
                    return _('screens of {number} players from #{first} to end').format(
                        first=first, number=number
                    )
                case (None, last, number, None) if (
                    last is not None and number is not None
                ):
                    return _(
                        'screens of {number} players from start to #{last}'
                    ).format(last=last, number=number)
                case (first, last, number, None) if (
                    first is not None and last is not None and number is not None
                ):
                    return _(
                        'screens of {number} players from #{first} to #{last}'
                    ).format(first=first, last=last, number=number)
                case (None, None, None, parts) if parts is not None:
                    return _('players on {parts} screens').format(parts=parts)
                case (first, None, None, parts) if (
                    first is not None and parts is not None
                ):
                    return _('players from #{first} to end, on {parts} screens').format(
                        first=first, parts=parts
                    )
                case (None, last, None, parts) if (
                    last is not None and parts is not None
                ):
                    return _(
                        'players from start to #{last}, on {parts} screens'
                    ).format(last=last, parts=parts)
                case (first, last, None, parts) if (
                    first is not None and last is not None and parts is not None
                ):
                    return _(
                        'players from #{first} to #{last}, on {parts} screens'
                    ).format(first=first, last=last, parts=parts)
                case _:
                    raise ValueError(
                        f'first={self.first}, last={self.last}, parts={self.parts}, number={self.number}'
                    )

    def __str__(self):
        return f'Tournament {self.tournament.uniq_id} ({self.numbers_str})'
