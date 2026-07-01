import functools
import weakref
from datetime import datetime
from functools import cached_property
from math import ceil
from typing import TYPE_CHECKING, Optional
from _weakref import ReferenceType

from common.i18n import _
from data.screen import Screen

from utils.enum import (
    ScreenType,
    PlayersScreenPlayerFormat,
    PlayersScreenBoardFormat,
    PlayersScreenOpponentFormat,
)
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

    def resolve_label(self, template: str, abbreviated: bool = False) -> str:
        """Substitute the tokens %t (tournament), %f/%l (first/last of the
        family's overall range) in a label template. ``abbreviated`` shortens
        player names (menu navigation)."""
        text = template.replace('%t', self.tournament.name)
        if '%f' not in text and '%l' not in text:
            return text
        screens = list(self.screens_by_uniq_id.values())
        if not screens:
            return text.replace('%f', '-').replace('%l', '-')
        first = screens[0].sorted_screen_sets[0].range_bounds(abbreviated)[0]
        last = screens[-1].sorted_screen_sets[0].range_bounds(abbreviated)[1]
        return text.replace('%f', first).replace('%l', last)

    @property
    def label_template(self) -> str:
        """The family name as a label template: the range ``(%f - %l)`` is
        appended when the name carries neither ``%f`` nor ``%l`` (so a family
        always shows its range), otherwise the name is used as is."""
        name = self.name
        if '%f' in name or '%l' in name:
            return name
        return f'{name} (%f - %l)'

    @property
    def display_name(self) -> str:
        """The family's full name for admin display (cards, menu details)."""
        return self.resolve_label(self.label_template, abbreviated=False)

    @property
    def nav_label(self) -> str:
        """The family's compact name for the navigation menu."""
        return self.resolve_label(self.label_template, abbreviated=True)

    @property
    def menu_label(self) -> str:
        """The family's menu label (full): the custom menu text with its
        tokens resolved, or the family name."""
        if self.menu_text:
            return self.resolve_label(self.menu_text, abbreviated=False)
        return self.display_name

    @property
    def nav_menu_label(self) -> str:
        """The family's menu label for the navigation menu (abbreviated)."""
        if self.menu_text:
            return self.resolve_label(self.menu_text, abbreviated=True)
        return self.nav_label

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
    def players_player_format(self) -> PlayersScreenPlayerFormat:
        player_format = self.stored_family.players_player_format
        assert player_format is not None
        return PlayersScreenPlayerFormat(player_format)

    @property
    def players_board_format(self) -> PlayersScreenBoardFormat:
        board_format = self.stored_family.players_board_format
        assert board_format is not None
        return PlayersScreenBoardFormat(board_format)

    @property
    def players_opponent_format(self) -> PlayersScreenOpponentFormat:
        opponent_format = self.stored_family.players_opponent_format
        assert opponent_format is not None
        return PlayersScreenOpponentFormat(opponent_format)

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
    def last_update(self) -> datetime:
        return self.stored_family.last_update

    def _calculate_screens(self) -> bool:
        players_instead_of_boards: bool
        cut_items_number: int = 0
        match ScreenType(self.type):
            case ScreenType.BOARDS | ScreenType.INPUT:
                if self.tournament.current_round:
                    players_instead_of_boards = False
                    if self.shows_team_matches:
                        # Team screens list matches (a match spans several
                        # rows); hidden byes carry no table number.
                        total_items_number: int = len(
                            [
                                team_board
                                for team_board in self.tournament.get_round_team_boards(
                                    self.tournament.current_round
                                )
                                if team_board.display_number is not None
                            ]
                        )
                    else:
                        total_items_number = len(self.tournament.boards or [])
                    if total_items_number:
                        if self.first:
                            self._calculated_first = max(
                                1, min(self.first, total_items_number)
                            )
                        else:
                            self._calculated_first = 1
                        if self.last:
                            self._calculated_last = max(
                                self._calculated_first,
                                min(self.last, total_items_number),
                            )
                        else:
                            self._calculated_last = total_items_number
                        cut_items_number = (
                            self._calculated_last - self._calculated_first + 1
                        )
                else:
                    players_instead_of_boards = True
                    cut_items_number = len(self.tournament.sorted_tournament_players)
                    if cut_items_number:
                        self._calculated_first = 1
                        self._calculated_last = cut_items_number
            case ScreenType.CHECK_IN:
                players_instead_of_boards = True
                if self.tournament.is_team_tournament:
                    cut_items_number = len(
                        [
                            team
                            for team in self.event.teams_by_id.values()
                            if team.tournament_id == self.tournament.id
                        ]
                    )
                else:
                    cut_items_number = len(self.tournament.sorted_tournament_players)
                if cut_items_number:
                    self._calculated_first = 1
                    self._calculated_last = cut_items_number
            case ScreenType.PLAYERS | ScreenType.RANKING:
                players_instead_of_boards = False
                if ScreenType(self.type) == ScreenType.PLAYERS:
                    if self.tournament.current_round:
                        if self.players_show_unpaired:
                            total_items_number = len(
                                self.tournament.sorted_tournament_players
                            )
                        else:
                            total_items_number = len(
                                self.tournament.sorted_tournament_players_without_unpaired
                            )
                    else:
                        total_items_number = len(
                            self.tournament.sorted_tournament_players
                        )
                else:
                    self.tournament.compute_tournament_player_ranks(
                        after_round=self.tournament.correct_ranking_round(
                            self.ranking_round
                        )
                    )
                    total_items_number = len(
                        [
                            player
                            for player in self.tournament.tournament_players_by_rank.values()
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
                if total_items_number:
                    if self.first:
                        self._calculated_first = max(
                            1, min(self.first, total_items_number)
                        )
                    else:
                        self._calculated_first = 1
                    if self.last:
                        self._calculated_last = max(
                            self._calculated_first, min(self.last, total_items_number)
                        )
                    else:
                        self._calculated_last = total_items_number
                    cut_items_number = (
                        self._calculated_last - self._calculated_first + 1
                    )
            case _:
                raise ValueError(f'type={self.type}')
        if cut_items_number:
            # OK now we know the number of items and the number of the first item to take
            # Let's go for the number of items by part and the number of parts
            if self.number:
                if players_instead_of_boards:
                    self._calculated_number = self.number * 2
                elif (
                    self.type in (ScreenType.BOARDS, ScreenType.INPUT)
                    and self.shows_team_matches
                ):
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
                self.columns * 2 if players_instead_of_boards else self.columns
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
        is_team = self.tournament.is_team_tournament
        offset = 0
        if self.type in (ScreenType.BOARDS, ScreenType.INPUT):
            if self.shows_team_matches:
                strings = {
                    'all': _('all the matches'),
                    'from': _('matches from #{first} to end'),
                    'to': _('matches from start to #{last}'),
                    'range': _('matches from #{first} to #{last}'),
                    'number': _('screens of {number} matches per column'),
                    'number_from': _(
                        'screens of {number} matches per column from #{first} to end'
                    ),
                    'number_to': _(
                        'screens of {number} matches per column from start to #{last}'
                    ),
                    'number_range': _(
                        'screens of {number} matches per column from #{first} to #{last}'
                    ),
                    'parts': _('matches on {parts} screens'),
                    'parts_from': _('matches from #{first} to end, on {parts} screens'),
                    'parts_to': _('matches from start to #{last}, on {parts} screens'),
                    'parts_range': _(
                        'matches from #{first} to #{last}, on {parts} screens'
                    ),
                }
            else:
                offset = self.tournament.first_board_number - 1
                strings = {
                    'all': _('all the boards'),
                    'from': _('boards from #{first} to end'),
                    'to': _('boards from start to #{last}'),
                    'range': _('boards from #{first} to #{last}'),
                    'number': _('screens of {number} boards'),
                    'number_from': _('screens of {number} boards from #{first} to end'),
                    'number_to': _('screens of {number} boards from start to #{last}'),
                    'number_range': _(
                        'screens of {number} boards from #{first} to #{last}'
                    ),
                    'parts': _('boards on {parts} screens'),
                    'parts_from': _('boards from #{first} to end, on {parts} screens'),
                    'parts_to': _('boards from start to #{last}, on {parts} screens'),
                    'parts_range': _(
                        'boards from #{first} to #{last}, on {parts} screens'
                    ),
                }
        elif is_team:
            strings = {
                'all': _('all the teams'),
                'from': _('teams from #{first} to end'),
                'to': _('teams from start to #{last}'),
                'range': _('teams from #{first} to #{last}'),
                'number': _('screens of {number} teams'),
                'number_from': _('screens of {number} teams from #{first} to end'),
                'number_to': _('screens of {number} teams from start to #{last}'),
                'number_range': _('screens of {number} teams from #{first} to #{last}'),
                'parts': _('teams on {parts} screens'),
                'parts_from': _('teams from #{first} to end, on {parts} screens'),
                'parts_to': _('teams from start to #{last}, on {parts} screens'),
                'parts_range': _('teams from #{first} to #{last}, on {parts} screens'),
            }
        else:
            strings = {
                'all': _('all the players'),
                'from': _('players from #{first} to end'),
                'to': _('players from start to #{last}'),
                'range': _('players from #{first} to #{last}'),
                'number': _('screens of {number} players'),
                'number_from': _('screens of {number} players from #{first} to end'),
                'number_to': _('screens of {number} players from start to #{last}'),
                'number_range': _(
                    'screens of {number} players from #{first} to #{last}'
                ),
                'parts': _('players on {parts} screens'),
                'parts_from': _('players from #{first} to end, on {parts} screens'),
                'parts_to': _('players from start to #{last}, on {parts} screens'),
                'parts_range': _(
                    'players from #{first} to #{last}, on {parts} screens'
                ),
            }
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
