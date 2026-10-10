import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import cache
from operator import attrgetter
from pathlib import Path
import tempfile
from typing import TextIO, TYPE_CHECKING

from common import TMP_DIR
from data.pairings.bbp_history import (
    TeamTournamentHistory,
    TournamentHistory,
    parse_bbp_checklist_text,
    parse_bbp_team_checklist_text,
)
from typing import override

from common.exception import PairingEngineError, SharlyChessException
from common.i18n import _
from common.logger import (
    get_logger,
)
from common.tool_installer import BbpPairingsInstaller
from data.board import Board
from data.pairings.round_robin_schedule import (
    RoundRobinSchedule,
    ScheduleRound,
    ScheduleViolation,
    Table,
    schedule_violations,
    single_cycle_round_count,
)
from data.pairings.settings import BergerNumbersSetting, ReverseLastRoundsSetting
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredBoard, StoredTeamBoard
from utils import Utils
from utils.enum import BoardColor, Result, TeamByeType

if TYPE_CHECKING:
    from data.teams.team import Team
    from data.teams.team_board import TeamBoard
    from data.tournament import Tournament

logger = get_logger()


class PairingEngine(ABC):
    @abstractmethod
    def _generate_stored_boards(
        self,
        tournament: 'Tournament',
        round_: int,
        partial_pairings: bool = False,
        prohibited_pairing_override: 'list | None' = None,
    ) -> list[StoredBoard]:
        """Generate a list of boards matching all the pairings of tournament
        *tournament* at round *at_round*.
        Bye players should not be taken into account.
        If the pairing generation fails, raise a SharlyChessException.
        If pairing is impossible, return an empty list.
        ``prohibited_pairing_override`` is the effective 260 line set for
        engines that honor prohibited pairings; engines with fixed pairing
        tables ignore it."""

    @abstractmethod
    def invalid_player_count_message(self, tournament: 'Tournament') -> str | None:
        """Returns an explanation message if the player count is invalid, or None if it is."""

    @property
    def pab_result(self) -> Result:
        return Result.PAIRING_ALLOCATED_BYE

    @property
    def honors_prohibited_pairings(self) -> bool:
        """Whether this engine can avoid prohibited pairings. Engines
        with fixed pairing tables (round-robins) cannot — every player
        meets every other, so prohibitions are never resolved for them."""
        return False

    @property
    def reorder_boards(self) -> bool:
        return False

    def team_seat_owner(
        self,
        tournament: 'Tournament',
        team_board: 'TeamBoard',
        board_index: int,
        physical_side: str,
    ) -> 'Team | None':
        """Which of the match's two teams owns physical side
        *physical_side* (``'white'`` / ``'black'``) of the board at
        *board_index*, before anyone is seated there.

        The colour pattern settles it: its *i*-th character is the
        colour team_a takes on board *i*."""
        if team_board.team_b is None:
            return None
        pattern = tournament.color_pattern or ''
        if 0 <= board_index < len(pattern):
            team_a_color = pattern[board_index]
        else:
            team_a_color = (
                BoardColor.WHITE.value
                if board_index % 2 == 0
                else BoardColor.BLACK.value
            )
        team_a_is_white = team_a_color == BoardColor.WHITE.value
        team_a_owns = (
            team_a_is_white if physical_side == 'white' else not team_a_is_white
        )
        return team_board.team_a if team_a_owns else team_board.team_b

    def team_board_slots(
        self,
        tournament: 'Tournament',
        team_board: 'TeamBoard',
        team_id: int,
    ) -> dict[int, int]:
        """Board index → the lineup slot of *team_id* seated on it.

        A team match seats each team's *i*-th player on board *i*, so
        the two numbers coincide. Systems whose table rotates one team
        around the other (a Scheveningen) override this."""
        n = tournament.team_player_count or 0
        return {index: index for index in range(n)}

    def generate_pairings(
        self,
        tournament: 'Tournament',
        round_: int,
        partial_pairings: bool = False,
    ) -> str:
        """Generate the pairings of the round *round_* for tournament *tournament*, returns an error message or an empty string on success."""
        if self.pairings_generation_disabled_message(tournament, round_):
            raise ValueError(
                f'Pairings generation not allowed for round {round_} '
                f'of tournament [{tournament.name}].'
            )
        # Resolve + freeze this round's prohibited pairings before
        # generating. The snapshot keeps the configured groups; the
        # (possibly relaxed) effective 260 set is fed to bbp as an
        # override. Complementary reuses the frozen snapshot groups.
        prohibited_override = None
        if not partial_pairings and self.honors_prohibited_pairings:
            error, prohibited_override = self._resolve_and_snapshot_prohibited(
                tournament, round_
            )
            if error:
                return error
        try:
            stored_boards = self._generate_stored_boards(
                tournament,
                round_,
                partial_pairings,
                prohibited_pairing_override=prohibited_override,
            )
        except PairingEngineError as e:
            logger.exception(e)
            if e.detail:
                return _('Pairing generation failed: {details}').format(
                    details=e.detail
                )
            return _('An error occurred. Consult the logs for more details.')
        except Exception as e:
            logger.exception(e)
            return _('An error occurred. Consult the logs for more details.')
        if not partial_pairings and len(stored_boards) == 0:
            return _('Pairing is not possible.')
        if self.reorder_boards:
            # Board order follows the players' virtual points, which are
            # only computed when a round is rendered. The pairing settings
            # feeding them (acceleration groups, initial scores) are saved
            # by the same request that generates the pairings, *after* that
            # render — so recompute here rather than sorting on values
            # predating the settings the pairing was made with.
            tournament.set_for_round(round_)
            boards = [
                Board(tournament, round_, stored_board)
                for stored_board in stored_boards
            ]
            available_indexes = tournament.board_operations.available_indexes(round_)
            for board in sorted(boards, reverse=True):
                board.index = available_indexes.pop(0)
        tournament.board_operations.create(stored_boards, round_, self.pab_result)
        return ''

    def _prohibited_pairing_feasible(
        self, tournament: 'Tournament', round_: int, prohibited_lines: list
    ) -> bool:
        """Can bbpPairings pair this round with the given 260 lines? Only
        meaningful for bbp-driven (Swiss) engines; others never relax
        (no soft prohibitions reach them) so the default refuses."""
        raise NotImplementedError

    def _resolve_and_snapshot_prohibited(
        self, tournament: 'Tournament', round_: int
    ) -> tuple[str, 'list | None']:
        """Freeze this round's prohibited-pairing groups as the snapshot
        (for display + 260 export), then resolve the *effective* 260 lines
        to feed bbpPairings: hard groups always, soft groups relaxed from
        the bottom of the standings if the full set is infeasible, and the
        groups avoided as bbpPairings' lowest-priority criterion as SCS
        lines.

        Returns ``(error, override_lines)``. ``error`` is non-empty when
        the hard constraints alone can't be paired (the round is left
        unpaired). ``override_lines`` is the relaxed 260 set to hand the
        real bbp run (``None`` when there's nothing prohibited)."""
        from data.prohibited_pairings import resolve_soft_protect_rank

        hard_groups, soft_groups, lowest_criterion_groups, rank_by_member = (
            tournament.prohibited_pairings.relaxation_inputs(after_round=round_ - 1)
        )
        if not hard_groups and not soft_groups and not lowest_criterion_groups:
            with EventDatabase(tournament.event.uniq_id, True) as database:
                tournament.prohibited_pairings.write_snapshot(round_, None, database)
            return '', None
        lowest_criterion_lines = tournament.prohibited_pairings.lowest_criterion_lines(
            lowest_criterion_groups, round_
        )

        protect_rank: int | None = None
        if soft_groups:
            bottom = max(rank_by_member.values(), default=0) + 1
            thresholds = sorted(
                {
                    rank_by_member.get(member, bottom)
                    for group in soft_groups
                    for member in group
                }
            )

            def feasible(cutoff: int) -> bool:
                lines = tournament.prohibited_pairings.applied_lines(
                    hard_groups, soft_groups, cutoff, rank_by_member, round_
                )
                return self._prohibited_pairing_feasible(
                    tournament, round_, lines + lowest_criterion_lines
                )

            protect_rank, hard_infeasible = resolve_soft_protect_rank(
                thresholds, feasible
            )
            if hard_infeasible:
                with EventDatabase(tournament.event.uniq_id, True) as database:
                    tournament.prohibited_pairings.write_snapshot(
                        round_, None, database
                    )
                return (
                    _('The prohibited pairings cannot be satisfied for this round.'),
                    None,
                )

        with EventDatabase(tournament.event.uniq_id, True) as database:
            tournament.prohibited_pairings.write_snapshot(
                round_, protect_rank, database
            )
        return '', tournament.prohibited_pairings.applied_lines(
            hard_groups,
            soft_groups,
            protect_rank if protect_rank is not None else 0,
            rank_by_member,
            round_,
        ) + lowest_criterion_lines

    def pairings_generation_disabled_message(
        self, tournament: 'Tournament', at_round: int
    ) -> str | None:
        """Determines if the pairings generation for round *at_round* is disabled.
        Returns an explanation message if it is, None if it is not."""
        return self.invalid_player_count_message(tournament)

    def expected_round_pairs(
        self, tournament: 'Tournament', round_: int, stored_prohibitions: bool = False
    ) -> set[tuple[int, int | None]]:
        """The pairs the engine makes for *round_*, as
        :func:`data.pairings.manual_pairing.round_pairs` reads them. With
        *stored_prohibitions*, the prohibited pairings are those stored for
        the round, as imported, rather than worked out again. Raises a
        :class:`SharlyChessException` when the engine fails."""
        prohibited_override = (
            None
            if stored_prohibitions
            else self._expected_prohibited_override(tournament, round_)
        )
        tournament.set_for_round(round_)
        return {
            (stored_board.white_player_id, stored_board.black_player_id)
            for stored_board in self._generate_stored_boards(
                tournament, round_, prohibited_pairing_override=prohibited_override
            )
            if stored_board.white_player_id is not None
        }

    def _expected_prohibited_override(
        self, tournament: 'Tournament', round_: int
    ) -> 'list | None':
        if not self.honors_prohibited_pairings:
            return None
        error, prohibited_override = self._resolve_and_snapshot_prohibited(
            tournament, round_
        )
        if error:
            raise SharlyChessException(error)
        return prohibited_override

    def pairings_diff(
        self,
        tournament: 'Tournament',
        round_: int,
        ignore_order: bool = False,
        expected_stored_boards: list[StoredBoard] | None = None,
    ) -> list[tuple[Board | None, Board | None]]:
        """For round *round_* of tournament *tournament*, get the diff between
        the real pairings and the expected ones.
        Returns a list of real board / expected board when the boards differ."""
        if not tournament.round_has_pairings(round_):
            raise ValueError(f'No pairings for round {round_}')
        pairings_diff: list[tuple[Board | None, Board | None]] = []
        tournament.set_for_round(round_)
        real_boards = tournament.get_round_boards(round_)

        if ignore_order:
            real_boards = sorted(real_boards, reverse=True)
        if expected_stored_boards is None:
            expected_stored_boards = self._generate_stored_boards(tournament, round_)
        expected_boards = sorted(
            (
                Board(tournament, round_, stored_board)
                for stored_board in expected_stored_boards
            ),
            key=None if ignore_order or self.reorder_boards else attrgetter('index'),
            reverse=ignore_order or self.reorder_boards,
        )
        for i in range(len(real_boards)):
            real = real_boards[i]
            if i >= len(expected_boards):
                pairings_diff.append((real, None))
                continue
            expected = expected_boards[i]
            real_black_id = getattr(real.black_tournament_player, 'id', None)
            expected_black_id = getattr(expected.black_tournament_player, 'id', None)
            if (
                real.white_tournament_player.id != expected.white_tournament_player.id
                or real_black_id != expected_black_id
            ):
                pairings_diff.append((real, expected))
        pairings_diff.extend(
            (None, expected_boards[i])
            for i in range(len(real_boards), len(expected_boards))
        )
        return pairings_diff


