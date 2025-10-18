from abc import ABC, abstractmethod

from common.i18n import _
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
    def tooltip(self) -> str | None:
        """Tooltip to display on the option of the cutter."""

    @property
    @abstractmethod
    def acronym_suffix(self) -> str | None:
        """Represents the cutter in the tie-break acronym as a suffix (ex: BH-C1)."""

    @property
    def name_suffix(self) -> str | None:
        """Represents the cutter in the tie-break name as a suffix (ex: Buchholz - Cut 1)."""
        return self.name


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
    def tooltip(self) -> str | None:
        return None

    @property
    def acronym_suffix(self) -> str | None:
        return None

    @property
    def name_suffix(self) -> str | None:
        return None


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
    def acronym_suffix(self) -> str | None:
        return _('C{value} *** CUT TIE BREAK ACRONYM SUFFIX').format(
            value=self.cut_value()
        )


class Cut1TieBreakCutter(CutTieBreakCutter):
    @staticmethod
    def cut_value() -> int:
        return 1

    @property
    def tooltip(self) -> str | None:
        return _('Cut the least significant value.')


class Cut2TieBreakCutter(CutTieBreakCutter):
    @staticmethod
    def cut_value() -> int:
        return 2

    @property
    def tooltip(self) -> str | None:
        return _('Cut the two least significant values.')


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
    def acronym_suffix(self) -> str | None:
        return _('M{value} *** MEDIAN TIE BREAK ACRONYM SUFFIX').format(
            value=self.cut_value()
        )


class Median1TieBreakCutter(MedianTieBreakCutter):
    @staticmethod
    def cut_value() -> int:
        return 1

    @property
    def tooltip(self) -> str | None:
        return _('Cut the least and the most significant values.')


class Median2TieBreakCutter(MedianTieBreakCutter):
    @staticmethod
    def cut_value() -> int:
        return 2

    @property
    def tooltip(self) -> str | None:
        return _('Cut the two least and the two most significant values.')
