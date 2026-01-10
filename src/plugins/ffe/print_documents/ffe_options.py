from abc import ABC
from functools import cached_property
from types import UnionType
from typing import Any, override

from common.exception import OptionError
from data.print_documents import PrintOption
from plugins.ffe.utils import PlayerFFELicence


class FFEPrintOption(PrintOption, ABC):
    @property
    def template_name(self) -> str:
        return f'/print_options/{self.static_id().replace("-", "_")}.html'


class FFEDocumentTypePrintOption(FFEPrintOption):
    @staticmethod
    def static_id() -> str:
        return 'ffe-document-type'

    @property
    def type(self) -> type | UnionType:
        return str

    @property
    def default_value(self) -> Any:
        return None

    @property
    def ffe_print_document_id(self) -> str:
        from plugins.ffe.print_documents.ffe_documents import FFEPrintDocument

        return FFEPrintDocument.static_id()

    @property
    def ffe_document_type_options(self) -> dict[str, str]:
        from plugins.ffe.print_documents.ffe_managers import FFEDocumentTypeManager

        return {
            ffe_document_type.static_id(): ffe_document_type.static_name()
            for ffe_document_type in FFEDocumentTypeManager().objects()
        }

    @property
    def valid_option_ids_per_type_id(self) -> dict[str, list[str]]:
        from plugins.ffe.print_documents.ffe_managers import FFEDocumentTypeManager

        type_options = FFEDocumentTypeManager().type_by_id()
        return {
            type_id: type_options[type_id].get_valid_option_ids()
            for type_id in type_options
        }

    @override
    def validate(self):
        from plugins.ffe.print_documents.ffe_managers import FFEDocumentTypeManager

        if self.value not in (
            ffe_document_type.static_id()
            for ffe_document_type in FFEDocumentTypeManager().objects()
        ):
            # Untranslated, should not happen
            raise OptionError(f'Unknown FFE document type: {self.value}', self)


class FFELicencePrintOption(FFEPrintOption):
    @staticmethod
    def static_id() -> str:
        return 'ffe-licence'

    @property
    def type(self) -> type | UnionType:
        return int

    @property
    def default_value(self) -> Any:
        return PlayerFFELicence.A

    @property
    def _form_numbers_by_ffe_licence(self) -> dict[PlayerFFELicence, int]:
        return {
            PlayerFFELicence.A: 3,
            PlayerFFELicence.B: 4,
        }

    @property
    def _ffe_licences_by_value(self) -> dict[int, PlayerFFELicence]:
        return {
            ffe_licence.value: ffe_licence
            for ffe_licence in self._form_numbers_by_ffe_licence
        }

    @cached_property
    def _form_numbers_by_value(self) -> dict[int, PlayerFFELicence]:
        return {
            ffe_licence.value: ffe_licence
            for ffe_licence, form_number in self._form_numbers_by_ffe_licence.items()
        }

    @property
    def ffe_licence_options(self) -> dict[int, str]:
        return {
            value: ffe_licence.name
            for value, ffe_licence in self._ffe_licences_by_value.items()
        }

    @property
    def ffe_licence(self) -> PlayerFFELicence:
        return self._ffe_licences_by_value[self.value]

    @property
    def form_number(self) -> int:
        return self._form_numbers_by_ffe_licence[self.ffe_licence]

    @override
    def validate(self):
        try:
            _ffe_licence = self.ffe_licence
        except KeyError:
            # Untranslated, should not happen
            raise OptionError(f'Unknown FFE licence: {self.value}', self)
