from abc import ABC, abstractmethod
from typing import IO, ClassVar, override

from common.i18n.utils import unicode_normalize

from common.i18n import _
from data.input_output.trf.trf_serializer import TrfSerializer
from data.tournament import Tournament
from utils.entity import IdentifiableEntity
from utils.enum import EventType


class TournamentExporter(IdentifiableEntity, ABC):
    """Abstract class representing an export format for a tournament."""

    supported_event_types: ClassVar[list[EventType] | None] = None
    """The event types this exporter supports, or None for all types.
    Unsupported exporters are filtered out of the export menu."""

    @classmethod
    def supports_event_type(cls, event_type: EventType) -> bool:
        return (
            cls.supported_event_types is None or event_type in cls.supported_event_types
        )

    @property
    def tooltip(self) -> str | None:
        """Tooltip to display on the export button."""
        return None

    @property
    def data_loss_modal_redirect(self) -> bool:
        """Defines if the export button should redirect to the data loss warning modal."""
        return True

    def is_unavailable_message(self, tournament: Tournament) -> str | None:
        """Get a message about why the export is unavailable for the tournament.
        Returns None if the export is available."""
        return None

    def warning_message(self, tournament: Tournament) -> str | None:
        """Get a warning message about the export for the tournament.
        Returns None for no warning."""
        return None

    @abstractmethod
    def dump_to_file(self, file: IO, tournament: Tournament):
        """Dump the content of the *tournament* to export into the *file*."""

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Extension of the file to download."""

    @staticmethod
    def file_name(tournament: Tournament) -> str:
        """Name of the file to download."""
        return tournament.sanitized_name

    @property
    def file_encoding(self) -> str | None:
        return None

    @property
    def is_binary_file(self) -> bool:
        return False


class Trf26TournamentExporter(TournamentExporter):
    @staticmethod
    def static_id() -> str:
        return 'trf-26'

    @staticmethod
    def static_name() -> str:
        return _('TRF26')

    @property
    def file_extension(self) -> str:
        return 'trf'

    @property
    def file_encoding(self) -> str:
        return 'ascii'

    def dump_to_file(self, file: IO, tournament: Tournament):
        trf_tournament = TrfSerializer.dumps(tournament.to_trf())
        file.write(unicode_normalize(trf_tournament))


class PgnTournamentExporter(TournamentExporter):
    @staticmethod
    def static_id() -> str:
        return 'pgn'

    @staticmethod
    def static_name() -> str:
        return _('PGN')

    @property
    def tooltip(self) -> str:
        return _(
            'Export all the games of the last round of the tournament '
            'to the PGN format (usage: pairings transfer).'
        )

    @property
    def data_loss_modal_redirect(self) -> bool:
        return False

    @property
    def file_extension(self) -> str:
        return 'pgn'

    @property
    def file_encoding(self) -> str:
        return 'UTF-8'

    @staticmethod
    @override
    def file_name(tournament: Tournament) -> str:
        return (
            tournament.sanitized_name
            + '-'
            + _('round_{round}').format(round=tournament.current_round)
        )

    def dump_to_file(self, file: IO, tournament: Tournament):
        for board in tournament.boards:
            file.write(board.to_pgn(tournament, tournament.current_round))
