import re
import time
import weakref
from datetime import datetime
from functools import cached_property
from logging import Logger
from typing import TYPE_CHECKING
from _weakref import ReferenceType

from common import (
    RGB,
    hexa_to_rgb,
    format_timestamp_date_time,
    format_timestamp_date,
    format_timestamp_time,
)
from common.i18n import _
from common.papi_web_config import PapiWebConfig
from common.logger import get_logger
from database.sqlite.event.event_store import StoredTimerHour, StoredTimer

if TYPE_CHECKING:
    from data.event import Event


logger: Logger = get_logger()


class TimerHour:
    """A data wrapper around a stored timer hour."""

    def __init__(
        self,
        timer: 'Timer',
        stored_timer_hour: StoredTimerHour,
    ):
        self._timer_ref: 'ReferenceType[Timer]' = weakref.ref(timer)
        self.stored_timer_hour: StoredTimerHour = stored_timer_hour
        self.timestamp: int | None = None
        self.last_valid: bool = False
        self.error: str | None = None

    @property
    def timer(self) -> 'Timer':
        _timer = self._timer_ref()
        if _timer is None:
            raise RuntimeError('Timer reference has been garbage collected')
        return _timer

    @property
    def datetime(self) -> datetime | None:
        return datetime.fromtimestamp(self.timestamp) if self.timestamp else None

    @property
    def datetime_str(self) -> str | None:
        return format_timestamp_date_time(self.timestamp) if self.timestamp else None

    @property
    def date_str(self) -> str | None:
        return format_timestamp_date(self.timestamp) if self.timestamp else None

    @property
    def time_str(self) -> str | None:
        return format_timestamp_time(self.timestamp) if self.timestamp else None

    @property
    def id(self) -> int | None:
        return self.stored_timer_hour.id if self.stored_timer_hour else None

    @property
    def uniq_id(self) -> str | None:
        return self.stored_timer_hour.uniq_id if self.stored_timer_hour else None

    @property
    def order(self) -> int | None:
        return self.stored_timer_hour.order if self.stored_timer_hour else None

    @cached_property
    def round(self) -> int:
        try:
            return max(int(self.uniq_id or 0), 0)
        except ValueError:
            return 0

    def _format_stored_text(self, text, round_default_text) -> str:
        if self.round:
            return (
                text.format(self.round)
                if text
                else round_default_text.format(self.round)
            )
        else:
            return text if text else ''

    @cached_property
    def text_before(self) -> str:
        return self._format_stored_text(
            self.stored_timer_hour.text_before,
            PapiWebConfig.default_timer_round_text_before,
        )

    @cached_property
    def text_after(self) -> str:
        return self._format_stored_text(
            self.stored_timer_hour.text_after,
            PapiWebConfig.default_timer_round_text_after,
        )

    @property
    def timestamp_1(self) -> int:
        if self.timestamp is None:
            raise RuntimeError('Timestamp is not defined')
        return self.timestamp - self.timer.delays[1] * 60 - self.timer.delays[2] * 60

    @property
    def timestamp_2(self) -> int:
        if self.timestamp is None:
            raise RuntimeError('Timestamp is not defined')
        return self.timestamp - self.timer.delays[2] * 60

    @property
    def timestamp_3(self) -> int:
        if self.timestamp is None:
            raise RuntimeError('Timestamp is not defined')
        return self.timestamp

    @property
    def timestamp_next(self) -> int:
        if self.timestamp is None:
            raise RuntimeError('Timestamp is not defined')
        return self.timestamp + self.timer.delays[3] * 60

    @property
    def datetime_str_1(self) -> str:
        return format_timestamp_date_time(self.timestamp_1)

    @property
    def datetime_str_2(self) -> str:
        return format_timestamp_date_time(self.timestamp_2)

    @property
    def datetime_str_3(self) -> str:
        return format_timestamp_date_time(self.timestamp_3)

    @property
    def datetime_str_next(self) -> str:
        return format_timestamp_date_time(self.timestamp_next)

    def __repr__(self):
        return (
            f'{self.__class__.__name__}(id={self.id} order={self.order} uniq_id={self.uniq_id} '
            f'datetime={self.datetime_str} texts=[{self.text_before}]/[{self.text_after}])'
        )


