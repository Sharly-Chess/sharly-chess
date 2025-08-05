from abc import ABC, abstractmethod

from common.i18n import _
from utils.entity import IdentifiableEntity


class PairingStyle(IdentifiableEntity, ABC):
    @abstractmethod
    @property
    def template(self) -> str:
        """Returns the print template for the pairing style."""


class BoardsPairingStyle(PairingStyle):
    @staticmethod
    def static_id() -> str:
        return 'boards'

    @staticmethod
    def static_name() -> str:
        return _('Boards')

    @property
    def template(self) -> str:
        return '/admin/print/boards.html'


class PlayersPairingStyleSorter(PairingStyle):
    @staticmethod
    def static_id() -> str:
        return 'players'

    @staticmethod
    def static_name() -> str:
        return _('Players')

    @property
    def template(self) -> str:
        return '/admin/print/players.html'
