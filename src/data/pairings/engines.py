from abc import ABC, abstractmethod
from functools import cache
from operator import attrgetter
from pathlib import Path
from typing import TextIO, TYPE_CHECKING

from data.pairings.bbp_history import TournamentHistory, parse_bbp_checklist_text
import trf
from typing_extensions import override

from common import TMP_DIR
from common.exception import SharlyChessException
from common.i18n import _
from common.logger import (
    get_logger,
    print_interactive_info,
    print_interactive_error,
    print_interactive_success,
)
from common.tool_installer import BbpPairingsInstaller
from data.board import Board
from data.pairings.settings import BergerNumbersSetting
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredBoard
from utils import StaticUtils
from utils.enum import TrfType, Result

if TYPE_CHECKING:
    from data.tournament import Tournament

logger = get_logger()


class PairingEngine(ABC):
    @abstractmethod
    def _generate_stored_boards(
        self,
        tournament: 'Tournament',
        round_: int,
        partial_pairings: bool = False,
    ) -> list[StoredBoard]:
        """Generate a list of boards matching all the pairings of tournament
        *tournament* at round *at_round*.
        Bye players should not be taken into account.
        If the pairing generation fails, raise a SharlyChessException."""

    @abstractmethod
    def invalid_player_count_message(self, tournament: 'Tournament') -> str | None:
        """Returns an explanation message if the player count is invalid, or None if it is."""

    @property
    def pab_result(self) -> Result:
        return Result.PAIRING_ALLOCATED_BYE

    @property
    def reorder_boards(self) -> bool:
        return False

    def generate_pairings(
        self,
        tournament: 'Tournament',
        round_: int,
        partial_pairings: bool = False,
    ):
        """Generate the pairings of the round *round_* for tournament *tournament*."""
        if self.pairings_generation_disabled_message(tournament, round_):
            raise ValueError(
                f'Pairings generation not allowed for round {round_} '
                f'of tournament [{tournament.name}].'
            )
        stored_boards = self._generate_stored_boards(
            tournament, round_, partial_pairings
        )

        boards = [
            Board(tournament, round_, stored_board) for stored_board in stored_boards
        ]
        if self.reorder_boards:
            available_indexes = tournament.get_available_board_indexes(round_)
            for board in sorted(boards, reverse=True):
                board.stored_board.index = available_indexes.pop(0)
        tournament.create_boards(stored_boards, round_, self.pab_result)

    def pairings_generation_disabled_message(
        self, tournament: 'Tournament', at_round: int
    ) -> str | None:
        """Determines if the pairings generation for round *at_round* is disabled.
        Returns an explanation message if it is, None if it is not."""
        if tournament.check_in_open:
            return _('Pairings disabled while check-in is open.')
        return self.invalid_player_count_message(tournament)

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
            real_black_id = getattr(real.black_player, 'id', None)
            expected_black_id = getattr(expected.black_player, 'id', None)
            if (
                real.white_player.id != expected.white_player.id
                or real_black_id != expected_black_id
            ):
                pairings_diff.append((real, expected))
        for i in range(len(real_boards), len(expected_boards)):
            pairings_diff.append((None, expected_boards[i]))
        return pairings_diff


