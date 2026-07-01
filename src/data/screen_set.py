import math
import weakref
from collections.abc import Iterable
from itertools import chain
from typing import Any, TYPE_CHECKING, Optional
from _weakref import ReferenceType

from common.i18n import _
from data.board import Board
from data.player import TournamentPlayer
from datetime import datetime

from utils.enum import (
    ScreenType,
    PlayersScreenPlayerFormat,
    PlayersScreenBoardFormat,
    PlayersScreenOpponentFormat,
)
from database.sqlite.event.event_store import StoredScreenSet

if TYPE_CHECKING:
    from data.event import Event
    from data.screen import Screen
    from data.family import Family
    from data.team_board import TeamBoard
    from data.tournament import Tournament


class ScreenSet:
    """A data wrapper around a stored screen set."""

    def __init__(
        self,
        screen: 'Screen',
        stored_screen_set: StoredScreenSet | None = None,
        family: Optional['Family'] = None,
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
        self._family_ref: 'ReferenceType[Family] | None' = (
            weakref.ref(family) if family else None
        )
        self.family_part: int | None = family_part
        self.uniq_id: str
        if self.stored_screen_set:
            self.uniq_id = f'{self.screen.uniq_id}_{self.stored_screen_set.order:03}'
        else:
            self.uniq_id = f'{self.screen.uniq_id}_{self.family_part:03}'
        fixed_boards_str: str | None = (
            self.stored_screen_set.fixed_boards_str
            if self.screen.type in [ScreenType.BOARDS, ScreenType.INPUT]
            and self.stored_screen_set
            else None
        )
        self.fixed_board_numbers: list[int] | None = None
        self.first: int = 0
        self.last: int = 0
        if self.stored_screen_set:
            if fixed_boards_str is not None:
                if fixed_boards_str:
                    self.fixed_board_numbers = []
                    for fixed_board_str in list(
                        map(str.strip, fixed_boards_str.split(','))
                    ):
                        if fixed_board_str:
                            assert fixed_board_str.isdigit()  # validated by the form
                            self.fixed_board_numbers.append(int(fixed_board_str))
                else:
                    self.fixed_board_numbers = [
                        tournament_player.fixed
                        for tournament_player in self.tournament.tournament_players_by_id.values()
                        if tournament_player.fixed
                    ]
            else:
                if self.stored_screen_set.first:
                    self.first = max(1, self.stored_screen_set.first)
                if self.stored_screen_set.last:
                    self.last = max(1, self.stored_screen_set.last)
                    if self.first:
                        self.last = max(self.first, self.last)
        else:
            assert self.family is not None
            self.fixed_board_numbers = []
            if (
                self.family.calculated_first
                and self.family.calculated_last
                and self.family.calculated_number
                and self.family_part
            ):
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
        self.first_item: Any | None = (
            None  # change this to Board | TournamentPlayer | None ?
        )
        self.last_item: Any | None = (
            None  # change this to Board | TournamentPlayer | None ?
        )
        self.items_lists: list[list[Any]] | None = (
            None  # change this to Board | TournamentPlayer | None ?
        )
        # Team-mode extractions cache separately: the player/board cache
        # above may already be filled by an individual-path caller (e.g.
        # the screen title) within the same request.
        self._team_first_item: Any | None = None
        self._team_last_item: Any | None = None
        self._team_items_lists: list[list[Any]] | None = None

    @property
    def screen(self) -> 'Screen':
        screen = self._screen_ref()
        if screen is None:
            raise RuntimeError('Screen reference has been garbage collected')
        return screen

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
        if self.stored_screen_set:
            return self.stored_screen_set.tournament_id
        if self.family is None:
            raise RuntimeError('Family reference unexpectedly None')
        return self.family.tournament_id

    @property
    def tournament(self) -> 'Tournament':
        return self.event.tournaments_by_id[self.tournament_id]

    @property
    def shows_team_matches(self) -> bool:
        """Whether the boards/input rendering shows team-match blocks:
        only team-vs-team pairing systems have match envelopes — flat
        fixed-table systems (e.g. Molter) keep the individual board
        list even in a team event."""
        return (
            self.tournament.is_team_tournament
            and self.tournament.pairing_system.paired_by_team
        )

    @property
    def columns(self) -> int:
        return self.screen.columns

    @property
    def players_show_unpaired(self) -> bool:
        return self.screen.players_show_unpaired

    @property
    def players_player_format(self) -> PlayersScreenPlayerFormat:
        return self.screen.players_player_format

    @property
    def players_board_format(self) -> PlayersScreenBoardFormat:
        return self.screen.players_board_format

    @property
    def players_opponent_format(self) -> PlayersScreenOpponentFormat:
        return self.screen.players_opponent_format

    @property
    def name_for_boards(self) -> str:
        if self.tournament.current_round:
            if self.shows_team_matches:
                return self._name_for_team_matches()
            self._extract_boards()
            if self.stored_screen_set:
                name = self.stored_screen_set.name
            else:
                if self.family is None:
                    raise RuntimeError('Family reference unexpectedly None')
                name = self.family.name
            if name is None:
                if self.first or self.last:
                    name = _('Boards %f-%l')
                else:
                    name = '%t'
            name = name.replace('%t', str(self.tournament.name))
            if r'%f' in name and self.first_board is not None:
                name = name.replace(
                    r'%f',
                    str(self.first_board.id + self.tournament.first_board_number - 1)
                    if self.first_board and self.first_board.id is not None
                    else '-',
                )
            if r'%l' in name and self.last_board is not None:
                name = name.replace(
                    r'%l',
                    str(self.last_board.id + self.tournament.first_board_number - 1)
                    if self.last_board and self.last_board.id is not None
                    else '-',
                )
            return name
        else:
            return self.name_for_players

    def _name_for_team_matches(self) -> str:
        """Set title in team mode: ``%f``/``%l`` are the first and last
        match table numbers shown by the set."""
        self._extract_team_matches()
        if self.stored_screen_set:
            name = self.stored_screen_set.name
        else:
            if self.family is None:
                raise RuntimeError('Family reference unexpectedly None')
            name = self.family.name
        if name is None:
            if self.first or self.last:
                name = _('Matches %f-%l')
            else:
                name = '%t'
        name = name.replace('%t', str(self.tournament.name))
        first_match = self._team_first_item
        last_match = self._team_last_item
        if r'%f' in name:
            name = name.replace(
                r'%f',
                str(first_match.display_number)
                if first_match is not None and first_match.display_number is not None
                else '-',
            )
        if r'%l' in name:
            name = name.replace(
                r'%l',
                str(last_match.display_number)
                if last_match is not None and last_match.display_number is not None
                else '-',
            )
        return name

    @property
    def name_for_players(self) -> str:
        self._extract_players_by_name()
        if self.stored_screen_set:
            name = self.stored_screen_set.name
        else:
            assert self.family is not None
            name = self.family.name
        if name is None:
            if self.first or self.last:
                name = _('%f to %l')
            else:
                name = '%t'
        name = name.replace('%t', str(self.tournament.name))
        if self.first_tournament_player_by_name is not None:
            name = name.replace(
                '%f', self.first_tournament_player_by_name.last_name[:8]
            )
        if self.last_tournament_player_by_name is not None:
            name = name.replace('%l', self.last_tournament_player_by_name.last_name[:8])
        return name

    @property
    def ranking_round(self) -> int:
        return self.tournament.correct_ranking_round(self.screen.ranking_round)

    @property
    def ranking_crosstable(self) -> bool:
        return self.screen.ranking_crosstable

    @property
    def ranking_min_points(self) -> float | None:
        return self.screen.ranking_min_points

    @property
    def ranking_max_points(self) -> float | None:
        return self.screen.ranking_max_points

    @property
    def name_for_ranking(self) -> str:
        if self.tournament.is_team_tournament:
            return self._name_for_team_standings()
        self._extract_players_by_rank()
        if self.stored_screen_set:
            name = self.stored_screen_set.name
        else:
            assert self.family is not None
            name = self.family.name
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
        if self.first_tournament_player_by_rank is not None:
            name = name.replace(r'%f', str(self.first_tournament_player_by_rank.rank))
        if self.last_tournament_player_by_rank is not None:
            name = name.replace('%l', str(self.last_tournament_player_by_rank.rank))
        return name

    def _name_for_team_standings(self) -> str:
        """Set title for a team ranking: ``%f``/``%l`` are the first and
        last team ranks shown by the set."""
        self._extract_team_standings()
        if self.stored_screen_set:
            name = self.stored_screen_set.name
        else:
            assert self.family is not None
            name = self.family.name
        if name is None:
            if self.first or self.last:
                name = _('Ranking %f to %l')
            else:
                name = _('%t ranking')
        name = name.replace('%t', str(self.tournament.name))
        if self._team_first_item is not None:
            name = name.replace(r'%f', str(self._team_first_item['rank']))
        if self._team_last_item is not None:
            name = name.replace(r'%l', str(self._team_last_item['rank']))
        return name

    def _extract_team_data(self, items: list[Any]):
        """Slice ``items`` by ``first``/``last`` and split across the
        screen columns, caching into the team-mode fields (kept apart
        from the player/board cache — see ``__init__``)."""
        if not items:
            self._team_items_lists = [
                [],
            ] * self.columns
            return
        if self.first:
            first = max(1, min(self.first, len(items))) - 1
        else:
            first = 0
        if self.last:
            last = max(first, min(self.last, len(items)) - 1)
        else:
            last = len(items) - 1
        selected_items = items[first : last + 1]
        if not selected_items:
            self._team_items_lists = [
                [],
            ] * self.columns
            return
        self._team_first_item = selected_items[0]
        self._team_last_item = selected_items[-1]
        items_number = len(selected_items)
        q, r = divmod(items_number, self.columns)
        first_index = 0
        self._team_items_lists = []
        for _num in range(1, self.columns + 1):
            last_index = first_index + q
            more: int = min(r, 1)
            last_index += more
            r -= more
            self._team_items_lists.append(selected_items[first_index:last_index])
            first_index = last_index

    def _extract_data(self, items: list[Any], extract_boards: bool):
        if not items:
            self.items_lists = [
                [],
            ] * self.columns
            return
        # at first select the desired items
        first_index: int
        last_index: int
        if extract_boards and self.fixed_board_numbers:
            if TYPE_CHECKING:
                assert all(isinstance(item, Board) for item in items)
            selected_items = [
                board for board in items if board.number in self.fixed_board_numbers
            ]
        else:
            if self.first:
                first = max(1, min(self.first, len(items))) - 1
            else:
                first = 0
            if self.last:
                last = max(first, min(self.last, len(items)) - 1)
            else:
                last = len(items) - 1
            selected_slice = slice(first, last + 1)
            selected_items = items[selected_slice]
            if not selected_items:
                self.items_lists = [
                    [],
                ] * self.columns
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
            self._extract_data(items=self.tournament.boards, extract_boards=True)

    @property
    def boards_lists(self) -> list[list[Board]]:
        self._extract_boards()
        if TYPE_CHECKING:
            assert (
                isinstance(self.items_lists, list)
                and all(isinstance(item, list) for item in self.items_lists)
                and all(isinstance(item, Board) for item in chain(*self.items_lists))
            )
        return self.items_lists

    def _extract_team_matches(self):
        """Team-tournament counterpart of :meth:`_extract_boards`: the
        screen items are the round's numbered team matches (hidden byes
        carry no table) — ``first``/``last`` and the column split count
        matches, not the board rows they contain."""
        if self._team_items_lists is None:
            matches = sorted(
                (
                    team_board
                    for team_board in self.tournament.get_round_team_boards(
                        self.tournament.current_round
                    )
                    if team_board.display_number is not None
                ),
                key=lambda team_board: team_board.display_number or 0,
            )
            self._extract_team_data(items=matches)

    @property
    def team_matches_lists(self) -> 'list[list[TeamBoard]]':
        self._extract_team_matches()
        if TYPE_CHECKING:
            assert isinstance(self._team_items_lists, list)
        return self._team_items_lists

    @property
    def first_team_match(self) -> 'TeamBoard | None':
        self._extract_team_matches()
        return self._team_first_item

    @property
    def last_team_match(self) -> 'TeamBoard | None':
        self._extract_team_matches()
        return self._team_last_item

    @property
    def first_board(self) -> Board | None:
        self._extract_boards()
        if TYPE_CHECKING:
            assert self.first_item is None or isinstance(self.first_item, Board)
        return self.first_item

    @property
    def last_board(self) -> Board | None:
        self._extract_boards()
        if TYPE_CHECKING:
            assert self.last_item is None or isinstance(self.last_item, Board)
        return self.last_item

    def range_bounds(self) -> tuple[str, str]:
        """The first (``%f``) and last (``%l``) display values shown by this
        set, formatted as in the ``name_for_*`` titles. Used to resolve a
        family's overall range from its first and last screens."""
        dash = '-'
        screen_type = self.type
        tournament = self.tournament
        if (
            screen_type in (ScreenType.BOARDS, ScreenType.INPUT)
            and tournament.current_round
        ):
            if self.shows_team_matches:
                self._extract_team_matches()
                first, last = self._team_first_item, self._team_last_item
                return (
                    str(first.display_number)
                    if first is not None and first.display_number is not None
                    else dash,
                    str(last.display_number)
                    if last is not None and last.display_number is not None
                    else dash,
                )
            first_board, last_board = self.first_board, self.last_board
            offset = tournament.first_board_number - 1
            return (
                str(first_board.id + offset)
                if first_board and first_board.id is not None
                else dash,
                str(last_board.id + offset)
                if last_board and last_board.id is not None
                else dash,
            )
        if screen_type == ScreenType.RANKING:
            if tournament.is_team_tournament:
                self._extract_team_standings()
                first, last = self._team_first_item, self._team_last_item
                return (
                    str(first['rank']) if first is not None else dash,
                    str(last['rank']) if last is not None else dash,
                )
            first = self.first_tournament_player_by_rank
            last = self.last_tournament_player_by_rank
            return (
                str(first.rank) if first else dash,
                str(last.rank) if last else dash,
            )
        if screen_type == ScreenType.CHECK_IN and tournament.is_team_tournament:
            self._extract_teams_by_name()
            first, last = self._team_first_item, self._team_last_item
            return (
                first.name[:12] if first is not None else dash,
                last.name[:12] if last is not None else dash,
            )
        first = self.first_tournament_player_by_name
        last = self.last_tournament_player_by_name
        return (
            first.last_name[:8] if first else dash,
            last.last_name[:8] if last else dash,
        )

    def _extract_players_by_name(self):
        if self.items_lists is None:
            if self.players_show_unpaired:
                self._extract_data(
                    items=self.tournament.sorted_tournament_players,
                    extract_boards=False,
                )
            else:
                self._extract_data(
                    items=self.tournament.sorted_tournament_players_without_unpaired,
                    extract_boards=False,
                )

    @property
    def tournament_players_by_name_lists(self) -> list[list[TournamentPlayer]]:
        self._extract_players_by_name()
        if TYPE_CHECKING:
            assert (
                isinstance(self.items_lists, list)
                and all(isinstance(item, list) for item in self.items_lists)
                and all(
                    isinstance(item, TournamentPlayer)
                    for item in chain(*self.items_lists)
                )
            )
        return self.items_lists

    @property
    def tournament_players_by_name_tuple_lists(
        self,
    ) -> Iterable[tuple[list[TournamentPlayer], list[TournamentPlayer]]]:
        self._extract_players_by_name()
        if TYPE_CHECKING:
            assert (
                isinstance(self.items_lists, list)
                and all(isinstance(item, list) for item in self.items_lists)
                and all(
                    isinstance(item, TournamentPlayer)
                    for item in chain(*self.items_lists)
                )
            )
        players_by_name_lists: list[list[TournamentPlayer]] = self.items_lists
        for players_by_name in players_by_name_lists:
            yield (
                players_by_name[: (bound := math.ceil(len(players_by_name) / 2))],
                players_by_name[bound:],
            )

    @property
    def first_tournament_player_by_name(self) -> TournamentPlayer | None:
        self._extract_players_by_name()
        if TYPE_CHECKING:
            assert self.first_item is None or isinstance(
                self.first_item, TournamentPlayer
            )
        return self.first_item

    @property
    def last_tournament_player_by_name(self) -> TournamentPlayer | None:
        self._extract_players_by_name()
        if TYPE_CHECKING:
            assert self.last_item is None or isinstance(
                self.last_item, TournamentPlayer
            )
        return self.last_item

    def _extract_teams_by_name(self):
        """Team-tournament counterpart of :meth:`_extract_players_by_name`
        for the check-in screen: the items are the tournament's teams in
        name order."""
        if self._team_items_lists is None:
            self._extract_team_data(
                items=sorted(
                    (
                        team
                        for team in self.event.teams_by_id.values()
                        if team.tournament_id == self.tournament_id
                    ),
                    key=lambda team: team.name.lower(),
                )
            )

    @property
    def teams_by_name_lists(self) -> list[list[Any]]:
        """Per screen column, the column's teams (no tuple-splitting for
        correct column display).
        Counterpart to :attr:`tournament_players_by_name_lists` for teams."""
        self._extract_teams_by_name()
        if TYPE_CHECKING:
            assert isinstance(self._team_items_lists, list)
        return self._team_items_lists

    @property
    def teams_by_name_tuple_lists(self) -> 'Iterable[tuple[list[Any], list[Any]]]':
        """Per screen column, the column's teams split into two halves
        (mirroring :attr:`tournament_players_by_name_tuple_lists`)."""
        self._extract_teams_by_name()
        if TYPE_CHECKING:
            assert isinstance(self._team_items_lists, list)
        for teams_by_name in self._team_items_lists:
            yield (
                teams_by_name[: (bound := math.ceil(len(teams_by_name) / 2))],
                teams_by_name[bound:],
            )

    @property
    def first_team_by_name(self) -> Any | None:
        self._extract_teams_by_name()
        return self._team_first_item

    @property
    def last_team_by_name(self) -> Any | None:
        self._extract_teams_by_name()
        return self._team_last_item

    @property
    def first_team_standing(self) -> dict[str, Any] | None:
        self._extract_team_standings()
        return self._team_first_item

    @property
    def last_team_standing(self) -> dict[str, Any] | None:
        self._extract_team_standings()
        return self._team_last_item

    @property
    def name_for_teams(self) -> str:
        """Set title for the team check-in list: ``%f``/``%l`` are the
        first and last team names shown by the set."""
        self._extract_teams_by_name()
        if self.stored_screen_set:
            name = self.stored_screen_set.name
        else:
            assert self.family is not None
            name = self.family.name
        if name is None:
            if self.first or self.last:
                name = _('%f to %l')
            else:
                name = '%t'
        name = name.replace('%t', str(self.tournament.name))
        if self._team_first_item is not None:
            name = name.replace('%f', self._team_first_item.name[:12])
        if self._team_last_item is not None:
            name = name.replace('%l', self._team_last_item.name[:12])
        return name

    def _extract_team_standings(self):
        """Team-tournament counterpart of :meth:`_extract_players_by_rank`:
        the items are the team-standings rows (already ranked). The
        min/max-points window filters on the primary score (MP or GP,
        whichever ranks the tournament)."""
        if self._team_items_lists is None:
            from utils.enum import ScoreType

            primary_is_mp = (
                self.tournament.pairing_system.paired_by_team
                and self.tournament.primary_score == ScoreType.MATCH_POINTS
            )
            score_key = 'mp' if primary_is_mp else 'gp'
            self._extract_team_data(
                items=[
                    row
                    for row in self.tournament.team_standings(
                        after_round=self.ranking_round
                    )
                    if (
                        self.ranking_min_points is None
                        or row[score_key] >= self.ranking_min_points
                    )
                    and (
                        self.ranking_max_points is None
                        or row[score_key] <= self.ranking_max_points
                    )
                ]
            )

    @property
    def team_standings_lists(self) -> list[list[dict[str, Any]]]:
        self._extract_team_standings()
        if TYPE_CHECKING:
            assert isinstance(self._team_items_lists, list)
        return self._team_items_lists

    def _extract_players_by_rank(self):
        if self.items_lists is None:
            self.tournament.ensure_tournament_player_ranks_computed()
            self._extract_data(
                items=[
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
                ],
                extract_boards=False,
            )

    @property
    def tournament_players_by_rank_lists(self) -> list[list[TournamentPlayer]]:
        self._extract_players_by_rank()
        if TYPE_CHECKING:
            assert (
                isinstance(self.items_lists, list)
                and all(isinstance(item, list) for item in self.items_lists)
                and all(
                    isinstance(item, TournamentPlayer)
                    for item in chain(*self.items_lists)
                )
            )
        return self.items_lists

    @property
    def first_tournament_player_by_rank(self) -> TournamentPlayer | None:
        self._extract_players_by_rank()
        if TYPE_CHECKING:
            assert self.first_item is None or isinstance(
                self.first_item, TournamentPlayer
            )
        return self.first_item

    @property
    def last_tournament_player_by_rank(self) -> TournamentPlayer | None:
        self._extract_players_by_rank()
        if TYPE_CHECKING:
            assert self.last_item is None or isinstance(
                self.last_item, TournamentPlayer
            )
        return self.last_item

    @property
    def last_update(self) -> datetime:
        if self.stored_screen_set:
            return self.stored_screen_set.last_update
        else:
            assert self.family is not None
            return self.family.last_update

    @property
    def numbers_str(self) -> str:
        if self.fixed_board_numbers:
            return _('boards {board_numbers}').format(
                board_numbers=', '.join(map(str, self.fixed_board_numbers))
            )
        if self.type in [ScreenType.BOARDS, ScreenType.INPUT]:
            if self.shows_team_matches:
                match (self.first, self.last):
                    case (0, 0):
                        return _('all the matches')
                    case (first, 0) if first:
                        return _('matches from #{first} to end').format(first=first)
                    case (0, last) if last:
                        return _('matches from start to #{last}').format(last=last)
                    case (first, last):
                        return _('matches from #{first} to #{last}').format(
                            first=first, last=last
                        )
                    case _:
                        raise ValueError(f'first={self.first}, last={self.last}')
            match (self.first, self.last):
                case (0, 0):
                    return _('all the boards')
                case (first, 0) if first:
                    return _('boards from #{first} to end').format(
                        first=first + self.tournament.first_board_number - 1,
                    )
                case (0, last) if last:
                    return _('boards from start to #{last}').format(
                        last=last + self.tournament.first_board_number - 1,
                    )
                case (first, last):
                    return _('boards from #{first} to #{last}').format(
                        first=first + self.tournament.first_board_number - 1,
                        last=last + self.tournament.first_board_number - 1,
                    )
                case _:
                    raise ValueError(f'first={self.first}, last={self.last}')
        elif self.type in [ScreenType.PLAYERS, ScreenType.CHECK_IN]:
            if self.tournament.is_team_tournament:
                match (self.first, self.last):
                    case (0, 0):
                        return _('all the teams')
                    case (first, 0) if first:
                        return _('teams from #{first} to end').format(first=first)
                    case (0, last) if last:
                        return _('teams from start to #{last}').format(last=last)
                    case (first, last) if first and last:
                        return _('teams from #{first} to #{last}').format(
                            first=first, last=last
                        )
                    case _:
                        raise ValueError(f'first={self.first}, last={self.last}')
            match (self.first, self.last):
                case (0, 0):
                    return _('all the players')
                case (first, 0) if first:
                    return _('players from #{first} to end').format(first=first)
                case (0, last) if last:
                    return _('players from start to #{last}').format(last=last)
                case (first, last) if first and last:
                    return _('players from #{first} to #{last}').format(
                        first=first, last=last
                    )
                case _:
                    raise ValueError(f'first={self.first}, last={self.last}')
        else:
            match (self.first, self.last):
                case (0, 0):
                    return _('the whole ranking')
                case (first, 0) if first:
                    return _('ranking from #{first} to end').format(first=first)
                case (0, last) if last:
                    return _('ranking from start to #{last}').format(last=last)
                case (first, last) if first and last:
                    return _('ranking from #{first} to #{last}').format(
                        first=first, last=last
                    )
                case _:
                    raise ValueError(f'first={self.first}, last={self.last}')

    def __str__(self):
        return _('Tournament {tournament} ({numbers_str})').format(
            tournament=self.tournament.name, numbers_str=self.numbers_str
        )
