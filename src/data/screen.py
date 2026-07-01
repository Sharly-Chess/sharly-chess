import weakref
from collections.abc import Iterator, Collection
from datetime import datetime, timedelta
from functools import cached_property
from typing import TYPE_CHECKING, Any, Optional
from _weakref import ReferenceType

from common.background import inline_image_url
from common.i18n import _
from common.i18n.utils import normalized_key
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.board import Board
from data.screen_set import ScreenSet
from data.timer import Timer

from utils.enum import (
    ScreenType,
    PlayersScreenPlayerFormat,
    PlayersScreenBoardFormat,
    PlayersScreenOpponentFormat,
)
from database.sqlite.event.event_store import StoredScreen

if TYPE_CHECKING:
    from data.event import Event
    from data.family import Family
    from data.menu import MenuNavEntry


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
                | ScreenType.CHECK_IN
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
    def name(self) -> str:
        if self.stored_screen:
            if self.stored_screen.name:
                return self.stored_screen.name
        match self.type:
            case ScreenType.BOARDS | ScreenType.INPUT:
                return self.sorted_screen_sets[0].name_for_boards
            case ScreenType.PLAYERS | ScreenType.CHECK_IN:
                first_set = self.sorted_screen_sets[0]
                if (
                    self.type == ScreenType.CHECK_IN
                    and first_set.tournament.is_team_tournament
                ):
                    return first_set.name_for_teams
                return first_set.name_for_players
            case ScreenType.RANKING:
                return self.sorted_screen_sets[0].name_for_ranking
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
    def default_check_in_screen_menu_text(
        single_tournament: bool, first_last: bool
    ) -> str:
        if single_tournament:
            if first_last:
                return '%f-%l'
            else:
                return _('Check-in')
        else:
            if first_last:
                return '%t [%f-%l]'
            else:
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
    def menu_entry_label(self) -> str:
        match self.type:
            case (
                ScreenType.BOARDS
                | ScreenType.INPUT
                | ScreenType.PLAYERS
                | ScreenType.RANKING
                | ScreenType.CHECK_IN
            ):
                single_tournament = len(self.event.tournaments_by_id) == 1
                screen_set: ScreenSet = self.sorted_screen_sets[0]
                is_team = screen_set.tournament.is_team_tournament
                team_matches = screen_set.shows_team_matches
                first_item: Any
                if team_matches and self.type in (
                    ScreenType.INPUT,
                    ScreenType.BOARDS,
                ):
                    first_item = screen_set.first_team_match
                elif is_team and self.type == ScreenType.CHECK_IN:
                    first_item = screen_set.first_team_by_name
                elif is_team and self.type == ScreenType.RANKING:
                    first_item = screen_set.first_team_standing
                else:
                    first_item = screen_set.first_item
                first_last = (
                    bool(screen_set.first or screen_set.last) and first_item is not None
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
                        first_last=first_last,
                        team_matches=team_matches,
                    )
                elif self.type in [
                    ScreenType.PLAYERS,
                    ScreenType.INPUT,
                    ScreenType.BOARDS,
                ]:
                    text = self.menu_text or self.default_players_screen_menu_text(
                        single_tournament=single_tournament,
                        first_last=first_last,
                    )
                elif self.type == ScreenType.CHECK_IN:
                    text = self.menu_text or self.default_check_in_screen_menu_text(
                        single_tournament=single_tournament,
                        first_last=first_last,
                    )
                elif self.type == ScreenType.RANKING:
                    text = self.menu_text or self.default_ranking_screen_menu_text(
                        single_tournament=single_tournament,
                        first_last=first_last,
                        crosstable=self.ranking_crosstable,
                    )
                else:
                    text = self.menu_text or ''
                text = text.replace('%t', screen_set.tournament.name)
                if self.type == ScreenType.RANKING:
                    if is_team:
                        if '%f' in text:
                            first_standing = screen_set.first_team_standing
                            text = text.replace(
                                '%f',
                                str(first_standing['rank']) if first_standing else '-',
                            )
                        if '%l' in text:
                            last_standing = screen_set.last_team_standing
                            text = text.replace(
                                '%l',
                                str(last_standing['rank']) if last_standing else '-',
                            )
                    else:
                        if '%f' in text:
                            text = text.replace(
                                '%f',
                                str(screen_set.first_tournament_player_by_rank.rank)
                                if screen_set.first_tournament_player_by_rank
                                else '-',
                            )
                        if '%l' in text:
                            text = text.replace(
                                '%l',
                                str(screen_set.last_tournament_player_by_rank.rank)
                                if screen_set.last_tournament_player_by_rank
                                else '-',
                            )
                elif is_team and (
                    self.type == ScreenType.CHECK_IN
                    or (
                        not team_matches
                        and self.type in (ScreenType.INPUT, ScreenType.BOARDS)
                        and not screen_set.tournament.current_round
                    )
                ):
                    first_team = screen_set.first_team_by_name
                    last_team = screen_set.last_team_by_name
                    text = text.replace(
                        '%f', first_team.name[:8] if first_team else '-'
                    )
                    text = text.replace('%l', last_team.name[:8] if last_team else '-')
                elif team_matches and self.type in (
                    ScreenType.INPUT,
                    ScreenType.BOARDS,
                ):
                    first_match = screen_set.first_team_match
                    last_match = screen_set.last_team_match
                    if '%f' in text:
                        text = text.replace(
                            '%f',
                            str(first_match.display_number)
                            if first_match and first_match.display_number is not None
                            else '-',
                        )
                    if '%l' in text:
                        text = text.replace(
                            '%l',
                            str(last_match.display_number)
                            if last_match and last_match.display_number is not None
                            else '-',
                        )
                elif (
                    self.type in (ScreenType.PLAYERS, ScreenType.CHECK_IN)
                    or not screen_set.tournament.current_round
                ):
                    text = text.replace(
                        '%f',
                        str(
                            screen_set.first_tournament_player_by_name.last_name[:3]
                        ).upper()
                        if screen_set.first_tournament_player_by_name
                        else '-',
                    )
                    text = text.replace(
                        '%l',
                        str(
                            screen_set.last_tournament_player_by_name.last_name[:3]
                        ).upper()
                        if screen_set.last_tournament_player_by_name
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
            case ScreenType.IMAGE:
                menu_text = self.stored_screen.menu_text if self.stored_screen else None
                return menu_text or self.name
            case _:
                raise ValueError(f'type=[{self.type}]')

    def _menu_screens(self, admin: bool) -> list['Screen']:
        """The navigation entries shown on this screen: the resolved screens
        of the menu this screen belongs to. A screen belongs to at most one
        menu; the menu is only displayed when it holds more than one screen
        visible to the viewer."""
        for menu in self.event.sorted_menus:
            resolved = menu.resolved_screens()
            if not any(screen.uniq_id == self.uniq_id for screen in resolved):
                continue
            entries = (
                resolved if admin else [screen for screen in resolved if screen.public]
            )
            return entries if len(entries) > 1 else []
        return []

    @cached_property
    def public_menu_screens(self) -> list['Screen']:
        return self._menu_screens(False)

    @cached_property
    def admin_menu_screens(self) -> list['Screen']:
        return self._menu_screens(True)

    def _menu_nav_entries(self, admin: bool) -> list['MenuNavEntry']:
        from data.menu import group_menu_nav_entries

        return group_menu_nav_entries(self._menu_screens(admin))

    @cached_property
    def public_menu_nav_entries(self) -> list['MenuNavEntry']:
        return self._menu_nav_entries(False)

    @cached_property
    def admin_menu_nav_entries(self) -> list['MenuNavEntry']:
        return self._menu_nav_entries(True)

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
        return {screen_set.uniq_id: screen_set for screen_set in self.screen_sets}

    @cached_property
    def sorted_screen_sets(self) -> list[ScreenSet]:
        return sorted(
            self.screen_sets,
            key=lambda screen_set: screen_set.order or 0,
        )

    @property
    def input_exit_button(self) -> bool:
        if self.stored_screen:
            exit_button = self.stored_screen.input_exit_button
            assert exit_button is not None
            return exit_button
        else:
            if self.family is None:
                raise RuntimeError('Family reference unexpectedly None')
            return self.family.input_exit_button

    @property
    def players_show_unpaired(self) -> bool:
        match self.type:
            case ScreenType.BOARDS | ScreenType.INPUT | ScreenType.CHECK_IN:
                # Needed to display the players before the first round is paired
                return True
            case ScreenType.PLAYERS:
                if self.stored_screen:
                    show_unpaired = self.stored_screen.players_show_unpaired
                    assert show_unpaired is not None
                    return show_unpaired
                else:
                    if self.family is None:
                        raise RuntimeError('Family reference unexpectedly None')
                    return self.family.players_show_unpaired
            case _:
                raise ValueError(f'type=[{self.type}]')

    @property
    def players_player_format(self) -> PlayersScreenPlayerFormat:
        if self.type != ScreenType.PLAYERS:
            raise ValueError(f'type=[{self.type}]')
        if self.stored_screen:
            player_format = self.stored_screen.players_player_format
            assert player_format is not None
            return PlayersScreenPlayerFormat(player_format)
        else:
            if self.family is None:
                raise RuntimeError('Family reference unexpectedly None')
            return self.family.players_player_format

    @property
    def players_board_format(self) -> PlayersScreenBoardFormat:
        if self.type != ScreenType.PLAYERS:
            raise ValueError(f'type=[{self.type}]')
        if self.stored_screen:
            board_format = self.stored_screen.players_board_format
            assert board_format is not None
            return PlayersScreenBoardFormat(board_format)
        elif self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        return self.family.players_board_format

    @property
    def players_opponent_format(self) -> PlayersScreenOpponentFormat:
        if self.type != ScreenType.PLAYERS:
            raise ValueError(f'type=[{self.type}]')
        if self.stored_screen:
            opponent_format = self.stored_screen.players_opponent_format
            assert opponent_format is not None
            return PlayersScreenOpponentFormat(opponent_format)
        else:
            if self.family is None:
                raise RuntimeError('Family reference unexpectedly None')
            return self.family.players_opponent_format

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
                (
                    self.event.tournaments_by_id[tournament_id].name
                    for tournament_id in self.results_tournament_ids
                ),
                key=normalized_key,
            )
        )

    @cached_property
    def _results(self) -> list[Board]:
        boards: list[Board] = []
        oldest = datetime.now() - timedelta(minutes=self.results_max_age)
        for tournament in self.event.tournaments:
            if (
                self.results_tournament_ids
                and tournament.id not in self.results_tournament_ids
            ):
                continue
            for board in tournament.get_round_boards(tournament.current_round):
                if board.last_result_update and board.last_result_update >= oldest:
                    boards.append(board)
        boards.sort(key=lambda b: b.last_result_update or datetime.min, reverse=True)
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
