from abc import ABC
from typing import ClassVar

from common.i18n import _
import data.columns.player_datasheet as pds
from data.columns.handlers import PlayerDatasheetColumnHandler
from data.columns.player_datasheet import DatasheetColumn
from data.input_output.data_source import LocalDataSource
from data.input_output.player_updater_fields import (
    PlayerUpdaterField,
    NationalIdUpdaterField,
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
    ClubUpdaterField,
)
from data.player import Player
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.local_source_database import LocalSourcePlayerDatabase
from database.sqlite.national import NationalPlayerDatabase
from database.sqlite.national.cfc_database import CfcDatabase
from database.sqlite.national.chessa_database import ChessaDatabase
from database.sqlite.national.cfr_database import CfrDatabase
from database.sqlite.national.dsb_database import DsbDatabase
from database.sqlite.national.dsu_database import DsuDatabase
from database.sqlite.national.ecf_database import EcfDatabase
from database.sqlite.national.fsi_database import FsiDatabase
from database.sqlite.national.jcf_database import JcfDatabase
from database.sqlite.national.knsb_database import KnsbDatabase
from database.sqlite.national.lok_database import LokDatabase
from database.sqlite.national.mcf_database import McfDatabase
from database.sqlite.national.nzcf_database import NzcfDatabase
from database.sqlite.national.percasi_database import PercasiDatabase
from database.sqlite.national.ssl_database import SslDatabase
from database.sqlite.national.ucf_database import UcfDatabase
from utils.enum import PlayerRatingType


class NationalDataSource(LocalDataSource, ABC):
    """A federation's rating list converted locally, see
    `NationalPlayerDatabase`. The data source of a federation is activated
    with the first event of the federation."""

    national_database_type: ClassVar[type[NationalPlayerDatabase]]
    search_filter_ids = (
        'federation_filter',
        'gender_filter',
        'category_filter',
        'club_filter',
    )

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if hasattr(cls, 'national_database_type'):
            cls.federation = cls.national_database_type.federation
            cls.national_source_id = cls.national_database_type.national_source_id()

    @classmethod
    def static_id(cls) -> str:
        return cls.national_database_type.static_id()

    @classmethod
    def static_name(cls) -> str:
        return cls.national_database_type.static_name()

    @property
    def local_database_type(self) -> type[LocalSourcePlayerDatabase]:
        return self.national_database_type

    @property
    def short_name(self) -> str:
        return self.national_database_type.acronym

    @property
    def national_source_name(self) -> str:
        return self.national_database_type.acronym

    @property
    def player_updater_fields(self) -> list[PlayerUpdaterField]:
        rating_types = [PlayerRatingType.NATIONAL, PlayerRatingType.FIDE]
        return [
            NationalIdUpdaterField(),
            FideIDUpdaterField(),
            TitleUpdaterField(),
            WomenTitleUpdaterField(),
            NameUpdaterField(),
            CategoryUpdaterField(),
            GenderPlayerUpdater(),
            StandardRatingUpdaterField(rating_types),
            RapidRatingUpdaterField(rating_types),
            BlitzRatingUpdaterField(rating_types),
            FederationUpdaterField(),
            ClubUpdaterField(),
        ]

    def check_player_match(self, player1: StoredPlayer, player2: StoredPlayer) -> bool:
        return self.check_national_id_match(player1, player2)

    async def get_match_stored_players(
        self, players: list[Player]
    ) -> list[StoredPlayer] | None:
        database = self.national_database_type()
        if not database.exists():
            return None
        national_ids = [
            player.national_id
            for player in players
            if player.national_id
            and player.national_source in (None, self.national_source_id)
        ]
        with database:
            return database.get_stored_players_by_national_id(national_ids)

    @property
    def search_fields(self) -> list[str]:
        return [_('Name'), _('National ID'), _('FIDE ID')]

    @property
    def player_search_result_template(self) -> str:
        return '/admin/players/national_search_result.html'

    async def get_stored_player_by_source_id(
        self,
        player_source_id: str,
    ) -> StoredPlayer | None:
        with self.national_database_type() as database:
            return database.get_stored_player_by_national_id(player_source_id)

    def get_player_source_id(self, stored_player: StoredPlayer) -> str:
        return stored_player.national_id or ''

    @property
    def import_identifier_column(self) -> DatasheetColumn:
        return pds.NationalIdColumn()

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
            pds.FideIDColumn(),
            pds.FederationColumn(),
            pds.ClubColumn(),
        ]
        columns += PlayerDatasheetColumnHandler.get_rating_columns(
            [PlayerRatingType.NATIONAL, PlayerRatingType.FIDE]
        )
        return columns

    async def get_stored_players_by_import_identifier(
        self, identifier_values: list[str]
    ) -> dict[str, StoredPlayer]:
        with self.national_database_type() as database:
            stored_players = database.get_stored_players_by_national_id(
                [value.strip() for value in identifier_values]
            )
        return {
            stored_player.national_id or '': stored_player
            for stored_player in stored_players
        }


class KnsbDataSource(NationalDataSource):
    national_database_type = KnsbDatabase


class FsiDataSource(NationalDataSource):
    national_database_type = FsiDatabase


class CfrDataSource(NationalDataSource):
    national_database_type = CfrDatabase


class SslDataSource(NationalDataSource):
    national_database_type = SslDatabase


class CfcDataSource(NationalDataSource):
    national_database_type = CfcDatabase


class DsbDataSource(NationalDataSource):
    national_database_type = DsbDatabase


class EcfDataSource(NationalDataSource):
    national_database_type = EcfDatabase


class ChessaDataSource(NationalDataSource):
    national_database_type = ChessaDatabase


class LokDataSource(NationalDataSource):
    national_database_type = LokDatabase


class UcfDataSource(NationalDataSource):
    national_database_type = UcfDatabase


class JcfDataSource(NationalDataSource):
    national_database_type = JcfDatabase


class NzcfDataSource(NationalDataSource):
    national_database_type = NzcfDatabase


class DsuDataSource(NationalDataSource):
    national_database_type = DsuDatabase


class McfDataSource(NationalDataSource):
    national_database_type = McfDatabase


class PercasiDataSource(NationalDataSource):
    national_database_type = PercasiDatabase


NATIONAL_DATA_SOURCE_TYPES: tuple[type[NationalDataSource], ...] = (
    KnsbDataSource,
    FsiDataSource,
    CfrDataSource,
    SslDataSource,
    CfcDataSource,
    DsbDataSource,
    EcfDataSource,
    ChessaDataSource,
    LokDataSource,
    UcfDataSource,
    JcfDataSource,
    NzcfDataSource,
    DsuDataSource,
    McfDataSource,
    PercasiDataSource,
)
