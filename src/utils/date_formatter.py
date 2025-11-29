from abc import ABC, abstractmethod

from common.i18n import _
from utils.entity import IdentifiableEntity


class DateFormatter(IdentifiableEntity, ABC):
    @property
    @abstractmethod
    def python_format(self) -> str:
        """Format used to parse a string in python.
        https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes"""

    @property
    @abstractmethod
    def air_date_picker_format(self) -> str:
        """Format used in AirDatePicker.
        https://air-datepicker.com/docs?scrollTo=dateFormat"""

    @property
    @abstractmethod
    def regex(self) -> str:
        """Regex expression recognizing a string of the format."""

    @property
    @abstractmethod
    def range_separator(self) -> str:
        """String used to split a range of dates."""

    @property
    @abstractmethod
    def value_to_date_js_function(self) -> str:
        """JS function converting a formatted string to a Date object."""


class ISODateFormatter(DateFormatter):
    @staticmethod
    def static_id() -> str:
        return 'ISO'

    @staticmethod
    def static_name() -> str:
        return _('YYYY-MM-DD')

    @property
    def python_format(self) -> str:
        return '%Y-%m-%d'

    @property
    def air_date_picker_format(self) -> str:
        return 'yyyy-MM-dd'

    @property
    def regex(self) -> str:
        return r'^\d{4}-\d{2}-\d{2}$'

    @property
    def range_separator(self) -> str:
        return ' / '

    @property
    def value_to_date_js_function(self) -> str:
        return '(value) => new Date(value)'


class EUDateFormatter(DateFormatter):
    @staticmethod
    def static_id() -> str:
        return 'EU'

    @staticmethod
    def static_name() -> str:
        return _('DD/MM/YYYY')

    @property
    def python_format(self) -> str:
        return '%d/%m/%Y'

    @property
    def air_date_picker_format(self) -> str:
        return 'dd/MM/yyyy'

    @property
    def regex(self) -> str:
        return r'^\d{2}\/\d{2}\/\d{4}$'

    @property
    def range_separator(self) -> str:
        return ' - '

    @property
    def value_to_date_js_function(self) -> str:
        return (
            '(value) => {'
            '   const [day, month, year] = value.split("/");'
            '   return new Date(+year, +month - 1, +day);'
            '}'
        )


class USDateFormatter(DateFormatter):
    @staticmethod
    def static_id() -> str:
        return 'US'

    @staticmethod
    def static_name() -> str:
        return _('MM/DD/YYYY')

    @property
    def python_format(self) -> str:
        return '%m/%d/%Y'

    @property
    def air_date_picker_format(self) -> str:
        return 'MM/dd/yyyy'

    @property
    def regex(self) -> str:
        return r'^\d{2}\/\d{2}\/\d{4}$'

    @property
    def range_separator(self) -> str:
        return ' - '

    @property
    def value_to_date_js_function(self) -> str:
        return (
            '(value) => {'
            '   const [month, day, year] = value.split("/");'
            '   return new Date(+year, +month - 1, +day);'
            '}'
        )
