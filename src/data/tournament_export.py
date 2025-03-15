from abc import ABC, abstractmethod
from typing import Any

from common.i18n import _
from data.util import TrfType


class AbstractTournamentExporter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def download_route(self) -> str:
        """Route downloading the export file.
        Should take as parameters event_uniq_id: str and tournament_id: int"""

    @property
    def route_parameters(self) -> dict[str, Any]:
        return {}


class Trf16TournamentExporter(AbstractTournamentExporter):
    @property
    def download_route(self) -> str:
        return 'admin-tournament-trf-export'

    @property
    def name(self) -> str:
        return _('Export to TRF16 (rating)')

    @property
    def route_parameters(self) -> dict[str, Any]:
        return {'usage': TrfType.RATING}


class TrfBxTournamentExporter(AbstractTournamentExporter):
    @property
    def download_route(self) -> str:
        return 'admin-tournament-trf-export'

    @property
    def name(self) -> str:
        return _('Export to TRF(bx) (pairing)')

    @property
    def route_parameters(self) -> dict[str, Any]:
        return {'usage': TrfType.PAIRING}