class BbpPairings(PairingEngine):
    BYE_ID = 0

    @property
    def honors_prohibited_pairings(self) -> bool:
        return True

    @property
    def executable_path(self) -> Path:
        return BbpPairingsInstaller().executable_path

    @property
    def reorder_boards(self) -> bool:
        return True

    def invalid_player_count_message(self, tournament: 'Tournament') -> str | None:
        if tournament.player_count <= tournament.rounds:
            return _(
                'Pairings generation not allowed if '
                'there are fewer players than rounds.'
            )
        return None

    def pairings_generation_disabled_message(
        self, tournament: 'Tournament', at_round: int
    ) -> str | None:
        if message := super().pairings_generation_disabled_message(
            tournament, at_round
        ):
            return message
        if any(
            not tournament.is_round_finished(round_) for round_ in range(1, at_round)
        ):
            return _(
                'Pairings generation not allowed if previous rounds have '
                'missing results, players to pair or absent players.'
            )
        if tournament.has_acceleration_beyond_last_round():
            return _(
                'Pairings generation not allowed while an acceleration rule '
                'extends past the last round. Adjust the acceleration settings '
                'or the number of rounds.'
            )
        return None

    def _generate_stored_boards(
        self,
        tournament: 'Tournament',
        round_: int,
        partial_pairings: bool = False,
        prohibited_pairing_override: 'list | None' = None,
    ) -> list[StoredBoard]:
        with tempfile.TemporaryDirectory() as tmpdir:
            pairings_dir: Path = Path(tmpdir)
            trf_file_path = pairings_dir / 'pairings-input.trfx'
            pairings_file_path = pairings_dir / 'pairings-output.txt'
            trf_tournament = tournament.to_trf(
                after_round=round_ - 1,
                for_engine=True,
                next_round_pairings_as_zpb=partial_pairings,
                prohibited_pairing_override=prohibited_pairing_override,
            )
            with open(trf_file_path, 'w', encoding='utf-8') as trf_file:
                from data.input_output.trf.trf_serializer import TrfSerializer

                TrfSerializer.dump(trf_file, trf_tournament)
            result = Utils.run_process(
                [
                    self.executable_path,
                    '--dutch',
                    trf_file_path,
                    '-p',
                    pairings_file_path,
                ],
                capture_output=True,
                encoding='utf-8',
            )
            # bbp opens the output file before it computes the matching, so a
            # failure (e.g. NO_VALID_PAIRING) leaves an *empty* file behind:
            # keying a full generation on the exit status rather than the
            # file's existence is what surfaces the reason instead of a bare
            # "not possible". Complementary (partial) runs stay lenient — an
            # unpaired remainder there is a normal outcome, reported by the
            # caller as "N players remain unpaired".
            full_generation_failed = result.returncode != 0 and not partial_pairings
            if full_generation_failed or not pairings_file_path.exists():
                detail = (result.stderr or result.stdout or '').strip()
                # Every bbp diagnostic embeds the input path and then the
                # reason as ``<verb> <trf_file_path>: <reason>``. The temp
                # path is meaningless to the operator, so keep only the part
                # after it (the reason itself may contain further colons).
                marker = f'{trf_file_path}: '
                if marker in detail:
                    detail = detail.split(marker, 1)[1].strip()
                raise PairingEngineError(
                    f'{tournament.log_prefix}round {round_} - Pairing generation '
                    f'with BbpPairings failed with status {result.returncode}.\n'
                    f'stdout: {result.stdout}\nstderr: {result.stderr}',
                    detail=detail,
                )
            try:
                bbp_tmp_dir = TMP_DIR / 'bbp-pairings'
                bbp_tmp_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy(
                    trf_file_path,
                    bbp_tmp_dir / f'{tournament.sanitized_name}-pairings-input.trfx',
                )
                shutil.copy(
                    pairings_file_path,
                    bbp_tmp_dir / f'{tournament.sanitized_name}-pairings-output.txt',
                )
            except PermissionError as e:
                logger.exception(
                    'Error logging the BbpPairings input / output files: %s', e
                )
            with open(pairings_file_path, encoding='utf-8') as pairing_file:
                return self._boards_from_file(
                    pairing_file, tournament, round_, partial_pairings
                )

    @classmethod
    def _boards_from_file(
        cls,
        file: TextIO,
        tournament: 'Tournament',
        round_: int,
        partial_pairings: bool,
    ) -> list[StoredBoard]:
        stored_boards: list[StoredBoard] = []
        file.readline()  # table_count
        has_pab = tournament.round_has_pab(round_)
        for raw_pairing in file.readlines():
            (white_trf_id, black_trf_id) = map(int, raw_pairing.split(' '))
            white_player = tournament.tournament_players_by_pairing_number[white_trf_id]
            if black_trf_id != cls.BYE_ID:
                black_player_id = tournament.tournament_players_by_pairing_number[
                    black_trf_id
                ].id
            elif not (
                white_player.pairings[round_].next_round_bye
                or (partial_pairings and has_pab)
            ):
                black_player_id = None
                has_pab = True
            else:
                continue
            stored_boards.append(
                StoredBoard(
                    id=None,
                    white_player_id=white_player.id,
                    black_player_id=black_player_id,
                    index=0,
                )
            )
        return stored_boards

    def get_history(
        self, tournament: 'Tournament', round_: int
    ) -> tuple[TournamentHistory, list[StoredBoard]]:
        with tempfile.TemporaryDirectory() as tmpdir:
            pairings_dir: Path = Path(tmpdir)
            trfx_file_path = pairings_dir / 'pairings-input.trfx'
            pairings_file_path = pairings_dir / 'pairings-output.txt'
            checklist_file_path = pairings_dir / 'checklist-output.txt'
            checklist_file_path.unlink(missing_ok=True)
            trf_tournament = tournament.to_trf(
                after_round=round_ - 1,
                for_engine=True,
                next_round_pairings_as_zpb=False,
            )
            with open(trfx_file_path, 'w', encoding='utf-8') as trf_file:
                from data.input_output.trf.trf_serializer import TrfSerializer

                TrfSerializer.dump(trf_file, trf_tournament)
            result = Utils.run_process(
                [
                    self.executable_path,
                    '--dutch',
                    trfx_file_path,
                    # The only way to get a checklist is to actually pair the round....
                    '-p',
                    pairings_file_path,
                    # Request the checklist
                    '-l',
                    checklist_file_path,
                ],
                capture_output=True,
                encoding='utf-8',
            )
            if not checklist_file_path.exists() or not pairings_file_path.exists():
                raise SharlyChessException(
                    f'{tournament.log_prefix}round {round_} - Pairing history '
                    f'from BbpPairings failed with status {result.returncode}.\n'
                    f'stdout: {result.stdout}\nstderr: {result.stderr}'
                )
            try:
                bbp_tmp_dir = TMP_DIR / 'bbp-pairings'
                bbp_tmp_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy(
                    trfx_file_path,
                    bbp_tmp_dir / f'{tournament.sanitized_name}-pairings-input.trfx',
                )
                shutil.copy(
                    pairings_file_path,
                    bbp_tmp_dir / f'{tournament.sanitized_name}-pairings-output.txt',
                )
                shutil.copy(
                    checklist_file_path,
                    bbp_tmp_dir / f'{tournament.sanitized_name}-checklist-output.txt',
                )
            except PermissionError as e:
                logger.exception(
                    'Error logging the BbpPairings input / output files: %s', e
                )
            with open(checklist_file_path, encoding='utf-8') as file:
                text_content = file.read()
                history_data = parse_bbp_checklist_text(text_content)

            with open(pairings_file_path, encoding='utf-8') as pairing_file:
                boards = self._boards_from_file(pairing_file, tournament, round_, False)

            return history_data, boards

    def _prohibited_pairing_feasible(
        self, tournament: 'Tournament', round_: int, prohibited_lines: list
    ) -> bool:
        try:
            boards = self._generate_stored_boards(
                tournament,
                round_,
                partial_pairings=False,
                prohibited_pairing_override=prohibited_lines,
            )
        except Exception:
            return False
        return len(boards) > 0


