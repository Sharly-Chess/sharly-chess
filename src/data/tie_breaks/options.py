from abc import ABC, abstractmethod
from functools import cached_property
from types import UnionType
from typing import Any, TYPE_CHECKING

from common.exception import OptionError
from common.i18n import _, ngettext
from data.tie_breaks.cutters import NoCutTieBreakCutter, TieBreakCutter
from utils.option import Option

if TYPE_CHECKING:
    from data.tie_breaks.managers import TieBreakCutterManager
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

    @property
    def is_variation(self) -> bool:
        """Defines if the option value is the default for the tie-break or if it is a variation."""
        return self.value != self.default_value

    @property
    @abstractmethod
    def variation_acronym(self) -> str:
        """Represents the variation in the tie-break acronym
        Example: BH/C1."""

    @abstractmethod
    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        """Set the value from a variation acronym if it matches it.
        Returns True if the acronym matched the option."""

    @property
    @abstractmethod
    def variation_name(self) -> str:
        """Represent the variation in the tie-break full name
        Example: Buchholz (Cut 1)."""

    @property
    @abstractmethod
    def variation_help_text(self) -> str:
        """Represent the variation in the tie-break help text."""

    @property
    def is_legacy(self) -> bool:
        """Defines if the option marks the tie-break as legacy.
        Tie-breaks with legacy options can no longer be modified."""
        return False


class SilentTieBreakOption(TieBreakOption, ABC):
    """Base class of options which are not displayed."""

    @property
    def variation_acronym(self) -> str:
        return ''

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        return False

    @property
    def variation_name(self) -> str:
        return ''

    @property
    def variation_help_text(self) -> str:
        return ''


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
    def cutter_manager(self) -> 'TieBreakCutterManager':
        from data.tie_breaks.managers import TieBreakCutterManager

        return TieBreakCutterManager(self.include_median)

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        try:
            self.value = self.cutter_manager.get_object(acronym).id
            return True
        except KeyError:
            return False

    @property
    def cutter_options(self) -> dict[str, 'SelectOption']:
        from web.utils import SelectOption

        return {
            cutter.id: SelectOption(cutter.name, tooltip=cutter.help_text)
            for cutter in self.cutter_manager.objects()
        }

    @cached_property
    def cutter(self) -> TieBreakCutter:
        return self.cutter_manager.get_object(self.value)

    def validate(self):
        super().validate()
        try:
            __ = self.cutter
        except KeyError:
            raise OptionError(f'Unknown cutter: {self.value}', self)

    @property
    def template_file_stem(self) -> str:
        return 'cutter'

    @property
    def variation_acronym(self) -> str:
        return self.cutter.acronym

    @property
    def variation_name(self) -> str:
        return self.cutter.name

    @property
    def variation_help_text(self) -> str:
        return self.cutter.help_text


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

    @property
    def variation_acronym(self) -> str:
        return 'P'

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        if acronym == 'P':
            self.value = True
            return True
        return False

    @property
    def variation_name(self) -> str:
        return _('forfeits played')

    @property
    def variation_help_text(self) -> str:
        return _('Forfeited games are considered as played.')


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

    @property
    def variation_acronym(self) -> str:
        return 'F'

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        if acronym == 'F':
            self.value = True
            return True
        return False

    @property
    def variation_name(self) -> str:
        return _('Fore')

    @property
    def variation_help_text(self) -> str:
        """`Buchholz` replaced by `Fore Buchholz` in the help text."""
        return ''


class KoyaLimitTieBreakOption(TieBreakOption):
    MAX_VALUE = 5

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
    def operator(self) -> str:
        return '+' if self.value > 0 else '-'

    @property
    def is_variation(self) -> bool:
        return bool(self.value)

    @property
    def variation_acronym(self) -> str:
        return f'L{self.operator}{self.value}'

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        if len(acronym) != 3 or acronym[0] != 'L':
            return False
        operator = acronym[1]
        if operator not in '+-':
            return False
        try:
            value = int(acronym[2])
            if not 0 < value <= self.MAX_VALUE:
                return False
            if operator == '-':
                value = -value
            self.value = value
            return True
        except ValueError:
            return False

    @property
    def variation_name(self) -> str:
        return ngettext(
            'Limit {operator} {count} half-point',
            'Limit {operator} {count} half-points',
            abs(self.value),
        ).format(operator=self.operator)

    @property
    def variation_help_text(self) -> str:
        """Included as an equation."""
        return ''

    @property
    def template_file_stem(self) -> str:
        return 'koya_limit'

    def validate(self):
        super().validate()
        if self.value and abs(self.value) > self.MAX_VALUE:
            raise OptionError(
                _('The limit can only be adjusted by {count} half-points.').format(
                    count=self.MAX_VALUE
                ),
                self,
            )


class EstimatedRatingsTieBreakOption(SilentTieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'ESTIMATED_RATINGS'

    @property
    def template_file_stem(self) -> str:
        return 'estimated_ratings'

    @property
    def type(self) -> type | UnionType:
        return bool

    @property
    def default_value(self) -> Any:
        return False

    @property
    def include_in_equals(self) -> bool:
        return False


class ReversedTieBreakOption(TieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'REVERSED'

    @property
    def template_file_stem(self) -> str:
        return 'reversed'

    @property
    def variation_acronym(self) -> str:
        return 'R'

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        if acronym == 'R':
            self.value = True
            return True
        return False

    @property
    def variation_name(self) -> str:
        return _('Reversed')

    @property
    def is_variation(self) -> bool:
        return bool(self.value)

    @property
    def variation_help_text(self) -> str:
        return ''

    @property
    def type(self) -> type | UnionType:
        return bool | None

    @property
    def default_value(self) -> Any:
        return None


class LegacyTieBreakOption(SilentTieBreakOption, ABC):
    @property
    def template_file_stem(self) -> str:
        return ''

    @property
    def template_name(self) -> str:
        return ''

    @property
    def variation_name(self) -> str:
        return _('Legacy')

    @property
    def type(self) -> type | UnionType:
        return bool

    @property
    def default_value(self) -> Any:
        return False

    @property
    def is_legacy(self) -> bool:
        return True


class LegacyMarch2026TieBreakOption(LegacyTieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'LEGACY_03_2026'

    @property
    def variation_help_text(self) -> str:
        return _('Rules used were only effective until march 2026 (legacy).')