class BbpPairings(PairingEngine):
    BYE_ID = 0

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
                'Pairings generation not allowed if previous '
                'rounds have missing results or unpaired players.'
            )
        return None

    def _generate_stored_boards(
        self,
        tournament: 'Tournament',
        round_: int,
        partial_pairings: bool = False,
    ) -> list[StoredBoard]:
        pairings_dir = TMP_DIR / 'pairings'
        pairings_dir.mkdir(exist_ok=True, parents=True)
        trf_file_path = pairings_dir / f'{tournament.sanitized_name}.trfx'
        pairings_file_path = pairings_dir / f'{tournament.sanitized_name}-pairings.txt'
        pairings_file_path.unlink(missing_ok=True)
        trf_tournament = tournament.to_trf(
            TrfType.TRF_BX,
            after_round=round_ - 1,
            next_round_pairings_as_zpb=partial_pairings,
        )
        with open(trf_file_path, 'w', encoding='utf-8') as trf_file:
            trf.dump(trf_file, trf_tournament)
        result = StaticUtils.run_process(
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
        if not pairings_file_path.exists():
            raise SharlyChessException(
                f'{tournament.log_prefix}round {round_} - Pairing generation '
                f'with BbpPairings failed with status {result.returncode}.\n'
                f'stdout: {result.stdout}\nstderr: {result.stderr}'
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
            white_player = tournament.players_by_pairing_number[white_trf_id]
            if black_trf_id != cls.BYE_ID:
                black_player_id = tournament.players_by_pairing_number[black_trf_id].id
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
        pairings_dir = TMP_DIR / 'pairings'
        pairings_dir.mkdir(exist_ok=True, parents=True)
        trfx_file_path = pairings_dir / f'{tournament.sanitized_name}.trfx'
        pairings_file_path = pairings_dir / f'{tournament.sanitized_name}.trf'
        checklist_file_path = pairings_dir / f'{tournament.sanitized_name}-history.txt'
        checklist_file_path.unlink(missing_ok=True)
        trf_tournament = tournament.to_trf(
            TrfType.TRF_BX,
            after_round=round_ - 1,
            next_round_pairings_as_zpb=False,
        )
        with open(trfx_file_path, 'w', encoding='utf-8') as trf_file:
            trf.dump(trf_file, trf_tournament)
        result = StaticUtils.run_process(
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
        with open(checklist_file_path, 'r', encoding='utf-8') as file:
            text_content = file.read()
            history_data = parse_bbp_checklist_text(text_content)

        with open(pairings_file_path, encoding='utf-8') as pairing_file:
            boards = self._boards_from_file(pairing_file, tournament, round_, False)

        return history_data, boards

    def generate_tournament(
        self,
        trf_file_path: Path,
        random_seed: int | None = None,
        overwrite: bool = True,
    ) -> bool:
        """Generates a random tournament."""
        if not overwrite and trf_file_path.exists():
            print_interactive_info(f'TRF file {trf_file_path} previously generated.')
            return True
        trf_file_path.parent.mkdir(parents=True, exist_ok=True)
        cmd: list[str] = [
            str(self.executable_path),
            # dutch pairing
            '--dutch',
            # generate
            '-g',
            # output file
            '-o',
            str(trf_file_path),
        ]
        if random_seed:
            cmd += [
                # random seed
                '-s',
                str(random_seed),
            ]
        result = StaticUtils.run_process(
            cmd,
            capture_output=True,
            encoding='utf-8',
        )
        if result.returncode:
            print_interactive_error(
                f'BbpPairings random tournament generator failed with status {result.returncode}.'
            )
            print_interactive_error(f'stdout: {result.stdout}')
            print_interactive_error(f'stderr: {result.stderr}')
            return False
        print_interactive_success(
            f'BbpPairings random tournament generator created TRF file {trf_file_path}.'
        )
        return True

    @classmethod
    def _diff_display(
        cls, pairing_diff: list[tuple[Board | None, Board | None]]
    ) -> str:
        message = f'Real boards{"":<19}Expected boards\n'
        for real_board, expected_board in pairing_diff:
            message += f'{cls._board_display(real_board)}   {cls._board_display(expected_board)}\n'
        return message

    @staticmethod
    def _board_display(board: Board | None) -> str:
        if not board:
            return f'{"":<14} - {"":<10}'
        return (
            f'{board.index:>2}. {board.white_player.full_name:<10}'
            f' - {getattr(board.black_player, "full_name", ""):<10}'
        )

    def check_tournament(
        self,
        trf_input_file_path: Path,
        overwrite: bool = True,
    ) -> bool:
        """Checks a tournament."""
        result_file_path = trf_input_file_path.with_suffix('.txt')
        if result_file_path.exists():
            if not overwrite:
                print_interactive_info(
                    f'Result file {result_file_path} previously generated.'
                )
                with open(result_file_path, 'r') as f:
                    result = f.read()
                if result:
                    print_interactive_error(result)
                    return False
                else:
                    return True
            result_file_path.unlink()

        from data.input_output.tournament_importer_options import FileOption
        from data.input_output.tournament_importers import TrfTournamentImporter
        from data.loader import EventLoader

        event_uniq_id: str = 'dummy'
        EventDatabase(event_uniq_id).create()
        event = EventLoader().load_event(event_uniq_id)
        tournament_id = TrfTournamentImporter(
            [
                FileOption(trf_input_file_path),
            ]
        ).load_tournament(event)
        event = EventLoader().load_event(event_uniq_id)
        tournament = event.tournaments_by_id[tournament_id]
        for round_ in range(1, tournament.rounds + 1):
            if diff := tournament.pairing_variation.engine.pairings_diff(
                tournament,
                round_,
                ignore_order=True,
            ):
                result = f'Round {round_}: {len(diff)} differences\n\n{self._diff_display(diff)}'
                print_interactive_error(result)
                with open(result_file_path, 'w') as f:
                    f.write(result)
                return False
        print_interactive_error(
            f'Pairings are correct for the {tournament.rounds} rounds.'
        )
        result_file_path.touch()
        return True


class RoundRobinPairingEngine(PairingEngine, ABC):
    MIN_PLAYERS = 3

    @override
    @property
    def pab_result(self) -> Result:
        return Result.REST_GAME

    @property
    @abstractmethod
    def player_encounters(self) -> int:
        """Number of times 2 players play against each other in the tournament."""

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
        return None


class BergerPairingEngine(RoundRobinPairingEngine):
    @property
    def player_encounters(self) -> int:
        return 1

    def get_round_pairings(
        self, player_count: int, round_: int
    ) -> list[tuple[int, int]]:
        """Pairings for the round *round_* of a tournament of *player_count* players."""
        return self.get_berger_table(player_count)[round_]

    @classmethod
    @cache
    def get_berger_table(cls, player_count: int) -> dict[int, list[tuple[int, int]]]:
        if player_count <= 2:
            raise ValueError(f'There must be at least 3 players, got {player_count}')
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

    def _generate_stored_boards(
        self,
        tournament: 'Tournament',
        round_: int,
        partial_pairings: bool = False,
    ) -> list[StoredBoard]:
        stored_boards: list[StoredBoard] = []
        player_id_by_pairing_number = {
            pairing_number: player_id
            for player_id, pairing_number in BergerNumbersSetting.get_value(
                tournament
            ).items()
        }
        pairings = self.get_round_pairings(tournament.player_count, round_)
        for index, pairing in enumerate(pairings):
            white_player_id = player_id_by_pairing_number.get(pairing[0], None)
            black_player_id = player_id_by_pairing_number.get(pairing[1], None)
            if not white_player_id:
                assert black_player_id is not None
                white_player_id = black_player_id
                black_player_id = None

            stored_boards.append(
                StoredBoard(
                    id=None,
                    white_player_id=white_player_id,
                    black_player_id=black_player_id,
                    index=index,
                )
            )
        return stored_boards


class DoubleBergerPairingEngine(BergerPairingEngine):
    @property
    def player_encounters(self) -> int:
        return 2

    def get_round_pairings(
        self, player_count: int, round_: int
    ) -> list[tuple[int, int]]:
        """For double-round Berger, in the first half of the tournament
        the pairings follow the Berger table, and in the second half it
        follows it from round 1 but with black and white colors permuted.

        The only exception is for the 2 last rounds of the first half, which
        are supposed to be permuted to avoid players from tripling a color
        (see FIDE Handbook section C.05.Annex 1)."""
        berger_table = self.get_berger_table(player_count)
        berger_table_round_count = self.get_single_encounter_round_count(player_count)
        if round_ <= berger_table_round_count - 2:
            return berger_table[round_]
        if round_ == berger_table_round_count - 1:
            return berger_table[round_ + 1]
        if round_ == berger_table_round_count:
            return berger_table[round_ - 1]
        return [
            (black_player, white_player)
            for white_player, black_player in berger_table[
                (round_ % (berger_table_round_count + 1)) + 1
            ]
        ]