def berger_order(tournament: 'Tournament') -> list[int]:
    """The players of *tournament* in the order of the Berger numbers set:
    those of players who have left since are dropped, and players without
    one follow, by starting rank."""
    players = tournament.tournament_players_by_id
    numbers: dict[int, int] = {}
    if BergerNumbersSetting.is_set(tournament):
        numbers = BergerNumbersSetting.from_stored_value(
            tournament.stored_pairing_settings[BergerNumbersSetting.static_id()]
        )
    ordered = [
        player_id
        for _number, player_id in sorted(
            (number, player_id)
            for player_id, number in numbers.items()
            if player_id in players
        )
    ]
    numbered = set(ordered)
    return ordered + [
        player.id
        for player in tournament.tournament_players_by_starting_rank.values()
        if player.id not in numbered
    ]


class ScheduledRoundRobin(ABC):
    """The schedule a round-robin, of players or of teams, is paired from:
    the one saved for the tournament or, without one, the Berger tables
    when the variation follows them."""

    @property
    @abstractmethod
    def encounters(self) -> int:
        """How many times two members meet in the tournament."""

    @property
    def follows_berger_tables(self) -> bool:
        return True

    @abstractmethod
    def berger_numbered_members(self, tournament: 'Tournament') -> dict[int, int]:
        """The ids of the members of *tournament* by Berger number."""

    @abstractmethod
    def member_namer(self, tournament: 'Tournament') -> Callable[[int], str]:
        """The name of a member of *tournament* from their id."""

    def berger_schedule(self, tournament: 'Tournament') -> RoundRobinSchedule:
        return RoundRobinSchedule.berger(
            self.berger_numbered_members(tournament),
            self.encounters,
            self.encounters == 2 and ReverseLastRoundsSetting.get_value(tournament),
        )

    @abstractmethod
    def paired_tables(
        self, tournament: 'Tournament', round_: int
    ) -> tuple[list[Table], list[int]]:
        """The pairs of *round_* as paired, and the members resting."""

    def paired_round(
        self, tournament: 'Tournament', round_: int
    ) -> ScheduleRound | None:
        """*round_* as paired, when it fits a round of the schedule."""
        tables, rests = self.paired_tables(tournament, round_)
        member_count = len(self.berger_numbered_members(tournament))
        if len(tables) != member_count // 2 or len(rests) != member_count % 2:
            return None
        return ScheduleRound(tables, rests[0] if rests else None)

    def paired_schedule(self, tournament: 'Tournament') -> RoundRobinSchedule | None:
        """The schedule of a tournament whose every round is paired."""
        member_count = len(self.berger_numbered_members(tournament))
        rounds: dict[int, ScheduleRound] = {}
        for round_ in range(
            1, self.encounters * single_cycle_round_count(member_count) + 1
        ):
            if (paired_round := self.paired_round(tournament, round_)) is None:
                return None
            rounds[round_] = paired_round
        return RoundRobinSchedule(rounds)

    def schedule(self, tournament: 'Tournament') -> RoundRobinSchedule | None:
        """The Berger tables when the variation follows them; otherwise the
        saved schedule, or the pairings when every round is paired, as in a
        tournament imported with its games."""
        if self.follows_berger_tables:
            return self.berger_schedule(tournament)
        if (saved := tournament.round_robin_schedule) is not None:
            return saved
        return self.paired_schedule(tournament)

    def schedule_fits(
        self, tournament: 'Tournament', schedule: RoundRobinSchedule
    ) -> bool:
        """Whether *schedule* is one of the members of *tournament* as they
        are, rather than as they were when it was made."""
        members = self.berger_numbered_members(tournament).values()
        return schedule.members == set(members) and schedule.fits(
            len(members), self.encounters
        )

    def schedule_violations(
        self, tournament: 'Tournament', schedule: RoundRobinSchedule
    ) -> list[ScheduleViolation]:
        """The rules *schedule* breaks. The colours of the Berger tables
        are theirs to answer for, even when the last rounds of the first
        cycle are not reversed."""
        return schedule_violations(
            schedule,
            self.berger_numbered_members(tournament).values(),
            self.encounters,
            self.member_namer(tournament),
            check_colours=schedule != self.berger_schedule(tournament),
        )

    def schedule_message(self, tournament: 'Tournament') -> str | None:
        """Why *tournament* cannot be paired from its schedule."""
        schedule = self.schedule(tournament)
        if schedule is None:
            return _('The schedule of the tournament has not been defined.')
        if not self.schedule_fits(tournament, schedule):
            return _(
                'The participants have changed since the schedule was saved: '
                'it has to be edited.'
            )
        if self.schedule_violations(tournament, schedule):
            return _('The schedule of the tournament breaks the round-robin rules.')
        return None


