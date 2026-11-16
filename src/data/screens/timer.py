import weakref
from collections import defaultdict
from collections.abc import Collection, Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, date
from enum import StrEnum
from functools import cached_property
from operator import attrgetter
from typing import TYPE_CHECKING
from _weakref import ReferenceType

from common import RGB, hexa_to_rgb
from common.i18n import _
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTimerHour, StoredTimer
from utils.date_time import format_date, format_time, format_datetime

if TYPE_CHECKING:
    from data.event import Event
    from data.screens.family import Family
    from data.screens.rotator import Rotator
    from data.screens.screen import Screen
    from data.tournament import Tournament


class ScheduleRoundStatus(StrEnum):
    NEW = 'new'
    CHANGED = 'changed'
    SAME = 'same'
    CONFLICT = 'conflict'


@dataclass
class ScheduleRound:
    """A round of a tournament's schedule, compared with the hours of a timer."""

    round: int
    triggered_at: datetime
    status: ScheduleRoundStatus
    hour: TimerHour | None = None
    conflicting_hour: TimerHour | None = None

    @property
    def selected(self) -> bool:
        return self.status in (ScheduleRoundStatus.NEW, ScheduleRoundStatus.CHANGED)

    @property
    def triggered_at_str(self) -> str:
        return format_datetime(self.triggered_at)


