from pathlib import Path
from data.input_output.tournament_importers import TournamentImporter
from database.sqlite.event.event_store import StoredPlayer, StoredTournament
from plugins.ffe.papi_converter import PapiConverter


class JsonTournamentImporter(TournamentImporter):
    @staticmethod
    def static_id() -> str:
        return 'JSON Test data'

    @staticmethod
    def static_name() -> str:
        return 'JSON Test data'

    @property
    def reorder_boards(self) -> bool:
        return True

    def load_stored_tournament(
        self, source_file: Path, stored_tournament: StoredTournament | None = None
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        # For the moment the json data format is the same as that produced by papi-converter
        return PapiConverter().read_papi_file(source_file, stored_tournament)
