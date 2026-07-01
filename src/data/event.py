import copy
import itertools
from collections import defaultdict
from contextlib import suppress
from datetime import date, datetime
from functools import total_ordering, cached_property
from logging import Logger
from operator import attrgetter
from types import NotImplementedType
from typing import Collection, TYPE_CHECKING

from common.i18n import _
from common.i18n.utils import by, normalized_key
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.account import Account, Permission
from data.board import PlayerRatingType
from data.display_controller import DisplayController
from data.family import Family
from data.player import Player, TournamentPlayer
from data.player_categories import (
    PlayerCategory,
    NoCategory,
    JuniorCategory,
    SeniorCategory,
)
from data.rotator import Rotator
from data.menu import Menu
from data.screen import Screen
from data.team import Team, TeamGroup
from data.timer import Timer
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from plugins.manager import plugin_manager
from plugins.utils import PluginData, Plugin
from utils import Utils
from utils.date_time import format_date, format_date_range
from utils.enum import (
    EventType,
    RoleType,
    ScreenType,
    TournamentRating,
)
from database.sqlite.event.event_store import (
    StoredEvent,
    StoredPlayer,
    StoredAccount,
    StoredRotator,
    StoredMenu,
    StoredPermission,
    StoredRole,
    StoredTeam,
    StoredTeamGroup,
    StoredTimer,
)

if TYPE_CHECKING:
    from data.team_affiliation import TeamAffiliationSource

logger: Logger = get_logger()


