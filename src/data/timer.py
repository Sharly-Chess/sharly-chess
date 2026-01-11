import weakref
from collections import defaultdict
from collections.abc import Collection
from datetime import datetime, timedelta, date
from functools import cached_property
from operator import attrgetter
from typing import TYPE_CHECKING
from _weakref import ReferenceType

from common import RGB, hexa_to_rgb
from common.i18n import _
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTimerHour, StoredTimer
from utils import Utils
from utils.date_time import format_date, format_time, format_datetime

if TYPE_CHECKING:
    from data.event import Event


class TimerHour:
    """A data wrapper around a stored timer hour."""

    def __init__(
        self,
        timer: 'Timer',
        stored_timer_hour: StoredTimerHour,
    ):
        self._timer_ref: 'ReferenceType[Timer]' = weakref.ref(timer)
        self.stored_timer_hour: StoredTimerHour = stored_timer_hour

    @property
    def timer(self) -> 'Timer':
        _timer = self._timer_ref()
        if _timer is None:
            raise RuntimeError('Timer reference has been garbage collected')
        return _timer

    @property
    def id(self) -> int:
        assert self.stored_timer_hour.id is not None
        return self.stored_timer_hour.id

    @property
    def uniq_id(self) -> str:
        return self.stored_timer_hour.uniq_id

    @property
    def name(self) -> str:
        if self.uniq_id.isdigit():
            return _('Round #{round}').format(round=self.uniq_id)
        return self.uniq_id

    @property
    def triggered_at(self) -> datetime:
        return self.stored_timer_hour.triggered_at

    @property
    def triggered_at_str(self) -> str:
        return format_datetime(self.triggered_at)

    @property
    def timestamp(self) -> int:
        return int(self.triggered_at.timestamp())

    @property
    def date_str(self) -> str:
        return format_date(self.triggered_at.date())

    @property
    def time_str(self) -> str:
        return format_time(self.triggered_at)

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
            _('Start of round {} in %%s').replace('%%', '%'),
        )

    @cached_property
    def text_after(self) -> str:
        return self._format_stored_text(
            self.stored_timer_hour.text_after,
            _('Round {} started for %%s').replace('%%', '%'),
        )

    @property
    def timestamp_1(self) -> int:
        return self.timestamp - self.timer.delays[1] * 60 - self.timer.delays[2] * 60

    @property
    def timestamp_2(self) -> int:
        return self.timestamp - self.timer.delays[2] * 60

    @property
    def timestamp_3(self) -> int:
        return self.timestamp

    @property
    def timestamp_next(self) -> int:
        return self.timestamp + self.timer.delays[3] * 60

    def update(self, stored_timer_hour: StoredTimerHour):
        stored_timer_hour.id = self.id
        with EventDatabase(self.timer.event.uniq_id, True) as database:
            database.update_stored_timer_hour(stored_timer_hour)
        self.stored_timer_hour = stored_timer_hour

    def __str__(self):
        return (
            f'{self.__class__.__name__}(id={self.id} uniq_id={self.uniq_id} '
            f'triggered_at={format_datetime(self.triggered_at)} '
            f'texts=[{self.text_before}]/[{self.text_after}])'
        )

    def __repr__(self):
        return f'{self.__class__.__name__}(timer={self.timer!r}, stored_timer_hour={self.stored_timer_hour!r})'


