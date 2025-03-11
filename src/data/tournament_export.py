from abc import ABC, abstractmethod

from common.i18n import _
from data.util import TrfType


class AbstractTournamentExporter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def download_url(self) -> str:
        """URL downloading the export file.
        Should be formattable with {event_uniq_id} and {tournament_id}"""
        pass


class Trf16TournamentExporter(AbstractTournamentExporter):
    @property
    def download_url(self) -> str:
        return (
            '/admin/tournament-trf-export/{event_uniq_id}/{tournament_id}'
            f'?usage={TrfType.RATING}'
        )

    @property
    def name(self) -> str:
        return _('Export to TRF16 (rating)')


class TrfBxTournamentExporter(AbstractTournamentExporter):
    @property
    def download_url(self) -> str:
        return (
            '/admin/tournament-trf-export/{event_uniq_id}/{tournament_id}'
            f'?usage={TrfType.PAIRING}'
        )

    @property
    def name(self) -> str:
        return _('Export to TRF(bx) (pairing)')
