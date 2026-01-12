import copy
from collections import defaultdict
from typing import TYPE_CHECKING

from packaging.version import Version

from common.i18n import _
from data.columns import player_datasheet
from data.columns.player_datasheet import DatasheetColumn
from data.input_output import DataSource
from data.input_output.data_source import FideDataSource
from data.player import PlayerRating
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.fide.fide_database import FideDatabase
from database.sqlite.local_source_database import LocalSourceDatabase
from plugins.scf import PLUGIN_NAME
from plugins.scf.scf_data_sources import ScfLocalDataSource
from plugins.scf.scf_database import ScfDatabase
from plugins.scf.scf_entity import ScfCodeDatasheetColumn
from plugins.scf.utils import SCFUtils
from plugins.scf.utils import (
    ScfPlayerPluginData,
)
from plugins.hookspec import hookimpl
from plugins.pairing_acceleration.pairing_acceleration import PairingAccelerationPlugin
from plugins.utils import (
    Plugin,
    PluginUtils,
    PluginData,
)
from utils.enum import (
    TournamentRating,
)
from web.controllers.base_controller import WebContext

if TYPE_CHECKING:
    from data.tournament import Tournament
    from data.player import Player, TournamentPlayer
    from database.sqlite.event.event_store import StoredEvent, StoredTournament


class ScfPlugin(Plugin):
    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return _('Swiss Chess Federation')

    @property
    def dependencies(self) -> list[type[Plugin]]:
        return [PairingAccelerationPlugin]

    @property
    def description(self) -> str:
        return _('Swiss Federation specific features')

    @property
    def version(self) -> Version:
        return Version('1.0.0')

    @property
    def default_is_enabled(self) -> bool:
        return True

    @property
    def default_event_is_enabled(self) -> bool:
        return True

    @property
    def federation(self) -> str | None:
        return 'SUI'

    def used_by_stored_tournament(
        self, stored_event: 'StoredEvent', stored_tournament: 'StoredTournament'
    ) -> bool:
        return False

    # ---------------------------------------------------------------------------------
    # Input-Output
    # ---------------------------------------------------------------------------------

    @hookimpl
    def insert_data_sources(self, data_sources: list[type[DataSource]]):
        local: type[DataSource] = ScfLocalDataSource
        fide: type[DataSource] = FideDataSource
        PluginUtils.insert_on_equals(data_sources, local, fide, False)

    @hookimpl
    def insert_local_source_databases(self, databases: list[type[LocalSourceDatabase]]):
        scf: type[LocalSourceDatabase] = ScfDatabase
        fide: type[LocalSourceDatabase] = FideDatabase
        PluginUtils.insert_on_equals(databases, scf, fide, False)

    # ---------------------------------------------------------------------------------
    # Players
    # ---------------------------------------------------------------------------------

    @hookimpl
    def get_player_plugin_data_class(self) -> tuple[str, type[PluginData]]:
        return self.id, ScfPlayerPluginData

    @hookimpl
    def insert_player_form_fields_template(
        self, templates_by_section: defaultdict[str, list[str]]
    ):
        templates_by_section['fide'].append('/scf_player_form_fields.html')

    @hookimpl
    def validate_player_form_fields(
        self,
        action: str,
        tournament: 'Tournament',
        player: 'Player',
        data: dict[str, str],
        errors: dict[str, str],
    ):
        if tournament:
            # When adding a player, the tournament may not be chosen (in this case do not test)
            try:
                scf_code = WebContext.form_data_to_int(
                    data, field := 'scf_code', minimum=1
                )
                scf_codes = [
                    SCFUtils.get_player_plugin_data(p).scf_code
                    for p in tournament.tournament_players_by_id.values()
                    if not player or p.id != player.id
                ]

                if scf_code and scf_code in scf_codes:
                    errors[field] = _(
                        'The player with SCF code [{scf_code}] already '
                        'plays tournament [{tournament}].'
                    ).format(scf_code=scf_code, tournament=tournament.name)
            except ValueError:
                errors[field] = _('Invalid SCF code [{scf_code}].').format(
                    scf_code=data[field]
                )

    @hookimpl
    async def augment_player_after_search(
        self, stored_player: StoredPlayer, data_source: DataSource
    ):
        if data_source.id in (ScfLocalDataSource.static_id(),):
            return
        # Try to get more information by requesting the SCF SQL server
        fide_id = stored_player.fide_id
        if not fide_id:
            return
        scf_stored_player: StoredPlayer | None = None
        if (scf_database := ScfDatabase()).exists():
            # Try to get more information by requesting the SCF database
            with scf_database:
                scf_stored_player = scf_database.get_stored_player_by_fide_id(fide_id)
        if scf_stored_player:
            for rating_type in TournamentRating:
                stored_rating = stored_player.ratings.get(rating_type.value, None)
                rating = (
                    PlayerRating.from_stored_value(stored_rating)
                    if stored_rating
                    else None
                )
                scf_stored_rating = scf_stored_player.ratings.get(
                    rating_type.value, None
                )
                if scf_stored_rating:
                    scf_rating = PlayerRating.from_stored_value(scf_stored_rating)
                    augmented_rating = PlayerRating(
                        fide=rating.fide
                        if rating and rating.fide is not None
                        else scf_rating.fide,
                        national=rating.national
                        if rating and rating.national is not None
                        else scf_rating.national,
                        estimated=rating.estimated
                        if rating and rating.estimated is not None
                        else scf_rating.estimated,
                    )
                    stored_player.ratings[rating_type.value] = (
                        augmented_rating.stored_value
                    )
            if not stored_player.year_of_birth:
                stored_player.year_of_birth = scf_stored_player.year_of_birth
                stored_player.date_of_birth = None
            if not stored_player.comment:
                stored_player.comment = scf_stored_player.comment
            if not stored_player.club:
                stored_player.club = scf_stored_player.club
            stored_player.plugin_data[self.id] = copy.copy(
                scf_stored_player.plugin_data.get(self.id, {})
            )

    @hookimpl
    def is_tournament_participation_possible(
        self, tournament: 'Tournament', tournament_player: 'TournamentPlayer'
    ) -> str | None:
        plugin_data = SCFUtils.get_player_plugin_data(tournament_player)
        scf_code = plugin_data.scf_code

        if scf_code and any(
            SCFUtils.get_player_plugin_data(player_).scf_code == scf_code
            for player_ in tournament.tournament_players_by_id.values()
        ):
            # This string is not translated because the error should never happen
            return f'SCF code [{scf_code}] already present in tournament [{tournament.name}].'

        return None

    @hookimpl
    def insert_player_datasheet_columns(self, datasheet_columns: list[DatasheetColumn]):
        tournament: type[DatasheetColumn] = player_datasheet.TournamentColumn
        scf_columns: list[DatasheetColumn] = [
            ScfCodeDatasheetColumn(),
        ]
        for column in scf_columns:
            PluginUtils.insert_on_isinstance(
                datasheet_columns, column, tournament, after=False
            )