class Timer:
    """A data wrapper around a stored timer."""

    def __init__(self, event: 'Event', stored_timer: StoredTimer):
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)
        self.stored_timer: StoredTimer = stored_timer
        self.timer_hours_by_id: dict[int, TimerHour] = {}
        self.valid: bool = True
        self.error: str | None = None
        self._build_timer_hours()

    @property
    def event(self) -> 'Event':
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event

    @property
    def id(self) -> int | None:
        return self.stored_timer.id if self.stored_timer else None

    @cached_property
    def timer_hour_uniq_ids(self) -> list[str]:
        return [
            timer_hour.uniq_id
            for timer_hour in self.timer_hours_by_id.values()
            if timer_hour.uniq_id
        ]

    @cached_property
    def timer_hours_sorted_by_order(self) -> list[TimerHour]:
        return sorted(
            self.timer_hours_by_id.values(),
            key=lambda timer_hour: timer_hour.order or 0,
        )

    @property
    def uniq_id(self) -> str | None:
        return self.stored_timer.uniq_id if self.stored_timer else None

    def _build_timer_hours(self):
        previous_valid_timer_hour: TimerHour | None = None
        for stored_timer_hour in self.stored_timer.stored_timer_hours:
            timer_hour: TimerHour = TimerHour(self, stored_timer_hour)
            assert timer_hour.id is not None
            self.timer_hours_by_id[timer_hour.id] = timer_hour
            if not stored_timer_hour.time_str:
                error = _('Time is not defined.')
                timer_hour.error = error
                self.event.add_warning(error, timer_hour=timer_hour)
            else:
                matches = re.match(
                    '^(?P<hour>[0-9]{1,2}):(?P<minute>[0-9]{1,2})$',
                    stored_timer_hour.time_str,
                )
                if not matches:
                    error = _('Invalid time [{time_str}].').format(
                        time_str=stored_timer_hour.time_str
                    )
                    timer_hour.error = error
                    self.event.add_warning(error, timer_hour=timer_hour)
                elif (
                    previous_valid_timer_hour is None and not stored_timer_hour.date_str
                ):
                    error = _('The date of the first hour is not defined (mandatory).')
                    timer_hour.error = error
                    self.event.add_warning(error, timer_hour=timer_hour)
                else:
                    datetime_str: str
                    if stored_timer_hour.date_str and not re.match(
                        '^#?(?P<year>[0-9]{4})-(?P<month>[0-9]{1,2})-(?P<day>[0-9]{1,2})$',
                        stored_timer_hour.date_str,
                    ):
                        error = _('Invalid date [{date_str}].').format(
                            date_str=stored_timer_hour.date_str
                        )
                        timer_hour.error = error
                        self.event.add_warning(error, timer_hour=timer_hour)
                    else:
                        if stored_timer_hour.date_str:
                            datetime_str = f'{stored_timer_hour.date_str} {stored_timer_hour.time_str}'
                        else:
                            # The UI tries to ensure that the first timer has a date defined,
                            # but this might not be the case after a timer has been deleted or re-ordered.
                            # In that case we'll fall through to the ValueError exception below.
                            previous_valid_timer_hour_date_str = (
                                previous_valid_timer_hour.date_str
                                if previous_valid_timer_hour
                                else '-'
                            )
                            datetime_str = f'{previous_valid_timer_hour_date_str} {stored_timer_hour.time_str}'
                        try:
                            timestamp = int(
                                time.mktime(
                                    datetime.strptime(
                                        datetime_str, '%Y-%m-%d %H:%M'
                                    ).timetuple()
                                )
                            )
                            timer_hour.timestamp = timestamp
                            if (
                                previous_valid_timer_hour
                                and previous_valid_timer_hour.timestamp is not None
                                and timestamp <= previous_valid_timer_hour.timestamp
                            ):
                                error = _(
                                    'Invalid hour [{hour}] (before previous hour [{previous_hour}]).'
                                ).format(
                                    hour=timer_hour.datetime_str,
                                    previous_hour=previous_valid_timer_hour.datetime_str,
                                )
                                timer_hour.error = error
                                self.event.add_warning(error, timer_hour=timer_hour)
                        except ValueError:
                            error = _('Invalid date and time [{datetime_str}].').format(
                                datetime_str=datetime_str
                            )
                            timer_hour.error = error
                            self.event.add_warning(error, timer_hour=timer_hour)
            if not timer_hour.error:
                previous_valid_timer_hour = timer_hour
        if previous_valid_timer_hour:
            for timer_hour in reversed(self.timer_hours_sorted_by_order):
                if not timer_hour.error:
                    timer_hour.last_valid = True
                    break
        else:
            error = _('No valid hour defined.')
            self.error = error
            self.event.add_warning(error, timer=self)

    @cached_property
    def colors(self) -> dict[int, str]:
        stored_colors = self.stored_timer.colors or {}
        return {
            i: stored_colors.get(i) or self.event.timer_colors[i] for i in range(1, 4)
        }

    @property
    def color_1_rgb(self) -> RGB:
        return hexa_to_rgb(self.colors[1]) or RGB(0, 0, 0)

    @property
    def color_2_rgb(self) -> RGB:
        return hexa_to_rgb(self.colors[2]) or RGB(0, 0, 0)

    @property
    def color_3_rgb(self) -> RGB:
        return hexa_to_rgb(self.colors[3]) or RGB(0, 0, 0)

    @cached_property
    def delays(self) -> dict[int, int]:
        stored_delays = self.stored_timer.delays or {}
        return {
            i: stored_delays.get(i) or self.event.timer_delays[i] for i in range(1, 4)
        }

    def get_previous_timer_hour(self, timer_hour: TimerHour) -> TimerHour | None:
        """From the given `timer_hour`, finds the previous TimerHour object.
        Relies on insertion order being consistent with timer ordering."""
        previous_timer_hour: TimerHour | None = None
        for th in self.timer_hours_by_id.values():
            if th.id == timer_hour.id:
                return previous_timer_hour
            previous_timer_hour = th
        return None

    def __repr__(self):
        return f'{type(self).__name__}({self.colors} {self.delays} {self.timer_hours_by_id})'
