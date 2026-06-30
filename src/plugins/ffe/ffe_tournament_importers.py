import json
from abc import abstractmethod
from functools import partial
from json import JSONDecodeError

from common.exception import SharlyChessException, DictReaderException, ImporterError
from common.i18n import _
from data.event import Event
from data.input_output.dict_reader import dict_to_dataclass
from data.input_output.tournament_importers import FileTournamentImporter
from database.sqlite.event.event_store import StoredTournament, StoredPlayer
from plugins.ffe import PLUGIN_NAME
from utils.enum import EventType
from plugins.ffe.papi_converter import PapiConverter, PapiData
from plugins.manager import plugin_manager
from plugins.pairing_acceleration.utils import PairingAccelerationUtils


class FfeTournamentImporter(FileTournamentImporter):
    # Papi (and its JSON twin) is an individual-tournament format.
    supported_event_types = [EventType.INDIVIDUAL]

    @classmethod
    def static_id(cls) -> str:
        return f'{PLUGIN_NAME}-{cls.sub_id()}'

    @staticmethod
    @abstractmethod
    def sub_id() -> str:
        """ID of the importer amongst the plugin."""

    def _add_rating_threshold_task(self, papi_data: PapiData):
        variables = papi_data.variables
        rating_threshold_1 = 0
        if variables.ratingThreshold1:
            if not variables.ratingThreshold1.isdigit():
                raise DictReaderException(
                    ['variables', 'ratingThreshold1'],
                    _('A positive integer is expected.'),
                )
            rating_threshold_1 = int(variables.ratingThreshold1)
        rating_threshold_2 = 0
        if variables.ratingThreshold2:
            if not variables.ratingThreshold2.isdigit():
                raise DictReaderException(
                    ['variables', 'ratingThreshold2'],
                    _('A positive integer is expected.'),
                )
            rating_threshold_2 = int(variables.ratingThreshold2)
        if (rating_threshold_1, rating_threshold_2) == (0, 0):
            return
        if rating_threshold_1 == rating_threshold_2 or rating_threshold_2 == 0:
            self.post_import_task.insert(
                0,
                partial(
                    PairingAccelerationUtils.set_pairing_settings_from_rating_threshold,
                    rating_threshold=rating_threshold_1,
                ),
            )
        else:
            self.post_import_task.insert(
                0,
                partial(
                    PairingAccelerationUtils.set_pairing_settings_from_dual_rating_thresholds,
                    lower_rating_threshold=rating_threshold_2,
                    upper_rating_threshold=rating_threshold_1,
                ),
            )

    def read_papi_data(
        self,
        event: Event,
        papi_data: PapiData,
        stored_tournament: StoredTournament | None,
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        stored_tournament, stored_players = PapiConverter().read_papi_data(
            event, papi_data, stored_tournament
        )
        for stored_player in stored_players:
            plugin_manager.hook_for_event(
                event, 'augment_stored_player_on_papi_import'
            )(
                event=event,
                importer=self,
                stored_player=stored_player,
            )
        return stored_tournament, stored_players


class PapiTournamentImporter(FfeTournamentImporter):
    @staticmethod
    def sub_id() -> str:
        return 'PAPI'

    @staticmethod
    def static_name() -> str:
        return _('Papi file')

    @property
    def modal_title(self) -> str:
        return _('Import Papi file')

    @property
    def accepted_file_suffixes(self) -> list[str]:
        return ['.papi']

    def load_stored_tournament(
        self, event: Event, stored_tournament: StoredTournament | None = None
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        (file_path,) = self.get_option_values()
        try:
            papi_data = PapiConverter().read_papi_file(file_path)
            self._add_rating_threshold_task(papi_data)
            return self.read_papi_data(event, papi_data, stored_tournament)
        except DictReaderException as exception:
            raise ImporterError(str(exception))


class PapiJsonTournamentImporter(FfeTournamentImporter):
    @staticmethod
    def sub_id() -> str:
        return 'PAPI_JSON'

    @staticmethod
    def static_name() -> str:
        return _('JSON file (papi-converter format)')

    @property
    def modal_title(self) -> str:
        return _('Import JSON file (papi-converter format)')

    @property
    def accepted_file_suffixes(self) -> list[str]:
        return ['.json']

    def load_stored_tournament(
        self, event: Event, stored_tournament: StoredTournament | None = None
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        (file_path,) = self.get_option_values()
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                papi_data_dict = json.load(file)
            papi_data = dict_to_dataclass(PapiData, papi_data_dict)
            self._add_rating_threshold_task(papi_data)
            return self.read_papi_data(event, papi_data, stored_tournament)
        except (UnicodeDecodeError, JSONDecodeError) as error:
            raise SharlyChessException(f'Error while reading JSON file: {error}')
        except DictReaderException as exception:
            raise ImporterError(str(exception))
