import json
import tempfile
from abc import abstractmethod, ABC
from functools import partial
from json import JSONDecodeError
from pathlib import Path
from types import UnionType
from typing import Any

from requests import Response, get

from common.logger import get_logger
from common.exception import SharlyChessException, DictReaderException, ImporterError
from common.i18n import _
from data.event import Event
from data.input_output.dict_reader import dict_to_dataclass
from data.input_output.tournament_importer_options import TournamentImporterOption
from data.input_output.tournament_importers import FileTournamentImporter
from data.tournament import Tournament
from database.sqlite.event.event_store import StoredTournament, StoredPlayer
from plugins.ffe import PLUGIN_NAME
from utils.enum import EventType
from plugins.ffe.papi_converter import PapiConverter, PapiData
from plugins.manager import plugin_manager
from data.pairings.acceleration import AccelerationUtils

logger = get_logger()


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
                    AccelerationUtils.set_pairing_settings_from_rating_threshold,
                    rating_threshold=rating_threshold_1,
                ),
            )
        else:
            self.post_import_task.insert(
                0,
                partial(
                    AccelerationUtils.set_pairing_settings_from_dual_rating_thresholds,
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


class FfeImporterOption(TournamentImporterOption, ABC):
    @classmethod
    def static_id(cls) -> str:
        return f'{PLUGIN_NAME}_{cls.sub_id()}'

    @staticmethod
    @abstractmethod
    def sub_id() -> str:
        """ID of option (unique amongst the other FFE options)"""

    @property
    def template_name(self) -> str:
        return f'/ffe_tournament_importer_options/{self.template_file_name}.html'

    @property
    def template_file_name(self) -> str:
        return self.sub_id()


class FfeTournamentIdOption(FfeImporterOption):
    @staticmethod
    def sub_id() -> str:
        return 'tournament_id'

    @property
    def type(self) -> type | UnionType:
        return int | None

    def get_default_value(self, tournament: Tournament | None = None) -> Any:
        return None


class OnlineTournamentImporter(FfeTournamentImporter):
    @staticmethod
    def sub_id() -> str:
        return 'online'

    @staticmethod
    def static_name() -> str:
        return _('Online FFE tournament')

    @property
    def modal_title(self) -> str:
        return _('Import online FFE tournament')

    @staticmethod
    def available_options() -> list[type[TournamentImporterOption]]:
        return [
            FfeTournamentIdOption,
        ]

    def load_stored_tournament(
        self, event: Event, stored_tournament: StoredTournament | None = None
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        (tournament_id,) = self.get_option_values()
        with tempfile.TemporaryDirectory() as tmpdir:
            target: Path = Path(tmpdir) / f'{tournament_id}.papi'
            url: str = f'https://www.echecs.asso.fr/Tournois/Id/{tournament_id}/{tournament_id}.papi'
            logger.info('Downloading [%s]...', url)
            try:
                response: Response = get(
                    url, allow_redirects=True, timeout=60, stream=True
                )
                match response.status_code:
                    case 200:
                        total = int(response.headers.get('content-length', 0))
                        logger.info('Receiving %.1f MB...', total / 1_048_576)
                        received = 0
                        with open(target, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=1024 * 1024):
                                f.write(chunk)
                                received += len(chunk)
                                logger.debug(
                                    'Downloaded %d / %d bytes.',
                                    received,
                                    total,
                                )
                        logger.info(
                            'Download complete (%.1f MB).',
                            received / 1_048_576,
                        )
                        papi_data = PapiConverter().read_papi_file(target)
                        self._add_rating_threshold_task(papi_data)
                        return self.read_papi_data(event, papi_data, stored_tournament)
                    case 404:
                        logger.error('Tournament [%d] not found.', tournament_id)
                        raise ImporterError(
                            _('Tournament [{tournament_id}] not found.').format(
                                tournament_id=tournament_id
                            )
                        )
                    case _:
                        logger.error(
                            'Could not download [{%s}], error code {%d}.',
                            url,
                            response.status_code,
                        )
                        raise ImporterError(
                            _('Could not download [{url}], error code {code}.').format(
                                url=url, code=response.status_code
                            )
                        )
            except ConnectionError as exception:
                logger.exception('Could not download [%s]', url, exception)
                raise ImporterError(
                    _('Could not download [{url}]: {error}.').format(
                        url=url, error=exception
                    )
                )
