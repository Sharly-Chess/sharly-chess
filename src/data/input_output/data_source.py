import asyncio
from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import date, datetime
from functools import cached_property
from logging import Logger
from typing import override, ClassVar
from collections.abc import Collection

from common import SharlyChessException
from common.i18n import _
from common.logger import get_logger
from common.network import NetworkMonitor
import data.columns.player_datasheet as pds
from data.columns.handlers import PlayerDatasheetColumnHandler
from data.columns.player_datasheet import DatasheetColumn
from data.event import Event
from data.input_output.player_updater_fields import (
    PlayerUpdaterField,
    FideIDUpdaterField,
    TitleUpdaterField,
    WomenTitleUpdaterField,
    NameUpdaterField,
    CategoryUpdaterField,
    GenderPlayerUpdater,
    StandardRatingUpdaterField,
    RapidRatingUpdaterField,
    BlitzRatingUpdaterField,
    FederationUpdaterField,
)
from data.player import Player, PlayerProfileLink, PlayerRating
from database.sqlite.config.config_database import ConfigDatabase
from database.sqlite.config.config_store import StoredOnlineDataSource
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.fide.fide_database import FideDatabase
from database.sqlite.local_source_database.databases import LocalSourcePlayerDatabase
from plugins.manager import plugin_manager
from utils.date_time import format_datetime
from utils.entity import IdentifiableEntity
from utils.enum import TournamentRating, PlayerRatingType

logger: Logger = get_logger()


def reliable_k_factor(
    k_factor: int | None, fide_rating: int | None, year_of_birth: int | None
) -> int | None:
    """What can still be trusted of a k-factor read from a FIDE database of
    an earlier rating period.

    A coefficient only ever goes down (40 once the player has played their
    30 games or turned 19, then 10 once their published rating has reached
    2400, for good). An outdated one is therefore an upper bound, and the
    lower of it and the estimate never overshoots: a 10 survives whatever
    the estimate says, while a 20 gives way to the 10 of a player who has
    reached 2400 since."""
    if k_factor is None:
        return None
    return min(
        k_factor, Player.estimate_fide_rating_coefficient(fide_rating, year_of_birth)
    )


def keep_reliable_k_factors(stored_player: StoredPlayer) -> None:
    """Reduce the k-factors of a player read from a FIDE database of an
    earlier rating period to what can still be trusted."""
    year_of_birth = stored_player.year_of_birth or (
        stored_player.date_of_birth.year if stored_player.date_of_birth else None
    )
    for tr_value, stored_rating in stored_player.ratings.items():
        rating = PlayerRating.from_stored_value(stored_rating)
        rating.k_factor = reliable_k_factor(rating.k_factor, rating.fide, year_of_birth)
        stored_player.ratings[tr_value] = rating.stored_value


class PlayerComparator:
    def __init__(
        self,
        fields: list[PlayerUpdaterField],
        player: Player,
        match_stored_player: StoredPlayer | None = None,
    ):
        self.player = player
        self.match_player: Player | None = None
        if match_stored_player:
            match_stored_player.id = 0
            self.match_player = Player(player.event, match_stored_player)
        self.diff_field_ids = self._get_diff_field_ids(fields)

    def _get_diff_field_ids(self, fields: list[PlayerUpdaterField]) -> list[str]:
        if not self.match_player:
            return []
        return [
            field.id
            for field in fields
            if field.is_updated(self.player, self.match_player)
        ]

    def updated_player_from_match(self, fields: list[PlayerUpdaterField]) -> Player:
        assert self.match_player is not None
        for field in fields:
            if field.id not in self.diff_field_ids:
                continue
            field.update_player(
                self.player.stored_player, self.match_player.stored_player
            )
        return self.player


