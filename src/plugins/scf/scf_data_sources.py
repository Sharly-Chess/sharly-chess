from common.i18n import _
from data.input_output.data_source import LocalDataSource
from data.input_output.player_updater_fields import (
    PlayerUpdaterField,
    FideIDUpdaterField,
    TitleUpdaterField,
    NameUpdaterField,
    CategoryUpdaterField,
    GenderPlayerUpdater,
    StandardRatingUpdaterField,
    FederationUpdaterField,
    ClubUpdaterField,
)
from data.player import Player
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.local_source_database import LocalSourcePlayerDatabase
from plugins.scf import PLUGIN_NAME
from plugins.scf.scf_database import ScfDatabase
from plugins.scf.utils import get_data


class ScfLocalDataSource(LocalDataSource):
    @staticmethod
    def static_id() -> str:
        return f'{PLUGIN_NAME}-local'

    @staticmethod
    def static_name() -> str:
        return _('SCF database (local)')

    @property
    def local_database_type(self) -> type[LocalSourcePlayerDatabase]:
        return ScfDatabase

    @property
    def player_updater_fields(self) -> list[PlayerUpdaterField]:
        return [
            FideIDUpdaterField(),
            TitleUpdaterField(),
            NameUpdaterField(),
            CategoryUpdaterField(),
            GenderPlayerUpdater(),
            StandardRatingUpdaterField(),
            FederationUpdaterField(),
            ClubUpdaterField(),
        ]

    @staticmethod
    def _get_scf_code(stored_player: StoredPlayer) -> str | None:
        return get_data(stored_player.plugin_data, 'scf_code', None)

    def check_player_match(self, player1: StoredPlayer, player2: StoredPlayer) -> bool:
        if scf_code := self._get_scf_code(player1):
            return scf_code == self._get_scf_code(player2)
        if fide_id := player1.fide_id:
            return fide_id == player2.fide_id
        return False

    async def get_match_stored_players(
        self, players: list[Player]
    ) -> list[StoredPlayer] | None:
        scf_codes: list[str] = []
        fide_ids: list[int] = []
        for player in players:
            if scf_code := self._get_scf_code(player.stored_player):
                scf_codes.append(scf_code)
            if fide_id := player.stored_player.fide_id:
                fide_ids.append(fide_id)

        database = ScfDatabase()
        if not database.exists():
            return None
        with database:
            scf_code_matches = database.get_stored_players_by_scf_code(scf_codes)
            fide_id_matches = database.get_stored_players_by_fide_id(fide_ids)
        return scf_code_matches + fide_id_matches

    @property
    def search_fields(self) -> list[str]:
        return [_('Name'), _('SCF Code'), _('FIDE ID')]

    @property
    def player_search_result_template(self) -> str:
        return '/scf_search_result.html'

    def get_player_source_id(self, stored_player: StoredPlayer) -> str:
        return str(get_data(stored_player.plugin_data, 'scf_code'))

    async def get_stored_player_by_source_id(
        self, player_source_id: str
    ) -> StoredPlayer | None:
        if not player_source_id.isdigit():
            return None
        with ScfDatabase() as database:
            return database.get_stored_player_by_scf_code(int(player_source_id))
