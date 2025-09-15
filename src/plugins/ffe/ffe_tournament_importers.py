import json
from json import JSONDecodeError

from common.exception import SharlyChessException, DictReaderException, ImporterError
from common.i18n import _
from data.input_output.tournament_importers import FileTournamentImporter
from database.sqlite.event.event_store import StoredTournament, StoredPlayer
from plugins.ffe.papi_converter import PapiConverter


class PapiTournamentImporter(FileTournamentImporter):
    @staticmethod
    def static_id() -> str:
        return 'PAPI'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Papi file', locale)

    @property
    def modal_title(self) -> str:
        return _('Import Papi file')

    @property
    def reorder_boards(self) -> bool:
        return True

    @property
    def accepted_file_suffixes(self) -> list[str]:
        return ['.papi']

    def load_stored_tournament(
        self, stored_tournament: StoredTournament | None = None
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        (file_path,) = self.get_option_values()
        try:
            return PapiConverter().read_papi_file(file_path, stored_tournament)
        except DictReaderException as exception:
            raise ImporterError(str(exception))


class PapiJsonTournamentImporter(FileTournamentImporter):
    @staticmethod
    def static_id() -> str:
        return 'PAPI_JSON'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('JSON file (papi-converter format)', locale)

    @property
    def modal_title(self) -> str:
        return _('Import JSON file (papi-converter format)')

    @property
    def accepted_file_suffixes(self) -> list[str]:
        return ['.json']

    @property
    def reorder_boards(self) -> bool:
        return True

    def load_stored_tournament(
        self, stored_tournament: StoredTournament | None = None
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        (file_path,) = self.get_option_values()
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                papi_data_dict = json.load(file)
            return PapiConverter().read_papi_data(papi_data_dict, stored_tournament)
        except (UnicodeDecodeError, JSONDecodeError) as error:
            raise SharlyChessException(f'Error while reading JSON file: {error}')
        except DictReaderException as exception:
            raise ImporterError(str(exception))
