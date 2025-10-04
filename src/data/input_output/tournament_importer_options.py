from abc import ABC, abstractmethod
from pathlib import Path
from types import UnionType
from typing import Any


from common.exception import OptionError
from common.i18n import _
from data.tournament import Tournament
from utils.option import Option


class TournamentImporterOption(Option, ABC):
    """Parent class of all the options of tournament importers."""

    @property
    def template_name(self) -> str:
        return f'/admin/tournaments/import_options/{self.template_file_name}.html'

    @property
    def template_file_name(self) -> str:
        """Name of the file of the template."""
        return self.id

    @property
    def default_value(self) -> Any:
        return self.get_default_value()

    @abstractmethod
    def get_default_value(self, tournament: Tournament | None = None) -> Any:
        """Set the default form value from the event or tournament on the modal."""


class FileOption(TournamentImporterOption):
    @staticmethod
    def static_id() -> str:
        return 'file'

    @property
    def type(self) -> type | UnionType:
        return Path | None

    def get_default_value(self, tournament: Tournament | None = None) -> Any:
        return None

    def validate(self):
        super().validate()
        if self.value is None:
            raise OptionError(_('A file is expected.'), self)
