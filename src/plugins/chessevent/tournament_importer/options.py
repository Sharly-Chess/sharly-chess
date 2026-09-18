from abc import ABC, abstractmethod
from types import UnionType

from data.input_output.tournament_importer_options import TournamentImporterOption
from data.tournament import Tournament
from plugins.chessevent import PLUGIN_NAME
from plugins.chessevent.utils import ChessEventUtils


class ChessEventImporterOption[V](TournamentImporterOption[V], ABC):
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


class ChessEventUserOption(ChessEventImporterOption[str | None]):
    @staticmethod
    def sub_id() -> str:
        return 'user'

    @property
    def type(self) -> type | UnionType:
        return str | None

    def get_default_value(self, tournament: Tournament | None = None) -> str | None:
        if not tournament:
            return None
        return ChessEventUtils.get_tournament_plugin_data(tournament).user


class ChessEventPasswordOption(ChessEventImporterOption[str | None]):
    @staticmethod
    def sub_id() -> str:
        return 'password'

    @property
    def type(self) -> type | UnionType:
        return str | None

    def get_default_value(self, tournament: Tournament | None = None) -> str | None:
        if not tournament:
            return None
        return ChessEventUtils.get_tournament_plugin_data(tournament).password


class ChessEventEventOption(ChessEventImporterOption[str | None]):
    @staticmethod
    def sub_id() -> str:
        return 'event'

    @property
    def type(self) -> type | UnionType:
        return str | None

    def get_default_value(self, tournament: Tournament | None = None) -> str | None:
        if not tournament:
            return None
        return ChessEventUtils.get_tournament_plugin_data(tournament).event_id


class ChessEventTournamentOption(ChessEventImporterOption[str | None]):
    @staticmethod
    def sub_id() -> str:
        return 'tournament_name'

    @property
    def type(self) -> type | UnionType:
        return str | None

    def get_default_value(self, tournament: Tournament | None = None) -> str | None:
        if not tournament:
            return None
        return ChessEventUtils.get_tournament_plugin_data(tournament).tournament_name