class DataSource(IdentifiableEntity, ABC):
    """Abstract class representing data source.
    Data sources can be used to search players or update them."""

    SEARCH_LIMIT = 30

    #: The federation whose events activate the data source, None for a
    #: data source activated another way.
    federation: ClassVar[str | None] = None

    #: The search filters the data source supports, see
    #: `SearchFilterManager.get_filters_by_datasource`.
    search_filter_ids: ClassVar[tuple[str, ...]] = ()

    #: The key stored as the `national_source` of the players whose
    #: `national_id` the data source provides, shared by the data sources of
    #: one federation; None for a data source without national identifiers.
    national_source_id: ClassVar[str | None] = None

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Determines if the data source is available."""

    def on_app_init(self) -> None:
        """Function to execute at the start of the server to initialize the data source."""

    @property
    def short_name(self) -> str:
        """The name where room is short (the search bar)."""
        return self.name

    # --------------------------------------------------------------------------
    # National identifiers
    # --------------------------------------------------------------------------

    @property
    def national_source_name(self) -> str:
        """Short name put before a national identifier."""
        return self.name

    @property
    def national_id_form_label(self) -> str:
        """The label of the national identifier on the player form."""
        return _('{source} ID:').format(source=self.national_source_name)

    @property
    def national_id_form_placeholder(self) -> str:
        return ''

    def player_profile_url(self, national_id: str) -> str | None:
        """The federation's profile page of a player, None when there is
        none."""
        return None

    def player_profile_link(self, player: Player) -> PlayerProfileLink | None:
        """The national identifier of a player, shown on the identity line
        of the record modal."""
        if not player.national_id:
            return None
        return PlayerProfileLink(
            label=f'{self.national_source_name} {player.national_id}',
            url=self.player_profile_url(player.national_id),
        )

    def check_national_id_match(
        self, player1: StoredPlayer, player2: StoredPlayer
    ) -> bool:
        """Whether two players carry the same identifier of the federation
        of the data source. An identifier without a source (typed in, or
        imported from a datasheet) is taken as one of the federation."""
        if not self.national_source_id or not player1.national_id:
            return False
        return player1.national_id == player2.national_id and all(
            player.national_source in (None, self.national_source_id)
            for player in (player1, player2)
        )

    # --------------------------------------------------------------------------
    # Activation
    # --------------------------------------------------------------------------

    @property
    @abstractmethod
    def is_active(self) -> bool:
        """Whether the data source is offered in the application."""

    @property
    @abstractmethod
    def is_forced_active(self) -> bool:
        """Whether the data source is active whatever the user says (a
        plugin needs it)."""

    @abstractmethod
    def activate(self) -> None:
        """Offers the data source in the application."""

    @abstractmethod
    def deactivate(self) -> None:
        """Withdraws the data source from the application."""

    @abstractmethod
    def activate_for_federation(self, federation: str) -> None:
        """Activates the data source of a federation the first time it is
        needed; a data source the user has removed stays removed."""

    @property
    def info_or_warning_message(self) -> tuple[str, bool]:
        """Message displayed on the players update modal and the player search.
        If the bool is set to True, show the message as a warning."""
        return '', False

    # --------------------------------------------------------------------------
    # Players update
    # --------------------------------------------------------------------------

    @property
    @abstractmethod
    def player_updater_fields(self) -> list[PlayerUpdaterField]:
        """Returns the player fields that can be updated by the data source."""

    @abstractmethod
    def check_player_match(self, player1: StoredPlayer, player2: StoredPlayer) -> bool:
        """Checks if the two players are a match."""

    @abstractmethod
    async def get_match_stored_players(
        self, players: list[Player]
    ) -> list[StoredPlayer] | None:
        """Get a list of stored players matching the given players."""

    async def get_player_comparators(
        self,
        players: list[Player],
        fields: list[PlayerUpdaterField],
        diff_only: bool = False,
    ) -> list[PlayerComparator] | None:
        """Get player comparators for all the players in the list.
        *restricted_field_ids* allows to only set the comparators with specific fields.
        If *diff_only*, the comparators returned are only the ones where a match has been found."""
        match_stored_players = await self.get_match_stored_players(players)
        if match_stored_players is None:
            return None
        k_factors_by_fide_id = self._fide_k_factors_by_fide_id(match_stored_players)
        database = FideDatabase()
        covered_dates = {
            reference_date
            for reference_date in {
                player.fide_k_factor_reference_date for player in players
            }
            if database.covers_rating_period(reference_date)
        }
        player_comparators: list[PlayerComparator] = []
        for player in players:
            match_player = next(
                (
                    match_stored_player
                    for match_stored_player in match_stored_players
                    if self.check_player_match(
                        player.stored_player, match_stored_player
                    )
                ),
                None,
            )
            if match_player is not None:
                match_player = self._with_k_factors(
                    match_player,
                    self._k_factors_for_player(
                        player,
                        k_factors_by_fide_id.get(match_player.fide_id or 0, {}),
                        player.fide_k_factor_reference_date in covered_dates,
                    ),
                )
            player_comparator = PlayerComparator(fields, player, match_player)
            if not diff_only or player_comparator.diff_field_ids:
                player_comparators.append(player_comparator)
        return player_comparators

    @staticmethod
    def _k_factors_for_player(
        player: Player,
        database_k_factors: dict[int, int | None],
        in_rating_period: bool,
    ) -> dict[int, int | None]:
        """The k-factors the update proposes for a player: the ones of the
        database inside its rating period, and outside of it what remains
        trustworthy of them, the player keeping their own where nothing
        does."""
        if in_rating_period:
            return database_k_factors
        k_factors: dict[int, int | None] = {}
        for tournament_rating in TournamentRating:
            tr_value = tournament_rating.value
            k_factor = reliable_k_factor(
                database_k_factors.get(tr_value),
                player.ratings[tournament_rating].fide,
                player.year_of_birth,
            )
            k_factors[tr_value] = (
                k_factor
                if k_factor is not None
                else player.ratings[tournament_rating].k_factor
            )
        return k_factors

    @staticmethod
    def _fide_k_factors_by_fide_id(
        match_stored_players: list[StoredPlayer],
    ) -> dict[int, dict[int, int | None]]:
        """Read the k-factors of the matched players in the FIDE database,
        so that they are brought over whatever the data source is."""
        database = FideDatabase()
        fide_ids = [
            match_stored_player.fide_id
            for match_stored_player in match_stored_players
            if match_stored_player.fide_id
        ]
        if not fide_ids or not database.exists():
            return {}
        with database:
            fide_stored_players = database.get_stored_players_by_fide_id(fide_ids)
        return {
            fide_stored_player.fide_id: {
                tr_value: PlayerRating.from_stored_value(stored_rating).k_factor
                for tr_value, stored_rating in fide_stored_player.ratings.items()
            }
            for fide_stored_player in fide_stored_players
            if fide_stored_player.fide_id
        }

    @staticmethod
    def _with_k_factors(
        match_stored_player: StoredPlayer,
        k_factors: dict[int, int | None],
    ) -> StoredPlayer:
        ratings: dict[int, dict[str, int | None]] = {}
        for tournament_rating in TournamentRating:
            tr_value = tournament_rating.value
            rating = PlayerRating.from_stored_value(
                match_stored_player.ratings.get(tr_value, {})
            )
            rating.k_factor = k_factors.get(tr_value)
            ratings[tr_value] = rating.stored_value
        return replace(match_stored_player, ratings=ratings)

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

    @property
    @abstractmethod
    def search_error_icon(self) -> str:
        """Icon to display in the search results in case of an error."""

    @abstractmethod
    async def search_player(
        self,
        string: str,
        federation: str,
        page: int = 0,
        limit: int | None = None,
        filters: dict | None = None,
    ) -> list[StoredPlayer]:
        """Search a player in the data source from a string.
        Returns maximum *limit* results (no limit if *limit* is None)."""

    @abstractmethod
    async def get_stored_player_by_source_id(
        self,
        player_source_id: str,
    ) -> StoredPlayer | None:
        """Get a player by its identifier in the data source."""

    @abstractmethod
    def get_player_source_id(self, stored_player: StoredPlayer) -> str:
        """Get the id of the player in the source formatted as a string."""

    async def fetch_player(
        self,
        player_source_id: str,
        with_arbiter_title: bool,
        k_factor_reference_date: date,
    ) -> StoredPlayer | None:
        stored_player = await self.get_stored_player_by_source_id(player_source_id)
        if stored_player:
            self._adjust_player_from_fide_database(
                stored_player, k_factor_reference_date
            )
            await plugin_manager.ahook.augment_player_after_search(
                stored_player=stored_player,
                data_source=self,
                with_arbiter_title=with_arbiter_title,
            )
        return stored_player

    @staticmethod
    def _adjust_player_from_fide_database(
        src_stored_player: StoredPlayer,
        k_factor_reference_date: date,
    ) -> None:
        """Cross-references the player with the FIDE Database.
        Override this method to disable this behavior."""
        fide_id = src_stored_player.fide_id
        database = FideDatabase()
        if not fide_id or not database.exists():
            return
        in_rating_period = database.covers_rating_period(k_factor_reference_date)
        year_of_birth = src_stored_player.year_of_birth or (
            src_stored_player.date_of_birth.year
            if src_stored_player.date_of_birth
            else None
        )
        with database:
            fide_stored_player = database.get_stored_player_by_fide_id(
                player_fide_id=fide_id,
            )
            if not fide_stored_player:
                return
            src_stored_player.federation = fide_stored_player.federation
            src_stored_player.title = fide_stored_player.title
            src_stored_player.women_title = fide_stored_player.women_title
            src_stored_player.transient_arbiter_titles['fide'] = (
                fide_stored_player.transient_arbiter_titles.get('fide', '')
            )
            for rating_type in TournamentRating:
                stored_fide_rating = fide_stored_player.ratings.get(
                    rating_type.value, None
                )
                if not stored_fide_rating:
                    continue
                fide_player_rating = PlayerRating.from_stored_value(stored_fide_rating)
                if not fide_player_rating.fide:
                    continue
                source_rating = PlayerRating.from_stored_value(
                    src_stored_player.ratings.get(rating_type.value, None) or {}
                )
                if source_rating.fide is None:
                    source_rating.fide = fide_player_rating.fide
                source_rating.k_factor = (
                    fide_player_rating.k_factor
                    if in_rating_period
                    else reliable_k_factor(
                        fide_player_rating.k_factor,
                        source_rating.fide,
                        year_of_birth,
                    )
                )
                src_stored_player.ratings[rating_type.value] = (
                    source_rating.stored_value
                )

    # --------------------------------------------------------------------------
    # Player Import
    # --------------------------------------------------------------------------

    @property
    @abstractmethod
    def import_identifier_column(self) -> DatasheetColumn:
        """Column of the identifier of the import."""

    @property
    @abstractmethod
    def imported_datasheet_columns(self) -> list[DatasheetColumn]:
        """datasheet columns that the datasource is importing.
        These columns won't be available on import."""

    def get_all_datasheet_columns(self, event: Event) -> Collection[DatasheetColumn]:
        """Fetch the datasheet columns that can be imported with the data source."""
        return PlayerDatasheetColumnHandler(event, self).columns

    @abstractmethod
    async def get_stored_players_by_import_identifier(
        self, identifier_values: list[str]
    ) -> dict[str, StoredPlayer]:
        """Fetch stored players from their identifier values.
        Return a dict with the ones that have been found."""


