from abc import ABC, abstractmethod
from typing import IO, override

import trf

from common import unicode_normalize
from common.i18n import _
from data.tournament import Tournament
from utils.entity import IdentifiableEntity
from utils.enum import TrfType


class TournamentExporter(IdentifiableEntity, ABC):
    """Abstract class representing an export format for a tournament."""

    @property
    @abstractmethod
    def tooltip(self) -> str:
        """Tooltip to display on the export button."""

    def is_unavailable_message(self, tournament: Tournament) -> str | None:
        """Get a message about why the export is unavailable for the tournament.
        Returns None if the export is available."""
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
        return tournament.name

    @property
    def file_encoding(self) -> str | None:
        return None

    @property
    def is_binary_file(self) -> bool:
        return False


class Trf16TournamentExporter(TournamentExporter):
    @staticmethod
    def static_id() -> str:
        return 'trf-16'

    @staticmethod
    def static_name() -> str:
        return 'TRF16'

    @property
    def tooltip(self) -> str:
        return _('Export the tournament to the TRF16 format.')

    @property
    def file_extension(self) -> str:
        return 'trf'

    @property
    def file_encoding(self) -> str:
        return 'ascii'

    def dump_to_file(self, file: IO, tournament: Tournament):
        trf_tournament = trf.dumps(tournament.to_trf(TrfType.TRF_16))
        file.write(unicode_normalize(trf_tournament))


class TrfBxTournamentExporter(TournamentExporter):
    @staticmethod
    def static_id() -> str:
        return 'trf-bx'

    @staticmethod
    def static_name() -> str:
        return 'TRF(bx)'

    @property
    def tooltip(self) -> str:
        return _(
            'Export the tournament to the TRF(bx) format (usage: pairings generation).'
        )

    @property
    def file_extension(self) -> str:
        return 'trfx'

    @property
    def file_encoding(self) -> str:
        return 'ascii'

    def dump_to_file(self, file: IO, tournament: Tournament):
        trf_tournament = trf.dumps(tournament.to_trf(TrfType.TRF_BX))
        file.write(unicode_normalize(trf_tournament))


class PgnTournamentExporter(TournamentExporter):
    @staticmethod
    def static_id() -> str:
        return 'pgn'

    @staticmethod
    def static_name() -> str:
        return 'PGN'

    @property
    def tooltip(self) -> str:
        return _(
            'Export all the games of the last round of the tournament '
            'to the PGN format (usage: pairings transfer).'
        )

    @property
    def file_extension(self) -> str:
        return 'pgn'

    @property
    def file_encoding(self) -> str:
        return 'UTF-8'

    @staticmethod
    @override
    def file_name(tournament: Tournament) -> str:
        return f'{tournament.name} - ' + _('Round #{round}').format(
            round=tournament.current_round
        )

    def dump_to_file(self, file: IO, tournament: Tournament):
        for board in tournament.boards:
            file.write(board.to_pgn(tournament, tournament.current_round))
