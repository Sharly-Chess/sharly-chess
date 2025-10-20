from abc import ABC, abstractmethod

from common.i18n import _, ngettext
from utils.entity import IdentifiableEntity


class TieBreakCutter(IdentifiableEntity, ABC):
    @property
    @abstractmethod
    def bottom_cut(self) -> int:
        """Number of bottom values to cut."""

    @property
    @abstractmethod
    def top_cut(self) -> int:
        """Number of top values to cut."""

    @property
    @abstractmethod
    def help_text(self) -> str:
        """Tooltip to display on the option of the cutter."""

    @property
    @abstractmethod
    def acronym(self) -> str:
        """Represents the cutter in the tie-break acronym as a suffix (ex: BH-C1)."""


class NoCutTieBreakCutter(TieBreakCutter):
    @staticmethod
    def static_id() -> str:
        return 'NO_CUT'

    @staticmethod
    def static_name() -> str:
        return '-'

    @property
    def bottom_cut(self) -> int:
        return 0

    @property
    def top_cut(self) -> int:
        return 0

    @property
    def help_text(self) -> str:
        return ''

    @property
    def acronym(self) -> str:
        return ''


class CutTieBreakCutter(TieBreakCutter, ABC):
    @classmethod
    def static_id(cls) -> str:
        return f'CUT_{cls.cut_value()}'

    @classmethod
    def static_name(cls) -> str:
        return _('Cut {value} *** CUT TIE BREAK NAME').format(value=cls.cut_value())

    @staticmethod
    @abstractmethod
    def cut_value() -> int:
        """Value of the cut."""

    @property
    def top_cut(self) -> int:
        return 0

    @property
    def bottom_cut(self) -> int:
        return self.cut_value()

    @property
    def acronym(self) -> str:
        return f'C{self.cut_value()}'

    @property
    def help_text(self) -> str:
        return ngettext(
            'The least significant value is removed.',
            'The {count} least significant values are removed.',
            self.cut_value(),
        ).format(count=self.cut_value())


class Cut1TieBreakCutter(CutTieBreakCutter):
    @staticmethod
    def cut_value() -> int:
        return 1


class Cut2TieBreakCutter(CutTieBreakCutter):
    @staticmethod
    def cut_value() -> int:
        return 2


class MedianTieBreakCutter(TieBreakCutter, ABC):
    @classmethod
    def static_id(cls) -> str:
        return f'MEDIAN_{cls.cut_value()}'

    @classmethod
    def static_name(cls) -> str:
        return _('Median {value}').format(value=cls.cut_value())

    @staticmethod
    @abstractmethod
    def cut_value() -> int:
        """Value of the cut."""

    @property
    def top_cut(self) -> int:
        return self.cut_value()

    @property
    def bottom_cut(self) -> int:
        return self.cut_value()

    @property
    def acronym(self) -> str:
        return f'M{self.cut_value()}'

    @property
    def help_text(self) -> str:
        return ngettext(
            'The least and the most significant values are removed.',
            'The {count} least and the {count} most significant values are removed.',
            self.cut_value(),
        ).format(count=self.cut_value())


class Median1TieBreakCutter(MedianTieBreakCutter):
    @staticmethod
    def cut_value() -> int:
        return 1


class Median2TieBreakCutter(MedianTieBreakCutter):
    @staticmethod
    def cut_value() -> int:
        return 2
