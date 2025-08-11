import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from logging import Logger
from typing import override, ClassVar

from common import format_timestamp_date_time
from common.i18n import _
from common.logger import get_logger
from common.network import NetworkMonitor
from data.player import Player, PlayerRating
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.fide.fide_database import FideDatabase
from database.sqlite.local_source_database import LocalSourceDatabase
from plugins.manager import plugin_manager
from utils.entity import IdentifiableEntity
from utils.enum import TournamentRating, PlayerRatingType

logger: Logger = get_logger()


class PlayerComparator(ABC):
    def __init__(
        self,
        field_ids: list[str],
        player: Player,
        match_stored_player: StoredPlayer | None = None,
    ):
        self.field_ids = field_ids
        self.player = player
        self.match_player: Player | None = None
        if match_stored_player:
            match_stored_player.id = 0
            self.match_player = Player(player.tournament, match_stored_player)

    @property
    @abstractmethod
    def diff_field_ids(self) -> list[str] | None:
        """Returns the list of fields amongst the selected fields on which
        the 2 players have a diff. If match is unset, returns None."""
        ...

    @abstractmethod
    def update_player_from_match(self, field_ids: list[str]):
        """Updates the selected fields of the player from the match_player."""
        ...


class FidePlayerComparator(PlayerComparator):
    def match_date_differs(self) -> bool:
        src_date = self.player.date_of_birth
        match_date = self.match_player.date_of_birth if self.match_player else None
        if src_date is None:
            return match_date is not None
        if match_date is None:
            return False
        if src_date.year != match_date.year:
            return True
        if (match_date.month, match_date.day) == (1, 1):
            return False
        if (src_date.month, src_date.day) == (match_date.month, match_date.day):
            return False
        return True

    @cached_property
    def diff_field_ids(self) -> list[str] | None:
        if not self.match_player:
            return None
        diff_field_ids: list[str] = []
        for tr in TournamentRating:
            field_id: str = f'rating_{tr.value}'
            if field_id in self.field_ids:
                src_rating = self.player.get_rating(tr)
                match_rating = self.match_player.get_rating(tr)

                if match_rating.value and src_rating != match_rating:
                    diff_field_ids.append(field_id)
        field_id: str = 'name'
        if field_id in self.field_ids:
            if (self.player.first_name, self.player.last_name) != (
                self.match_player.first_name,
                self.match_player.last_name,
            ):
                diff_field_ids.append(field_id)
        field_id: str = 'federation'
        if field_id in self.field_ids:
            if self.player.federation.name != self.match_player.federation.name:
                diff_field_ids.append(field_id)
        field_id: str = 'club'
        if field_id in self.field_ids:
            if (not self.player.club and self.match_player.club) or (
                self.player.club
                and self.match_player.club
                and self.player.club.name != self.match_player.club.name
            ):
                diff_field_ids.append(field_id)
        field_id: str = 'gender'
        if field_id in self.field_ids:
            if self.player.gender != self.match_player.gender:
                diff_field_ids.append(field_id)
        field_id: str = 'date_of_birth'
        if field_id in self.field_ids:
            if self.match_date_differs():
                diff_field_ids.append(field_id)
        field_id: str = 'fide_id'
        if field_id in self.field_ids:
            if (
                self.match_player.fide_id
                and self.player.fide_id != self.match_player.fide_id
            ):
                diff_field_ids.append(field_id)
        return diff_field_ids

    def update_player_from_match(self, field_ids: list[str]):
        if not self.match_player:
            return
        stored_player = self.player.stored_player
        match_stored_player = self.match_player.stored_player
        updated_ratings: dict[TournamentRating, PlayerRating] = {}
        for tr in TournamentRating:
            field_id: str = f'rating_{tr.value}'
            if field_id in field_ids:
                match_rating = self.match_player.get_rating(tr)
                if match_rating.value:
                    updated_ratings[tr] = match_rating
        self.player.update_ratings(updated_ratings)
        field_id: str = 'name'
        if field_id in field_ids:
            if (stored_player.first_name, stored_player.last_name) != (
                match_stored_player.first_name,
                match_stored_player.last_name,
            ):
                stored_player.last_name = match_stored_player.last_name
                stored_player.first_name = match_stored_player.first_name
        field_id: str = 'federation'
        if field_id in field_ids:
            if stored_player.federation != match_stored_player.federation:
                stored_player.federation = match_stored_player.federation
        field_id: str = 'club'
        if field_id in field_ids:
            if stored_player.club != match_stored_player.club:
                stored_player.club = match_stored_player.club
        field_id: str = 'gender'
        if field_id in field_ids:
            if stored_player.gender != match_stored_player.gender:
                stored_player.gender = match_stored_player.gender
        field_id: str = 'date_of_birth'
        if field_id in field_ids:
            if self.match_date_differs():
                stored_player.date_of_birth = match_stored_player.date_of_birth
        field_id: str = 'fide_id'
        if field_id in field_ids:
            match_fide_id = match_stored_player.fide_id
            if match_fide_id and stored_player.fide_id != match_fide_id:
                stored_player.fide_id = match_fide_id


