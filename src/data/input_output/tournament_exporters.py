from abc import ABC, abstractmethod
from typing import IO, override

import trf

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
    def file_encoding(self) -> str:
        return 'UTF-8'

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

    def dump_to_file(self, file: IO, tournament: Tournament):
        trf.dump(file, tournament.to_trf(TrfType.TRF_16))


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

    def dump_to_file(self, file: IO, tournament: Tournament):
        trf.dump(file, tournament.to_trf(TrfType.TRF_BX))


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

    @staticmethod
    @override
    def file_name(tournament: Tournament) -> str:
        return f'{tournament.name} - ' + _('Round #{round}').format(
            round=tournament.current_round
        )

    def dump_to_file(self, file: IO, tournament: Tournament):
        show_tournament_name = len(tournament.event.tournaments_by_id.values()) != 1
        for board in tournament.boards:
            file.write(
                board.to_pgn(
                    tournament,
                    tournament.current_round,
                    show_tournament_name,
                )
            )
