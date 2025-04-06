from abc import ABC, abstractmethod
from typing import Any

from common.i18n import _
from utils.entity import IdentifiableEntity
from utils.enum import TrfType


class TournamentExporter(IdentifiableEntity, ABC):
    """Abstract class representing an export format for a tournament."""
    @property
    @abstractmethod
    def download_route(self) -> str:
        """Route downloading the export file.
        Should take as parameters event_uniq_id: str and tournament_id: int"""

    @property
    def route_parameters(self) -> dict[str, Any]:
        return {}


class Trf16TournamentExporter(TournamentExporter):
    @staticmethod
    def static_id() -> str:
        return 'trf-16'

    @staticmethod
    def static_name() -> str:
        return _('Export to TRF16 (rating)')

    @property
    def download_route(self) -> str:
        return 'admin-tournament-trf-export'


    @property
    def route_parameters(self) -> dict[str, Any]:
        return {'usage': TrfType.RATING}


class TrfBxTournamentExporter(TournamentExporter):
    @staticmethod
    def static_id() -> str:
        return 'trf-bx'

    @staticmethod
    def static_name() -> str:
        return _('Export to TRF(bx) (pairing)')

    @property
    def download_route(self) -> str:
        return 'admin-tournament-trf-export'

    @property
    def route_parameters(self) -> dict[str, Any]:
        return {'usage': TrfType.PAIRING}
