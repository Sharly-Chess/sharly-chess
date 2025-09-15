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

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Boards', locale)

    @property
    def print_document_type(self) -> type['PrintDocument']:
        from data.print_documents.documents import BoardPairingPrintDocument

        return BoardPairingPrintDocument


class PlayersPairingStyleSorter(PairingStyle):
    @staticmethod
    def static_id() -> str:
        return 'players'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Players', locale)

    @property
    def print_document_type(self) -> type['PrintDocument']:
        from data.print_documents.documents import PlayerPairingPrintDocument

        return PlayerPairingPrintDocument
