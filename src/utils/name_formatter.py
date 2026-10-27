from abc import ABC, abstractmethod

from common.i18n import _
from common.i18n.utils import normalized_key
from utils.entity import EntityManager, IdentifiableEntity


class NameFormatter(IdentifiableEntity, ABC):
    #: Whether last names are displayed in capitals.
    capitalise_last_name: bool = False

    def format_last_name(self, last_name: str) -> str:
        return last_name.upper() if self.capitalise_last_name else last_name

    @staticmethod
    def format_first_name(first_name: str) -> str:
        """Capitalises a first name written all in capitals or all in lower
        case, which tells nothing of its case. Mixed case is kept as written."""
        if first_name.isupper() or first_name.islower():
            return first_name.title()
        return first_name

    def format(self, first_name: str | None, last_name: str) -> str:
        """The full name of a person."""
        if not first_name:
            return self.format_last_name(last_name)
        return self._format(
            self.format_first_name(first_name), self.format_last_name(last_name)
        )

    @abstractmethod
    def _format(self, first_name: str, last_name: str) -> str:
        pass

    def sort_key(self, first_name: str | None, last_name: str) -> tuple[str, str]:
        """Sorts people by the name displayed first."""
        return normalized_key(last_name), normalized_key(first_name)


class LastFirstNameFormatter(NameFormatter):
    @staticmethod
    def static_id() -> str:
        return 'LAST_FIRST'

    @staticmethod
    def static_name() -> str:
        return _('Last First')

    def _format(self, first_name: str, last_name: str) -> str:
        return f'{last_name} {first_name}'


class LastCommaFirstNameFormatter(NameFormatter):
    @staticmethod
    def static_id() -> str:
        return 'LAST_COMMA_FIRST'

    @staticmethod
    def static_name() -> str:
        return _('Last, First')

    def _format(self, first_name: str, last_name: str) -> str:
        return f'{last_name}, {first_name}'


class FirstLastNameFormatter(NameFormatter):
    @staticmethod
    def static_id() -> str:
        return 'FIRST_LAST'

    @staticmethod
    def static_name() -> str:
        return _('First Last')

    def _format(self, first_name: str, last_name: str) -> str:
        return f'{first_name} {last_name}'

    def sort_key(self, first_name: str | None, last_name: str) -> tuple[str, str]:
        return normalized_key(first_name), normalized_key(last_name)


class FirstCommaLastNameFormatter(NameFormatter):
    @staticmethod
    def static_id() -> str:
        return 'FIRST_COMMA_LAST'

    @staticmethod
    def static_name() -> str:
        return _('First, Last')

    def _format(self, first_name: str, last_name: str) -> str:
        return f'{first_name}, {last_name}'

    def sort_key(self, first_name: str | None, last_name: str) -> tuple[str, str]:
        return normalized_key(first_name), normalized_key(last_name)


class NameFormatterManager(EntityManager[NameFormatter]):
    def entity_types(self) -> list[type[NameFormatter]]:
        return [
            LastFirstNameFormatter,
            LastCommaFirstNameFormatter,
            FirstLastNameFormatter,
            FirstCommaLastNameFormatter,
        ]


def current_name_formatter() -> NameFormatter:
    from common.sharly_chess_config import SharlyChessConfig

    return SharlyChessConfig().name_formatter
