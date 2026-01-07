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
        return f'/print_options/{self.template_file_name}.html'


class FFELicencePrintOption(FFEPrintOption):
    @staticmethod
    def static_id() -> str:
        return 'ffe-licence'

    @property
    def type(self) -> type | UnionType:
        return str

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
    def _ffe_licences_by_value(self) -> dict[str, PlayerFFELicence]:
        return {
            str(ffe_licence.value): ffe_licence
            for ffe_licence in self._form_numbers_by_ffe_licence
        }

    @cached_property
    def _form_numbers_by_value(self) -> dict[str, PlayerFFELicence]:
        return {
            str(ffe_licence.value): ffe_licence
            for ffe_licence, form_number in self._form_numbers_by_ffe_licence.items()
        }

    @property
    def ffe_licence_options(self) -> dict[str, str]:
        return {
            value: ffe_licence.name
            for value, ffe_licence in self._ffe_licences_by_value.items()
        }

    @property
    def ffe_licence(self) -> PlayerFFELicence:
        return self._ffe_licences_by_value[self.value]

    @property
    def form_number(self) -> PlayerFFELicence:
        return self._form_numbers_by_value[self.value]

    @override
    def validate(self):
        try:
            _ffe_licence = self.ffe_licence
        except KeyError:
            # Untranslated, should not happen
            raise OptionError(f'Unknown FFE licence: {self.value}', self)
