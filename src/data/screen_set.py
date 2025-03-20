import math
import weakref
from collections.abc import Iterable
from itertools import chain
from logging import Logger
from typing import Any, TYPE_CHECKING
from _weakref import ReferenceType

from common import format_timestamp_date_time
from common.i18n import _
from common.logger import get_logger
from data.board import Board
from data.player import Player
from data.util import ScreenType
from database.sqlite.event.event_store import StoredScreenSet

if TYPE_CHECKING:
    from data.event import Event
    from data.screen import Screen
    from data.family import Family
    from data.tournament import Tournament

logger: Logger = get_logger()


class ScreenSet:
    """A data wrapper around a stored screen set."""

    def __init__(
        self,
        screen: 'Screen',
        stored_screen_set: StoredScreenSet | None = None,
        family: 'Family | None' = None,
        family_part: int | None = None,
    ):
        if stored_screen_set is None:
            assert family is not None and family_part is not None, (
                f'screen_set={stored_screen_set}, family={family}, family_part={family_part}'
            )
        else:
            assert family is None and family_part is None, (
                f'screen_set={stored_screen_set}, family={family}, family_part={family_part}'
            )
        self._screen_ref: 'ReferenceType[Screen]' = weakref.ref(screen)
        self.stored_screen_set: StoredScreenSet | None = stored_screen_set
        self._family_ref: 'ReferenceType[Family] | None' = weakref.ref(family) if family else None
        self.family_part: int | None = family_part
        self.uniq_id: str
        if self.stored_screen_set:
            self.uniq_id = f'{self.screen.uniq_id}_{self.stored_screen_set.order}'
        else:
            self.uniq_id = f'{self.screen.uniq_id}_{self.family_part}'
        fixed_boards_str: str | None = (
            self.stored_screen_set.fixed_boards_str
            if self.screen.type in [ScreenType.BOARDS, ScreenType.INPUT]
            and self.stored_screen_set
            else None
        )
        self.fixed_board_numbers: list[int] | None = None
        self.first: int | None = None
        self.last: int | None = None
        if self.stored_screen_set:
            if fixed_boards_str is not None:
                if fixed_boards_str:
                    self.fixed_board_numbers = []
                    for fixed_board_str in list(
                        map(str.strip, fixed_boards_str.split(','))
                    ):
                        if fixed_board_str:
                            try:
                                self.fixed_board_numbers.append(int(fixed_board_str))
                            except ValueError:
                                self.event.add_warning(
                                    _(
                                        'Invalid board number [{fixed_board_str}].'
                                    ).format(fixed_board_str=fixed_board_str),
                                    screen_set=self,
                                )
                else:
                    self.fixed_board_numbers = [
                        player.fixed
                        for player in self.tournament.players_by_id.values()
                        if player.fixed
                    ]
            else:
                self.first = self.stored_screen_set.first
                self.last = self.stored_screen_set.last
        else:
            self.fixed_board_numbers = []
            self.first = (
                self.family.calculated_first
                + (self.family_part - 1) * self.family.calculated_number
            )
            self.last = min(
                self.family.calculated_last,
                self.family.calculated_first
                + self.family_part * self.family.calculated_number
                - 1,
            )
        if self.first and self.last and self.first > self.last:
            self.event.add_warning(
                _(
                    'Numbers {first} and {last} are not compatible ({first} > {last}).'
                ).format(first=self.first, last=self.last),
                screen_set=self,
            )
        self.first_item: Any | None = None  # change this to Board | Player | None ?
        self.last_item: Any | None = None  # change this to Board | Player | None ?
        self.items_lists: list[list[Any]] | None = (
            None  # change this to Board | Player | None ?
        )

    @property
    def screen(self) -> 'Screen':
        return self._screen_ref()

    @property
    def family(self) -> 'Family | None':
        return self._family_ref() if self._family_ref else None

    @property
    def id(self) -> int | None:
        return self.stored_screen_set.id if self.stored_screen_set else None

    @property
    def type(self) -> ScreenType:
        return self.screen.type

    @property
    def order(self) -> int | None:
        return self.stored_screen_set.order if self.stored_screen_set else None

    @property
    def event(self) -> 'Event':
        return self.screen.event

    @property
    def tournament_id(self) -> int:
        return (
            self.stored_screen_set.tournament_id
            if self.stored_screen_set
            else self.family.tournament_id
        )

    @property
    def tournament(self) -> 'Tournament':
        return self.event.tournaments_by_id[self.tournament_id]

    @property
    def columns(self) -> int:
        return self.screen.columns

    @property
    def players_show_unpaired(self) -> bool:
        return self.screen.players_show_unpaired

    @property
    def name_for_boards(self) -> str | None:
        if self.tournament.current_round:
            self._extract_boards()
            name: str | None = (
                self.stored_screen_set.name
                if self.stored_screen_set
                else self.family.name
            )
            if name is None:
                if self.first or self.last:
                    name = _('Boards %f-%l')
                else:
                    name = '%t'
            name = name.replace('%t', str(self.tournament.name))
            if r'%f' in name and self.first_item is not None:
                name = name.replace(r'%f', str(self.first_board.id))
            if r'%l' in name and self.last_item is not None:
                name = name.replace(r'%l', str(self.last_board.id))
            return name
        else:
            return self.name_for_players

    @property
    def name_for_players(self) -> str | None:
        self._extract_players_by_name()
        name: str | None = (
            self.stored_screen_set.name if self.stored_screen_set else self.family.name
        )
        if name is None:
            if self.first or self.last:
                name = _('%f to %l')
            else:
                name = '%t'
        name = name.replace('%t', str(self.tournament.name))
        if self.first_item is not None:
            name = name.replace('%f', self.first_player_by_name.last_name[:8])
        if self.last_item is not None:
            name = name.replace('%l', self.last_player_by_name.last_name[:8])
        return name

    @property
    def ranking_round(self) -> int:
        return self.tournament.correct_ranking_round(
            self.screen.ranking_round
        )

    @property
    def ranking_crosstable(self) -> bool:
        return self.screen.ranking_crosstable

    @property
    def ranking_min_points(self) -> int | None:
        return self.screen.ranking_min_points

    @property
    def ranking_max_points(self) -> int | None:
        return self.screen.ranking_max_points

    @property
    def name_for_ranking(self) -> str | None:
        self._extract_players_by_rank()
        name: str | None = (
            self.stored_screen_set.name if self.stored_screen_set else self.family.name
        )
        if name is None:
            if self.first or self.last:
                if self.screen.ranking_crosstable:
                    name = _('Crosstable %f to %l')
                else:
                    name = _('Ranking %f to %l')
            else:
                if self.screen.ranking_crosstable:
                    name = _('%t crosstable')
                else:
                    name = _('%t ranking')
        name = name.replace('%t', str(self.tournament.name))
        if self.first_item is not None:
            name = name.replace(r'%f', str(self.first_player_by_rank.rank))
        if self.last_item is not None:
            name = name.replace('%l', str(self.last_player_by_rank.rank))
        return name

    def _extract_data(self, items: list[Any]):
        if not items:
            self.items_lists = [
                [],
            ] * self.columns
            return
        # at first select the desired items
        first_index: int
        last_index: int
        if self.fixed_board_numbers:
            if TYPE_CHECKING:
                assert all(isinstance(item, Board) for item in items)
            selected_items = [
                board for board in items if board.number in self.fixed_board_numbers
            ]
        else:
            first = self.first - 1 if self.first is not None else 0
            last = self.last if self.last is not None else len(items)
            selected_slice = slice(first, last)
            selected_items = items[selected_slice]
            if not selected_items:
                return
            self.first_item = selected_items[0]
            self.last_item = selected_items[-1]
        # now split in columns
        items_number = len(selected_items)
        q, r = divmod(items_number, self.columns)
        first_index = 0
        self.items_lists = []
        for _num in range(1, self.columns + 1):
            last_index = first_index + q
            more: int = min(r, 1)
            last_index += more
            r -= more
            self.items_lists.append(selected_items[first_index:last_index])
            first_index = last_index

    def _extract_boards(self):
        if self.items_lists is None:
            self._extract_data(self.tournament.boards)

    @property
    def boards_lists(self) -> list[list[Board]]:
        self._extract_boards()
        if TYPE_CHECKING:
            assert (
                isinstance(self.items_lists, list)
                and all(isinstance(item, list) for item in self.items_lists)
                and all(
                    isinstance(item, Board)
                    for item in chain(*self.items_lists)
                )
            )
        return self.items_lists

    @property
    def first_board(self) -> Board:
        if not self.first_item:
            self._extract_boards()
        if TYPE_CHECKING:
            assert isinstance(self.first_item, Board)
        return self.first_item

    @property
    def last_board(self) -> Board:
        self._extract_boards()
        if TYPE_CHECKING:
            assert isinstance(self.last_item, Board)
        return self.last_item

    def _extract_players_by_name(self):
        if self.items_lists is None:
            if self.players_show_unpaired:
                self._extract_data(self.tournament.players_by_name_with_unpaired)
            else:
                self._extract_data(self.tournament.players_by_name_without_unpaired)

    @property
    def players_by_name_lists(self) -> list[list[Player]]:
        self._extract_players_by_name()
        if TYPE_CHECKING:
            assert (
                isinstance(self.items_lists, list)
                and all(isinstance(item, list) for item in self.items_lists)
                and all(
                    isinstance(item, Player)
                    for item in chain(*self.items_lists)
                )
            )
        return self.items_lists

    @property
    def players_by_name_tuple_lists(
        self,
    ) -> Iterable[tuple[list[Player], list[Player]]]:
        self._extract_players_by_name()
        if TYPE_CHECKING:
            assert (
                isinstance(self.items_lists, list)
                and all(isinstance(item, list) for item in self.items_lists)
                and all(
                    isinstance(item, Player)
                    for item in chain(*self.items_lists)
                )
            )
        players_by_name_lists: list[list[Player]] = self.items_lists
        for players_by_name in players_by_name_lists:
            yield (
                players_by_name[: (bound := math.ceil(len(players_by_name) / 2))],
                players_by_name[bound:],
            )

    @property
    def first_player_by_name(self) -> Player:
        if not self.first_item:
            self._extract_players_by_name()
        if TYPE_CHECKING:
            assert isinstance(self.first_item, Player)
        return self.first_item

    @property
    def last_player_by_name(self) -> Player:
        if not self.last_item:
            self._extract_players_by_name()
        if TYPE_CHECKING:
            assert isinstance(self.last_item, Player)
        return self.last_item

    def _extract_players_by_rank(self):
        if self.items_lists is None:
            self._extract_data(
                [
                    player
                    for player in self.tournament.players_by_rank.values()
                    if (
                        self.ranking_min_points is None or player.points >= self.ranking_min_points
                    ) and (
                        self.ranking_max_points is None or player.points <= self.ranking_max_points
                    )
                ]
            )

    @property
    def players_by_rank_lists(self) -> list[list[Player]]:
        self._extract_players_by_rank()
        if TYPE_CHECKING:
            assert (
                isinstance(self.items_lists, list)
                and all(isinstance(item, list) for item in self.items_lists)
                and all(
                    isinstance(item, Player)
                    for item in chain(*self.items_lists)
                )
            )
        return self.items_lists

    @property
    def first_player_by_rank(self) -> Player:
        if not self.first_item:
            self._extract_players_by_rank()
        if TYPE_CHECKING:
            assert isinstance(self.first_item, Player)
        return self.first_item

    @property
    def last_player_by_rank(self) -> Player:
        if not self.last_item:
            self._extract_players_by_rank()
        if TYPE_CHECKING:
            assert isinstance(self.last_item, Player)
        return self.last_item

    @property
    def last_update(self) -> int | None:
        return (
            self.stored_screen_set.last_update
            if self.stored_screen_set
            else self.family.last_update
        )

    @property
    def last_update_str(self) -> str | None:
        return format_timestamp_date_time(self.last_update)

    @property
    def numbers_str(self):
        if self.fixed_board_numbers:
            return _('boards {board_numbers}').format(
                board_numbers=', '.join(map(str, self.fixed_board_numbers))
            )
        if self.type in [ScreenType.BOARDS, ScreenType.INPUT]:
            match (self.first, self.last):
                case (None, None):
                    return _('all the boards')
                case (first, None) if first is not None:
                    return _('boards from #{first} to end').format(first=first)
                case (first, last) if first is not None and last is not None:
                    return _('boards from #{first} to #{last}').format(
                        first=first, last=last
                    )
                case (None, last) if last is not None:
                    return _('boards from start to #{last}').format(last=last)
                case _:
                    raise ValueError(f'first={self.first}, last={self.last}')
        elif self.type in [ScreenType.PLAYERS]:
            match (self.first, self.last):
                case (None, None):
                    return _('all the players')
                case (first, None) if first is not None:
                    return _('players from #{first} to end').format(first=first)
                case (first, last) if first is not None and last is not None:
                    return _('players from #{first} to #{last}').format(
                        first=first, last=last
                    )
                case (None, last) if last is not None:
                    return _('players from start to #{last}').format(last=last)
                case _:
                    raise ValueError(f'first={self.first}, last={self.last}')
        else:
            match (self.first, self.last):
                case (None, None):
                    return _('the whole ranking')
                case (first, None) if first is not None:
                    return _('ranking from #{first} to end').format(first=first)
                case (first, last) if first is not None and last is not None:
                    return _('ranking from #{first} to #{last}').format(
                        first=first, last=last
                    )
                case (None, last) if last is not None:
                    return _('ranking from start to #{last}').format(last=last)
                case _:
                    raise ValueError(f'first={self.first}, last={self.last}')

    def __str__(self):
        return _('Tournament {tournament_uniq_id} ({numbers_str})').format(
            tournament_uniq_id=self.tournament.uniq_id, numbers_str=self.numbers_str
        )
