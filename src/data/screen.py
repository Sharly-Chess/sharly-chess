import fnmatch
import time
import weakref
from collections.abc import Iterator
from functools import cached_property
from typing import TYPE_CHECKING, Optional
from _weakref import ReferenceType

from common import format_timestamp_date_time
from common.background import inline_image_url
from common.i18n import _
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.board import Board
from data.screen_set import ScreenSet
from data.timer import Timer
from utils.enum import ScreenType
from database.sqlite.event.event_store import StoredScreen

if TYPE_CHECKING:
    from data.event import Event
    from data.family import Family


logger = get_logger()


class Screen:
    """A data wrapper around a stored screen."""

    def __init__(
        self,
        event: 'Event',
        stored_screen: StoredScreen | None = None,
        family: Optional['Family'] = None,
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
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)
        self.stored_screen: StoredScreen | None = stored_screen
        self._family_ref: Optional['ReferenceType[Family]'] = (
            weakref.ref(family) if family else None
        )
        self.family_part: int | None = family_part

    @property
    def event(self) -> 'Event':
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event

    @property
    def family(self) -> 'Family | None':
        return self._family_ref() if self._family_ref else None

    @cached_property
    def screen_sets_by_id(self) -> dict[int | None, ScreenSet]:
        match self.type:
            case (
                ScreenType.BOARDS
                | ScreenType.INPUT
                | ScreenType.PLAYERS
                | ScreenType.RANKING
            ):
                if self.stored_screen:
                    return {
                        stored_screen_set.id: ScreenSet(
                            self, stored_screen_set=stored_screen_set
                        )
                        for stored_screen_set in self.stored_screen.stored_screen_sets
                    }
                else:
                    return {
                        self.id: ScreenSet(
                            self, family=self.family, family_part=self.family_part
                        )
                    }
            case ScreenType.RESULTS | ScreenType.IMAGE:
                return {}
            case _:
                raise ValueError(f'type=[{self.type}]')

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
    def type(self) -> ScreenType:
        if self.stored_screen:
            return ScreenType(self.stored_screen.type)
        if self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        return self.family.type

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
    def name(self) -> str | None:
        if self.stored_screen:
            if self.stored_screen.name:
                return self.stored_screen.name
        match self.type:
            case ScreenType.BOARDS | ScreenType.INPUT:
                return self.screen_sets_sorted_by_order[0].name_for_boards
            case ScreenType.PLAYERS:
                return self.screen_sets_sorted_by_order[0].name_for_players
            case ScreenType.RANKING:
                return self.screen_sets_sorted_by_order[0].name_for_ranking
            case ScreenType.RESULTS:
                return _('Last results')
            case ScreenType.IMAGE:
                return _('Image')
            case _:
                raise ValueError(f'type=[{self.type}]')

    @property
    def columns(self) -> int:
        if self.stored_screen:
            return self.stored_screen.columns or 1
        else:
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
    def menu_link(self) -> bool | None:
        if self.stored_screen:
            return self.stored_screen.menu_link
        if self.family:
            return self.family.menu_link
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
        single_tournament: bool, first_last: bool
    ) -> str:
        if single_tournament:
            if first_last:
                return _('Boards %f-%l')
            else:
                return _('By board')
        else:
            if first_last:
                return _('%t [Boards %f-%l]')
            else:
                return _('%t (by board)')

    @staticmethod
    def default_players_screen_menu_text(
        single_tournament: bool, first_last: bool
    ) -> str:
        if single_tournament:
            if first_last:
                return '%f-%l'
            else:
                return _('By player')
        else:
            if first_last:
                return '%t [%f-%l]'
            else:
                return _('%t (by player)')

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
                else:
                    return _('Ranking %f-%l')
            else:
                if crosstable:
                    return _('Crosstable')
                else:
                    return _('Ranking')
        else:
            if first_last:
                if crosstable:
                    return '%t crosstable [%f-%l]'
                else:
                    return '%t ranking [%f-%l]'
            else:
                if crosstable:
                    return '%t crosstable'
                else:
                    return _('%t ranking')

    @property
    def menu_label(self) -> str | None:
        if not self.menu_link:
            return None
        match self.type:
            case (
                ScreenType.BOARDS
                | ScreenType.INPUT
                | ScreenType.PLAYERS
                | ScreenType.RANKING
            ):
                single_tournament = len(self.event.tournaments_by_id) == 1
                screen_set: ScreenSet = self.screen_sets_sorted_by_order[0]
                first_last = (
                    bool(screen_set.first or screen_set.last)
                    and screen_set.first_item is not None
                )
                text: str
                if (
                    self.type
                    in [
                        ScreenType.INPUT,
                        ScreenType.BOARDS,
                    ]
                    and screen_set.tournament.current_round
                ):
                    text = self.menu_text or self.default_boards_screen_menu_text(
                        single_tournament=single_tournament,
                        first_last=first_last and screen_set.first_item is not None,
                    )
                elif self.type in [
                    ScreenType.PLAYERS,
                    ScreenType.INPUT,
                    ScreenType.BOARDS,
                ]:
                    text = self.menu_text or self.default_players_screen_menu_text(
                        single_tournament=single_tournament,
                        first_last=first_last and screen_set.first_item is not None,
                    )
                elif self.type == ScreenType.RANKING:
                    text = self.menu_text or self.default_ranking_screen_menu_text(
                        single_tournament=single_tournament,
                        first_last=first_last and screen_set.first_item is not None,
                        crosstable=self.ranking_crosstable,
                    )
                else:
                    text = self.menu_text or ''
                text = text.replace('%t', screen_set.tournament.name)
                if self.type == ScreenType.RANKING:
                    if '%f' in text:
                        text = text.replace(
                            '%f',
                            str(screen_set.first_player_by_rank.rank)
                            if screen_set.first_player_by_rank
                            else '-',
                        )
                    if '%l' in text:
                        text = text.replace(
                            '%l',
                            str(screen_set.last_player_by_rank.rank)
                            if screen_set.last_player_by_rank
                            else '-',
                        )
                elif (
                    self.type == ScreenType.PLAYERS
                    or not screen_set.tournament.current_round
                ):
                    text = text.replace(
                        '%f',
                        str(screen_set.first_player_by_name.last_name[:3]).upper()
                        if screen_set.first_player_by_name
                        else '-',
                    )
                    text = text.replace(
                        '%l',
                        str(screen_set.last_player_by_name.last_name[:3]).upper()
                        if screen_set.last_player_by_name
                        else '-',
                    )
                elif self.type in [
                    ScreenType.INPUT,
                    ScreenType.BOARDS,
                ]:
                    if '%f' in text:
                        text = text.replace(
                            '%f',
                            str(
                                screen_set.first_board.id
                                + screen_set.tournament.first_board_number
                                - 1
                            )
                            if screen_set.first_board
                            and screen_set.first_board.id is not None
                            else '-',
                        )
                    if '%l' in text:
                        text = text.replace(
                            '%l',
                            str(
                                screen_set.last_board.id
                                + screen_set.tournament.first_board_number
                                - 1
                            )
                            if screen_set.last_board
                            and screen_set.last_board.id is not None
                            else '-',
                        )
                return text
            case ScreenType.RESULTS:
                assert self.stored_screen is not None
                return self.stored_screen.menu_text or _('Last results')
            case _:
                raise ValueError(f'type=[{self.type}]')

    def _menu_screens(self, admin: bool) -> list['Screen']:
        menu_screens: list['Screen'] = []
        if self.menu is not None:
            for menu_part in map(str.strip, self.menu.split(',')):
                if not menu_part:
                    continue
                is_screen_category = True
                match menu_part:
                    case '@boards':
                        menu_screens += (
                            self.event.screens_by_screen_type_sorted_by_uniq_id[
                                ScreenType.BOARDS
                            ]
                            if admin
                            else self.event.public_screens_by_screen_type_sorted_by_uniq_id[
                                ScreenType.BOARDS
                            ]
                        )
                    case '@input':
                        menu_screens += (
                            self.event.screens_by_screen_type_sorted_by_uniq_id[
                                ScreenType.INPUT
                            ]
                            if admin
                            else self.event.public_screens_by_screen_type_sorted_by_uniq_id[
                                ScreenType.INPUT
                            ]
                        )
                    case '@players':
                        menu_screens += (
                            self.event.screens_by_screen_type_sorted_by_uniq_id[
                                ScreenType.PLAYERS
                            ]
                            if admin
                            else self.event.public_screens_by_screen_type_sorted_by_uniq_id[
                                ScreenType.PLAYERS
                            ]
                        )
                    case '@results':
                        menu_screens += (
                            self.event.screens_by_screen_type_sorted_by_uniq_id[
                                ScreenType.RESULTS
                            ]
                            if admin
                            else self.event.public_screens_by_screen_type_sorted_by_uniq_id[
                                ScreenType.RESULTS
                            ]
                        )
                    case '@ranking':
                        menu_screens += (
                            self.event.screens_by_screen_type_sorted_by_uniq_id[
                                ScreenType.RANKING
                            ]
                            if admin
                            else self.event.public_screens_by_screen_type_sorted_by_uniq_id[
                                ScreenType.RANKING
                            ]
                        )
                    case '@family':
                        if self.family_id is None:
                            logger.warning(
                                'Pattern [@family] can be used by screen families only.'
                            )
                        else:
                            menu_screens += self.event.families_by_id[
                                self.family_id
                            ].screens_by_uniq_id.values()
                    case _:
                        is_screen_category = False
                if is_screen_category:
                    continue
                if '*' in menu_part:
                    menu_part_screen_uniq_ids: list[str] = fnmatch.filter(
                        self.event.screens_by_uniq_id.keys(), menu_part
                    )
                    menu_screens += [
                        self.event.screens_by_uniq_id[screen_uniq_id]
                        for screen_uniq_id in menu_part_screen_uniq_ids
                    ]
                elif menu_part in self.event.screens_by_uniq_id:
                    menu_screens.append(self.event.screens_by_uniq_id[menu_part])
        return menu_screens

    @cached_property
    def public_menu_screens(self) -> list['Screen']:
        return self._menu_screens(False)

    @cached_property
    def admin_menu_screens(self) -> list['Screen']:
        return self._menu_screens(True)

    @property
    def menu(self) -> str:
        if self.stored_screen:
            return self.stored_screen.menu or ''
        if self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        return self.family.menu or ''

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

    @cached_property
    def screen_sets_by_uniq_id(self) -> dict[str, ScreenSet]:
        return {
            screen_set.uniq_id: screen_set
            for screen_set in self.screen_sets_by_id.values()
        }

    @cached_property
    def screen_sets_sorted_by_order(self) -> list[ScreenSet]:
        return sorted(
            self.screen_sets_by_id.values(),
            key=lambda screen_set: screen_set.order or 0,
        )

    @property
    def input_exit_button(self) -> bool:
        match self.type:
            case ScreenType.INPUT:
                if self.stored_screen:
                    if self.stored_screen.input_exit_button is not None:
                        return self.stored_screen.input_exit_button
                    else:
                        return SharlyChessConfig.default_input_exit_button
                else:
                    if self.family is None:
                        raise RuntimeError('Family reference unexpectedly None')
                    return self.family.input_exit_button
            case _:
                raise ValueError(f'type=[{self.type}]')

    @property
    def players_show_unpaired(self) -> bool:
        match self.type:
            case ScreenType.BOARDS | ScreenType.INPUT:
                # Needed to display the players before the first round is paired
                return True
            case ScreenType.PLAYERS:
                if self.stored_screen:
                    if self.stored_screen.players_show_unpaired is not None:
                        return self.stored_screen.players_show_unpaired
                    else:
                        return SharlyChessConfig.default_players_show_unpaired
                else:
                    if self.family is None:
                        raise RuntimeError('Family reference unexpectedly None')
                    return self.family.players_show_unpaired
            case _:
                raise ValueError(f'type=[{self.type}]')

    @property
    def players_show_opponent(self) -> bool:
        match self.type:
            case ScreenType.PLAYERS:
                if self.stored_screen:
                    if self.stored_screen.players_show_opponent is not None:
                        return self.stored_screen.players_show_opponent
                    else:
                        return SharlyChessConfig.default_players_show_opponent
                else:
                    if self.family is None:
                        raise RuntimeError('Family reference unexpectedly None')
                    return self.family.players_show_opponent
            case _:
                raise ValueError(f'type=[{self.type}]')

    @property
    def icon_str(self) -> str:
        return self.type.icon_str

    @staticmethod
    def screen_type_str(
        type_: ScreenType,
        crosstable: bool | None,
    ) -> str:
        if type_ == ScreenType.RANKING:
            if crosstable:
                return _('Crosstable')
            else:
                return _('Ranking')
        else:
            return str(type_)

    @property
    def type_str(self) -> str:
        return self.screen_type_str(
            self.type,
            self.ranking_crosstable if self.type == ScreenType.RANKING else None,
        )

    @cached_property
    def results_limit(self) -> int:
        match self.type:
            case ScreenType.RESULTS:
                assert self.stored_screen is not None
                if not self.stored_screen.results_limit:
                    return SharlyChessConfig.default_results_screen_limit
                elif (
                    self.stored_screen.results_limit
                    and self.stored_screen.results_limit % self.columns > 0
                ):
                    results_limit: int = self.columns * (
                        self.stored_screen.results_limit // self.columns + 1
                    )
                    logger.info(
                        f'Screen [{self.uniq_id}]: Maximum number of results set to '
                        f'[{results_limit}] to fit on [{self.columns}] columns.'
                    )
                    return results_limit
                else:
                    return self.stored_screen.results_limit
            case _:
                raise ValueError(f'type=[{self.type}]')

    @cached_property
    def results_max_age(self) -> int:
        match self.type:
            case ScreenType.RESULTS:
                assert self.stored_screen is not None
                return (
                    self.stored_screen.results_max_age
                    or SharlyChessConfig.default_results_screen_max_age
                )
            case _:
                raise ValueError(f'type=[{self.type}]')

    @cached_property
    def results_tournament_ids(self) -> list[int]:
        match self.type:
            case ScreenType.RESULTS:
                assert self.stored_screen is not None
                return [
                    tournament_id
                    for tournament_id in self.stored_screen.results_tournament_ids
                    if tournament_id in self.event.tournaments_by_id
                ]
            case _:
                raise ValueError(f'type=[{self.type}]')

    @cached_property
    def results_tournament_names(self) -> str:
        return ', '.join(
            sorted(
                [
                    self.event.tournaments_by_id[results_tournament_id].name
                    for results_tournament_id in self.results_tournament_ids
                ]
            )
        )

    @cached_property
    def _results(self) -> list[Board]:
        boards: list[Board] = []
        oldest = time.time() - self.results_max_age * 60
        for tournament in self.event.tournaments_by_id.values():
            if (
                self.results_tournament_ids
                and tournament.id not in self.results_tournament_ids
            ):
                continue
            for round_ in range(1, tournament.current_round + 1):
                for player in tournament.players_by_id.values():
                    pairing = player.pairings[round_]
                    if pairing.board and pairing.board.white_player.id == player.id:
                        if (
                            pairing.board.last_result_update
                            and pairing.board.last_result_update >= oldest
                        ):
                            boards.append(pairing.board)

        boards.sort(
            key=lambda board: board.last_result_update or float('-inf'), reverse=True
        )
        return boards

    def _clear_results_cache(self):
        self.__dict__.pop('_results', None)

    @property
    def results_lists(self) -> Iterator[list[Board]]:
        column_size: int = (
            self.results_limit if self.results_limit else len(self._results)
        ) // self.columns
        for i in range(self.columns):
            yield self._results[i * column_size : (i + 1) * column_size]

    @property
    def ranking_crosstable(self) -> bool:
        match self.type:
            case ScreenType.RANKING:
                if self.stored_screen:
                    return self.stored_screen.ranking_crosstable
                else:
                    if self.family is None:
                        raise RuntimeError('Family reference unexpectedly None')
                    return self.family.ranking_crosstable
            case _:
                raise ValueError(f'type=[{self.type}]')

    @property
    def ranking_round(self) -> int | None:
        match self.type:
            case ScreenType.RANKING:
                if self.stored_screen:
                    return self.stored_screen.ranking_round
                else:
                    if self.family is None:
                        raise RuntimeError('Family reference unexpectedly None')
                    return self.family.ranking_round
            case _:
                raise ValueError(f'type=[{self.type}]')

    @property
    def ranking_min_points(self) -> float | None:
        match self.type:
            case ScreenType.RANKING:
                if self.stored_screen:
                    return self.stored_screen.ranking_min_points
                else:
                    if self.family is None:
                        raise RuntimeError('Family reference unexpectedly None')
                    return self.family.ranking_min_points
            case _:
                raise ValueError(f'type=[{self.type}]')

    @property
    def ranking_max_points(self) -> float | None:
        match self.type:
            case ScreenType.RANKING:
                if self.stored_screen:
                    return self.stored_screen.ranking_max_points
                else:
                    if self.family is None:
                        raise RuntimeError('Family reference unexpectedly None')
                    return self.family.ranking_max_points
            case _:
                raise ValueError(f'type=[{self.type}]')

    @property
    def last_update(self) -> float:
        if self.stored_screen:
            return self.stored_screen.last_update or 0.0
        if self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        return self.family.last_update or 0.0

    @property
    def background_image(self) -> str:
        if self.stored_screen and self.stored_screen.background_image:
            return self.stored_screen.background_image
        else:
            return self.event.background_image

    @cached_property
    def background_url(self) -> str:
        return inline_image_url(self.background_image)

    @property
    def background_color(self) -> str:
        if self.stored_screen and self.stored_screen.background_color:
            return self.stored_screen.background_color
        else:
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

    @property
    def last_update_str(self) -> str | None:
        return format_timestamp_date_time(self.last_update)
