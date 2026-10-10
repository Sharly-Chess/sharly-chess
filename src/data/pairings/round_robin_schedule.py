"""The schedule of a round-robin: who meets whom, with which colours, in
every round, defined for the whole tournament before it starts. The members
are players, or teams in a team round-robin."""

from collections import Counter
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from itertools import combinations
from typing import TYPE_CHECKING, Any, Self

from common.i18n import _

if TYPE_CHECKING:
    from data.tournament import Tournament

REST = -1
"""The table index of a round's rest seat."""

type Seat = tuple[int, int]
"""A seat of a round: the table index (:data:`REST` for the rest seat) and
the side, 0 for the first member (white) and 1 for the second (black)."""

type Table = tuple[int | None, int | None]
"""The members of a table, first (white) then second (black); ``None`` for
a seat not filled yet."""


def single_cycle_round_count(member_count: int) -> int:
    """The rounds in which every member meets every other one once."""
    return member_count if member_count % 2 == 1 else member_count - 1


@dataclass
class ScheduleRound:
    tables: list[Table]
    rest: int | None = None


@dataclass
class RoundRobinSchedule:
    rounds: dict[int, ScheduleRound] = field(default_factory=dict)

    @classmethod
    def empty(cls, member_count: int, encounters: int) -> Self:
        """A schedule with every seat of every round left empty."""
        return cls(
            {
                round_: ScheduleRound([(None, None)] * (member_count // 2))
                for round_ in range(
                    1, encounters * single_cycle_round_count(member_count) + 1
                )
            }
        )

    @classmethod
    def berger(
        cls,
        member_ids_by_number: Mapping[int, int],
        encounters: int,
        reverse_last_rounds: bool,
    ) -> Self:
        """The schedule of the Berger tables (FIDE C.05 Annex 1), the
        members given by their Berger number. In a double round-robin, the
        second cycle repeats the first with the colours reversed."""
        from data.pairings.engines import (
            BergerPairingEngine,
            DoubleBergerPairingEngine,
        )

        member_count = len(member_ids_by_number)
        if member_count < 2:
            return cls.empty(member_count, encounters)
        table = BergerPairingEngine.get_berger_table(member_count)
        single_rounds = single_cycle_round_count(member_count)
        rounds: dict[int, ScheduleRound] = {}
        for round_ in range(1, encounters * single_rounds + 1):
            source_round, invert = DoubleBergerPairingEngine.source_round(
                round_, single_rounds, reverse_last_rounds
            )
            schedule_round = ScheduleRound([])
            for white, black in table[source_round]:
                if invert:
                    white, black = black, white
                white_id = member_ids_by_number.get(white)
                black_id = member_ids_by_number.get(black)
                if white_id is None or black_id is None:
                    schedule_round.rest = white_id or black_id
                else:
                    schedule_round.tables.append((white_id, black_id))
            rounds[round_] = schedule_round
        return cls(rounds)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            {
                int(round_): ScheduleRound(
                    [(first, second) for first, second in round_data['tables']],
                    round_data.get('rest'),
                )
                for round_, round_data in data.items()
            }
        )

    def to_json(self) -> dict[str, Any]:
        return {
            str(round_): {
                'tables': [list(table) for table in schedule_round.tables],
                'rest': schedule_round.rest,
            }
            for round_, schedule_round in sorted(self.rounds.items())
        }

    def member_at(self, round_: int, seat: Seat) -> int | None:
        schedule_round = self.rounds[round_]
        table, side = seat
        if table == REST:
            return schedule_round.rest
        return schedule_round.tables[table][side]

    def seat_of(self, round_: int, member: int) -> Seat | None:
        schedule_round = self.rounds[round_]
        if schedule_round.rest == member:
            return REST, 0
        for index, table in enumerate(schedule_round.tables):
            if member in table:
                return index, table.index(member)
        return None

    def place(self, round_: int, seat: Seat, member: int | None) -> None:
        """Seat *member* at *seat* of *round_*, leaving empty the seat they
        had in the round."""
        previous_seat = self.seat_of(round_, member) if member is not None else None
        if previous_seat == seat:
            return
        if previous_seat is not None:
            self._set(round_, previous_seat, None)
        self._set(round_, seat, member)

    def seated(self, round_: int) -> set[int]:
        """The members seated in *round_*, resting included."""
        schedule_round = self.rounds[round_]
        return {
            member
            for member in (
                *(member for table in schedule_round.tables for member in table),
                schedule_round.rest,
            )
            if member is not None
        }

    def swap_colours(self, round_: int, table: int) -> None:
        schedule_round = self.rounds[round_]
        first, second = schedule_round.tables[table]
        schedule_round.tables[table] = second, first

    def _set(self, round_: int, seat: Seat, member: int | None) -> None:
        schedule_round = self.rounds[round_]
        table, side = seat
        if table == REST:
            schedule_round.rest = member
            return
        members = list(schedule_round.tables[table])
        members[side] = member
        schedule_round.tables[table] = members[0], members[1]

    def copy(self) -> 'RoundRobinSchedule':
        return RoundRobinSchedule.from_json(self.to_json())

    @property
    def members(self) -> set[int]:
        """The members seated somewhere in the schedule."""
        return {
            member
            for schedule_round in self.rounds.values()
            for member in (
                *(member for table in schedule_round.tables for member in table),
                schedule_round.rest,
            )
            if member is not None
        }

    def fits(self, member_count: int, encounters: int) -> bool:
        """Whether the schedule has the rounds and tables of a round-robin of
        *member_count* members meeting *encounters* times."""
        return sorted(self.rounds) == list(
            range(1, encounters * single_cycle_round_count(member_count) + 1)
        ) and all(
            len(schedule_round.tables) == member_count // 2
            for schedule_round in self.rounds.values()
        )

    def resized(
        self, member_ids: Collection[int], encounters: int
    ) -> 'RoundRobinSchedule':
        """The schedule of a round-robin of the members *member_ids* meeting
        *encounters* times, keeping as much of this one as fits: the games
        and the rest of each of its rounds, between members still in the
        field. The seats left are empty."""
        members = set(member_ids)
        schedule = RoundRobinSchedule.empty(len(members), encounters)

        def kept(member: int | None) -> int | None:
            return member if member in members else None

        for round_, schedule_round in schedule.rounds.items():
            if (own_round := self.rounds.get(round_)) is None:
                continue
            tables = [
                (kept(first), kept(second))
                for first, second in own_round.tables[: len(schedule_round.tables)]
            ]
            schedule_round.tables[: len(tables)] = tables
            if len(members) % 2 == 1:
                schedule_round.rest = kept(own_round.rest)
        return schedule

    def adapted(self, member_ids: Collection[int]) -> 'RoundRobinSchedule | None':
        """The schedule for the members *member_ids*, when they differ from
        its own by one member who can take or leave the rest seats: a
        newcomer to an odd field plays the member resting in each round,
        and the opponents of a member leaving an even field rest instead.
        ``None`` when the schedule cannot be adapted so."""
        members = set(member_ids)
        own_members = self.members
        if members == own_members:
            return self
        added, removed = members - own_members, own_members - members
        if len(added) == 1 and not removed:
            return self._with_newcomer(added.pop())
        if len(removed) == 1 and not added:
            return self._without_member(removed.pop())
        return None

    def _with_newcomer(self, newcomer: int) -> 'RoundRobinSchedule | None':
        if any(round_.rest is None for round_ in self.rounds.values()):
            return None
        schedule = self.copy()
        newcomer_colours: list[bool] = []
        first_games: dict[int, bool] = {}
        for round_ in sorted(schedule.rounds):
            schedule_round = schedule.rounds[round_]
            rester = schedule_round.rest
            assert rester is not None
            if rester in first_games:
                # The second game of a double round-robin reverses the
                # colours of the first.
                newcomer_white = not first_games[rester]
            else:
                newcomer_white = not newcomer_colours[-1] if newcomer_colours else True
            table: Table = (newcomer, rester) if newcomer_white else (rester, newcomer)
            schedule_round.tables.append(table)
            schedule_round.rest = None
            if rester not in first_games and schedule._colour_run(rester, round_):
                schedule_round.tables[-1] = table[1], table[0]
                newcomer_white = not newcomer_white
            first_games.setdefault(rester, newcomer_white)
            newcomer_colours.append(newcomer_white)
        return schedule

    def _without_member(self, member: int) -> 'RoundRobinSchedule | None':
        if any(round_.rest is not None for round_ in self.rounds.values()):
            return None
        schedule = self.copy()
        for schedule_round in schedule.rounds.values():
            table = next(table for table in schedule_round.tables if member in table)
            schedule_round.tables.remove(table)
            schedule_round.rest = table[1] if table[0] == member else table[0]
        return schedule

    def _colour_run(self, member: int, round_: int) -> bool:
        """Whether *member* has the same colour in three rounds in a row
        around *round_*."""
        colours = dict(self.colour_sequence(member))
        return any(
            (white := colours.get(start)) is not None
            and all(colours.get(start + offset) == white for offset in (1, 2))
            for start in range(round_ - 2, round_ + 1)
        )

    def colour_sequence(self, member: int) -> list[tuple[int, bool | None]]:
        """Each round with whether *member* has white in it, ``None`` when
        they do not play."""
        sequence: list[tuple[int, bool | None]] = []
        for round_ in sorted(self.rounds):
            seat = self.seat_of(round_, member)
            sequence.append(
                (round_, None if seat is None or seat[0] == REST else seat[1] == 0)
            )
        return sequence


class Breach(StrEnum):
    """The rules a schedule may be saved breaking, a round having been
    played otherwise than planned."""

    REPEATED_MEETING = 'repeated_meeting'
    REPEATED_REST = 'repeated_rest'
    MISSING_MEETING = 'missing_meeting'
    WHITE_RUN = 'white_run'
    BLACK_RUN = 'black_run'
    SAME_COLOURS = 'same_colours'


def describe_breach(
    breach: Breach,
    members: tuple[int, ...],
    rounds: tuple[int, ...],
    encounters: int,
    name: Callable[[int], str],
    locale: str | None = None,
) -> str:
    """*breach* by *members* in *rounds*, as a sentence."""
    listed = ', '.join(map(str, rounds))
    match breach:
        case Breach.REPEATED_MEETING:
            return (
                _(
                    '[{first}] and [{second}] meet more than once (rounds {rounds}).',
                    locale,
                )
                if encounters == 1
                else _(
                    '[{first}] and [{second}] meet more than twice (rounds {rounds}).',
                    locale,
                )
            ).format(first=name(members[0]), second=name(members[1]), rounds=listed)
        case Breach.REPEATED_REST:
            return (
                _('[{member}] rests more than once (rounds {rounds}).', locale)
                if encounters == 1
                else _('[{member}] rests more than twice (rounds {rounds}).', locale)
            ).format(member=name(members[0]), rounds=listed)
        case Breach.MISSING_MEETING:
            return (
                _('[{first}] and [{second}] never meet.', locale)
                if encounters == 1
                else _('[{first}] and [{second}] meet only once.', locale)
            ).format(first=name(members[0]), second=name(members[1]))
        case Breach.WHITE_RUN | Breach.BLACK_RUN:
            return (
                _(
                    '[{member}] has White {count} rounds in a row '
                    '(rounds {first} to {last}).',
                    locale,
                )
                if breach == Breach.WHITE_RUN
                else _(
                    '[{member}] has Black {count} rounds in a row '
                    '(rounds {first} to {last}).',
                    locale,
                )
            ).format(
                member=name(members[0]),
                count=len(rounds),
                first=rounds[0],
                last=rounds[-1],
            )
        case Breach.SAME_COLOURS:
            return _(
                '[{white}] has White in both games against [{black}].', locale
            ).format(white=name(members[0]), black=name(members[1]))


@dataclass(frozen=True)
class ScheduleViolation:
    round: int | None
    """The round the violation shows in, ``None`` for the whole schedule."""
    message: str
    breach: Breach | None = None
    """The rule broken, when the schedule can be saved all the same, a
    round being played otherwise than planned; every seat must still be
    filled, once."""
    members: tuple[int, ...] = ()
    rounds: tuple[int, ...] = ()

    @property
    def forceable(self) -> bool:
        return self.breach is not None


def schedule_violations(
    schedule: RoundRobinSchedule,
    member_ids: Collection[int],
    encounters: int,
    name: Callable[[int], str],
    check_colours: bool = True,
) -> list[ScheduleViolation]:
    """The rules *schedule* breaks for the members *member_ids*, who should
    each meet every other one *encounters* times (FIDE C.05): every member
    seated in every round, at most one rest each cycle, no pair meeting
    more than its share and, with *check_colours*, no member with the same
    colour three rounds in a row nor, in a double round-robin, with the
    same colour in both games against an opponent."""
    members = set(member_ids)
    member_count = len(members)
    if not schedule.fits(member_count, encounters):
        return [
            ScheduleViolation(
                None,
                _(
                    'The schedule does not fit the number of participants ({count}).'
                ).format(count=member_count),
            )
        ]
    violations = _seating_violations(schedule, members, name)
    seated = not violations
    violations.extend(_encounter_violations(schedule, members, encounters, name))
    if seated and check_colours:
        violations.extend(_colour_violations(schedule, members, encounters, name))
    return violations


def _breach(
    round_: int | None,
    breach: Breach,
    members: tuple[int, ...],
    rounds: tuple[int, ...],
    encounters: int,
    name: Callable[[int], str],
) -> ScheduleViolation:
    return ScheduleViolation(
        round_,
        describe_breach(breach, members, rounds, encounters, name),
        breach,
        members,
        rounds,
    )


def _seating_violations(
    schedule: RoundRobinSchedule,
    members: set[int],
    name: Callable[[int], str],
) -> list[ScheduleViolation]:
    violations: list[ScheduleViolation] = []
    for round_, schedule_round in sorted(schedule.rounds.items()):
        seated = [member for table in schedule_round.tables for member in table]
        if len(members) % 2 == 1 or schedule_round.rest is not None:
            seated.append(schedule_round.rest)
        if empty_seats := seated.count(None):
            violations.append(
                ScheduleViolation(
                    round_,
                    _('{count} seat(s) are not filled.').format(count=empty_seats),
                )
            )
        counts = Counter(member for member in seated if member is not None)
        for member, count in sorted(counts.items()):
            if member not in members:
                violations.append(
                    ScheduleViolation(
                        round_,
                        _('A participant who has left the tournament is seated.'),
                    )
                )
            elif count > 1:
                violations.append(
                    ScheduleViolation(
                        round_,
                        _('[{member}] is seated more than once.').format(
                            member=name(member)
                        ),
                    )
                )
        if not empty_seats:
            violations.extend(
                ScheduleViolation(
                    round_, _('[{member}] is not seated.').format(member=name(member))
                )
                for member in sorted(members - counts.keys())
            )
    return violations


def _encounter_violations(
    schedule: RoundRobinSchedule,
    members: set[int],
    encounters: int,
    name: Callable[[int], str],
) -> list[ScheduleViolation]:
    violations: list[ScheduleViolation] = []
    meetings: dict[frozenset[int], list[int]] = {}
    rests: dict[int, list[int]] = {}
    for round_, schedule_round in sorted(schedule.rounds.items()):
        for first, second in schedule_round.tables:
            if first is not None and second is not None and first != second:
                meetings.setdefault(frozenset((first, second)), []).append(round_)
        if schedule_round.rest is not None:
            rests.setdefault(schedule_round.rest, []).append(round_)
    for pair, rounds in sorted(meetings.items(), key=lambda item: item[1]):
        if len(rounds) > encounters and pair <= members:
            first, second = sorted(pair, key=name)
            violations.append(
                _breach(
                    rounds[encounters],
                    Breach.REPEATED_MEETING,
                    (first, second),
                    tuple(rounds),
                    encounters,
                    name,
                )
            )
    for member, rounds in sorted(rests.items(), key=lambda item: item[1]):
        if len(rounds) > encounters and member in members:
            violations.append(
                _breach(
                    rounds[encounters],
                    Breach.REPEATED_REST,
                    (member,),
                    tuple(rounds),
                    encounters,
                    name,
                )
            )
    complete = all(
        None not in table
        for schedule_round in schedule.rounds.values()
        for table in schedule_round.tables
    )
    if complete and not violations:
        for first, second in combinations(sorted(members, key=name), 2):
            if len(meetings.get(frozenset((first, second)), [])) < encounters:
                violations.append(
                    _breach(
                        None,
                        Breach.MISSING_MEETING,
                        (first, second),
                        (),
                        encounters,
                        name,
                    )
                )
    return violations


def _colour_runs(
    sequence: list[tuple[int, bool | None]],
) -> list[tuple[bool, list[int]]]:
    """The runs of rounds in which a member has the same colour, each
    with whether it is white; a round they do not play ends a run."""
    runs: list[tuple[bool, list[int]]] = []
    for round_, white in sequence:
        if white is None:
            continue
        if runs and runs[-1][0] == white and runs[-1][1][-1] == round_ - 1:
            runs[-1][1].append(round_)
        else:
            runs.append((white, [round_]))
    return runs


def _colour_violations(
    schedule: RoundRobinSchedule,
    members: set[int],
    encounters: int,
    name: Callable[[int], str],
) -> list[ScheduleViolation]:
    violations: list[ScheduleViolation] = []
    for member in sorted(members, key=name):
        for is_white, rounds in _colour_runs(schedule.colour_sequence(member)):
            if len(rounds) >= 3:
                violations.append(
                    _breach(
                        rounds[2],
                        Breach.WHITE_RUN if is_white else Breach.BLACK_RUN,
                        (member,),
                        tuple(rounds),
                        encounters,
                        name,
                    )
                )
    if encounters == 2:
        games: dict[frozenset[int], list[tuple[int, int, int]]] = {}
        for round_, schedule_round in sorted(schedule.rounds.items()):
            for white, black in schedule_round.tables:
                if white is not None and black is not None:
                    games.setdefault(frozenset((white, black)), []).append(
                        (round_, white, black)
                    )
        for (_round, first_white, black), (last_round, last_white, _black) in (
            pair_games for pair_games in games.values() if len(pair_games) == 2
        ):
            if first_white == last_white:
                violations.append(
                    _breach(
                        last_round,
                        Breach.SAME_COLOURS,
                        (first_white, black),
                        (last_round,),
                        encounters,
                        name,
                    )
                )
    return violations


@dataclass(frozen=True)
class ScheduleBreach:
    """A rule the saved schedule of a round-robin breaks, the schedule having
    been saved all the same after a round was played otherwise than planned.
    The log lists it for as long as the schedule breaks it."""

    violation: ScheduleViolation
    encounters: int
    date: None = None

    @property
    def round_(self) -> int:
        return self.violation.round or 1

    @property
    def label(self) -> str:
        return _('Round-robin schedule')

    @property
    def date_str(self) -> str:
        return ''

    def _describe(self, name: Callable[[int], str], locale: str | None = None) -> str:
        violation = self.violation
        assert violation.breach is not None
        return describe_breach(
            violation.breach,
            violation.members,
            violation.rounds,
            self.encounters,
            name,
            locale,
        )

    def summary(self, tournament: 'Tournament', locale: str | None = None) -> str:
        from data.pairings.engines import ScheduledRoundRobin

        engine = tournament.pairing_variation.engine
        assert isinstance(engine, ScheduledRoundRobin)
        return self._describe(engine.member_namer(tournament), locale)

    def trf_comment_for(self, tournament: 'Tournament') -> str:
        """The TRF comment, in the pairing numbers of today."""
        if tournament.is_team_tournament and tournament.pairing_system.paired_by_team:
            teams = tournament.event.teams_by_id

            def number(member: int) -> str:
                return str(teams[member].pairing_number or 0)

        else:
            players = tournament.tournament_players_by_id

            def number(member: int) -> str:
                return str(players[member].pairing_number or 0)

        return f'Schedule @ Round {self.round_}: {self._describe(number, "en")}'