class TimerHour:
    """A data wrapper around a stored timer hour."""

    def __init__(
        self,
        timer: Timer,
        stored_timer_hour: StoredTimerHour,
    ):
        self._timer_ref: ReferenceType[Timer] = weakref.ref(timer)
        self.stored_timer_hour: StoredTimerHour = stored_timer_hour

    @property
    def timer(self) -> Timer:
        _timer = self._timer_ref()
        if _timer is None:
            raise RuntimeError('Timer reference has been garbage collected')
        return _timer

    @property
    def id(self) -> int:
        assert self.stored_timer_hour.id is not None
        return self.stored_timer_hour.id

    @property
    def round(self) -> int | None:
        return self.stored_timer_hour.round

    @property
    def label(self) -> str | None:
        return self.stored_timer_hour.label

    @property
    def is_round(self) -> bool:
        return self.round is not None

    @property
    def name(self) -> str:
        if self.round is None:
            return self.label or ''
        round_name = _('Round #{round}').format(round=self.round)
        if self.label:
            return f'{self.label} · {round_name}'
        return round_name

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

    @property
    def default_text_before(self) -> str:
        return self.default_texts(self.round, self.label)[0]

    @property
    def default_text_after(self) -> str:
        return self.default_texts(self.round, self.label)[1]

    @staticmethod
    def default_texts(round_: int | str | None, label: str | None) -> tuple[str, str]:
        """The texts shown before and after the hour when none is given,
        `%s` standing for the time left or elapsed."""
        label = label or ''
        if round_ is None:
            return (
                _('{label} in %%s').replace('%%', '%').format(label=label),
                _('{label} (%%s ago)').replace('%%', '%').format(label=label),
            )
        if label:
            return (
                _('{label}: round {round} starts in %%s')
                .replace('%%', '%')
                .format(label=label, round=round_),
                _('{label}: round {round} started %%s ago')
                .replace('%%', '%')
                .format(label=label, round=round_),
            )
        return (
            _('Round {round} starts in %%s').replace('%%', '%').format(round=round_),
            _('Round {round} started %%s ago').replace('%%', '%').format(round=round_),
        )

    def _custom_text(self, text: str | None) -> str | None:
        if not text:
            return None
        if self.round is not None:
            return text.replace('{}', str(self.round))
        return text

    @cached_property
    def text_before(self) -> str:
        return (
            self._custom_text(self.stored_timer_hour.text_before)
            or self.default_text_before
        )

    @cached_property
    def text_after(self) -> str:
        return (
            self._custom_text(self.stored_timer_hour.text_after)
            or self.default_text_after
        )

    @property
    def has_custom_texts(self) -> bool:
        return bool(
            self.stored_timer_hour.text_before or self.stored_timer_hour.text_after
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

    def update(self, stored_timer_hour: StoredTimerHour) -> None:
        stored_timer_hour.id = self.id
        with EventDatabase(self.timer.event.uniq_id, True) as database:
            database.update_stored_timer_hour(stored_timer_hour)
        self.stored_timer_hour = stored_timer_hour

    def __str__(self) -> str:
        return (
            f'{self.__class__.__name__}(id={self.id} round={self.round} label={self.label} '
            f'triggered_at={format_datetime(self.triggered_at)} '
            f'texts=[{self.text_before}]/[{self.text_after}])'
        )

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(timer={self.timer!r}, stored_timer_hour={self.stored_timer_hour!r})'


class Timer:
    """A data wrapper around a stored timer."""

    def __init__(self, event: Event, stored_timer: StoredTimer):
        self._event_ref: ReferenceType[Event] = weakref.ref(event)
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
    def event(self) -> Event:
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

    @property
    def colors(self) -> dict[int, str]:
        return self.event.timer_colors

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
        event_delays = self.event.timer_delays
        return {
            i: event_delays[i] if (delay := stored_delays.get(i)) is None else delay
            for i in range(1, 4)
        }

    @property
    def screens(self) -> list[Screen]:
        return [
            screen
            for screen in self.event.sorted_basic_screens
            if screen.stored_screen and screen.stored_screen.timer_id == self.id
        ]

    @property
    def families(self) -> list[Family]:
        return [
            family
            for family in self.event.sorted_families
            if family.timer_id == self.id
        ]

    @property
    def rotators(self) -> list[Rotator]:
        return [
            rotator
            for rotator in self.event.sorted_rotators
            if rotator.timer_id == self.id
        ]

    @property
    def first_date(self) -> date:
        """The first day an hour may be set on: today, before the event."""
        return min(self.event.start_date, date.today())

    @property
    def last_date(self) -> date:
        """The last day an hour may be set on: today, after the event."""
        return max(self.event.stop_date, date.today())

    @property
    def first_date_str(self) -> str:
        return format_date(self.first_date)

    @property
    def last_date_str(self) -> str:
        return format_date(self.last_date)

    @property
    def has_available_date(self) -> bool:
        hour_dates = {hour.triggered_at.date() for hour in self.timer_hours}
        current_date = self.first_date
        while current_date <= self.last_date:
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
    def timer_hours_by_date_str(self) -> dict[str, list[TimerHour]]:
        timer_hours_by_date: dict[str, list[TimerHour]] = defaultdict(list)
        for timer_hour in self.sorted_timer_hours:
            timer_hours_by_date[timer_hour.date_str].append(timer_hour)
        return timer_hours_by_date

    @property
    def next_round(self) -> int:
        rounds = {hour.round for hour in self.timer_hours if hour.round is not None}
        return next(
            round_ for round_ in range(1, len(rounds) + 2) if round_ not in rounds
        )

    @property
    def phase_bar_style(self) -> str:
        """The CSS of a bar coloured as the timer is, from a while before the
        hour to the end of its display, the hour marked at --timer-hour-at."""
        fade_1, fade_2, after = self.delays[1], self.delays[2], self.delays[3]
        lead = max(5.0, (fade_1 + fade_2) / 3)
        total = lead + fade_1 + fade_2 + after

        def at(minutes: float) -> str:
            return f'{100 * minutes / total:.1f}%'

        green, orange, red = self.colors[1], self.colors[2], self.colors[3]
        return (
            f'background: linear-gradient(to right, {green} 0%, {green} {at(lead)}, '
            f'{orange} {at(lead + fade_1)}, {red} {at(lead + fade_1 + fade_2)}, '
            f'{red} 100%); --timer-hour-at: {at(lead + fade_1 + fade_2)}'
        )

    def free_hour_time(self, now: datetime) -> datetime:
        """The time a new hour starts from: the next quarter of an hour while
        the event is running, an hour after the last hour otherwise, and the
        morning of the first day of the event for a timer with no hours;
        moved on until no other hour takes it."""
        event = self.event
        step = timedelta(minutes=15)
        if event.start_date <= now.date() <= event.stop_date:
            triggered_at = now.replace(second=0, microsecond=0) + timedelta(
                minutes=15 - now.minute % 15
            )
        elif self.timer_hours:
            triggered_at = self.sorted_timer_hours[-1].triggered_at + timedelta(hours=1)
        else:
            triggered_at = datetime.combine(event.start_date, datetime.min.time())
            triggered_at += timedelta(hours=9)
        taken = {hour.triggered_at for hour in self.timer_hours}
        while triggered_at in taken:
            triggered_at += step
        return triggered_at

    def update(self, stored_timer: StoredTimer) -> None:
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

    def delete_timer_hour(self, timer_hour_id: int) -> None:
        with EventDatabase(self.event.uniq_id, True) as database:
            database.delete_stored_timer_hour(timer_hour_id)
        if timer_hour_id in self.timer_hours_by_id:
            del self.timer_hours_by_id[timer_hour_id]

    def schedule_rounds(self, tournament: Tournament) -> list[ScheduleRound]:
        """The scheduled rounds of the tournament, each matched with the round
        hour of the same number, if any."""
        hour_by_round: dict[int, TimerHour] = {}
        for timer_hour in self.sorted_timer_hours:
            if timer_hour.round is not None:
                hour_by_round.setdefault(timer_hour.round, timer_hour)
        schedule_rounds: list[ScheduleRound] = []
        for round_, triggered_at in sorted(tournament.round_datetimes.items()):
            if triggered_at is None:
                continue
            hour = hour_by_round.get(round_)
            conflicting_hour = next(
                (
                    other
                    for other in self.timer_hours
                    if other.triggered_at == triggered_at and other is not hour
                ),
                None,
            )
            if hour is not None and hour.triggered_at == triggered_at:
                status = ScheduleRoundStatus.SAME
            elif conflicting_hour is not None:
                status = ScheduleRoundStatus.CONFLICT
            elif hour is None:
                status = ScheduleRoundStatus.NEW
            else:
                status = ScheduleRoundStatus.CHANGED
            schedule_rounds.append(
                ScheduleRound(round_, triggered_at, status, hour, conflicting_hour)
            )
        return schedule_rounds

    def copy_schedule(
        self, tournament: Tournament, rounds: Iterable[int]
    ) -> tuple[int, int]:
        """Adds or moves the round hours of the given rounds to the tournament's
        schedule, and returns how many were added and how many moved."""
        rounds = set(rounds)
        added = moved = 0
        for schedule_round in self.schedule_rounds(tournament):
            if schedule_round.round not in rounds or not schedule_round.selected:
                continue
            if schedule_round.hour is None:
                self.add_timer_hour(
                    StoredTimerHour(
                        id=None,
                        timer_id=self.id,
                        triggered_at=schedule_round.triggered_at,
                        round=schedule_round.round,
                    )
                )
                added += 1
            else:
                self.move_timer_hour(schedule_round.hour, schedule_round.triggered_at)
                moved += 1
        return added, moved

    def move_timer_hour(self, timer_hour: TimerHour, triggered_at: datetime) -> None:
        stored_timer_hour = replace(
            timer_hour.stored_timer_hour, triggered_at=triggered_at
        )
        with EventDatabase(self.event.uniq_id, True) as database:
            database.update_stored_timer_hour(stored_timer_hour)
        self.timer_hours_by_id[timer_hour.id] = TimerHour(self, stored_timer_hour)

    def later_hours_of_the_day(self, timer_hour: TimerHour) -> list[TimerHour]:
        return [
            hour
            for hour in self.sorted_timer_hours
            if hour.triggered_at > timer_hour.triggered_at
            and hour.triggered_at.date() == timer_hour.triggered_at.date()
        ]

    def postpone_conflicts(
        self, timer_hour: TimerHour, minutes: int, with_later_hours: bool
    ) -> list[TimerHour]:
        """The hours that stay where they are and whose time a postponed hour
        would take."""
        moved = self._postponed_hours(timer_hour, with_later_hours)
        delta = timedelta(minutes=minutes)
        new_times = {hour.triggered_at + delta for hour in moved}
        moved_ids = {hour.id for hour in moved}
        return [
            hour
            for hour in self.timer_hours
            if hour.id not in moved_ids and hour.triggered_at in new_times
        ]

    def _postponed_hours(
        self, timer_hour: TimerHour, with_later_hours: bool
    ) -> list[TimerHour]:
        return [timer_hour] + (
            self.later_hours_of_the_day(timer_hour) if with_later_hours else []
        )

    def postpone(
        self, timer_hour: TimerHour, minutes: int, with_later_hours: bool
    ) -> int:
        """Moves the hour, and the later hours of its day if asked, by the given
        number of minutes; returns how many hours moved."""
        moved = self._postponed_hours(timer_hour, with_later_hours)
        delta = timedelta(minutes=minutes)
        for hour in moved:
            self.move_timer_hour(hour, hour.triggered_at + delta)
        return len(moved)

    def delete_all_timer_hours(self) -> None:
        """Delete every timer hour for this timer in one pass."""
        with EventDatabase(self.event.uniq_id, True) as database:
            for timer_hour_id in list(self.timer_hours_by_id):
                database.delete_stored_timer_hour(timer_hour_id)
        self.timer_hours_by_id.clear()

    def update_timer_hours_date(self, previous_date: date, new_date: date) -> None:
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

    def __str__(self) -> str:
        return f'{type(self).__name__}({self.colors} {self.delays} {self.timer_hours_by_id})'

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(event={self.event!r}, stored_timer={self.stored_timer!r})'
