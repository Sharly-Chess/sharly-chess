from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime
from functools import cached_property
from typing import TYPE_CHECKING

from common.i18n import _
from database.sqlite.event.event_store import StoredTournamentPeriod
from plugins.utils import PluginData
from utils import Utils
from utils.date_time import format_date_range

if TYPE_CHECKING:
    from data.tournament import Tournament

# FIDE rates a tournament as a single event only when it lasts 30 days or
# less; a longer one is reported slice by slice, each slice within that
# span.
MAX_PERIOD_DAYS: int = 30

# The value of a tournament's tie-break rating setting that reads, for
# each game, the ratings of the slice the game was played in (VCL Q214).
# An empty setting is the first rating (C.07:10's default) and anything
# else is the id of the slice the arbiter named (Q216).
TIE_BREAK_RATING_BY_ROUND: str = 'round'


def dates_exceed_period(start_date: date, stop_date: date) -> bool:
    """Whether a tournament running between those dates is longer than
    FIDE rates as a single tournament."""
    return (stop_date - start_date).days + 1 > MAX_PERIOD_DAYS


def period_field_suffix(period_id: int) -> str:
    """What a form field of one slice is called.

    A slice's fields carry the names the plugin already uses, suffixed
    with the slice they belong to — so a plugin renders and reads its own
    fields without knowing that slices exist."""
    return f'_period_{period_id}'


def period_field_data(data: dict[str, str], period_id: int) -> dict[str, str]:
    """The form as one slice's fields state it, under the plain names."""
    suffix = period_field_suffix(period_id)
    return {
        field.removesuffix(suffix): value
        for field, value in data.items()
        if field.endswith(suffix)
    }


def period_first_rounds(marked_rounds: Collection[int], rounds: int) -> list[int]:
    """The rounds the periods start at, from the rounds the arbiter marked.
    Round 1 always starts one, and a mark past the last round is dropped."""
    return sorted(
        {1} | {round_nb for round_nb in marked_rounds if 1 < round_nb <= rounds}
    )


@dataclass
class PeriodSpan:
    """One period as the form shows it, worked out from values that are
    not saved yet. The stored periods (``TournamentPeriod``) answer the
    same questions once they are."""

    first_round: int
    last_round: int
    round_dates: dict[int, date]
    # The stored period this span describes, when the tournament already
    # has one starting at that round: a boundary the arbiter has just
    # marked has nothing stored behind it yet.
    period_id: int | None = None

    @property
    def start_date(self) -> date | None:
        return min(self.round_dates.values()) if self.round_dates else None

    @property
    def stop_date(self) -> date | None:
        return max(self.round_dates.values()) if self.round_dates else None

    @property
    def days(self) -> int | None:
        if self.start_date is None or self.stop_date is None:
            return None
        return (self.stop_date - self.start_date).days + 1

    @property
    def overflow_round(self) -> int | None:
        """The first round played more than 30 days after the period
        started — where the period has to be split."""
        start_date = self.start_date
        if start_date is None:
            return None
        return next(
            (
                round_nb
                for round_nb in sorted(self.round_dates)
                if (self.round_dates[round_nb] - start_date).days + 1 > MAX_PERIOD_DAYS
            ),
            None,
        )

    @property
    def too_long(self) -> bool:
        return (days := self.days) is not None and days > MAX_PERIOD_DAYS

    @property
    def rounds_str(self) -> str:
        return rounds_str(self.first_round, self.last_round)

    @property
    def dates_str(self) -> str:
        if self.start_date is None or self.stop_date is None:
            return ''
        return format_date_range(self.start_date, self.stop_date)


def period_spans(
    first_rounds: list[int],
    rounds: int,
    round_datetimes: dict[int, datetime | None],
    period_id_by_first_round: dict[int, int] | None = None,
) -> list[PeriodSpan]:
    """The periods those boundaries describe, with the dates the rounds
    they cover give them."""
    spans: list[PeriodSpan] = []
    for index, first_round in enumerate(first_rounds):
        last_round = (
            first_rounds[index + 1] - 1 if index + 1 < len(first_rounds) else rounds
        )
        spans.append(
            PeriodSpan(
                first_round=first_round,
                last_round=last_round,
                round_dates={
                    round_nb: round_datetime.date()
                    for round_nb in range(first_round, last_round + 1)
                    if (round_datetime := round_datetimes.get(round_nb)) is not None
                },
                period_id=(period_id_by_first_round or {}).get(first_round),
            )
        )
    return spans


def period_too_long_message(span: PeriodSpan) -> str:
    """What to tell the arbiter about a period FIDE would not rate as one
    tournament: how long it runs, and the round to split before."""
    if span.overflow_round is not None:
        return _(
            'This period lasts %(days)d days: split it before round #%(round)d.'
        ) % {'days': span.days, 'round': span.overflow_round}
    return _('This period lasts %(days)d days; FIDE allows %(max)d at most.') % {
        'days': span.days,
        'max': MAX_PERIOD_DAYS,
    }


