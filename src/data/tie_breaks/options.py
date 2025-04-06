from abc import ABC
from types import UnionType
from typing import Any, override, Iterable

from common.i18n import _
from utils.option import Option, OptionError


class TieBreakOption(Option, ABC):
    """Abstract class representing an option of a tie-break"""

    @property
    def template_name(self) -> str:
        # TODO Implement templates for tie-break options
        return ''


class AbstractCutTieBreakOption(TieBreakOption, ABC):
    @property
    def type(self) -> type | UnionType:
        return int

    @property
    def default_value(self) -> Any:
        return 0

    @override
    def validate(self):
        super().validate()
        if self.value < 0:
            raise OptionError(_('A positive integer is expected.'), self)


class CutTieBreakOption(AbstractCutTieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'CUT'


class CutTopTieBreakOption(AbstractCutTieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'CUT_TOP'


class CutBottomTieBreakOption(AbstractCutTieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'CUT_BOTTOM'


class PlayedModifierTieBreakOption(TieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'PLAYED_MODIFIER'

    @property
    def type(self) -> type | UnionType:
        return bool

    @property
    def default_value(self) -> Any:
        return False


class ForeModifierTieBreakOption(TieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'FORE_MODIFIER'

    @property
    def type(self) -> type | UnionType:
        return bool

    @property
    def default_value(self) -> Any:
        return False


class LimitTieBreakOption(TieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'LIMIT'

    @property
    def type(self) -> type | UnionType:
        return float | None

    @property
    def default_value(self) -> Any:
        return None


class ExcludeIdsTieBreakOption(TieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'EXCLUDE_IDS'

    @property
    def type(self) -> type | UnionType:
        return Iterable[int] | None

    @property
    def default_value(self) -> Any:
        return None
