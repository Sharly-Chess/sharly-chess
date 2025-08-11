from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from common.i18n import _
from utils.entity import IdentifiableEntity

if TYPE_CHECKING:
    from data.print_documents import PrintDocument


class PairingStyle(IdentifiableEntity, ABC):
    @property
    @abstractmethod
    def print_document_type(self) -> type['PrintDocument']:
        """The type of document to use for printing."""


class BoardsPairingStyle(PairingStyle):
    @staticmethod
    def static_id() -> str:
        return 'boards'

    @staticmethod
    def static_name() -> str:
        return _('Boards')

    @property
    def print_document_type(self) -> type['PrintDocument']:
        from data.print_documents.documents import BoardPairingPrintDocument

        return BoardPairingPrintDocument


class PlayersPairingStyleSorter(PairingStyle):
    @staticmethod
    def static_id() -> str:
        return 'players'

    @staticmethod
    def static_name() -> str:
        return _('Players')

    @property
    def print_document_type(self) -> type['PrintDocument']:
        from data.print_documents.documents import PlayerPairingPrintDocument

        return PlayerPairingPrintDocument
