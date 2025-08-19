from pathlib import Path

from common.exception import SharlyChessException
from common.i18n import _
from data.input_output import TournamentImporter
from database.sqlite.event.event_store import StoredTournament, StoredPlayer
from plugins.ffe.papi_converter import PapiConverter


class PapiTournamentImporter(TournamentImporter):
    @staticmethod
    def static_id() -> str:
        return 'PAPI'

    @staticmethod
    def static_name() -> str:
        return _('Papi file')

    @property
    def modal_title(self) -> str:
        return _('Import Papi file')

    @property
    def reorder_boards(self) -> bool:
        return True

    def load_stored_tournament(
        self, source_file: Path, stored_tournament: StoredTournament | None = None
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        if source_file.suffix != '.papi':
            raise SharlyChessException(
                _('File is expected to have the [{suffix}] suffix').format(
                    suffix='papi'
                )
            )
        return PapiConverter().read_papi_file(source_file, stored_tournament)


class PapiJsonTournamentImporter(TournamentImporter):
    @staticmethod
    def static_id() -> str:
        return 'PAPI_JSON'

    @staticmethod
    def static_name() -> str:
        return _('JSON file (papi-converter format)')

    @property
    def modal_title(self) -> str:
        return _('Import JSON file (papi-converter format)')

    @property
    def reorder_boards(self) -> bool:
        return True

    def load_stored_tournament(
        self, source_file: Path, stored_tournament: StoredTournament | None = None
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        if source_file.suffix != '.json':
            raise SharlyChessException(
                _('File is expected to have the [{suffix}] suffix').format(
                    suffix='json'
                )
            )
        return PapiConverter().read_papi_file(source_file, stored_tournament)
