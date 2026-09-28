from abc import ABC, abstractmethod

from common.i18n import _
from common.i18n.utils import normalized_key
from utils.entity import EntityManager, IdentifiableEntity


class NameFormatter(IdentifiableEntity, ABC):
    def format_last_name(self, last_name: str) -> str:
        return last_name

    def format(self, first_name: str | None, last_name: str) -> str:
        """The full name of a person."""
        if not first_name:
            return self.format_last_name(last_name)
        return self._format(first_name, self.format_last_name(last_name))

    @abstractmethod
    def _format(self, first_name: str, last_name: str) -> str:
        pass

    def sort_key(self, first_name: str | None, last_name: str) -> tuple[str, str]:
        """Sorts people by the name displayed first."""
        return normalized_key(last_name), normalized_key(first_name)


class UpperLastFirstNameFormatter(NameFormatter):
    @staticmethod
    def static_id() -> str:
        return 'UPPER_LAST_FIRST'

    @staticmethod
    def static_name() -> str:
        return _('LAST, First')

    def format_last_name(self, last_name: str) -> str:
        return last_name.upper()

    def _format(self, first_name: str, last_name: str) -> str:
        return f'{last_name}, {first_name}'


class LastFirstNameFormatter(NameFormatter):
    @staticmethod
    def static_id() -> str:
        return 'LAST_FIRST'

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


class NameFormatterManager(EntityManager[NameFormatter]):
    def entity_types(self) -> list[type[NameFormatter]]:
        return [
            UpperLastFirstNameFormatter,
            LastFirstNameFormatter,
            FirstLastNameFormatter,
        ]


def current_name_formatter() -> NameFormatter:
    from common.sharly_chess_config import SharlyChessConfig

    return SharlyChessConfig().name_formatter