class RoundRobinPairingEngine(ScheduledRoundRobin, PairingEngine):
    MIN_PLAYERS = 3

    @override
    @property
    def pab_result(self) -> Result:
        return Result.REST_GAME

    @property
    @abstractmethod
    def player_encounters(self) -> int:
        """Number of times 2 players play against each other in the tournament."""

    @property
    @override
    def encounters(self) -> int:
        return self.player_encounters

    @override
    def berger_numbered_members(self, tournament: 'Tournament') -> dict[int, int]:
        return dict(enumerate(berger_order(tournament), 1))

    @override
    def member_namer(self, tournament: 'Tournament') -> Callable[[int], str]:
        players = tournament.tournament_players_by_id
        return lambda player_id: players[player_id].full_name

    @override
    def paired_tables(
        self, tournament: 'Tournament', round_: int
    ) -> tuple[list[Table], list[int]]:
        tables: list[Table] = []
        rests: list[int] = []
        for board in tournament.get_round_boards(round_):
            white = board.stored_board.white_player_id
            black = board.stored_board.black_player_id
            if white is None:
                continue
            if black is None:
                rests.append(white)
            else:
                tables.append((white, black))
        return tables, rests

    @staticmethod
    def get_single_encounter_round_count(player_count: int) -> int:
        """Number of rounds necessary for each player to play against every other player."""
        return player_count if player_count % 2 == 1 else player_count - 1

    def get_round_count(self, player_count: int) -> int:
        """Number of rounds in the tournament."""
        return self.player_encounters * self.get_single_encounter_round_count(
            player_count
        )

    def invalid_player_count_message(self, tournament: 'Tournament') -> str | None:
        player_count = tournament.player_count
        if player_count < self.MIN_PLAYERS:
            return _(
                'Too few players to generate the pairings (minimum: {min}).'
            ).format(min=self.MIN_PLAYERS)
        round_count = self.get_round_count(player_count)
        if tournament.rounds != round_count:
            return _(
                'The round count is incompatible with the '
                'number of players (expected: {expected}).'
            ).format(expected=round_count)
        return self.schedule_message(tournament)

    def _generate_stored_boards(
        self,
        tournament: 'Tournament',
        round_: int,
        partial_pairings: bool = False,
        prohibited_pairing_override: 'list | None' = None,
    ) -> list[StoredBoard]:
        schedule = self.schedule(tournament)
        assert schedule is not None
        schedule_round = schedule.rounds[round_]
        stored_boards = [
            StoredBoard(
                id=None,
                white_player_id=white_player_id,
                black_player_id=black_player_id,
                index=index,
            )
            for index, (white_player_id, black_player_id) in enumerate(
                schedule_round.tables
            )
        ]
        if schedule_round.rest is not None:
            stored_boards.append(
                StoredBoard(
                    id=None,
                    white_player_id=schedule_round.rest,
                    black_player_id=None,
                    index=len(stored_boards),
                )
            )
        return stored_boards