@total_ordering
class Event:
    """A data wrapper around a StoredEvent."""

    def __init__(self, stored_event: StoredEvent):
        self.stored_event: StoredEvent = stored_event

    @staticmethod
    def plugin_data_class_by_plugin_id() -> dict[str, type[PluginData]]:
        return {
            plugin_id: plugin_data_class
            for plugin_id, plugin_data_class in plugin_manager.hook.get_event_plugin_data_class()
        }

    @property
    def uniq_id(self) -> str:
        return self.stored_event.uniq_id

    @property
    def name(self) -> str:
        return self.stored_event.name

    @cached_property
    def start_date(self) -> date:
        if not self.tournaments:
            return date.today()
        return min(tournament.start_date for tournament in self.tournaments)

    @cached_property
    def stop_date(self) -> date:
        if not self.tournaments:
            return date.today()
        return max(tournament.stop_date for tournament in self.tournaments)

    @property
    def start_date_str(self) -> str:
        return format_date(self.start_date)

    @property
    def stop_date_str(self) -> str:
        return format_date(self.stop_date)

    @property
    def date_range_str(self) -> str:
        return format_date_range(self.start_date, self.stop_date)

    @property
    def passed(self) -> bool:
        return self.stop_date < date.today()

    @property
    def coming(self) -> bool:
        return self.start_date > date.today()

    @property
    def current(self) -> bool:
        return self.start_date <= date.today() <= self.stop_date

    @property
    def federation(self) -> str:
        return self.stored_event.federation

    @property
    def event_type(self) -> EventType:
        return self.stored_event.event_type

    @property
    def is_team_event(self) -> bool:
        return self.event_type == EventType.TEAM

    @property
    def player_rating_type(self) -> PlayerRatingType:
        return PlayerRatingType(self.stored_event.player_rating_type)

    @property
    def default_tournament_rating(self) -> TournamentRating:
        """Time-control cadence used for ratings outside any tournament
        context (unassigned players / teams): the shared cadence when
        every tournament of the event uses the same one, Standard
        otherwise (multiple cadences or no tournament yet)."""
        cadences = {tournament.rating for tournament in self.tournaments}
        if len(cadences) == 1:
            return next(iter(cadences))
        return TournamentRating.STANDARD

    @property
    def allow_multi_tournament_players(self) -> bool:
        return (
            self.stored_event.allow_multi_tournament_players
            or self.has_multi_tournament_players
        )

    @cached_property
    def prize_currency(self) -> str:
        if stored := self.stored_event.prize_currency:
            return stored
        if federation := Utils.get_country_currency(self.federation):
            return federation
        if plugin := plugin_manager.hook_for_event(
            self, 'get_default_prize_currency'
        )():
            return plugin
        return SharlyChessConfig.default_prize_currency

    @cached_property
    def player_categories(self) -> list[PlayerCategory]:
        categories: list[PlayerCategory]
        if self.stored_event.age_categories:
            categories = sorted(
                PlayerCategory.from_id(category_id)
                for category_id in self.stored_event.age_categories
            )

        else:
            categories = copy.copy(
                SharlyChessConfig().default_player_category_set.categories
            )
        # Insert a category as filler for all the players not represented in the categories
        index: int = 0
        while index < len(categories) and isinstance(categories[index], JuniorCategory):
            index += 1
        if index == 0:  # No youth category
            # Add a youth category matching the min senior category's limit
            categories.insert(0, JuniorCategory(categories[0].age_limit))
        else:
            # Add a senior category matching the max youth category's limit
            categories.insert(index, SeniorCategory(categories[index - 1].age_limit))
        categories.insert(0, NoCategory())
        return categories

    @cached_property
    def junior_categories(self) -> list[JuniorCategory]:
        return [
            category
            for category in self.player_categories
            if isinstance(category, JuniorCategory)
        ]

    @cached_property
    def senior_categories(self) -> list[SeniorCategory]:
        return [
            category
            for category in self.player_categories
            if isinstance(category, SeniorCategory)
        ]

    @property
    def age_category_base_date(self) -> date | None:
        return self.stored_event.age_category_base_date

    @property
    def age_category_change_month(self) -> int:
        return self.stored_event.age_category_change_month

    @property
    def enabled_plugins(self) -> list[Plugin]:
        """The event's enabled plugins, excluding any that don't support
        the event's type (e.g. enabled before the type was set, or stored
        by an older version that didn't enforce type support)."""
        return [
            plugin
            for plugin_id in self.stored_event.enabled_plugins
            if (plugin := plugin_manager.plugins_by_id[plugin_id]).supports_event_type(
                self.event_type
            )
        ]

    @property
    def location(self) -> str | None:
        return self.stored_event.location

    @property
    def organiser_name(self) -> str | None:
        return self.stored_event.organiser_name

    @property
    def organiser_home_page(self) -> str | None:
        return self.stored_event.organiser_home_page

    @property
    def organiser_email(self) -> str | None:
        return self.stored_event.organiser_email

    @property
    def organiser_director(self) -> str | None:
        return self.stored_event.organiser_director

    @property
    def background_color(self) -> str:
        return (
            self.stored_event.background_color
            or SharlyChessConfig.default_background_color
        )

    @cached_property
    def timer_colors(self) -> dict[int, str]:
        colors = SharlyChessConfig.default_timer_colors
        stored_colors = self.stored_event.timer_colors
        if stored_colors is not None:
            for i in range(1, 4):
                if i in stored_colors and (color := stored_colors[i]) is not None:
                    colors[i] = color
        return colors

    @cached_property
    def timer_delays(self) -> dict[int, int]:
        delays = SharlyChessConfig.default_timer_delays
        stored_delays = self.stored_event.timer_delays
        if stored_delays is not None:
            for i in range(1, 4):
                if i in stored_delays and (delay := stored_delays[i]) is not None:
                    delays[i] = delay
        return delays

    @property
    def public(self) -> bool:
        return self.stored_event.public

    @property
    def message_text(self) -> str | None:
        return self.stored_event.message_text

    @property
    def message_color(self) -> str:
        return (
            self.stored_event.message_color or SharlyChessConfig.default_message_color
        )

    @property
    def message_background_color(self) -> str:
        return (
            self.stored_event.message_background_color
            or SharlyChessConfig.default_message_background_color
        )

    @property
    def screens(self) -> Collection[Screen]:
        return self.screens_by_uniq_id.values()

    @property
    def sorted_screens(self) -> list[Screen]:
        return sorted(self.screens, key=by('name'))

    @property
    def sorted_screens_by_screen_type(
        self,
    ) -> defaultdict[ScreenType, list[Screen]]:
        sorted_screens_by_screen_type: defaultdict[ScreenType, list[Screen]] = (
            defaultdict(list[Screen])
        )
        for screen in self.sorted_screens:
            sorted_screens_by_screen_type[screen.type].append(screen)
        return sorted_screens_by_screen_type

    @property
    def sorted_public_screens(self) -> list[Screen]:
        return [screen for screen in self.sorted_screens if screen.public]

    @property
    def sorted_public_screens_by_screen_type(
        self,
    ) -> defaultdict[ScreenType, list[Screen]]:
        sorted_public_screens_by_screen_type: defaultdict[ScreenType, list[Screen]] = (
            defaultdict(list[Screen])
        )
        for screen in self.sorted_public_screens:
            sorted_public_screens_by_screen_type[screen.type].append(screen)
        return sorted_public_screens_by_screen_type

    @property
    def rotators(self) -> Collection[Rotator]:
        return self.rotators_by_id.values()

    @cached_property
    def sorted_rotators(self) -> list[Rotator]:
        return sorted(self.rotators, key=by('name'))

    @cached_property
    def public_sorted_rotators(self) -> list[Rotator]:
        return [rotator for rotator in self.sorted_rotators if rotator.public]

    @property
    def last_update(self) -> datetime:
        return EventDatabase.database_modified_at(self.uniq_id)

    @cached_property
    def timers_by_id(self) -> dict[int, Timer]:
        timers_by_id: dict[int, Timer] = {
            stored_timer.id: Timer(self, stored_timer)
            for stored_timer in self.stored_event.stored_timers
            if stored_timer.id is not None
        }
        return timers_by_id

    @property
    def timers(self) -> Collection[Timer]:
        return self.timers_by_id.values()

    @property
    def timers_by_name(self) -> dict[str, Timer]:
        return {timer.name: timer for timer in self.timers}

    def get_unused_timer_name(self, base_name: str | None = None) -> str:
        """Returns the first unused timer name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)..."""
        return Utils.get_unused_item_name(
            base_name or _('New timer'), self.timers_by_name
        )

    def create_timer(self, stored_timer: StoredTimer) -> Timer:
        with EventDatabase(self.uniq_id, True) as database:
            timer_id = database.add_stored_timer(stored_timer)
            stored_timer.id = timer_id
            for stored_timer_hour in stored_timer.stored_timer_hours:
                stored_timer_hour.timer_id = timer_id
                stored_timer_hour.id = database.add_stored_timer_hour(stored_timer_hour)
        self.stored_event.stored_timers.append(stored_timer)
        timer = Timer(self, stored_timer)
        self.timers_by_id[timer.id] = timer
        return timer

    def delete_timer(self, timer: Timer):
        with EventDatabase(self.uniq_id, True) as database:
            database.delete_stored_timer(timer.id)
        with suppress(ValueError):
            self.stored_event.stored_timers.remove(timer.stored_timer)
        if timer.id in self.timers_by_id:
            del self.timers_by_id[timer.id]

    @property
    def tournaments(self) -> Collection[Tournament]:
        return self.tournaments_by_id.values()

    @cached_property
    def tournaments_by_id(self) -> dict[int, Tournament]:
        tournaments_by_id: dict[int, Tournament] = {
            stored_tournament.id: Tournament(self, stored_tournament)
            for stored_tournament in self.stored_event.stored_tournaments
            if stored_tournament.id is not None
        }
        return tournaments_by_id

    @cached_property
    def tournaments_by_name(self) -> dict[str, Tournament]:
        return {tournament.name: tournament for tournament in self.tournaments}

    @cached_property
    def sorted_tournaments(self) -> list[Tournament]:
        return sorted(self.tournaments, key=attrgetter('index'))

    @cached_property
    def sorted_not_finished_tournaments(self) -> list[Tournament]:
        return [
            tournament
            for tournament in self.sorted_tournaments
            if not tournament.finished
        ]

    @cached_property
    def player_distribution_error_message(self) -> str | None:
        """Returns an error message if distributing the player among the tournaments is not allowed, None otherwise."""
        if self.is_team_event:
            # Players belong to teams — distributing them individually
            # would tear the rosters apart.
            return _('Players cannot be distributed in a team event.')
        if not self.tournaments:
            return _('Can not distribute the players (no tournaments found).')
        if not self.player_count:
            return _('Can not distribute the players (no players found).')
        if len(self.tournaments) == 1:
            return _('Can not distribute the players (only one tournament).')
        if any(tournament.started for tournament in self.tournaments):
            return _(
                'Distributing the players is not allowed once one tournament is started.'
            )
        if any(
            tournament.rating != self.sorted_tournaments[0].rating
            for tournament in self.sorted_tournaments[1:]
        ):
            return _(
                'Distributing the players is allowed only if all the tournaments use the same rating.'
            )
        if error_message := plugin_manager.hook_for_event(
            self, 'player_distribution_error_message'
        )(event=self):
            return error_message
        return None

    @cached_property
    def plugin_data(self) -> dict[str, PluginData]:
        return {
            plugin_id: plugin_data_class.from_stored_value(
                self.stored_event.plugin_data.get(plugin_id, {})
            )
            for plugin_id, plugin_data_class in self.plugin_data_class_by_plugin_id().items()
        }

    # --------------------------------------------------------------------------
    # Players
    # --------------------------------------------------------------------------

    def clear_player_cache(self):
        Utils.reset_cached_properties(
            self,
            'player_count',
            'players_by_id',
            'sorted_players',
        )

    def add_player(
        self, stored_player: StoredPlayer, tournaments: list[Tournament]
    ) -> int:
        with EventDatabase(self.uniq_id, True) as database:
            stored_player.id = database.add_stored_player(stored_player)
            self.stored_event.stored_players.append(stored_player)
            self.clear_player_cache()
            for tournament in tournaments:
                tournament.add_player_to_tournament(stored_player, database)
        return stored_player.id

    def delete_player(self, player: Player):
        with EventDatabase(self.uniq_id, True) as database:
            database.delete_stored_player(player.id)
        del self.players_by_id[player.id]
        tournament = player.optional_single_tournament
        if tournament is not None:
            del tournament.tournament_players_by_id[player.id]
        plugin_manager.hook_for_event(self, 'on_player_deleted')(player=player)

    def update_player(self, player: Player, new_stored_player: StoredPlayer):
        new_stored_player.id = player.id
        new_stored_player.check_in = player.check_in
        player.replace_stored_player(new_stored_player)
        with EventDatabase(self.uniq_id, True) as database:
            database.update_stored_player(player.stored_player)

    def update_players(self, players: list[Player]):
        with EventDatabase(self.uniq_id, True) as database:
            for player in players:
                database.update_stored_player(player.stored_player)

    def _are_player_duplicates(self, stored_player: StoredPlayer, player: Player):
        if player.id == stored_player.id:
            return False
        if stored_player.date_of_birth and (
            stored_player.last_name,
            stored_player.first_name,
            stored_player.date_of_birth,
        ) == (player.last_name, player.first_name, player.date_of_birth):
            return True
        if stored_player.fide_id and stored_player.fide_id == player.fide_id:
            return True
        if any(
            plugin_manager.hook_for_event(self, 'are_players_duplicates')(
                stored_player=stored_player, player=player
            )
        ):
            return True
        return False

    def get_player_duplicate(
        self,
        stored_player: StoredPlayer,
        tournament: Tournament,
        player_id: int | None = None,
    ) -> Player | None:
        players = (
            tournament.tournament_players
            if self.allow_multi_tournament_players
            else self.players
        )
        return next(
            (
                player
                for player in players
                if player.id != player_id
                and self._are_player_duplicates(stored_player, player)
            ),
            None,
        )

    @cached_property
    def has_multi_tournament_players(self) -> bool:
        for ref_player in self.players:
            if any(
                self._are_player_duplicates(ref_player.stored_player, player)
                for player in self.players
            ):
                return True
        return False

    @property
    def player_count(self) -> int:
        return len(self.players_by_id)

    @property
    def team_count(self) -> int:
        return len(self.stored_event.stored_teams)

    @cached_property
    def players_by_id(self) -> dict[int, Player]:
        return {
            stored_player.id: Player(self, stored_player)
            for stored_player in self.stored_event.stored_players
            if stored_player.id is not None
        }

    @property
    def players(self) -> Collection[Player]:
        return self.players_by_id.values()

    @cached_property
    def sorted_players(self) -> list[Player]:
        return sorted(self.players, key=attrgetter('name_sort_key'))

    @property
    def tournament_players(self) -> list[TournamentPlayer]:
        return list(
            itertools.chain.from_iterable(
                [tournament.tournament_players for tournament in self.tournaments]
            )
        )

    def get_unused_tournament_name(
        self,
        base_name: str | None = None,
    ) -> str:
        """Returns the first unused tournament name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)..."""
        return Utils.get_unused_item_name(
            base_name or _('New tournament'),
            [tournament.name for tournament in self.tournaments],
        )

    def move_player_to_tournament(
        self, player: Player, destination_tournament: Tournament
    ):
        """Moves the given player from its current tournament to *destination_tournament*."""
        source_tournament = player.single_tournament
        with EventDatabase(self.uniq_id, write=True) as database:
            destination_tournament.add_player_to_tournament(
                player.stored_player, database
            )
            database.delete_stored_tournament_player(source_tournament.id, player.id)
            del source_tournament.tournament_players_by_id[player.id]
        player.optional_single_tournament_id = destination_tournament.id
        self.clear_player_cache()

    # --------------------------------------------------------------------------
    # Teams
    # --------------------------------------------------------------------------

    @cached_property
    def teams_by_id(self) -> dict[int, Team]:
        return {
            stored_team.id: Team(self, stored_team)
            for stored_team in self.stored_event.stored_teams
            if stored_team.id is not None
        }

    @property
    def teams(self) -> Collection[Team]:
        return self.teams_by_id.values()

    @cached_property
    def sorted_teams(self) -> list[Team]:
        return sorted(self.teams, key=attrgetter('name'))

    def clear_team_cache(self):
        Utils.reset_cached_properties(
            self, 'teams_by_id', 'sorted_teams', 'team_groups_by_id'
        )

    @cached_property
    def team_groups_by_id(self) -> dict[int, TeamGroup]:
        return {
            stored_team_group.id: TeamGroup(self, stored_team_group)
            for stored_team_group in self.stored_event.stored_team_groups
            if stored_team_group.id is not None
        }

    @property
    def team_groups(self) -> Collection[TeamGroup]:
        return self.team_groups_by_id.values()

    def team_group_team_counts(self) -> dict[int, int]:
        """How many teams reference each group id."""
        counts: dict[int, int] = {}
        for team in self.teams:
            if team.group_id is not None:
                counts[team.group_id] = counts.get(team.group_id, 0) + 1
        return counts

    def add_team_group(self, name: str) -> TeamGroup:
        with EventDatabase(self.uniq_id, True) as database:
            group_id = database.add_stored_team_group(name)
            self.stored_event.stored_team_groups.append(
                StoredTeamGroup(id=group_id, name=name)
            )
        self.clear_team_cache()
        return self.team_groups_by_id[group_id]

    def find_or_create_team_group(self, name: str) -> TeamGroup:
        """Reuse the team group with this name (case-insensitive) or create
        one. Used when filling affiliations in bulk."""
        for group in self.team_groups:
            if group.name.lower() == name.lower():
                return group
        return self.add_team_group(name)

    def team_affiliation_sources(self) -> 'list[TeamAffiliationSource]':
        """The ways a team's affiliation can be derived from its players —
        core (the players' common club) plus any contributed by plugins."""
        from data.team_affiliation import core_team_affiliation_sources
        from plugins.manager import plugin_manager

        sources = list(core_team_affiliation_sources())
        for plugin_result in plugin_manager.hook_for_event(
            self, 'get_team_affiliation_sources'
        )():
            if plugin_result:
                sources.extend(plugin_result)
        return sources

    def update_team_group(self, group_id: int, name: str):
        with EventDatabase(self.uniq_id, True) as database:
            database.update_stored_team_group(group_id, name)
        for stored_team_group in self.stored_event.stored_team_groups:
            if stored_team_group.id == group_id:
                stored_team_group.name = name
        self.clear_team_cache()

    def delete_team_group(self, group_id: int):
        with EventDatabase(self.uniq_id, True) as database:
            database.delete_stored_team_group(group_id)
        self.stored_event.stored_team_groups = [
            stored_team_group
            for stored_team_group in self.stored_event.stored_team_groups
            if stored_team_group.id != group_id
        ]
        # Detach the group from any team that referenced it (the DB FK
        # already set those to NULL via ON DELETE SET NULL).
        for stored_team in self.stored_event.stored_teams:
            if stored_team.group_id == group_id:
                stored_team.group_id = None
        self.clear_team_cache()

    def add_team(self, stored_team: StoredTeam) -> Team:
        with EventDatabase(self.uniq_id, True) as database:
            stored_team.id = database.add_stored_team(stored_team)
            self.stored_event.stored_teams.append(stored_team)
        self.clear_team_cache()
        for tournament in self.tournaments:
            tournament.clear_team_cache()
        return self.teams_by_id[stored_team.id]

    def delete_team(self, team: Team):
        with EventDatabase(self.uniq_id, True) as database:
            database.delete_stored_team(team.id)
        self.stored_event.stored_teams = [
            stored_team
            for stored_team in self.stored_event.stored_teams
            if stored_team.id != team.id
        ]
        self.clear_team_cache()
        for tournament in self.tournaments:
            tournament.clear_team_cache()

    @cached_property
    def basic_screens_by_id(self) -> dict[int, Screen]:
        screens_by_id: dict[int, Screen] = {
            stored_screen.id: Screen(self, stored_screen=stored_screen)
            for stored_screen in self.stored_event.stored_screens
            if stored_screen.id is not None
        }
        return screens_by_id

    @property
    def basic_screens(self) -> Collection[Screen]:
        return self.basic_screens_by_id.values()

    @cached_property
    def basic_screens_by_uniq_id(self) -> dict[str, Screen]:
        return {screen.uniq_id: screen for screen in self.basic_screens}

    @cached_property
    def sorted_basic_screens(self) -> list[Screen]:
        return sorted(self.basic_screens, key=by('name'))

    def get_unused_screen_uniq_id(
        self,
        screen_type: ScreenType | None = None,
        base_uniq_id: str | None = None,
    ) -> str:
        """Returns the first unused screen uniq_id looking like base_uniq_id:
        base_uniq_id, or base_uniq_id-2, or base_uniq_id-n+1...
        screen_type is used when the given ID is empty to set an ID that corresponds to the screen type."""
        screen_uniq_id = base_uniq_id
        if screen_uniq_id is None:
            if screen_type is None:
                raise ValueError('Either screen_type or base_uniq_id must be provided.')
            screen_uniq_id = _('{screen_type}-screen').format(
                screen_type=screen_type.value
            )

        return Utils.get_unused_item_uniq_id(
            screen_uniq_id,
            self.basic_screens_by_uniq_id,
        )

    def get_unused_screen_name(
        self,
        screen_type: ScreenType,
        base_name: str | None = None,
    ) -> str:
        """Returns the first unused screen name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)...
        screen_type is used when the given name is empty to set a default name that corresponds to the screen type."""
        return Utils.get_unused_item_name(
            base_name or screen_type.name,
            [
                str(screen.name)
                for screen in self.basic_screens
                if screen.name is not None
            ],
        )

    @property
    def basic_screens_by_screen_type_by_id(
        self,
    ) -> defaultdict[ScreenType, dict[int, Screen]]:
        basic_screens_by_screen_type_by_id: defaultdict[
            ScreenType, dict[int, Screen]
        ] = defaultdict(dict[int, Screen])
        for screen in self.basic_screens:
            basic_screens_by_screen_type_by_id[screen.type][screen.id] = screen
        return basic_screens_by_screen_type_by_id

    @property
    def sorted_basic_screens_by_screen_type(
        self,
    ) -> defaultdict[ScreenType, list[Screen]]:
        sorted_basic_screens_by_screen_type: defaultdict[ScreenType, list[Screen]] = (
            defaultdict(list[Screen])
        )

        for screen_type in self.basic_screens_by_screen_type_by_id:
            sorted_basic_screens_by_screen_type[screen_type] = sorted(
                self.basic_screens_by_screen_type_by_id[screen_type].values(),
                key=by('uniq_id'),
            )
        return sorted_basic_screens_by_screen_type

    @cached_property
    def families_by_id(self) -> dict[int, Family]:
        families_by_id: dict[int, Family] = {
            stored_family.id: Family(self, stored_family=stored_family)
            for stored_family in self.stored_event.stored_families
            if stored_family.id is not None
        }
        return families_by_id

    @property
    def families(self) -> Collection[Family]:
        return self.families_by_id.values()

    @cached_property
    def sorted_families(self) -> list[Family]:
        return sorted(self.families, key=by('name'))

    @cached_property
    def families_by_uniq_id(self) -> dict[str, Family]:
        return {family.uniq_id: family for family in self.families}

    @property
    def families_by_screen_type(self) -> dict[ScreenType, list[Family]]:
        families_by_screen_type: dict[ScreenType, list[Family]] = defaultdict(list)
        for family in self.sorted_families:
            families_by_screen_type[family.type].append(family)
        return families_by_screen_type

    def get_unused_family_uniq_id(
        self,
        family_type: ScreenType | None = None,
        base_uniq_id: str | None = None,
    ) -> str:
        """Returns the first unused family uniq_id looking like base_uniq_id:
        base_uniq_id, or base_uniq_id-2, or base_uniq_id-n+1...
        family_type is used when the given ID is empty to set an ID that corresponds to the family type."""
        family_uniq_id = base_uniq_id
        if family_uniq_id is None:
            if family_type is None:
                raise ValueError('Either family_type or base_uniq_id must be provided.')
            family_uniq_id = _('{family_type}-screen').format(
                family_type=family_type.value
            )
        return Utils.get_unused_item_uniq_id(
            family_uniq_id,
            self.families_by_uniq_id,
        )

    def get_unused_family_name(
        self,
        family_type: ScreenType,
        base_name: str | None = None,
    ) -> str:
        """Returns the first unused family name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)...
        family_type is used when the given name is empty to set a name that corresponds to the family type."""
        return Utils.get_unused_item_name(
            base_name or family_type.name,
            [family.name for family in self.families],
        )

    @property
    def screens_by_uniq_id(self) -> dict[str, Screen]:
        screens_by_uniq_id: dict[str, Screen] = copy.copy(self.basic_screens_by_uniq_id)
        for family in self.families:
            screens_by_uniq_id |= family.screens_by_uniq_id
        return screens_by_uniq_id

    @property
    def family_screens_by_uniq_id(self) -> dict[str, Screen]:
        family_screens_by_uniq_id: dict[str, Screen] = {}
        for family in self.families:
            family_screens_by_uniq_id |= family.screens_by_uniq_id
        return family_screens_by_uniq_id

    @cached_property
    def rotators_by_id(self) -> dict[int, Rotator]:
        rotators_by_id: dict[int, Rotator] = {
            stored_rotator.id: Rotator(self, stored_rotator)
            for stored_rotator in self.stored_event.stored_rotators
            if stored_rotator.id is not None
        }
        return rotators_by_id

    @cached_property
    def rotators_by_name(self) -> dict[str, Rotator]:
        return {rotator.name: rotator for rotator in self.rotators}

    def get_unused_rotator_name(self, base_name: str | None = None) -> str:
        """Returns the first unused rotator name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)..."""
        return Utils.get_unused_item_name(
            base_name or _('New rotator'), self.rotators_by_name
        )

    def create_rotator(self, stored_rotator: StoredRotator) -> Rotator:
        with EventDatabase(self.uniq_id, True) as database:
            rotator_id = database.add_stored_rotator(stored_rotator)
            stored_rotator.id = rotator_id
            for rotating_screen in stored_rotator.stored_rotating_screens:
                rotating_screen.rotator_id = rotator_id
                rotating_screen.id = database.add_stored_rotating_screen(
                    rotating_screen
                )
        self.stored_event.stored_rotators.append(stored_rotator)
        rotator = Rotator(self, stored_rotator)
        self.rotators_by_id[rotator.id] = rotator
        return rotator

    def update_rotator(self, stored_rotator: StoredRotator):
        with EventDatabase(self.uniq_id, True) as database:
            database.update_stored_rotator(stored_rotator)

    def delete_rotator(self, rotator: Rotator):
        with EventDatabase(self.uniq_id, True) as database:
            database.delete_stored_rotator(rotator.id)
        with suppress(ValueError):
            self.stored_event.stored_rotators.remove(rotator.stored_rotator)
        if rotator.id in self.rotators_by_id:
            del self.rotators_by_id[rotator.id]

    @cached_property
    def menus_by_id(self) -> dict[int, Menu]:
        return {
            stored_menu.id: Menu(self, stored_menu)
            for stored_menu in self.stored_event.stored_menus
            if stored_menu.id is not None
        }

    @cached_property
    def menus_by_name(self) -> dict[str, Menu]:
        return {menu.name: menu for menu in self.menus_by_id.values()}

    @property
    def sorted_menus(self) -> list[Menu]:
        return sorted(self.menus_by_id.values(), key=by('name'))

    @property
    def public_sorted_menus(self) -> list[Menu]:
        return [menu for menu in self.sorted_menus if menu.public]

    def get_unused_menu_name(self, base_name: str | None = None) -> str:
        """Returns the first unused menu name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)..."""
        return Utils.get_unused_item_name(
            base_name or _('New menu'), self.menus_by_name
        )

    def create_menu(self, stored_menu: StoredMenu) -> Menu:
        with EventDatabase(self.uniq_id, True) as database:
            menu_id = database.add_stored_menu(stored_menu)
            stored_menu.id = menu_id
            for menu_item in stored_menu.stored_menu_items:
                menu_item.menu_id = menu_id
                menu_item.id = database.add_stored_menu_item(menu_item)
        self.stored_event.stored_menus.append(stored_menu)
        menu = Menu(self, stored_menu)
        self.menus_by_id[menu.id] = menu
        return menu

    def update_menu(self, stored_menu: StoredMenu):
        with EventDatabase(self.uniq_id, True) as database:
            database.update_stored_menu(stored_menu)

    def delete_menu(self, menu: Menu):
        with EventDatabase(self.uniq_id, True) as database:
            database.delete_stored_menu(menu.id)
        with suppress(ValueError):
            self.stored_event.stored_menus.remove(menu.stored_menu)
        if menu.id in self.menus_by_id:
            del self.menus_by_id[menu.id]

    @property
    def menu_claimed_screen_types(self) -> set[ScreenType]:
        """Screen types already used as an 'all screens of this type' item
        in some menu. A screen may only belong to a single menu."""
        return {
            screen_type
            for menu in self.menus_by_id.values()
            for screen_type in menu.screen_types
        }

    @property
    def menu_claimed_screen_ids(self) -> set[int]:
        """Ids of screens added individually to some menu."""
        return {
            screen.id for menu in self.menus_by_id.values() for screen in menu.screens
        }

    @property
    def menu_claimed_family_ids(self) -> set[int]:
        """Ids of families added to some menu."""
        return {
            family.id for menu in self.menus_by_id.values() for family in menu.families
        }

    @cached_property
    def display_controllers_by_id(self) -> dict[int, DisplayController]:
        display_controllers_by_id: dict[int, DisplayController] = {
            stored_display_controller.id: DisplayController(
                self, stored_display_controller
            )
            for stored_display_controller in self.stored_event.stored_display_controllers
            if stored_display_controller.id is not None
        }
        return display_controllers_by_id

    @property
    def display_controllers(self) -> Collection[DisplayController]:
        return self.display_controllers_by_id.values()

    @cached_property
    def display_controllers_by_name(self) -> dict[str, DisplayController]:
        return {
            display_controller.name: display_controller
            for display_controller in self.display_controllers
        }

    @cached_property
    def sorted_display_controllers(self) -> list[DisplayController]:
        return sorted(self.display_controllers, key=by('name'))

    @cached_property
    def sorted_public_display_controllers(self) -> list[DisplayController]:
        return [
            controller
            for controller in self.sorted_display_controllers
            if controller.public
        ]

    def get_unused_display_controller_name(
        self,
        base_name: str | None = None,
    ) -> str:
        """Returns the first unused display controller name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)..."""
        return Utils.get_unused_item_name(
            base_name or _('New display controller'),
            [
                display_controller.name
                for display_controller in self.display_controllers
            ],
        )

    # -------------------------------------------------------------------------
    # Accounts
    # -------------------------------------------------------------------------

    @property
    def predefined_accounts(self) -> bool:
        """Returns True if predefined accounts, False otherwise."""
        return not self.stored_event.stored_accounts

    @cached_property
    def accounts_by_id(self) -> dict[int, Account]:
        if self.predefined_accounts:
            return {
                account.id: account
                for account in [
                    Account.predefined_administrator_account(),
                    Account.predefined_anonymous_account(),
                ]
            }
        else:
            return {
                stored_account.id: Account(stored_account)
                for stored_account in self.stored_event.stored_accounts
                if stored_account.id is not None
            }

    @property
    def accounts(self) -> Collection[Account]:
        return self.accounts_by_id.values()

    def create_predefined_accounts(self):
        """Sets own accounts if not already done"""
        if not self.predefined_accounts:
            raise ValueError('Default accounts already exist.')
        with EventDatabase(self.uniq_id, True) as database:
            for account in self.accounts:
                stored_account = account.stored_account
                database.add_stored_account(stored_account)
                for stored_permission in stored_account.stored_permissions:
                    database.add_stored_permission(stored_permission)
                self.stored_event.stored_accounts.append(stored_account)

    def create_account(self, stored_account: StoredAccount) -> Account:
        if self.predefined_accounts:
            self.create_predefined_accounts()
        with EventDatabase(self.uniq_id, True) as database:
            account_id = database.add_stored_account(stored_account)
            stored_account.id = account_id
            for stored_permission in stored_account.stored_permissions:
                stored_permission.account_id = account_id
                database.add_stored_permission(stored_permission)
            for stored_role in stored_account.stored_roles:
                stored_role.account_id = account_id
                self.set_account_role(database, stored_role)
        self.stored_event.stored_accounts.append(stored_account)
        account = Account(stored_account)
        self.accounts_by_id[account.id] = account
        return account

    def update_account(self, stored_account: StoredAccount):
        with EventDatabase(self.uniq_id, True) as database:
            database.update_stored_account(stored_account)
            database.delete_stored_roles(account_id=stored_account.id)
            for stored_role in stored_account.stored_roles:
                stored_role.account_id = stored_account.id
                self.set_account_role(database, stored_role)

    def delete_account(self, account: Account):
        with EventDatabase(self.uniq_id, True) as database:
            database.delete_stored_account(account.id)
            database.commit()
        with suppress(ValueError):
            self.stored_event.stored_accounts.remove(account.stored_account)
        if account.id in self.accounts_by_id:
            del self.accounts_by_id[account.id]

    def set_account_role(
        self,
        database: EventDatabase,
        stored_role: StoredRole,
    ):
        assert stored_role.account_id is not None
        if stored_role.role == RoleType.CHIEF_ARBITER.value:
            # Delete any previous chief arbiter roles for these tournaments
            database.delete_stored_roles(
                role=RoleType.CHIEF_ARBITER.value,
                tournament_ids=stored_role.tournament_ids,
            )
        database.add_stored_roles(
            stored_role.account_id, stored_role.role, stored_role.tournament_ids
        )

    @staticmethod
    def _delete_redundant_account_permissions(
        account: Account, database: EventDatabase
    ):
        redundant_stored_permissions = [
            permission.stored_permission
            for permission in account.permissions
            if account.is_permission_redundant(permission)
        ]
        for stored_permission in redundant_stored_permissions:
            database.delete_stored_permission(stored_permission)
            account.stored_account.stored_permissions.remove(stored_permission)

    def add_account_permission(
        self, account: Account, stored_permission: StoredPermission
    ):
        with EventDatabase(self.uniq_id, True) as database:
            database.add_stored_permission(stored_permission)
            account.stored_account.stored_permissions.append(stored_permission)
            self._delete_redundant_account_permissions(account, database)

    def update_account_permission(
        self,
        account: Account,
        permission: Permission,
        stored_permission: StoredPermission,
    ):
        with EventDatabase(self.uniq_id, True) as database:
            database.delete_stored_permission(permission.stored_permission)
            database.add_stored_permission(stored_permission)
            stored_permissions = account.stored_account.stored_permissions
            stored_permissions.remove(permission.stored_permission)
            stored_permissions.append(stored_permission)
            self._delete_redundant_account_permissions(account, database)

    def delete_account_permission(self, account: Account, permission: Permission):
        stored_permission = permission.stored_permission
        with EventDatabase(self.uniq_id, True) as database:
            database.delete_stored_permission(stored_permission)
        account.stored_account.stored_permissions.remove(stored_permission)

    @property
    def sorted_accounts(self) -> list[Account]:
        return sorted(
            self.accounts,
            key=lambda account: (
                not account.administrator,
                account.anonymous,
                normalized_key(account.full_name),
            ),
        )

    @property
    def user_accounts_by_id(self) -> dict[int, Account]:
        return {
            account.id: account for account in self.accounts if account.user_account
        }

    @property
    def active_user_accounts_by_id(self) -> dict[int, Account]:
        return {
            account.id: account
            for account in self.accounts
            if account.user_account and account.active
        }

    @property
    def user_accounts_by_name(self) -> dict[str, Account]:
        return {
            account.full_name: account
            for account in self.accounts
            if account.user_account
        }

    @property
    def sorted_user_accounts(self) -> list[Account]:
        return sorted(
            self.user_accounts_by_name.values(),
            key=by('full_name'),
        )

    @property
    def active_user_accounts_by_name(self) -> dict[str, Account]:
        return {
            account.full_name: account
            for account in self.accounts
            if account.user_account and account.active
        }

    @property
    def sorted_active_user_accounts(self) -> list[Account]:
        return sorted(
            self.active_user_accounts_by_name.values(),
            key=by('full_name'),
        )

    @property
    def administrator_account(self) -> Account:
        return self.accounts_by_id[Account.ADMINISTRATOR_ID]

    @property
    def anonymous_account(self) -> Account:
        return self.accounts_by_id[Account.ANONYMOUS_ID]

    # -------------------------------------------------------------------------
    # Plugins
    # -------------------------------------------------------------------------

    def __lt__(self, other: 'Event'):
        # p1 < p2 calls p1.__lt__(p2)
        return self.uniq_id > other.uniq_id

    def __eq__(self, other: object) -> bool | NotImplementedType:
        # p1 == p2 calls p1.__eq__(p2)
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.uniq_id == other.uniq_id
