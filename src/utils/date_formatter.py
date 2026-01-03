from abc import ABC, abstractmethod
from datetime import datetime

from common.i18n import _
from utils.entity import IdentifiableEntity


class DateFormatter(IdentifiableEntity, ABC):
    @classmethod
    def static_name(cls) -> str:
        return cls._humanized_format()

    @staticmethod
    @abstractmethod
    def _humanized_format() -> str:
        """Localized and humanized format displayed to users."""

    @property
    def humanized_format(self) -> str:
        return self._humanized_format()

    @property
    def datetime_humanized_format(self) -> str:
        return _('{date_format} HH:MM').format(format=self.humanized_format)

    @property
    def range_humanized_format(self) -> str:
        return self.humanized_format + self.range_separator + self.humanized_format

    @property
    @abstractmethod
    def python_format(self) -> str:
        """Format used to parse a string in python.
        https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes"""

    @property
    def time_python_format(self) -> str:
        return '%H:%M'

    @property
    def datetime_python_format(self) -> str:
        return self.python_format + ' ' + self.time_python_format

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
    def datetime_regex(self) -> str:
        return self.regex.replace('$', r'\s\d{2}:\d{2}$')

    @property
    @abstractmethod
    def range_separator(self) -> str:
        """String used to split a range of dates."""

    @property
    @abstractmethod
    def value_to_date_js_function(self) -> str:
        """JS function converting a formatted string to a Date object."""

    def date_str_to_iso_format(self, date_str: str) -> str:
        return datetime.strptime(date_str, self.python_format).date().isoformat()


class ISODateFormatter(DateFormatter):
    @staticmethod
    def static_id() -> str:
        return 'ISO'

    @staticmethod
    def _humanized_format() -> str:
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

    def date_str_to_iso_format(self, date_str: str) -> str:
        return date_str


class EUDateFormatter(DateFormatter):
    @staticmethod
    def static_id() -> str:
        return 'EU'

    @staticmethod
    def _humanized_format() -> str:
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
        return """
            (value) => {

                const [day, month, year] = value.split(' ')[0].split('/');
                var hour = 0;
                var minute = 0;
                if (value.includes(':')) {
                    [hour, minute] = value.split(' ')[1].split(':');
                }
                return new Date(+year, +month - 1, +day, +hour, +minute);
            }
            """


class USDateFormatter(DateFormatter):
    @staticmethod
    def static_id() -> str:
        return 'US'

    @staticmethod
    def _humanized_format() -> str:
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
        return '(value) => new Date(value)'
