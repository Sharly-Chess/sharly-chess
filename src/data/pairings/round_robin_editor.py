"""The editing of a round-robin's schedule by the arbiter: a draft, changed
seat by seat, then saved once it keeps the round-robin rules. The games
already played cannot be changed; in a team round-robin, neither can the
rounds already paired, whose lineups are set."""

from typing import TYPE_CHECKING

from common.i18n import _
from data.pairings.engines import (
    RoundRobinPairingEngine,
    ScheduledRoundRobin,
    TeamRoundRobinPairingEngine,
    berger_order,
)
from data.pairings.round_robin_schedule import (
    REST,
    RoundRobinSchedule,
    ScheduleViolation,
    Seat,
    Table,
)
from database.sqlite.event.event_store import StoredBoard
from utils import Utils
from utils.enum import Result

if TYPE_CHECKING:
    from data.tournament import Tournament


class RoundRobinScheduleEditor:
    def __init__(
        self, tournament: 'Tournament', played_games_unlocked: bool = False
    ) -> None:
        engine = tournament.pairing_variation.engine
        assert isinstance(engine, ScheduledRoundRobin)
        self.tournament = tournament
        self.engine: ScheduledRoundRobin = engine
        self.played_games_unlocked = played_games_unlocked and not self.is_team
        """Whether the games already played can be changed, to set them as
        they were really played; the matches of a team round, whose lineups
        are set, cannot."""
        self.results_to_enter: list[int] = []
        """The rounds of the games changed whose result could not be kept,
        once the schedule is saved."""

    @property
    def is_team(self) -> bool:
        return isinstance(self.engine, TeamRoundRobinPairingEngine)

    @property
    def follows_berger_tables(self) -> bool:
        return self.engine.follows_berger_tables

    @property
    def must_edit(self) -> bool:
        """Whether the schedule is edited whatever the arbiter does: a
        custom round-robin has nothing else to be paired from, until its
        schedule is saved for the participants as they are and, for an
        individual one, its rounds paired."""
        if self.follows_berger_tables:
            return False
        schedule = self.engine.schedule(self.tournament)
        if schedule is None or not self.engine.schedule_fits(self.tournament, schedule):
            return True
        return not self.is_team and not self.tournament.has_pairings

    @property
    def can_start(self) -> bool:
        """Whether the arbiter can choose to edit the schedule: once the
        tournament is paired, or of a custom one at any time."""
        return self.tournament.has_pairings or not self.follows_berger_tables

    @property
    def editing(self) -> bool:
        return self.tournament.round_robin_schedule_draft is not None or self.must_edit

    @property
    def draft(self) -> RoundRobinSchedule:
        draft = self.tournament.round_robin_schedule_draft
        if draft is None:
            assert self.must_edit
            return self._initial_draft()
        if not draft.fits(self.member_count, self.engine.encounters):
            return self._refitted(draft)
        return draft

    @property
    def draft_empty(self) -> bool:
        """Whether nobody is seated yet in the schedule being edited."""
        draft = self.draft
        return not any(draft.seated(round_) for round_ in draft.rounds)

    @property
    def members_by_number(self) -> dict[int, int]:
        return self.engine.berger_numbered_members(self.tournament)

    @property
    def member_count(self) -> int:
        return len(self.members_by_number)

    def member_name(self, member: int) -> str:
        return self.engine.member_namer(self.tournament)(member)

    @property
    def member_options(self) -> list[tuple[int, str]]:
        """The members to choose from, by Berger number."""
        name = self.engine.member_namer(self.tournament)
        return [
            (member, f'{number}. {name(member)}')
            for number, member in sorted(self.members_by_number.items())
        ]

    # -------------------------------------------------------------------------
    # Draft lifecycle
    # -------------------------------------------------------------------------

    def start(self) -> None:
        """Start editing from the schedule the tournament is paired from,
        the pairings already made taking precedence."""
        self._set_draft(self._initial_draft())

    def cancel(self) -> None:
        self.tournament.set_round_robin_schedule(
            self.tournament.round_robin_schedule, None
        )

    def can_force(self, violations: list[ScheduleViolation]) -> bool:
        """Whether a schedule breaking the rules with *violations* can be
        saved all the same: once results are entered, a round may have been
        played otherwise than planned, but every seat must be filled once."""
        return (
            bool(violations)
            and self.tournament.has_results
            and all(violation.forceable for violation in violations)
        )

    def save(self, force: bool = False) -> str | None:
        """Save the draft, and pair the games of an individual round-robin
        from it. A tournament following the Berger tables whose schedule
        no longer does turns into a custom one. A schedule breaking the
        rules is saved only when *force* is given and it can be, the rules
        it breaks then being listed in the log. Returns why the draft cannot
        be saved."""
        draft = self.draft
        violations = self.violations(draft)
        if violations and not (force and self.can_force(violations)):
            return _('The schedule breaks the round-robin rules.')
        for round_ in draft.rounds:
            if self._changes_locked_games(draft, round_):
                return _(
                    'The schedule changes games already played in round {round}.'
                ).format(round=round_)
        tournament = self.tournament
        if self.follows_berger_tables and draft != self.engine.berger_schedule(
            tournament
        ):
            tournament.set_pairing_variation(self._custom_variation_id)
        tournament.set_round_robin_schedule(draft, None)
        if not self.is_team:
            self._pair_from(draft)
        return None

    @property
    def _custom_variation_id(self) -> str:
        from data.pairings.variations import (
            CustomRoundRobinVariation,
            CustomTeamRoundRobinVariation,
            DoubleCustomRoundRobinVariation,
            DoubleCustomTeamRoundRobinVariation,
        )

        double = self.engine.encounters == 2
        if self.is_team:
            if double:
                return DoubleCustomTeamRoundRobinVariation.static_id()
            return CustomTeamRoundRobinVariation.static_id()
        if double:
            return DoubleCustomRoundRobinVariation.static_id()
        return CustomRoundRobinVariation.static_id()

    def _set_draft(self, draft: RoundRobinSchedule) -> None:
        self.tournament.set_round_robin_schedule(
            self.tournament.round_robin_schedule, draft
        )

    def _refitted(self, schedule: RoundRobinSchedule) -> RoundRobinSchedule:
        """*schedule*, made for other participants, for those of the
        tournament: a newcomer to an odd field takes the rests; otherwise
        what still fits is kept."""
        members = self.members_by_number.values()
        return schedule.adapted(members) or schedule.resized(
            members, self.engine.encounters
        )

    def _initial_draft(self) -> RoundRobinSchedule:
        encounters = self.engine.encounters
        schedule = self.engine.schedule(self.tournament)
        if schedule is None:
            schedule = RoundRobinSchedule.empty(self.member_count, encounters)
        elif not self.engine.schedule_fits(self.tournament, schedule):
            schedule = self._refitted(schedule)
        else:
            schedule = schedule.copy()
        for round_ in schedule.rounds:
            if (
                paired := self.engine.paired_round(self.tournament, round_)
            ) is not None:
                schedule.rounds[round_] = paired
        return schedule

    # -------------------------------------------------------------------------
    # Changes
    # -------------------------------------------------------------------------

    def round_locked(self, round_: int) -> bool:
        """Whether no seat of *round_* can change: a team round once its
        matches are paired."""
        return self.is_team and bool(self.tournament.get_round_team_boards(round_))

    def locked_tables(self, round_: int) -> set[int]:
        """The tables of *round_* in the draft whose game has been played."""
        schedule_round = self.draft.rounds.get(round_)
        if schedule_round is None:
            return set()
        if self.round_locked(round_):
            return set(range(len(schedule_round.tables)))
        if self.played_games_unlocked:
            return set()
        played = self._played_pairs(round_)
        return {
            index
            for index, table in enumerate(schedule_round.tables)
            if table in played
        }

    def seat_options(
        self, round_: int
    ) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
        """The members who can take a seat of *round_*: those not seated
        yet in the round, then those seated, but not in a game played."""
        seated = self.draft.seated(round_)
        locked = self.locked_members(round_)
        options = [
            (member, label)
            for member, label in self.member_options
            if member not in locked
        ]
        return (
            [option for option in options if option[0] not in seated],
            [option for option in options if option[0] in seated],
        )

    def locked_members(self, round_: int) -> set[int]:
        """The members of *round_* who cannot change seats."""
        schedule_round = self.draft.rounds.get(round_)
        if schedule_round is None:
            return set()
        members = {
            member
            for index in self.locked_tables(round_)
            for member in schedule_round.tables[index]
            if member is not None
        }
        if self.round_locked(round_) and schedule_round.rest is not None:
            members.add(schedule_round.rest)
        return members

    def _played_pairs(self, round_: int) -> set[Table]:
        if self.is_team:
            return set()
        return {
            (board.stored_board.white_player_id, board.stored_board.black_player_id)
            for board in self.tournament.get_round_boards(round_)
            if board.stored_board.black_player_id is not None
            and board.result != Result.NO_RESULT
        }

    def _changes_locked_games(self, schedule: RoundRobinSchedule, round_: int) -> bool:
        schedule_round = schedule.rounds[round_]
        if self.round_locked(round_):
            return self.engine.paired_round(self.tournament, round_) != schedule_round
        if self.played_games_unlocked:
            return False
        return not self._played_pairs(round_) <= set(schedule_round.tables)

    def _seat_locked(self, round_: int, seat: Seat | None) -> bool:
        if seat is None:
            return False
        if self.round_locked(round_):
            return True
        table, _side = seat
        return table != REST and table in self.locked_tables(round_)

    def place(self, round_: int, seat: Seat, member: int | None) -> str | None:
        """Seat *member* at *seat* of *round_*, leaving empty the seat they
        had in the round. Returns why they cannot be."""
        draft = self.draft
        if round_ not in draft.rounds:
            return _('Round {round} is not in the schedule.').format(round=round_)
        if member is not None and member not in self.members_by_number.values():
            return _('This participant is not in the tournament.')
        if self._seat_locked(round_, seat) or (
            member is not None
            and self._seat_locked(round_, draft.seat_of(round_, member))
        ):
            return _('The games already played cannot be changed.')
        draft.place(round_, seat, member)
        self._set_draft(draft)
        return None

    def swap_colours(self, round_: int, table: int) -> str | None:
        draft = self.draft
        if self._seat_locked(round_, (table, 0)):
            return _('The games already played cannot be changed.')
        draft.swap_colours(round_, table)
        self._set_draft(draft)
        return None

    def fill_from_berger_tables(self) -> str | None:
        """Replace the draft with the Berger tables, unless games have
        already been played."""
        if any(self.locked_tables(round_) for round_ in self.draft.rounds):
            return _(
                'Games have already been played: '
                'the schedule cannot be filled from the Berger tables.'
            )
        self._set_draft(self.engine.berger_schedule(self.tournament))
        return None

    def clear(self) -> None:
        """Empty every seat whose game has not been played."""
        draft = self.draft
        for round_, schedule_round in draft.rounds.items():
            locked = self.locked_tables(round_)
            if self.round_locked(round_):
                continue
            schedule_round.tables = [
                table if index in locked else (None, None)
                for index, table in enumerate(schedule_round.tables)
            ]
            schedule_round.rest = None
        self._set_draft(draft)

    # -------------------------------------------------------------------------
    # Checks
    # -------------------------------------------------------------------------

    def violations(
        self, schedule: RoundRobinSchedule | None = None
    ) -> list[ScheduleViolation]:
        return self.engine.schedule_violations(
            self.tournament, schedule if schedule is not None else self.draft
        )

    # -------------------------------------------------------------------------
    # Pairings
    # -------------------------------------------------------------------------

    def admit_newcomers(self) -> None:
        """Follow the players who joined an individual round-robin: they
        take the next Berger numbers, and the round count follows the field.
        A custom one paired before its first result is unpaired, its
        schedule going back to its editing."""
        tournament = self.tournament
        if self.is_team or tournament.has_results:
            return
        tournament.reset_player_derived_cache()
        self._number_newcomers()
        tournament.persist_automatic_rounds()
        if self.follows_berger_tables or not tournament.has_pairings:
            return
        for player in tournament.tournament_players:
            Utils.reset_cached_properties(player, 'pairings_by_round')
        tournament.board_operations.unpair(list(tournament.boards_by_id.values()))
        tournament.set_current_round(0)

    def _number_newcomers(self) -> None:
        """Give the players who joined the next Berger numbers, after those
        already set, whose order is kept."""
        from data.pairings.settings import BergerNumbersSetting

        tournament = self.tournament
        if not BergerNumbersSetting.is_set(tournament):
            return
        numbers = {
            player_id: number
            for number, player_id in enumerate(berger_order(tournament), 1)
        }
        if numbers == BergerNumbersSetting.from_stored_value(
            tournament.stored_pairing_settings[BergerNumbersSetting.static_id()]
        ):
            return
        tournament.update_pairing_settings(
            tournament.stored_pairing_settings
            | {
                BergerNumbersSetting.static_id(): BergerNumbersSetting.to_stored_value(
                    numbers
                )
            }
        )

    def _pair_from(self, schedule: RoundRobinSchedule) -> None:
        """Make the boards of every round follow *schedule*, keeping the
        games already played."""
        tournament = self.tournament
        engine = self.engine
        assert isinstance(engine, RoundRobinPairingEngine)
        operations = tournament.board_operations
        for round_, schedule_round in sorted(schedule.rounds.items()):
            wanted: list[tuple[int, int | None]] = [
                (white, black)
                for white, black in schedule_round.tables
                if white is not None and black is not None
            ]
            if schedule_round.rest is not None:
                wanted.append((schedule_round.rest, None))
            boards = tournament.get_round_boards(round_)
            existing = {
                (board.stored_board.white_player_id, board.stored_board.black_player_id)
                for board in boards
            }
            if existing == set(wanted):
                continue
            played = self._played_pairs(round_)
            if played:
                obsolete = [
                    board
                    for board in boards
                    if (
                        board.stored_board.white_player_id,
                        board.stored_board.black_player_id,
                    )
                    not in wanted
                ]
                missing = [pair for pair in wanted if pair not in existing]
            else:
                obsolete, missing = boards, wanted
            results = {
                player.id: pairing.result
                for board in obsolete
                if board.stored_board.black_player_id is not None
                and board.result != Result.NO_RESULT
                for player, pairing in (
                    (board.white_tournament_player, board.white_pairing),
                    (board.black_tournament_player, board.black_pairing),
                )
                if player is not None
            }
            operations.unpair(obsolete)
            indexes = iter(operations.available_indexes(round_))
            operations.create(
                [
                    StoredBoard(
                        id=None,
                        white_player_id=white,
                        black_player_id=black,
                        index=(
                            next(indexes, 0)
                            if black is not None
                            else len(schedule_round.tables)
                        ),
                    )
                    for white, black in missing
                ],
                round_,
                engine.pab_result,
            )
            if results:
                self._keep_results(round_, missing, results)
        if tournament.current_round == 0:
            tournament.set_current_round(1)

    def _keep_results(
        self,
        round_: int,
        pairs: list[tuple[int, int | None]],
        results: dict[int, Result],
    ) -> None:
        """Give the games of *pairs*, made in *round_* from games already
        played, the results their players had, when they agree; the others
        are left to enter again."""
        boards_by_pair = {
            (board.stored_board.white_player_id, board.stored_board.black_player_id): (
                board
            )
            for board in self.tournament.get_round_boards(round_)
        }
        for white, black in pairs:
            white_result = results.get(white)
            black_result = results.get(black) if black is not None else None
            if white_result is None and black_result is None:
                continue
            if (
                black is not None
                and white_result is not None
                and black_result == white_result.opposite_result
            ):
                self.tournament.add_result(boards_by_pair[white, black], white_result)
            elif round_ not in self.results_to_enter:
                self.results_to_enter.append(round_)
