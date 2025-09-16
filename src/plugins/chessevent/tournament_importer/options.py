from abc import ABC, abstractmethod
from types import UnionType
from typing import Any

from data.input_output.tournament_importer_options import TournamentImporterOption
from data.tournament import Tournament
from plugins.chessevent import PLUGIN_NAME
from plugins.chessevent.utils import get_data


class ChessEventImporterOption(TournamentImporterOption, ABC):
    @classmethod
    def static_id(cls) -> str:
        return f'{PLUGIN_NAME}_{cls.sub_id()}'

    @staticmethod
    @abstractmethod
    def sub_id() -> str:
        """ID of option (unique amongst the other ChessEvent options)"""

    @property
    def template_name(self) -> str:
        return f'/chessevent_tournament_importer_options/{self.template_file_name}.html'

    @property
    def template_file_name(self) -> str:
        return self.sub_id()


class ChessEventUserOption(ChessEventImporterOption):
    @staticmethod
    def sub_id() -> str:
        return 'user_id'

    @property
    def type(self) -> type | UnionType:
        return str | None

    def get_default_value(self, tournament: Tournament | None = None) -> Any:
        if not tournament:
            return None
        return get_data(tournament.plugin_data, 'chessevent_user_id', None)


class ChessEventPasswordOption(ChessEventImporterOption):
    @staticmethod
    def sub_id() -> str:
        return 'password'

    @property
    def type(self) -> type | UnionType:
        return str | None

    def get_default_value(self, tournament: Tournament | None = None) -> Any:
        if not tournament:
            return None
        return get_data(tournament.plugin_data, 'chessevent_password', None)


class ChessEventEventOption(ChessEventImporterOption):
    @staticmethod
    def sub_id() -> str:
        return 'event_id'

    @property
    def type(self) -> type | UnionType:
        return str | None

    def get_default_value(self, tournament: Tournament | None = None) -> Any:
        if not tournament:
            return None
        return get_data(tournament.plugin_data, 'chessevent_event_id', None)


class ChessEventTournamentOption(ChessEventImporterOption):
    @staticmethod
    def sub_id() -> str:
        return 'tournament_name'

    @property
    def type(self) -> type | UnionType:
        return str | None

    def get_default_value(self, tournament: Tournament | None = None) -> Any:
        if not tournament:
            return None
        return get_data(tournament.plugin_data, 'chessevent_tournament_name', None)