class LocalDataSource(DataSource, ABC):
    @property
    @abstractmethod
    def local_database_type(self) -> type[LocalSourcePlayerDatabase]:
        """The type of the local database used for this source."""

    @cached_property
    def database(self) -> LocalSourcePlayerDatabase:
        return self.local_database_type()

    @property
    def info_or_warning_message(self) -> tuple[str, bool]:
        message = (
            _('Last update: {updated_at} (outdated)')
            if self.database.is_outdated
            else _('Last update: {updated_at}')
        )
        return (
            message.format(updated_at=self.database.updated_at_str),
            self.database.is_outdated,
        )

    @property
    def is_available(self) -> bool:
        return self.local_database_type.file_path().exists()

    @property
    def is_active(self) -> bool:
        return self.database.is_active

    @property
    def is_forced_active(self) -> bool:
        return self.database.is_forced_active

    def activate(self) -> None:
        self.database.activate()

    def deactivate(self) -> None:
        self.database.deactivate()

    def activate_for_federation(self, federation: str) -> None:
        self.database.activate_for_federation(federation)

    def on_app_init(self) -> None:
        self.database.check()
        self.database.install_if_missing()

    @property
    def search_error_icon(self) -> str:
        return 'bi-database-fill-dash'

    async def search_player(
        self,
        string: str,
        federation: str,
        page: int = 0,
        limit: int | None = None,
        filters: dict | None = None,
    ) -> list[StoredPlayer]:
        if not self.is_available:
            raise SharlyChessException(
                _(
                    'This database is not installed '
                    '(to install it: Menu > Data sources).'
                )
            )
        with self.local_database_type() as database:
            return database.search_player(string, federation, page, limit, filters)