class Timer:
    """A data wrapper around a stored timer."""

    def __init__(self, event: 'Event', stored_timer: StoredTimer):
        self._event_ref: 'ReferenceType[Event]' = weakref.ref(event)
        self.stored_timer: StoredTimer = stored_timer
        self.timer_hours_by_id: dict[int, TimerHour] = self._get_timer_hours_by_id()
        self.valid: bool = True
        self.error: str | None = None

    def _get_timer_hours_by_id(self) -> dict[int, TimerHour]:
        timer_hours_by_id = {}
        for stored_entry in self.stored_timer.stored_timer_hours:
            assert stored_entry.id is not None
            timer_hours_by_id[stored_entry.id] = TimerHour(self, stored_entry)
        return timer_hours_by_id

    @property
    def event(self) -> 'Event':
        event = self._event_ref()
        if event is None:
            raise RuntimeError('Event reference has been garbage collected')
        return event

    @property
    def id(self) -> int:
        assert self.stored_timer.id is not None
        return self.stored_timer.id

    @property
    def name(self) -> str:
        return self.stored_timer.name

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

    @property
    def has_available_date(self) -> bool:
        hour_dates = {hour.triggered_at.date() for hour in self.timer_hours}
        current_date = self.event.start_date
        while current_date <= self.event.stop_date:
            if current_date not in hour_dates:
                return True
            current_date += timedelta(days=1)
        return False

    @property
    def timer_hours(self) -> Collection[TimerHour]:
        return self.timer_hours_by_id.values()

    @property
    def sorted_timer_hours(self) -> list[TimerHour]:
        return sorted(self.timer_hours, key=attrgetter('triggered_at'))

    @property
    def timer_hour_uniq_ids(self) -> list[str]:
        return [timer_hour.uniq_id for timer_hour in self.timer_hours_by_id.values()]

    @property
    def timer_hours_by_date_str(self) -> dict[str, list[TimerHour]]:
        timer_hours_by_date: dict[str, list[TimerHour]] = defaultdict(list)
        for timer_hour in self.sorted_timer_hours:
            timer_hours_by_date[timer_hour.date_str].append(timer_hour)
        return timer_hours_by_date

    @property
    def next_round(self) -> int:
        rounds = [
            int(uniq_id) for uniq_id in self.timer_hour_uniq_ids if uniq_id.isdigit()
        ]
        return next(
            round_ for round_ in range(1, len(rounds) + 2) if round_ not in rounds
        )

    def get_unused_hour_name(self, base_name: str) -> str:
        return Utils.get_unused_item_name(base_name, self.timer_hour_uniq_ids)

    def update(self, stored_timer: StoredTimer):
        stored_timer.id = self.id
        stored_timer.stored_timer_hours = self.stored_timer.stored_timer_hours
        with EventDatabase(self.event.uniq_id, True) as database:
            database.update_stored_timer(stored_timer)
        self.stored_timer = stored_timer

    def add_timer_hour(self, stored_timer_hour: StoredTimerHour) -> TimerHour:
        with EventDatabase(self.event.uniq_id, True) as database:
            id_ = database.add_stored_timer_hour(stored_timer_hour)
            stored_timer_hour.id = id_
        timer_hour = TimerHour(self, stored_timer_hour)
        self.timer_hours_by_id[id_] = timer_hour
        return timer_hour

    def delete_timer_hour(self, timer_hour_id: int):
        with EventDatabase(self.event.uniq_id, True) as database:
            database.delete_stored_timer_hour(timer_hour_id)
        if timer_hour_id in self.timer_hours_by_id:
            del self.timer_hours_by_id[timer_hour_id]

    def update_timer_hours_date(self, previous_date: date, new_date: date):
        hours_by_date_str = self.timer_hours_by_date_str
        new_date_hours_triggered_at = [
            hour.triggered_at
            for hour in hours_by_date_str.get(format_date(new_date), [])
        ]
        with EventDatabase(self.event.uniq_id, True) as database:
            for timer_hour in hours_by_date_str.get(format_date(previous_date), []):
                stored_hour = timer_hour.stored_timer_hour
                triggered_at = stored_hour.triggered_at.replace(
                    year=new_date.year, month=new_date.month, day=new_date.day
                )
                if triggered_at in new_date_hours_triggered_at:
                    continue
                stored_hour.triggered_at = triggered_at
                database.update_stored_timer_hour(stored_hour)

    def __str__(self):
        return f'{type(self).__name__}({self.colors} {self.delays} {self.timer_hours_by_id})'

    def __repr__(self):
        return f'{self.__class__.__name__}(event={self.event!r}, stored_timer={self.stored_timer!r})'
