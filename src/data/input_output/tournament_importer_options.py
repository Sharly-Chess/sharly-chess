from abc import ABC, abstractmethod
from pathlib import Path
from types import UnionType
from typing import Any


from common.exception import OptionError
from common.i18n import _
from data.tournament import Tournament
from utils.enum import TournamentRating
from utils.option import Option


class TournamentImporterOption[V](Option[V], ABC):
    """Parent class of all the options of tournament importers."""

    @property
    def template_name(self) -> str:
        return f'/admin/tournaments/import_options/{self.template_file_name}.html'

    @property
    def template_file_name(self) -> str:
        """Name of the file of the template."""
        return self.id

    @property
    def default_value(self) -> V:
        return self.get_default_value()

    @abstractmethod
    def get_default_value(self, tournament: Tournament | None = None) -> V:
        """Set the default form value from the event or tournament on the modal."""

    @property
    def template_context(self) -> dict[str, Any]:
        """Context to add to the template for the option."""
        return {}


class FileOption(TournamentImporterOption[Path | None]):
    @staticmethod
    def static_id() -> str:
        return 'file'

    @property
    def type(self) -> type | UnionType:
        return Path | None

    def get_default_value(self, tournament: Tournament | None = None) -> Path | None:
        return None

    def validate(self) -> None:
        super().validate()
        if self.value is None:
            raise OptionError(_('A file is expected.'), self)


class TournamentRatingOption(TournamentImporterOption[int]):
    @staticmethod
    def static_id() -> str:
        return 'tournament_rating'

    @property
    def type(self) -> type | UnionType:
        return int

    def get_default_value(self, tournament: Tournament | None = None) -> int:
        if tournament:
            return tournament.rating.value
        return TournamentRating.STANDARD.value

    def validate(self) -> None:
        super().validate()
        try:
            TournamentRating(self.value)
        except ValueError:
            raise OptionError(f'Unknown tournament type {self.value}', self) from None

    @property
    def template_context(self) -> dict[str, Any]:
        return {
            'rating_options': {
                str(rating.value): rating.short_name for rating in TournamentRating
            }
        }