class OnlineDataSource(DataSource, ABC):
    connection_status: ClassVar[bool | None] = None
    _connection_last_checked_at: ClassVar[datetime | None] = None
    _background_tasks: ClassVar[set[asyncio.Task]] = set()
    _stored_data_source: ClassVar[StoredOnlineDataSource | None] = None

    @property
    def stored_data_source(self) -> StoredOnlineDataSource:
        cls = self.__class__
        if cls._stored_data_source is None:
            with ConfigDatabase() as database:
                cls._stored_data_source = database.load_stored_online_data_source(
                    self.id
                ) or StoredOnlineDataSource(name=self.id)
        return cls._stored_data_source

    @property
    def default_is_active(self) -> bool:
        """Whether the data source is active until the user says otherwise."""
        return False

    @property
    def is_forced_active(self) -> bool:
        return False

    @property
    def is_active(self) -> bool:
        if self.is_forced_active:
            return True
        stored_is_active = self.stored_data_source.is_active
        if stored_is_active is None:
            return self.default_is_active
        return stored_is_active

    def _set_is_active(self, is_active: bool) -> None:
        stored_data_source = self.stored_data_source
        stored_data_source.is_active = is_active
        with ConfigDatabase(write=True) as database:
            database.upsert_stored_online_data_source(stored_data_source)

    def activate(self) -> None:
        self._set_is_active(True)

    def deactivate(self) -> None:
        self._set_is_active(False)

    def activate_for_federation(self, federation: str) -> None:
        if self.federation != federation:
            return
        if self.stored_data_source.is_active is not None:
            return
        self.activate()

    @classmethod
    @abstractmethod
    async def check_connection(cls) -> bool:
        """Check the connection to the data source.
        If it fails, log the error."""

    def on_app_init(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop yet — safe fallback if someone calls too early
            loop = asyncio.get_event_loop()

        # The loop only holds a weak reference, so the task is kept here until
        # it is done or it can be collected before it has run.
        task = loop.create_task(self.reload_connection_status())
        OnlineDataSource._background_tasks.add(task)
        task.add_done_callback(OnlineDataSource._background_tasks.discard)

    @classmethod
    async def reload_connection_status(cls) -> None:
        cls._connection_last_checked_at = datetime.now()
        if not NetworkMonitor.connected():
            cls.connection_status = None
            return
        cls.connection_status = await cls.check_connection()

    @property
    def is_available(self) -> bool:
        return True

    @property
    def connection_last_checked_at_str(self) -> str:
        if not self._connection_last_checked_at:
            return ''
        return format_datetime(self._connection_last_checked_at)

    @property
    def search_error_icon(self) -> str:
        return 'bi-cloud-fill-dash'

    async def search_player(
        self,
        string: str,
        federation: str,
        page: int = 0,
        limit: int | None = None,
        filters: dict | None = None,
    ) -> list[StoredPlayer]:
        cls = self.__class__
        cls._connection_last_checked_at = datetime.now()
        if not NetworkMonitor.connected():
            cls.connection_status = None
            raise SharlyChessException(_('No internet connection'))
        try:
            players = await self._search_player(
                string, federation, page, limit, filters
            )
            cls.connection_status = True
            return players
        except SharlyChessException as exception:
            cls.connection_status = False
            raise exception

    @abstractmethod
    async def _search_player(
        self,
        string: str,
        federation: str,
        page: int = 0,
        limit: int | None = None,
        filters: dict | None = None,
    ) -> list[StoredPlayer]:
        """Search a player in the data source from a string.
        Returns maximum *limit* results (no limit if *limit* is None)."""


class FideDataSource(LocalDataSource):
    search_filter_ids = ('federation_filter', 'gender_filter', 'category_filter')

    @staticmethod
    def static_id() -> str:
        return 'fide'

    @staticmethod
    def static_name() -> str:
        return _('FIDE database')

    @property
    def short_name(self) -> str:
        return 'FIDE'

    @property
    def local_database_type(self) -> type[LocalSourcePlayerDatabase]:
        return FideDatabase

    @property
    def player_updater_fields(self) -> list[PlayerUpdaterField]:
        return [
            FideIDUpdaterField(),
            TitleUpdaterField(),
            WomenTitleUpdaterField(),
            NameUpdaterField(),
            CategoryUpdaterField(),
            GenderPlayerUpdater(),
            StandardRatingUpdaterField([PlayerRatingType.FIDE]),
            RapidRatingUpdaterField([PlayerRatingType.FIDE]),
            BlitzRatingUpdaterField([PlayerRatingType.FIDE]),
            FederationUpdaterField(),
        ]

    @staticmethod
    @override
    def _adjust_player_from_fide_database(
        src_stored_player: StoredPlayer,
        k_factor_reference_date: date,
    ) -> None:
        if not FideDatabase().covers_rating_period(k_factor_reference_date):
            keep_reliable_k_factors(src_stored_player)

    def check_player_match(self, player1: StoredPlayer, player2: StoredPlayer) -> bool:
        return bool(player1.fide_id) and player1.fide_id == player2.fide_id

    async def get_match_stored_players(
        self, players: list[Player]
    ) -> list[StoredPlayer] | None:
        database = FideDatabase()
        if not database.exists():
            return None
        fide_ids = [player.fide_id for player in players if player.fide_id]
        with database:
            return database.get_stored_players_by_fide_id(fide_ids)

    @property
    def search_fields(self) -> list[str]:
        return [_('Name'), _('FIDE ID')]

    @property
    def player_search_result_template(self) -> str:
        return '/admin/players/fide_search_result.html'

    async def get_stored_player_by_source_id(
        self,
        player_source_id: str,
    ) -> StoredPlayer | None:
        if not player_source_id.isdigit():
            return None
        with FideDatabase() as database:
            return database.get_stored_player_by_fide_id(
                player_fide_id=int(player_source_id),
            )

    def get_player_source_id(self, stored_player: StoredPlayer) -> str:
        return str(stored_player.fide_id)

    @property
    def import_identifier_column(self) -> DatasheetColumn:
        return pds.FideIDColumn()

    @property
    def imported_datasheet_columns(self) -> list[DatasheetColumn]:
        columns: list[DatasheetColumn] = [
            pds.TitleColumn(),
            pds.WomenTitleColumn(),
            pds.LastNameColumn(),
            pds.FirstNameColumn(),
            pds.DateOfBirthColumn(),
            pds.YearOfBirthColumn(),
            pds.GenderColumn(),
            pds.FederationColumn(),
        ]
        columns += PlayerDatasheetColumnHandler.get_rating_columns(
            [PlayerRatingType.FIDE]
        )
        return columns

    async def get_stored_players_by_import_identifier(
        self, identifier_values: list[str]
    ) -> dict[str, StoredPlayer]:
        with FideDatabase() as database:
            stored_players = database.get_stored_players_by_fide_id(
                [int(value) for value in identifier_values]
            )
        return {
            str(stored_player.fide_id): stored_player
            for stored_player in stored_players
        }