@dataclass
class PlayerUpdaterField:
    name: str
    id: str

    @staticmethod
    def ratings_fields() -> list['PlayerUpdaterField']:
        return [
            PlayerUpdaterField(rating.name, f'rating_{rating.value}')
            for rating in TournamentRating
        ]

    @staticmethod
    def identity_fields() -> list['PlayerUpdaterField']:
        return [
            PlayerUpdaterField(_('Name'), 'name'),
            PlayerUpdaterField(_('Gender'), 'gender'),
            PlayerUpdaterField(_('Date of birth'), 'date_of_birth'),
        ]

    @staticmethod
    def federation_fields() -> list['PlayerUpdaterField']:
        return [PlayerUpdaterField(_('Federation'), 'federation')]

    @staticmethod
    def club_fields() -> list['PlayerUpdaterField']:
        return [PlayerUpdaterField(_('Club'), 'club')]

    @staticmethod
    def fide_fields() -> list['PlayerUpdaterField']:
        return [PlayerUpdaterField(_('FIDE ID'), 'fide_id')]


class DataSource(IdentifiableEntity, ABC):
    """Abstract class representing data source.
    Data sources can be used to search players or update them."""

    SEARCH_LIMIT = 10

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Determines if the data source is available."""

    def on_app_init(self):
        """Function to execute at the start of the server to initialize the data source."""

    # --------------------------------------------------------------------------
    # Players update
    # --------------------------------------------------------------------------

    @property
    @abstractmethod
    def player_updater_fields(self) -> list[PlayerUpdaterField]:
        """Returns the player fields that can be updated by the data source."""

    @property
    def players_update_message(self) -> tuple[str, bool]:
        """Message displayed on the players update modal.
        If the bool is set to True, show the message as a warning."""
        return '', False

    @abstractmethod
    async def get_player_matches(
        self,
        players: list[Player],
        field_ids: list[str],
        diff_only: bool,
    ) -> list[PlayerComparator] | None:
        """If the database access fails, returns None. Otherwise for each player,
        returns a MatchPlayer object (if a match is found, set *match_player* with
        the extracted player, else set it to None). If diff_only is True, identical
        matches are omitted."""

    @staticmethod
    def create_player_comparators(
        players: list[Player],
        match_stored_players: list[StoredPlayer],
        match_condition: Callable[[StoredPlayer, StoredPlayer], bool],
        field_ids: list[str],
        diff_only: bool,
        comparator: type[PlayerComparator],
    ) -> list[PlayerComparator]:
        player_comparators: list[PlayerComparator] = []
        for player in players:
            player_comparator = comparator(
                field_ids,
                player,
                next(
                    (
                        match_stored_player
                        for match_stored_player in match_stored_players
                        if match_condition(player.stored_player, match_stored_player)
                    ),
                    None,
                ),
            )
            if not diff_only or player_comparator.diff_field_ids:
                player_comparators.append(player_comparator)
        return player_comparators

    # --------------------------------------------------------------------------
    # Player search
    # --------------------------------------------------------------------------

    @property
    def search_element_name(self) -> str:
        return f'{self.id.replace("-", "_")}_search'

    @property
    @abstractmethod
    def search_fields(self) -> list[str]:
        """Localized list of names of the fields
        which can be used to search for a player."""

    @property
    @abstractmethod
    def player_search_result_template(self) -> str:
        """Template containing the info to display for a player as a search result.
        Template takes [player] as a template variable."""

    @abstractmethod
    async def search_player(
        self, string: str, limit: int | None = None
    ) -> list[StoredPlayer]:
        """Search a player in the data source from a string.
        Returns maximum *limit* results (no limit if *limit* is None)."""

    @abstractmethod
    async def get_stored_player_by_source_id(
        self, player_source_id: str
    ) -> StoredPlayer | None:
        """Get a player by its identifier in the data source."""

    @abstractmethod
    def get_player_source_id(self, stored_player: StoredPlayer) -> str:
        """Get the id of the player in the source formatted as a string."""

    async def fetch_player(self, player_source_id: str) -> StoredPlayer | None:
        stored_player = await self.get_stored_player_by_source_id(player_source_id)
        if stored_player:
            self._adjust_player_from_fide_database(stored_player)
            await plugin_manager.ahook.augment_player_after_search(
                stored_player=stored_player, data_source=self
            )
        return stored_player

    @staticmethod
    def _adjust_player_from_fide_database(src_stored_player: StoredPlayer):
        """Cross-references the player with the FIDE Database.
        Override this method to disable this behavior."""
        fide_id = src_stored_player.fide_id
        database = FideDatabase()
        if not fide_id or not database.exists():
            return
        with database:
            fide_stored_player = database.get_stored_player_by_fide_id(fide_id)
            if not fide_stored_player:
                return
            src_stored_player.federation = fide_stored_player.federation
            src_stored_player.title = fide_stored_player.title
            for rating_type in TournamentRating:
                stored_fide_rating = fide_stored_player.ratings.get(
                    rating_type.value, None
                )
                if not stored_fide_rating:
                    continue
                fide_rating = PlayerRating.from_stored_value(stored_fide_rating)
                stored_source_rating = src_stored_player.ratings.get(
                    rating_type.value, None
                )
                source_rating = (
                    PlayerRating.from_stored_value(stored_source_rating)
                    if stored_source_rating
                    else None
                )
                if not source_rating or (
                    source_rating.type == PlayerRatingType.ESTIMATED
                    and fide_rating.type != PlayerRatingType.ESTIMATED
                ):
                    src_stored_player.ratings[rating_type.value] = stored_fide_rating


class LocalDataSource(DataSource, ABC):
    @property
    @abstractmethod
    def local_database_type(self) -> type[LocalSourceDatabase]:
        """The type of the local database used for this source."""

    @property
    def players_update_message(self) -> tuple[str, bool]:
        database = self.local_database_type()
        message = (
            _('Last update: {updated_at} (outdated)')
            if database.is_outdated
            else _('Last update: {updated_at}')
        )
        return (
            message.format(updated_at=database.updated_at_str),
            database.is_outdated,
        )

    @property
    def is_available(self) -> bool:
        return self.local_database_type.file_path().exists()

    def on_app_init(self):
        self.local_database_type().check()

    async def search_player(
        self, string: str, limit: int | None = None
    ) -> list[StoredPlayer]:
        with self.local_database_type() as database:
            return database.search_player(string, limit)


class OnlineDataSource(DataSource, ABC):
    connection_status: ClassVar[bool | None] = None
    _connection_last_checked_at: ClassVar[float | None] = None

    @classmethod
    @abstractmethod
    async def check_connection(cls) -> bool:
        """Check the connection to the data source.
        If it fails, log the error."""

    def on_app_init(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.reload_connection_status())

    @classmethod
    async def reload_connection_status(cls):
        cls._connection_last_checked_at = time.time()
        if NetworkMonitor.connected():
            cls.connection_status = await cls.check_connection()

    @property
    def is_available(self) -> bool:
        return NetworkMonitor.connected() and bool(self.connection_status)

    @property
    def connection_last_checked_at_str(self) -> str:
        return format_timestamp_date_time(self._connection_last_checked_at)


class FideDataSource(LocalDataSource):
    @staticmethod
    def static_id() -> str:
        return 'fide'

    @staticmethod
    def static_name() -> str:
        return _('FIDE database')

    @property
    def local_database_type(self) -> type[LocalSourceDatabase]:
        return FideDatabase

    @property
    def player_updater_fields(self) -> list[PlayerUpdaterField]:
        return (
            PlayerUpdaterField.ratings_fields()
            + PlayerUpdaterField.identity_fields()
            + PlayerUpdaterField.federation_fields()
        )

    @staticmethod
    @override
    def _adjust_player_from_fide_database(src_stored_player: StoredPlayer):
        pass

    async def get_player_matches(
        self,
        players: list[Player],
        field_ids: list[str],
        diff_only: bool,
    ) -> list[PlayerComparator] | None:
        database = FideDatabase()
        if not database.exists():
            return None
        fide_ids = [player.fide_id for player in players if player.fide_id]
        with database:
            match_players = database.get_stored_players_by_fide_id(fide_ids)
            return self.create_player_comparators(
                players,
                match_players,
                lambda p1, p2: p1.fide_id is not None and p1.fide_id == p2.fide_id,
                field_ids,
                diff_only,
                FidePlayerComparator,
            )

    @property
    def search_fields(self) -> list[str]:
        return [_('Name'), _('FIDE ID')]

    @property
    def player_search_result_template(self) -> str:
        return '/admin/players/fide_search_result.html'

    async def get_stored_player_by_source_id(
        self, player_source_id: str
    ) -> StoredPlayer | None:
        if not player_source_id.isdigit():
            return None
        with FideDatabase() as database:
            return database.get_stored_player_by_fide_id(int(player_source_id))

    def get_player_source_id(self, stored_player: StoredPlayer) -> str:
        return str(stored_player.fide_id)