def rounds_str(first_round: int, last_round: int) -> str:
    if first_round >= last_round:
        return _('R%(round)d') % {'round': first_round}
    return _('R%(first)d–R%(last)d') % {'first': first_round, 'last': last_round}


class TournamentPeriod:
    """A rating period: the rounds a tournament reports to FIDE as one
    tournament of its own.

    The period covers ``first_round`` up to ``last_round``, the round
    before the next period starts at. Its dates come from the rounds it
    covers, and the rating list it is played on is the one in force when
    it starts."""

    def __init__(
        self,
        tournament: 'Tournament',
        stored_period: StoredTournamentPeriod,
        index: int,
        last_round: int,
    ):
        self.tournament = tournament
        self.stored_period = stored_period
        self.index = index
        self.last_round = last_round

    @property
    def id(self) -> int | None:
        return self.stored_period.id

    @property
    def first_round(self) -> int:
        return self.stored_period.first_round

    @property
    def rounds(self) -> range:
        return range(self.first_round, self.last_round + 1)

    @cached_property
    def plugin_data(self) -> dict[str, PluginData]:
        """What each plugin keeps about this slice.

        A slice is submitted as a tournament of its own, so a service
        that wants one registration per slice — the FFE gives each
        "tranche" its own homologation number — keeps that registration's
        identifiers here rather than on the tournament."""
        from data.tournament import Tournament

        return {
            plugin_id: plugin_data_class.from_stored_value(
                self.stored_period.plugin_data.get(plugin_id, {})
            )
            for plugin_id, plugin_data_class in (
                Tournament.plugin_data_class_by_plugin_id().items()
            )
        }

    def set_plugin_data(self, plugin_id: str, plugin_data: PluginData) -> None:
        """Record what a plugin keeps about this slice."""
        from database.sqlite.event.event_database import EventDatabase

        self.stored_period.plugin_data[plugin_id] = plugin_data.to_stored_value()
        Utils.reset_cached_properties(self, 'plugin_data')
        assert self.id is not None
        with EventDatabase(self.tournament.event.uniq_id, True) as database:
            database.set_tournament_period_plugin_data(
                self.id, self.stored_period.plugin_data
            )

    @property
    def round_datetimes(self) -> list[datetime]:
        return [
            round_datetime
            for round_nb in self.rounds
            if (round_datetime := self.tournament.round_datetimes.get(round_nb))
            is not None
        ]

    @property
    def start_datetime(self) -> datetime | None:
        round_datetimes = self.round_datetimes
        return min(round_datetimes) if round_datetimes else None

    @property
    def stop_datetime(self) -> datetime | None:
        round_datetimes = self.round_datetimes
        return max(round_datetimes) if round_datetimes else None

    @property
    def start_date(self) -> date | None:
        return (
            start_datetime.date() if (start_datetime := self.start_datetime) else None
        )

    @property
    def stop_date(self) -> date | None:
        return stop_datetime.date() if (stop_datetime := self.stop_datetime) else None

    @property
    def days(self) -> int | None:
        """The span in days, counting both end days, or None while the
        rounds it covers have no dates."""
        start_date, stop_date = self.start_date, self.stop_date
        if start_date is None or stop_date is None:
            return None
        return (stop_date - start_date).days + 1

    @property
    def too_long(self) -> bool:
        return (days := self.days) is not None and days > MAX_PERIOD_DAYS

    @property
    def rating_month(self) -> date | None:
        """The month of the rating list the period is played on: the one
        in force when it starts."""
        start_date = self.start_date
        return start_date.replace(day=1) if start_date else None

    @property
    def rounds_str(self) -> str:
        return rounds_str(self.first_round, self.last_round)

    @property
    def report_name(self) -> str:
        """What a report covering this slice calls itself: the
        tournament's name and the rounds the file holds.

        Federations name a slice's registration after its rounds — "OP
        Settimanale Autunno 2022 Rounds 5-6", "Belgian Interclubs Round
        2025-2026 Ronde 11" — and a file that says the same is told from
        the tournament's own at a glance."""
        if self.first_round >= self.last_round:
            rounds = _('Round %(round)d') % {'round': self.first_round}
        else:
            rounds = _('Rounds %(first)d-%(last)d') % {
                'first': self.first_round,
                'last': self.last_round,
            }
        return f'{self.tournament.name} {rounds}'

    @property
    def dates_str(self) -> str:
        start_date, stop_date = self.start_date, self.stop_date
        if start_date is None or stop_date is None:
            return ''
        return format_date_range(start_date, stop_date)
