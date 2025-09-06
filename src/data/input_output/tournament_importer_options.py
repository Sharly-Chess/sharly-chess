from abc import ABC, abstractmethod
from pathlib import Path
from types import UnionType
from typing import Any


from common.exception import OptionError
from common.i18n import _
from utils.option import Option


class TournamentImporterOption(Option, ABC):
    """Parent class of all the options of tournament importers."""

    @property
    def template_name(self) -> str:
        return f'/admin/tournaments/import_options/{self.template_file_name}.html'

    @property
    @abstractmethod
    def template_file_name(self) -> str:
        """Name of the file of the template."""


class FileOption(TournamentImporterOption):
    @staticmethod
    def static_id() -> str:
        return 'file'

    @property
    def template_file_name(self) -> str:
        return 'file'

    @property
    def type(self) -> type | UnionType:
        return Path | None

    @property
    def default_value(self) -> Any:
        return None

    def validate(self):
        super().validate()
        if self.value is None:
            raise OptionError(_('A file is expected.'), self)
