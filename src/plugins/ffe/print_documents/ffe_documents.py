from typing import Any

from data.print_documents import PrintOption
from data.print_documents.documents import (
    PrintDocument,
)
from data.print_documents.options import (
    TournamentsPrintOption,
    PlayersPrintOption,
    TournamentPrintOption,
    PlayerPrintOption,
)
from plugins.ffe.print_documents.ffe_managers import FFEDocumentTypeManager
from plugins.ffe.print_documents.ffe_options import (
    FFELicencePrintOption,
    FFEDocumentTypePrintOption,
)
from plugins.ffe.print_documents.ffe_types import FFEDocumentType
from plugins.ffe.utils import PlayerFFELicence


class FFEPrintDocument(PrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'ffe-document'

    @staticmethod
    def static_name() -> str:
        return 'Formulaires FFE'

    @property
    def title(self) -> str:
        return self.ffe_document_type.title

    @property
    def ffe_document_type(self) -> FFEDocumentType:
        return FFEDocumentTypeManager().get_object(
            self._get_option(FFEDocumentTypePrintOption).value
        )

    @property
    def ffe_licence(self) -> PlayerFFELicence:
        return PlayerFFELicence(self._get_option(FFELicencePrintOption).value)

    @property
    def template_name(self) -> str:
        return self.ffe_document_type.get_template_name()

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [
            FFEDocumentTypePrintOption,
            TournamentsPrintOption,
            TournamentPrintOption,
            PlayersPrintOption,
            FFELicencePrintOption,
            PlayerPrintOption,
        ]

    def validate_options(self):
        self._get_option(FFEDocumentTypePrintOption).validate()
        valid_options_types = self.ffe_document_type.get_valid_option_types()
        for option in self.options:
            if type(option) in valid_options_types:
                option.validate()

    @property
    def template_context(self) -> dict[str, Any]:
        return self.ffe_document_type.template_context(self)
