from abc import ABC, abstractmethod
from functools import cached_property
from types import UnionType
from typing import Any, TYPE_CHECKING

from common.exception import OptionError
from data.tie_breaks.cutters import NoCutTieBreakCutter, TieBreakCutter
from utils.option import Option

if TYPE_CHECKING:
    from web.utils import SelectOption


class TieBreakOption(Option, ABC):
    """Parent class of all the options of tie breaks."""

    @property
    def template_name(self) -> str:
        return f'/admin/tournaments/tie_break_options/{self.template_file_stem}.html'

    @property
    @abstractmethod
    def template_file_stem(self) -> str:
        """Stem of the file of the template."""


class BaseCutterTieBreakOption(TieBreakOption, ABC):
    @property
    @abstractmethod
    def include_median(self) -> bool:
        """Defines if the median cuts are included in the select."""

    @property
    def type(self) -> type | UnionType:
        return str

    @property
    def default_value(self) -> Any:
        return NoCutTieBreakCutter.static_id()

    @property
    def cutter_options(self) -> dict[str, 'SelectOption']:
        from data.tie_breaks.managers import TieBreakCutterManager
        from web.utils import SelectOption

        return {
            cutter.id: SelectOption(cutter.name, tooltip=cutter.tooltip)
            for cutter in TieBreakCutterManager(self.include_median).objects()
        }

    @cached_property
    def cutter(self) -> TieBreakCutter:
        from data.tie_breaks.managers import TieBreakCutterManager

        return TieBreakCutterManager(self.include_median).get_object(self.value)

    def validate(self):
        try:
            _cutter = self.cutter
        except KeyError:
            raise OptionError(f'Unknown cutter: {self.value}', self)

    @property
    def template_file_stem(self) -> str:
        return 'cutter'


class CutterTieBreakOption(BaseCutterTieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'CUTTER'

    @property
    def include_median(self) -> bool:
        return False


class CutterWithMedianTieBreakOption(BaseCutterTieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'CUTTER_WITH_MEDIAN'

    @property
    def include_median(self) -> bool:
        return True


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

    @property
    def template_file_stem(self) -> str:
        return 'played_modifier'


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

    @property
    def template_file_stem(self) -> str:
        return 'fore_modifier'


class KoyaLimitTieBreakOption(TieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'KOYA_LIMIT'

    @property
    def type(self) -> type | UnionType:
        return int | None

    @property
    def default_value(self) -> Any:
        return None

    @property
    def template_file_stem(self) -> str:
        return 'koya_limit'
