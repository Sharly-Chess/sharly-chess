import json
from abc import ABC, abstractmethod
from json import JSONDecodeError
from pathlib import Path
from types import UnionType
from typing import Any

from litestar.datastructures import UploadFile

from common.exception import SharlyChessException
from common.i18n import _
from utils.option import Option, OptionError


class TournamentImporterOption(Option, ABC):
    """Parent class of all the options of tournament importers."""

    @property
    def template_name(self) -> str:
        return f'/admin/tournaments/import_options/{self.template_file_name}.html'

    @property
    @abstractmethod
    def template_file_name(self) -> str:
        """Name of the file of the template."""


class FileTournamentImporterOption(TournamentImporterOption, ABC):
    """Option for a file input."""

    @property
    @abstractmethod
    def accepted_file_suffixes(self) -> list[str]:
        """List of suffixes accepted by the file input."""

    @property
    def template_file_name(self) -> str:
        return 'file'

    @property
    def type(self) -> type | UnionType:
        return UploadFile | None

    @property
    def default_value(self) -> Any:
        return None

    def validate(self):
        super().validate()
        if self.value is None:
            raise OptionError(_('A file is expected.'), self)
        suffix = Path(self.value.filename).suffix
        if suffix not in self.accepted_file_suffixes:
            raise OptionError(
                _('File has invalid suffix [{suffix}] (expected: {expected}).').format(
                    suffix=suffix,
                    expected=', '.join(self.accepted_file_suffixes),
                ),
                self,
            )


class TrfFileInput(FileTournamentImporterOption):
    @staticmethod
    def static_id() -> str:
        return 'trf_file'

    @property
    def accepted_file_suffixes(self) -> list[str]:
        return ['.trf', '.trfx']


class JsonFileOption(FileTournamentImporterOption):
    @staticmethod
    def static_id() -> str:
        return 'json_file'

    @property
    def accepted_file_suffixes(self) -> list[str]:
        return ['.json']

    async def load_json(self) -> dict[str, Any]:
        assert isinstance(self.value, UploadFile)
        try:
            return json.loads(await self.value.read())
        except (UnicodeDecodeError, JSONDecodeError) as error:
            raise SharlyChessException(
                f'Error while reading JSON file [{self.value.filename}]: {error}'
            )