class BergerPairingEngine(RoundRobinPairingEngine):
    @property
    def player_encounters(self) -> int:
        return 1

    @classmethod
    @cache
    def get_berger_table(cls, player_count: int) -> dict[int, list[tuple[int, int]]]:
        if player_count < 2:
            raise ValueError(f'There must be at least 2 players, got {player_count}')
        if player_count % 2 == 1:
            player_count += 1
        round_count = cls.get_single_encounter_round_count(player_count)
        previous_pairings = [
            (i + 1, player_count - i) for i in range(player_count // 2)
        ]
        berger_table = {1: previous_pairings}
        for round_ in range(2, round_count + 1):
            pairings = previous_pairings[:]
            if round_ % 2 == 1:
                pairings[0] = previous_pairings[-1][1], previous_pairings[0][0]
                pairings[-1] = previous_pairings[0][1], previous_pairings[1][0]
            else:
                pairings[0] = previous_pairings[0][1], previous_pairings[-1][1]
                pairings[-1] = previous_pairings[0][0], previous_pairings[1][0]
            for i in range(2, player_count // 2):
                pairings[-i] = previous_pairings[i - 1][1], previous_pairings[i][0]
            berger_table[round_] = pairings
            previous_pairings = pairings
        return berger_table


class DoubleBergerPairingEngine(BergerPairingEngine):
    @property
    def player_encounters(self) -> int:
        return 2

    @staticmethod
    def source_round(
        round_: int, single_rounds: int, reverse_last_rounds: bool
    ) -> tuple[int, bool]:
        """The Berger table round that round *round_* of a double
        round-robin plays, and whether its colours are inverted.

        The first cycle follows the Berger table and the second follows
        it again from round 1 with colours inverted. With
        *reverse_last_rounds*, the last two rounds of the first cycle are
        played in reverse order so that no one plays the same colour
        three times in a row (FIDE Handbook C.05 Annex 1). That needs at
        least three rounds per cycle."""
        if round_ > single_rounds:
            return (round_ % (single_rounds + 1)) + 1, True
        if reverse_last_rounds and single_rounds >= 3:
            if round_ == single_rounds - 1:
                return round_ + 1, False
            if round_ == single_rounds:
                return round_ - 1, False
        return round_, False


class CustomRoundRobinPairingEngine(RoundRobinPairingEngine):
    """A single round-robin paired from the schedule the arbiter defines."""

    @property
    def player_encounters(self) -> int:
        return 1

    @property
    @override
    def follows_berger_tables(self) -> bool:
        return False


class DoubleCustomRoundRobinPairingEngine(CustomRoundRobinPairingEngine):
    @property
    def player_encounters(self) -> int:
        return 2


def _team_ui_sort_key(team: 'Team') -> tuple[float, str]:
    """Sort key matching the team-admin UI:
    ``(pairing_number or ∞, name.lower())``. Shared by the pairing
    engines and the TRF export so the TPN order
    bbpPairings sees on TRF26 records matches what the user reorders
    on screen."""
    return (
        team.pairing_number if team.pairing_number is not None else float('inf'),
        team.name.lower(),
    )


class TeamPairingEngine(PairingEngine, ABC):
    """Shared machinery for every engine pairing team against team. A
    concrete engine decides *which* teams play whom each round; this
    base persists the resulting ``team_board`` envelopes + individual
    boards using the teams' effective round lineups."""

    BYE_ID = 0

    @property
    def byes_unpaired_absent_teams(self) -> bool:
        """Whether a team not paired this round (and not checked in) is given
        an automatic zero-point-bye envelope. True for the fixed-schedule /
        Swiss systems where every team is expected each round; False for an
        elimination bracket, where an unpaired team is knocked out or waiting
        in the other bracket, not sitting out a round."""
        return True

    def _generate_stored_boards(
        self,
        tournament: 'Tournament',
        round_: int,
        partial_pairings: bool = False,
        prohibited_pairing_override: 'list | None' = None,
    ) -> list[StoredBoard]:
        raise NotImplementedError(
            f'{type(self).__name__} uses generate_pairings directly.'
        )

    @staticmethod
    def _teams_for_tournament(tournament: 'Tournament') -> list['Team']:
        """Teams attached to this tournament, ordered the same way the
        team-admin UI lists them: by ``pairing_number`` when set (lower
        first), then lower-cased name. Keeps TPN assignment matching
        what the user sees on screen."""
        teams = [
            team
            for team in tournament.event.sorted_teams
            if team.tournament_id == tournament.id
        ]
        return sorted(teams, key=_team_ui_sort_key)

    def _persist_team_round(
        self,
        tournament: 'Tournament',
        round_: int,
        team_pairs: list[tuple[int, int | None]],
        partial_pairings: bool = False,
    ) -> None:
        stored_boards: list[StoredBoard] = []
        with EventDatabase(tournament.event.uniq_id, True) as database:
            existing = tournament.stored_tournament.stored_team_boards_by_round.get(
                round_, []
            )
            if partial_pairings:
                # Complementary pairing: keep every existing envelope
                # (manual byes, real matches, PAB) and append only the
                # new pairs bbpPairings returned for previously
                # unpaired teams.
                kept: list[StoredTeamBoard] = list(existing)
                # Fill the lowest free index first so a manual pairing
                # reuses the hole left by an earlier unpairing instead of
                # always appending at the end.
                used_indexes = {stb.index for stb in existing if stb.index is not None}

                def _next_free_index() -> int:
                    index = 0
                    while index in used_indexes:
                        index += 1
                    used_indexes.add(index)
                    return index

                for team_a_id, team_b_id in team_pairs:
                    stb = StoredTeamBoard(
                        id=None,
                        tournament_id=tournament.id,
                        round_=round_,
                        team_a_id=team_a_id,
                        team_b_id=team_b_id,
                        index=_next_free_index(),
                    )
                    stb.id = database.add_stored_team_board(stb)
                    kept.append(stb)
                    stored_boards.extend(
                        self._team_match_stored_boards(tournament, stb)
                    )
                tournament.stored_tournament.stored_team_boards_by_round[round_] = kept
        if partial_pairings:
            tournament.clear_team_cache()
            tournament.board_operations.create(stored_boards, round_, self.pab_result)
            return
        with EventDatabase(tournament.event.uniq_id, True) as database:
            existing = tournament.stored_tournament.stored_team_boards_by_round.get(
                round_, []
            )
            # Preserve manually-marked bye envelopes (HPB / FPB / ZPB)
            # across re-pairing; bbpPairings already excluded those
            # teams via 240 records, so its output won't reference them.
            manual_byes = [
                stb
                for stb in existing
                if stb.team_b_id is None
                and stb.bye_type in TeamByeType.manual_bye_types()
            ]
            manual_bye_team_ids = {stb.team_a_id for stb in manual_byes}
            # Drop everything else, then re-add manual byes + new pairs.
            database.delete_stored_team_boards_for_round(tournament.id, round_)
            tournament.stored_tournament.stored_team_boards_by_round.pop(round_, None)
            # Display order mirrors individual mode (board.py:__lt__):
            # strongest match first, PAB envelopes last. "Strength" of
            # a match is its stronger team's (MP, GP) tuple followed
            # by its weaker team's; for a PAB envelope (no team_b) we
            # demote the whole tuple to sort last. All else equal, the
            # user-curated TPN (set by drag-drop in the teams tab) is
            # the tie-breaker — lower TPN ranks higher.
            # Order matches by standings entering the round (exclude any
            # results already entered for the round being paired).
            standings_by_team_id = {
                row.team.id: row.score(tournament.primary_score)
                for row in tournament.team_standings(after_round=round_ - 1)
            }

            def _tpn_or_inf(team_id: int) -> float:
                team_ = tournament.event.teams_by_id.get(team_id)
                pn = team_.pairing_number if team_ is not None else None
                return float(pn) if pn is not None else float('inf')

            def _pair_sort_key(
                pair: tuple[int, int | None],
            ) -> tuple[int, float, float, float]:
                """Returns the sort key to use to sort the pair for table numbering, as a tuple.
                - 0. 0 for PAB, 1 otherwise
                - 1. the higher primary score
                - 2. the lower primary score
                - 3. the lowest pairing number of the high ranked team
                """
                a_id, b_id = pair
                if b_id is None:
                    return 0, 0.0, 0.0, -_tpn_or_inf(a_id)
                a = standings_by_team_id.get(a_id, 0.0)
                b = standings_by_team_id.get(b_id, 0.0)
                a_tpn, b_tpn = _tpn_or_inf(a_id), _tpn_or_inf(b_id)
                # The stronger side has the better standing; on a tie
                # (e.g. round 1, everyone on 0) the lower TPN is stronger
                # — NOT whichever side happens to be team_a (white). So
                # rank by (standing, -TPN) and compare the full key.
                if (a, -a_tpn) >= (b, -b_tpn):
                    stronger, weaker = a, b
                    stronger_tpn = a_tpn
                else:
                    stronger, weaker = b, a
                    stronger_tpn = b_tpn
                # Negate TPNs so that ``reverse=True`` (which makes
                # larger keys come first) puts the lower TPN first.
                return 1, stronger, weaker, -stronger_tpn

            if self.reorder_boards:
                # Swiss: table order follows match strength (strongest
                # match on table 1, PAB last).
                sorted_pairs = sorted(team_pairs, key=_pair_sort_key, reverse=True)
            else:
                # Round-robin: the Berger table already fixes the table
                # (échiquier) order for every round, so keep it verbatim
                # — only demote the PAB envelope to the last table.
                sorted_pairs = [p for p in team_pairs if p[1] is not None] + [
                    p for p in team_pairs if p[1] is None
                ]
            paired_team_ids = {
                team_id
                for pair in sorted_pairs
                for team_id in pair
                if team_id is not None
            }

            kept = []
            # Real / PAB matches own the table numbers 0…d-1, exactly
            # like individual boards. Hidden byes (HPB / FPB / ZPB) are
            # placed *after* them so they never consume a table number.
            for index, (team_a_id, team_b_id) in enumerate(sorted_pairs):
                stb = StoredTeamBoard(
                    id=None,
                    tournament_id=tournament.id,
                    round_=round_,
                    team_a_id=team_a_id,
                    team_b_id=team_b_id,
                    index=index,
                )
                stb.id = database.add_stored_team_board(stb)
                kept.append(stb)
                stored_boards.extend(self._team_match_stored_boards(tournament, stb))
            # Hidden byes (HPB / FPB / ZPB) hold a NULL index — they
            # don't occupy a table number.
            for bye_stb in manual_byes:
                new_stb = StoredTeamBoard(
                    id=None,
                    tournament_id=tournament.id,
                    round_=round_,
                    team_a_id=bye_stb.team_a_id,
                    team_b_id=None,
                    index=None,
                    bye_type=bye_stb.bye_type,
                )
                new_stb.id = database.add_stored_team_board(new_stb)
                kept.append(new_stb)
            # Absent teams (check_in=False) that aren't already on a
            # manual bye envelope get an auto-ZPB envelope for this
            # round. bbpPairings was instructed to skip them via 240
            # records, so its output won't reference them either. Teams
            # the schedule already paired this round (fixed-schedule
            # systems pair every team, present or not) keep their match —
            # no spurious ZPB on top of it. An elimination bracket never
            # byes an unpaired team: it is knocked out or waiting in the
            # other bracket, not sitting out.
            for team in tournament.teams if self.byes_unpaired_absent_teams else []:
                if (
                    team.check_in
                    or team.id in manual_bye_team_ids
                    or team.id in paired_team_ids
                ):
                    continue
                absent_stb = StoredTeamBoard(
                    id=None,
                    tournament_id=tournament.id,
                    round_=round_,
                    team_a_id=team.id,
                    team_b_id=None,
                    index=None,
                    bye_type=TeamByeType.ZPB,
                )
                absent_stb.id = database.add_stored_team_board(absent_stb)
                kept.append(absent_stb)
                manual_bye_team_ids.add(team.id)
            tournament.stored_tournament.stored_team_boards_by_round[round_] = kept
        tournament.clear_team_cache()
        tournament.board_operations.create(stored_boards, round_, self.pab_result)

    def _team_match_stored_boards(
        self,
        tournament: 'Tournament',
        stb: StoredTeamBoard,
    ) -> list[StoredBoard]:
        """Build StoredBoard entries for a team match. Board *i* seats
        each team's *i*-th player against the other's.
        Colors per board taken from *tournament.color_pattern* (a string of
        'W'/'B' characters, length = team_player_count, position i = team_a's
        color on board i). Falls back to WBWB... when no pattern is set.
        Team_b always gets the opposite color of team_a on each board.

        Overridden by systems whose table says who meets whom on each
        board rather than pairing the lineups straight across."""
        team_a = tournament.event.teams_by_id[stb.team_a_id]
        team_b = (
            tournament.event.teams_by_id[stb.team_b_id]
            if stb.team_b_id is not None
            else None
        )
        n = tournament.team_player_count or 0
        slots_a = team_a.effective_round_slots(stb.round_)
        slots_b = team_b.effective_round_slots(stb.round_) if team_b else [None] * n
        pattern = tournament.color_pattern or ''
        boards: list[StoredBoard] = []
        for board_index in range(n):
            player_a = slots_a[board_index] if board_index < len(slots_a) else None
            player_b = slots_b[board_index] if board_index < len(slots_b) else None
            if board_index < len(pattern):
                team_a_color_char = pattern[board_index]
            else:
                team_a_color_char = (
                    BoardColor.WHITE.value
                    if board_index % 2 == 0
                    else BoardColor.BLACK.value
                )
            team_a_is_white = team_a_color_char == BoardColor.WHITE.value
            if team_a_is_white:
                white_id = player_a.id if player_a else None
                black_id = player_b.id if player_b else None
            else:
                white_id = player_b.id if player_b else None
                black_id = player_a.id if player_a else None
            boards.append(
                StoredBoard(
                    id=None,
                    white_player_id=white_id,
                    black_player_id=black_id,
                    index=board_index,
                    team_board_id=stb.id,
                )
            )
        return boards


class TeamSwissEngine(TeamPairingEngine):
    """Team Swiss engine (FIDE C.04.6, TRF26-encoded).

    Builds a full TRF26 team file via :meth:`Tournament.to_trf` —
    including 310 team rosters, 192 colour-preference / score-config
    code, 352 board colour sequence, 362 match-points system and 320
    PAB overrides — and runs the in-tree ``bbpPairings --team``
    binary on it. The output is a list of ``(team_a_TPN, team_b_TPN)``
    matches for the round; this engine expands each match into per-
    board ``StoredBoard`` rows using each team's effective lineup for
    the round and the tournament's colour pattern."""

    @property
    def honors_prohibited_pairings(self) -> bool:
        return True

    @property
    def reorder_boards(self) -> bool:
        # Team Swiss orders tables by match strength (strongest match on
        # table 1); round-robins keep their fixed Berger table order.
        return True

    @property
    def executable_path(self) -> Path:
        return BbpPairingsInstaller().executable_path

    def invalid_player_count_message(self, tournament: 'Tournament') -> str | None:
        teams = self._teams_for_tournament(tournament)
        if len(teams) <= tournament.rounds:
            return _(
                'Pairings generation not allowed if there are fewer teams than rounds.'
            )
        n = tournament.team_player_count or 0
        if n <= 0:
            return _('Tournament has no team-player count configured.')
        return None

    def pairings_generation_disabled_message(
        self, tournament: 'Tournament', at_round: int
    ) -> str | None:
        if message := super().pairings_generation_disabled_message(
            tournament, at_round
        ):
            return message
        if any(
            not tournament.is_round_finished(round_) for round_ in range(1, at_round)
        ):
            return _(
                'Pairings generation not allowed if previous rounds have '
                'missing results, players to pair or absent players.'
            )
        return None

    @override
    def generate_pairings(
        self,
        tournament: 'Tournament',
        round_: int,
        partial_pairings: bool = False,
    ) -> str:
        if self.pairings_generation_disabled_message(tournament, round_):
            raise ValueError(
                f'Pairings generation not allowed for round {round_} '
                f'of tournament [{tournament.name}].'
            )
        # Resolve + freeze this round's prohibited pairings before
        # generating. The snapshot keeps the configured groups; the
        # (possibly relaxed) effective 260 set is fed to bbp as override.
        prohibited_override = None
        if not partial_pairings:
            error, prohibited_override = self._resolve_and_snapshot_prohibited(
                tournament, round_
            )
            if error:
                return error
        teams = self._teams_for_tournament(tournament)
        try:
            team_pairs = self._run_team_bbp(
                tournament,
                round_,
                teams,
                partial_pairings=partial_pairings,
                prohibited_pairing_override=prohibited_override,
            )
        except Exception as e:
            logger.exception(e)
            return _('An error occurred. Consult the logs for more details.')
        if not team_pairs and not partial_pairings:
            return _('Pairing is not possible.')
        self._persist_team_round(
            tournament, round_, team_pairs, partial_pairings=partial_pairings
        )
        return ''

    @override
    def expected_round_pairs(
        self, tournament: 'Tournament', round_: int, stored_prohibitions: bool = False
    ) -> set[tuple[int, int | None]]:
        return set(
            self._run_team_bbp(
                tournament,
                round_,
                self._teams_for_tournament(tournament),
                prohibited_pairing_override=(
                    None
                    if stored_prohibitions
                    else self._expected_prohibited_override(tournament, round_)
                ),
            )
        )

    def _prohibited_pairing_feasible(
        self, tournament: 'Tournament', round_: int, prohibited_lines: list
    ) -> bool:
        try:
            teams = self._teams_for_tournament(tournament)
            team_pairs = self._run_team_bbp(
                tournament,
                round_,
                teams,
                partial_pairings=False,
                prohibited_pairing_override=prohibited_lines,
            )
        except Exception:
            return False
        return bool(team_pairs)

    @staticmethod
    def _build_trf_id_map(teams: list['Team']) -> dict[int, int]:
        """Map team.id → TRF team pairing number (TPN, 1-based). Prefers
        the stored ``pairing_number``; falls back to canonical sort
        order so teams that haven't been ordered yet still get a
        unique TPN."""
        result: dict[int, int] = {}
        used: set[int] = set()
        # First pass: respect explicit pairing_number values.
        for team in teams:
            pn = team.pairing_number
            if pn is not None and pn not in used:
                result[team.id] = pn
                used.add(pn)
        # Second pass: fill in any teams without one using the lowest
        # unused TPN.
        next_tpn = 1
        for team in teams:
            if team.id in result:
                continue
            while next_tpn in used:
                next_tpn += 1
            result[team.id] = next_tpn
            used.add(next_tpn)
            next_tpn += 1
        return result

    def get_team_history(
        self, tournament: 'Tournament', round_: int
    ) -> TeamTournamentHistory:
        """The engine's own checklist for the round being paired: the score
        groups, colour preferences and bye eligibility it worked from, and
        the match it gave each team.

        Read from bbpPairings rather than recomputed here, so that what the
        arbiter is shown cannot drift from what the engine actually did —
        the individual modal has always worked this way.
        """
        from data.input_output.trf.trf_serializer import TrfSerializer

        trf_tournament = tournament.to_trf(after_round=round_ - 1, for_engine=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            pairings_dir = Path(tmpdir)
            trf_path = pairings_dir / 'team-pairings-input.trfx'
            out_path = pairings_dir / 'team-pairings-output.txt'
            checklist_path = pairings_dir / 'team-checklist-output.txt'
            with open(trf_path, 'w', encoding='utf-8') as file:
                TrfSerializer.dump(file, trf_tournament)
            result = Utils.run_process(
                [
                    self.executable_path,
                    '--team',
                    trf_path,
                    # The checklist is only written when a round is paired.
                    '-p',
                    out_path,
                    '-l',
                    checklist_path,
                ],
                capture_output=True,
                encoding='utf-8',
            )
            if not checklist_path.exists():
                raise SharlyChessException(
                    f'{tournament.log_prefix}round {round_} - Team pairing '
                    f'history from BbpPairings failed with status '
                    f'{result.returncode}.\n'
                    f'stdout: {result.stdout}\nstderr: {result.stderr}'
                )
            return parse_bbp_team_checklist_text(
                checklist_path.read_text(encoding='utf-8')
            )

    def _run_team_bbp(
        self,
        tournament: 'Tournament',
        round_: int,
        teams: list['Team'],
        partial_pairings: bool = False,
        prohibited_pairing_override: 'list | None' = None,
    ) -> list[tuple[int, int | None]]:
        from data.input_output.trf.trf_serializer import TrfSerializer

        trf_id_by_team_id = self._build_trf_id_map(teams)
        trf_tournament = tournament.to_trf(
            after_round=round_ - 1,
            for_engine=True,
            next_round_pairings_as_zpb=partial_pairings,
            prohibited_pairing_override=prohibited_pairing_override,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            pairings_dir = Path(tmpdir)
            trf_path = pairings_dir / 'team-pairings-input.trfx'
            out_path = pairings_dir / 'team-pairings-output.txt'
            with open(trf_path, 'w', encoding='utf-8') as f:
                TrfSerializer.dump(f, trf_tournament)
            result = Utils.run_process(
                [
                    self.executable_path,
                    '--team',
                    trf_path,
                    '-p',
                    out_path,
                ],
                capture_output=True,
                encoding='utf-8',
            )
            if not out_path.exists():
                raise SharlyChessException(
                    f'{tournament.log_prefix}round {round_} - Team pairing '
                    f'generation with BbpPairings failed with status '
                    f'{result.returncode}.\n'
                    f'stdout: {result.stdout}\nstderr: {result.stderr}'
                )
            try:
                bbp_tmp_dir = TMP_DIR / 'bbp-pairings'
                bbp_tmp_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy(
                    trf_path,
                    bbp_tmp_dir
                    / f'{tournament.sanitized_name}-team-pairings-input.trfx',
                )
                shutil.copy(
                    out_path,
                    bbp_tmp_dir
                    / f'{tournament.sanitized_name}-team-pairings-output.txt',
                )
            except PermissionError as e:
                logger.exception(
                    'Error logging the team BbpPairings input / output files: %s',
                    e,
                )
            team_by_trf_id = {trf_id_by_team_id[team.id]: team for team in teams}
            with open(out_path, encoding='utf-8') as f:
                return self._parse_team_pairs(f, team_by_trf_id)

    def _parse_team_pairs(
        self,
        file: TextIO,
        team_by_trf_id: dict[int, 'Team'],
    ) -> list[tuple[int, int | None]]:
        file.readline()  # team count
        pairs: list[tuple[int, int | None]] = []
        for line in file.readlines():
            tokens = line.split()
            if len(tokens) < 2:
                continue
            a_id, b_id = int(tokens[0]), int(tokens[1])
            team_a = team_by_trf_id.get(a_id)
            if team_a is None:
                continue
            team_b_id: int | None
            if b_id == self.BYE_ID:
                team_b_id = None
            else:
                team_b = team_by_trf_id.get(b_id)
                team_b_id = team_b.id if team_b is not None else None
            pairs.append((team_a.id, team_b_id))
        return pairs


class TeamRoundRobinPairingEngine(ScheduledRoundRobin, TeamPairingEngine):
    """Team round-robin shared logic: the matches of a round come from the
    schedule, and the team members are paired round by round, so lineups
    can change between rounds."""

    MIN_TEAMS = 2

    @property
    def pab_result(self) -> Result:
        return Result.REST_GAME

    @property
    @abstractmethod
    def team_encounters(self) -> int:
        """How many times each pair of teams meets (1 = Berger, 2 =
        Double Berger)."""

    @property
    @override
    def encounters(self) -> int:
        return self.team_encounters

    @override
    def berger_numbered_members(self, tournament: 'Tournament') -> dict[int, int]:
        return self._berger_to_team_id_map(self._teams_for_tournament(tournament))

    @override
    def member_namer(self, tournament: 'Tournament') -> Callable[[int], str]:
        teams = tournament.event.teams_by_id
        return lambda team_id: teams[team_id].name

    @override
    def paired_tables(
        self, tournament: 'Tournament', round_: int
    ) -> tuple[list[Table], list[int]]:
        tables: list[Table] = []
        rests: list[int] = []
        for team_board in tournament.get_round_team_boards(round_):
            stored_team_board = team_board.stored_team_board
            if stored_team_board.team_b_id is None:
                if stored_team_board.bye_type in TeamByeType.manual_bye_types():
                    continue
                rests.append(stored_team_board.team_a_id)
            else:
                tables.append(
                    (stored_team_board.team_a_id, stored_team_board.team_b_id)
                )
        return tables, rests

    @classmethod
    def get_single_encounter_round_count(cls, team_count: int) -> int:
        return team_count if team_count % 2 == 1 else team_count - 1

    def get_round_count(self, team_count: int) -> int:
        return self.team_encounters * self.get_single_encounter_round_count(team_count)

    def invalid_player_count_message(self, tournament: 'Tournament') -> str | None:
        teams = self._teams_for_tournament(tournament)
        if len(teams) < self.MIN_TEAMS:
            return _('Too few teams to generate the pairings (minimum: {min}).').format(
                min=self.MIN_TEAMS
            )
        expected = self.get_round_count(len(teams))
        if tournament.rounds != expected:
            return _(
                'The round count is incompatible with the number of '
                'teams (expected: {expected}).'
            ).format(expected=expected)
        n = tournament.team_player_count or 0
        if n <= 0:
            return _('Tournament has no team-player count configured.')
        # Incomplete rosters are allowed (as in team Swiss): a team with
        # fewer than ``n`` players just leaves a hole on the missing
        # boards, scored as a forfeit win for the present opponent.
        return self.schedule_message(tournament)

    def pairings_generation_disabled_message(
        self, tournament: 'Tournament', at_round: int
    ) -> str | None:
        if message := super().pairings_generation_disabled_message(
            tournament, at_round
        ):
            return message
        if any(
            not tournament.is_round_finished(round_) for round_ in range(1, at_round)
        ):
            return _(
                'Pairings generation not allowed if previous rounds have '
                'missing results.'
            )
        return None

    @staticmethod
    def _round_team_pairs(
        schedule: RoundRobinSchedule, round_: int
    ) -> list[tuple[int, int | None]]:
        """The (team_a_id, team_b_id) matches of *round_*, ``team_b_id``
        ``None`` for the team resting."""
        schedule_round = schedule.rounds[round_]
        team_pairs: list[tuple[int, int | None]] = [
            (team_a_id, team_b_id)
            for team_a_id, team_b_id in schedule_round.tables
            if team_a_id is not None
        ]
        if schedule_round.rest is not None:
            team_pairs.append((schedule_round.rest, None))
        return team_pairs

    def full_schedule(
        self, tournament: 'Tournament'
    ) -> dict[int, list[tuple[int, int | None]]]:
        """The matches of every round of the schedule, including those not
        paired yet, round → team-id pairs. A tournament configured with
        more rounds than the schedule has (the pairing button reports that
        mismatch) gets the schedule's rounds only."""
        teams = self._teams_for_tournament(tournament)
        if (
            len(teams) < self.MIN_TEAMS
            or (schedule := self.schedule(tournament)) is None
        ):
            return {}
        return {
            round_: self._round_team_pairs(schedule, round_)
            for round_ in sorted(schedule.rounds)
            if round_ <= tournament.rounds
        }

    @override
    def generate_pairings(
        self,
        tournament: 'Tournament',
        round_: int,
        partial_pairings: bool = False,
    ) -> str:
        if self.pairings_generation_disabled_message(tournament, round_):
            raise ValueError(
                f'Pairings generation not allowed for round {round_} '
                f'of tournament [{tournament.name}].'
            )
        schedule = self.schedule(tournament)
        assert schedule is not None
        try:
            team_pairs = self._round_team_pairs(schedule, round_)
        except Exception as e:
            logger.exception(e)
            return _('An error occurred. Consult the logs for more details.')
        if not team_pairs:
            return _('Pairing is not possible.')
        self._persist_team_round(tournament, round_, team_pairs)
        return ''

    @staticmethod
    def _berger_to_team_id_map(teams: list['Team']) -> dict[int, int]:
        """Berger number → team id. Berger numbers are assigned 1..N in
        the canonical ``_teams_for_tournament`` order."""
        return {i + 1: team.id for i, team in enumerate(teams)}


class TeamBergerEngine(TeamRoundRobinPairingEngine):
    """Single round-robin: each pair of teams meets once."""

    @property
    def team_encounters(self) -> int:
        return 1


class TeamDoubleBergerEngine(TeamBergerEngine):
    """Double round-robin: each pair of teams meets twice, colours
    inverted in the second half (FIDE Handbook C.05 Annex 1, applied
    at the team level via the same board-level colour pattern)."""

    @property
    def team_encounters(self) -> int:
        return 2


class CustomTeamRoundRobinEngine(TeamRoundRobinPairingEngine):
    """A single team round-robin paired from the schedule the arbiter
    defines."""

    @property
    def team_encounters(self) -> int:
        return 1

    @property
    @override
    def follows_berger_tables(self) -> bool:
        return False


class DoubleCustomTeamRoundRobinEngine(CustomTeamRoundRobinEngine):
    @property
    def team_encounters(self) -> int:
        return 2
