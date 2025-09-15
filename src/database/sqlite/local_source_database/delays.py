from abc import ABC, abstractmethod
from datetime import datetime, timedelta, date

from common.i18n import _
from utils.entity import IdentifiableEntity


class OutdatedDelay(IdentifiableEntity, ABC):
    """Delay according to which a database becomes outdated."""

    @abstractmethod
    def is_expired(self, start_time: datetime) -> bool:
        """Determines if the delay since *start_time* is expired."""


class DisabledOutdatedDelay(OutdatedDelay):
    @staticmethod
    def static_id() -> str:
        return 'disabled'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Disabled', locale)

    def is_expired(self, start_time: datetime) -> bool:
        return False


class DayCountOutdatedDelay(OutdatedDelay, ABC):
    """Represents the delays that expire after a specific amount of days."""

    @property
    @abstractmethod
    def days_expired(self) -> int:
        """Number of days for the delay to expire."""

    def is_expired(self, start_time: datetime) -> bool:
        return datetime.now() > start_time + timedelta(days=self.days_expired)


class DailyOutdatedDelay(DayCountOutdatedDelay):
    @staticmethod
    def static_id() -> str:
        return 'daily'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Daily', locale)

    @property
    def days_expired(self) -> int:
        return 1


class Days2OutdatedDelay(DayCountOutdatedDelay):
    @staticmethod
    def static_id() -> str:
        return '2days'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('{days} days', locale).format(days=2)

    @property
    def days_expired(self) -> int:
        return 2


class Days3OutdatedDelay(DayCountOutdatedDelay):
    @staticmethod
    def static_id() -> str:
        return '3days'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('{days} days', locale).format(days=3)

    @property
    def days_expired(self) -> int:
        return 3


class WeeklyOutdatedDelay(DayCountOutdatedDelay):
    @staticmethod
    def static_id() -> str:
        return 'weekly'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('Weekly', locale)

    @property
    def days_expired(self) -> int:
        return 7


class MonthFirstDayOutdatedDelay(OutdatedDelay):
    @staticmethod
    def static_id() -> str:
        return 'month_1st'

    @classmethod
    def static_name(cls, locale: str | None = None) -> str:
        return _('1st day of the month', locale)

    def is_expired(self, start_time: datetime) -> bool:
        now = datetime.now()
        first_day = date(now.year, now.month, 1)
        return start_time < datetime.combine(first_day, datetime.min.time())
