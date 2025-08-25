import tempfile
from pathlib import Path

from common.exception import SharlyChessException
from common.i18n import _
from data.input_output import TournamentImporter
from data.input_output.dict_reader import DictReaderException
from data.input_output.tournament_importer_options import (
    FileTournamentImporterOption,
    JsonFileOption,
    TournamentImporterOption,
)
from database.sqlite.event.event_store import StoredTournament, StoredPlayer
from plugins.ffe.papi_converter import PapiConverter
from utils.option import OptionError


class PapiFileOption(FileTournamentImporterOption):
    @staticmethod
    def static_id() -> str:
        return 'papi_file'

    @property
    def accepted_file_suffixes(self) -> list[str]:
        return ['.papi']


class PapiTournamentImporter(TournamentImporter):
    @staticmethod
    def static_id() -> str:
        return 'PAPI'

    @staticmethod
    def static_name() -> str:
        return _('Papi file')

    @staticmethod
    def available_options() -> list[type[TournamentImporterOption]]:
        return [PapiFileOption]

    @property
    def modal_title(self) -> str:
        return _('Import Papi file')

    @property
    def reorder_boards(self) -> bool:
        return True

    async def load_stored_tournament(
        self, stored_tournament: StoredTournament | None = None
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        papi_file_option = self._get_option(PapiFileOption)

        fd, tmp_name = tempfile.mkstemp(prefix='tournament-import-', suffix='.papi')
        Path(tmp_name).write_bytes(await papi_file_option.value.read())
        tmp_path = Path(tmp_name)
        try:
            return PapiConverter().read_papi_file(tmp_path, stored_tournament)
        except SharlyChessException as exception:
            raise OptionError(str(exception), papi_file_option)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


class PapiJsonTournamentImporter(TournamentImporter):
    @staticmethod
    def static_id() -> str:
        return 'PAPI_JSON'

    @staticmethod
    def static_name() -> str:
        return _('JSON file (papi-converter format)')

    @staticmethod
    def available_options() -> list[type[TournamentImporterOption]]:
        return [JsonFileOption]

    @property
    def modal_title(self) -> str:
        return _('Import JSON file (papi-converter format)')

    @property
    def reorder_boards(self) -> bool:
        return True

    async def load_stored_tournament(
        self, stored_tournament: StoredTournament | None = None
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        json_file_option = self._get_option(JsonFileOption)
        try:
            return PapiConverter().read_papi_data(
                await json_file_option.load_json(), stored_tournament
            )
        except DictReaderException as exception:
            raise OptionError(str(exception), json_file_option)
