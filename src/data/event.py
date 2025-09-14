import copy
import time
from collections import defaultdict, Counter
from contextlib import suppress
from functools import total_ordering, cached_property
from logging import Logger
from operator import attrgetter
from types import NotImplementedType
from typing import Any, Iterable

from common import (
    format_timestamp_date_time,
    format_timestamp_date,
    format_timestamp_time,
)
from common.background import inline_image_url
from common.i18n import _
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.access_levels.entities import Account
from data.display_controller import DisplayController
from data.family import Family
from data.player import Player, Club, Federation
from data.rotator import Rotator
from data.screen import Screen
from data.timer import Timer
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from plugins.manager import plugin_manager
from utils import StaticUtils
from utils.enum import (
    ScreenType,
    PlayerGender,
)
from database.sqlite.event.event_store import (
    StoredEvent,
    StoredPlayer,
    StoredAccount,
    StoredRotator,
)

logger: Logger = get_logger()


@total_ordering
class Event:
    """A data wrapper around a StoredEvent."""

    def __init__(self, stored_event: StoredEvent):
        self.stored_event: StoredEvent = stored_event

    @property
    def uniq_id(self) -> str:
        return self.stored_event.uniq_id

    @property
    def name(self) -> str:
        return self.stored_event.name

    @property
    def start(self) -> float:
        return self.stored_event.start

    @property
    def stop(self) -> float:
        return self.stored_event.stop

    def passed(self, now: float | None = None) -> bool:
        return self.stored_event.stop < (now or time.time())

    def coming(self, now: float | None = None) -> bool:
        return self.stored_event.start > (now or time.time())

    def current(self, now: float | None = None) -> bool:
        now = now or time.time()
        return not self.passed(now) and not self.coming(now)

    @property
    def federation(self) -> str:
        return self.stored_event.federation

    @cached_property
    def prize_currency(self) -> str:
        if stored := self.stored_event.prize_currency:
            return stored
        if federation := StaticUtils.get_country_currency(self.federation):
            return federation
        if plugin := plugin_manager.hook.get_default_prize_currency():
            return plugin
        return SharlyChessConfig.default_prize_currency

    @property
    def override_unrated_rapid_blitz(self) -> bool:
        return self.stored_event.override_unrated_rapid_blitz or False

    @property
    def formatted_start_date_time(self) -> str:
        return format_timestamp_date_time(self.start)

    @property
    def formatted_start_date(self) -> str:
        return format_timestamp_date(self.start)

    @property
    def formatted_start_time(self) -> str:
        return format_timestamp_time(self.start)

    @property
    def formatted_stop_date_time(self) -> str:
        return format_timestamp_date_time(self.stop)

    @property
    def formatted_stop_date(self) -> str:
        return format_timestamp_date(self.stop)

    @property
    def formatted_stop_time(self) -> str:
        return format_timestamp_time(self.stop)

    @property
    def location(self) -> str | None:
        return self.stored_event.location

    @property
    def background_image(self) -> str:
        if self.stored_event.hide_background_image:
            return ''
        return (
            self.stored_event.background_image
            or SharlyChessConfig.default_background_image
        )

    @property
    def background_url(self) -> str:
        return inline_image_url(self.background_image)

    @property
    def background_color(self) -> str:
        return (
            self.stored_event.background_color
            or SharlyChessConfig.default_background_color
        )

    @cached_property
    def record_illegal_moves(self) -> int:
        return (
            self.stored_event.record_illegal_moves
            or SharlyChessConfig.default_record_illegal_moves_number
        )

    @property
    def rules(self) -> str | None:
        return self.stored_event.rules

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
    def screens_sorted_by_uniq_id(self) -> list[Screen]:
        return sorted(self.screens_by_uniq_id.values(), key=lambda screen: screen.name)

    @property
    def screens_by_screen_type_sorted_by_uniq_id(
        self,
    ) -> defaultdict[ScreenType, list[Screen]]:
        screens_of_type_sorted_by_uniq_id: defaultdict[ScreenType, list[Screen]] = (
            defaultdict(list[Screen])
        )
        for screen in self.screens_sorted_by_uniq_id:
            screens_of_type_sorted_by_uniq_id[screen.type].append(screen)
        return screens_of_type_sorted_by_uniq_id

    @property
    def public_screens_sorted_by_uniq_id(self) -> list[Screen]:
        return [screen for screen in self.screens_by_uniq_id.values() if screen.public]

    @property
    def public_screens_by_screen_type_sorted_by_uniq_id(
        self,
    ) -> defaultdict[ScreenType, list[Screen]]:
        public_screens_by_screen_type_sorted_by_uniq_id: defaultdict[
            ScreenType, list[Screen]
        ] = defaultdict(list[Screen])
        for screen in self.public_screens_sorted_by_uniq_id:
            public_screens_by_screen_type_sorted_by_uniq_id[screen.type].append(screen)
        return public_screens_by_screen_type_sorted_by_uniq_id

    @cached_property
    def rotators_sorted_by_uniq_id(self) -> list[Rotator]:
        return sorted(self.rotators_by_id.values(), key=lambda rotator: rotator.uniq_id)

    @cached_property
    def public_rotators_sorted_by_uniq_id(self) -> list[Rotator]:
        return sorted(
            filter(attrgetter('public'), self.rotators_by_id.values()),
            key=attrgetter('uniq_id'),
        )

    @property
    def last_update(self) -> float:
        return EventDatabase.database_modified_timestamp(self.uniq_id)

    @cached_property
    def last_update_str(self) -> str:
        return format_timestamp_date_time(self.last_update)

    @cached_property
    def timers_by_id(self) -> dict[int, Timer]:
        timers_by_id: dict[int, Timer] = {
            stored_timer.id: Timer(self, stored_timer)
            for stored_timer in self.stored_event.stored_timers
            if stored_timer.id is not None
        }
        return timers_by_id

    @cached_property
    def timers_by_uniq_id(self) -> dict[str, Timer]:
        return {timer.uniq_id: timer for timer in self.timers_by_id.values()}

    def get_unused_timer_name(self, base_name: str | None = None) -> str:
        """Returns the first unused timer name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)..."""
        return StaticUtils.get_unused_item_name(
            base_name or _('New timer'), self.timers_by_uniq_id
        )

    @property
    def tournaments(self) -> Iterable[Tournament]:
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
    def tournaments_by_uniq_id(self) -> dict[str, Tournament]:
        return {
            tournament.uniq_id: tournament
            for tournament in self.tournaments_by_id.values()
        }

    @cached_property
    def tournaments_sorted_by_uniq_id(self) -> list[Tournament]:
        return sorted(
            self.tournaments_by_id.values(), key=lambda tournament: tournament.uniq_id
        )

    @cached_property
    def not_finished_tournaments_sorted_by_uniq_id(self) -> list[Tournament]:
        """Returns the playing tournaments where the Papi file exists
        (useful not to create players when there is no Papi file)."""
        return [
            tournament
            for tournament in self.tournaments_sorted_by_uniq_id
            if not tournament.finished
        ]

    @property
    def player_addable_tournaments(self) -> list[Tournament]:
        """List of tournaments in which players can be added."""
        return [
            tournament
            for tournament in self.tournaments_sorted_by_uniq_id
            if tournament.can_add_players
        ]

    # --------------------------------------------------------------------------
    # Players
    # --------------------------------------------------------------------------

    def clear_player_cache(self):
        player_cached_property_names = [
            'player_count',
            'players_by_id',
            'players_sorted_by_name',
            'gender_counts',
            'federation_counts',
            'club_counts',
            'check_in_counts',
        ]
        for property_name in player_cached_property_names:
            if property_name in self.__dict__:
                del self.__dict__[property_name]

    def add_player(
        self, stored_player: StoredPlayer, tournaments: list[Tournament]
    ) -> int:
        with EventDatabase(self.uniq_id, True) as database:
            stored_player.id = database.add_stored_player(stored_player)
            for tournament in tournaments:
                tournament.add_player_to_tournament(stored_player, database)
        return stored_player.id

    def delete_player(self, player_id: int):
        with EventDatabase(self.uniq_id, True) as database:
            database.delete_stored_player(player_id)

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

    @cached_property
    def player_count(self) -> int:
        return len(self.players_by_id)

    @cached_property
    def players_by_id(self) -> dict[int, Player]:
        return {
            player_id: player
            for tournament_players_id in [
                tournament.players_by_id
                for tournament in self.tournaments_by_id.values()
            ]
            for player_id, player in tournament_players_id.items()
        }

    @cached_property
    def players_sorted_by_name(self) -> list[Player]:
        return sorted(
            self.players_by_id.values(),
            key=lambda player: (player.last_name, player.first_name or ''),
        )

    @cached_property
    def gender_counts(self) -> Counter[PlayerGender]:
        counter: Counter[PlayerGender] = Counter[PlayerGender]()
        for tournament in self.tournaments_by_id.values():
            for gender in tournament.gender_counts:
                counter[gender] += tournament.gender_counts[gender]
        return counter

    @cached_property
    def federation_counts(self) -> Counter[Federation]:
        counter: Counter[Federation] = Counter[Federation]()
        for tournament in self.tournaments_by_id.values():
            for federation in tournament.federation_counts:
                counter[federation] += tournament.federation_counts[federation]
        return counter

    @cached_property
    def club_counts(self) -> Counter[Club]:
        counter: Counter[Club] = Counter[Club]()
        for tournament in self.tournaments_by_id.values():
            for club in tournament.club_counts:
                counter[club] += tournament.club_counts[club]
        return counter

    @cached_property
    def check_in_counts(self) -> Counter[bool | None]:
        counter: Counter[bool | None] = Counter[bool | None]()
        for tournament in self.tournaments_by_id.values():
            for check_in in tournament.players_by_check_in_status:
                counter[check_in] += tournament.check_in_counts[check_in]
        return counter

    def get_unused_tournament_name(
        self,
        base_name: str | None = None,
    ) -> str:
        """Returns the first unused tournament name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)..."""
        return StaticUtils.get_unused_item_name(
            base_name or _('New tournament'),
            [tournament.name for tournament in self.tournaments_by_id.values()],
        )

    def move_player_to_tournament(
        self, player: Player, destination_tournament: Tournament
    ):
        """Moves the given player from its current tournament to *destination_tournament*."""
        source_tournament = player.tournament
        with EventDatabase(self.uniq_id, write=True) as database:
            destination_tournament.add_player_to_tournament(
                player.stored_player, database
            )
            database.delete_stored_tournament_player(source_tournament.id, player.id)
            del source_tournament.players_by_id[player.id]
            player.stored_tournament_player = (
                database.load_player_stored_tournament_player(player.id)
            )

    @cached_property
    def basic_screens_by_id(self) -> dict[int, Screen]:
        screens_by_id: dict[int, Screen] = {
            stored_screen.id: Screen(self, stored_screen=stored_screen)
            for stored_screen in self.stored_event.stored_screens
            if stored_screen.id is not None
        }
        return screens_by_id

    @cached_property
    def basic_screens_by_uniq_id(self) -> dict[str, Screen]:
        return {screen.uniq_id: screen for screen in self.basic_screens_by_id.values()}

    @cached_property
    def basic_screens_sorted_by_name(self) -> list[Screen]:
        return sorted(self.basic_screens_by_id.values(), key=lambda screen: screen.name)

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

        return StaticUtils.get_unused_item_uniq_id(
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
        return StaticUtils.get_unused_item_name(
            base_name or screen_type.name,
            [
                str(screen.name)
                for screen in self.basic_screens_by_id.values()
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
        for screen in self.basic_screens_by_id.values():
            basic_screens_by_screen_type_by_id[screen.type][screen.id] = screen
        return basic_screens_by_screen_type_by_id

    @property
    def basic_screens_by_screen_type_sorted_by_uniq_id(
        self,
    ) -> defaultdict[ScreenType, list[Screen]]:
        basic_screens_by_screen_type_sorted_by_uniq_id: defaultdict[
            ScreenType, list[Screen]
        ] = defaultdict(list[Screen])
        for screen_type in self.basic_screens_by_screen_type_by_id:
            basic_screens_by_screen_type_sorted_by_uniq_id[screen_type] = sorted(
                self.basic_screens_by_screen_type_by_id[screen_type].values(),
                key=lambda screen: screen.uniq_id,
            )
        return basic_screens_by_screen_type_sorted_by_uniq_id

    @cached_property
    def families_by_id(self) -> dict[int, Family]:
        families_by_id: dict[int, Family] = {
            stored_family.id: Family(self, stored_family=stored_family)
            for stored_family in self.stored_event.stored_families
            if stored_family.id is not None
        }
        return families_by_id

    @cached_property
    def families_sorted_by_name(self) -> list[Family]:
        return sorted(self.families_by_id.values(), key=lambda family: family.name)

    @cached_property
    def families_by_uniq_id(self) -> dict[str, Family]:
        return {family.uniq_id: family for family in self.families_by_id.values()}

    @property
    def families_by_screen_type(self) -> dict[ScreenType, list[Family]]:
        families_by_screen_type: dict[ScreenType, list[Family]] = defaultdict(list)
        for family in self.families_sorted_by_name:
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
        return StaticUtils.get_unused_item_uniq_id(
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
        return StaticUtils.get_unused_item_name(
            base_name or family_type.name,
            [screen.name for screen in self.families_by_id.values()],
        )

    @property
    def screens_by_uniq_id(self) -> dict[str, Screen]:
        screens_by_uniq_id: dict[str, Screen] = copy.copy(self.basic_screens_by_uniq_id)
        for family in self.families_by_id.values():
            screens_by_uniq_id |= family.screens_by_uniq_id
        return screens_by_uniq_id

    @property
    def family_screens_by_uniq_id(self) -> dict[str, Screen]:
        family_screens_by_uniq_id: dict[str, Screen] = {}
        for family in self.families_by_id.values():
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
    def rotators_by_uniq_id(self) -> dict[str, Rotator]:
        return {rotator.uniq_id: rotator for rotator in self.rotators_by_id.values()}

    def get_unused_rotator_name(self, base_name: str | None = None) -> str:
        """Returns the first unused rotator name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)..."""
        return StaticUtils.get_unused_item_name(
            base_name or _('New rotator'), self.rotators_by_uniq_id
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
    def display_controllers_by_id(self) -> dict[int, DisplayController]:
        display_controllers_by_id: dict[int, DisplayController] = {
            stored_display_controller.id: DisplayController(
                self, stored_display_controller
            )
            for stored_display_controller in self.stored_event.stored_display_controllers
            if stored_display_controller.id is not None
        }
        return display_controllers_by_id

    @cached_property
    def display_controllers_by_uniq_id(self) -> dict[str, DisplayController]:
        return {
            display_controller.uniq_id: display_controller
            for display_controller in self.display_controllers_by_id.values()
        }

    @cached_property
    def display_controllers_sorted_by_uniq_id(self) -> list[DisplayController]:
        return sorted(
            self.display_controllers_by_id.values(),
            key=attrgetter('uniq_id'),
        )

    @cached_property
    def public_display_controllers_sorted_by_uniq_id(self) -> list[DisplayController]:
        return sorted(
            filter(attrgetter('public'), self.display_controllers_by_id.values()),
            key=attrgetter('uniq_id'),
        )

    def get_unused_display_controller_name(
        self,
        base_name: str | None = None,
    ) -> str:
        """Returns the first unused display controller name looking like base_name:
        base_name, or base_name (2), or base_name (n+1)..."""
        return StaticUtils.get_unused_item_name(
            base_name or _('New display controller'),
            [
                display_controller.name
                for display_controller in self.display_controllers_by_id.values()
            ],
        )

    # -------------------------------------------------------------------------
    # Accounts
    # -------------------------------------------------------------------------

    @cached_property
    def accounts_by_id(self) -> dict[int, Account]:
        return {
            stored_account.id: Account(stored_account)
            for stored_account in self.stored_event.stored_accounts
            if stored_account.id is not None
        }

    def create_account(self, stored_account: StoredAccount) -> Account:
        with EventDatabase(self.uniq_id, True) as database:
            stored_account = database.add_stored_account(stored_account)
        self.stored_event.stored_accounts.append(stored_account)
        account = Account(stored_account)
        self.accounts_by_id[account.id] = account
        return account

    def update_account(self, stored_account: StoredAccount):
        with EventDatabase(self.uniq_id, True) as database:
            database.update_stored_account(stored_account)

    def delete_account(self, account: Account):
        with EventDatabase(self.uniq_id, True) as database:
            database.delete_stored_account(account.id)
            database.commit()
        with suppress(ValueError):
            self.stored_event.stored_accounts.remove(account.stored_account)
        if account.id in self.accounts_by_id:
            del self.accounts_by_id[account.id]

    @property
    def accounts_sorted_by_name(self) -> list[Account]:
        return sorted(
            self.accounts_by_id.values(),
            key=lambda account: (
                not account.administrator,
                account.anonymous,
                account.full_name,
            ),
        )

    @property
    def user_accounts_by_id(self) -> dict[int, Account]:
        return {
            account.id: account
            for account in self.accounts_by_id.values()
            if account.user_account
        }

    @property
    def active_user_accounts_by_id(self) -> dict[int, Account]:
        return {
            account.id: account
            for account in self.accounts_by_id.values()
            if account.user_account and account.active
        }

    @property
    def user_accounts_by_name(self) -> dict[str, Account]:
        return {
            account.full_name: account
            for account in self.accounts_by_id.values()
            if account.user_account
        }

    @property
    def user_accounts_sorted_by_name(self) -> list[Account]:
        return sorted(
            self.user_accounts_by_name.values(),
            key=lambda account: (account.full_name,),
        )

    @property
    def active_user_accounts_by_name(self) -> dict[str, Account]:
        return {
            account.full_name: account
            for account in self.accounts_by_id.values()
            if account.user_account and account.active
        }

    @property
    def active_user_accounts_sorted_by_name(self) -> list[Account]:
        return sorted(
            self.active_user_accounts_by_name.values(),
            key=lambda account: (account.full_name,),
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

    @property
    def plugin_data(self) -> dict[str, dict[str, Any]]:
        return self.stored_event.plugin_data or {}

    def __lt__(self, other: 'Event'):
        # p1 < p2 calls p1.__lt__(p2)
        return self.uniq_id > other.uniq_id

    def __eq__(self, other: object) -> bool | NotImplementedType:
        # p1 == p2 calls p1.__eq__(p2)
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.uniq_id == other.uniq_id
