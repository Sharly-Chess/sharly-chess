from abc import ABC, abstractmethod
import subprocess
from functools import cache
from operator import attrgetter
from pathlib import Path
from typing import TextIO, TYPE_CHECKING

import trf
from packaging.version import Version
from typing_extensions import override

from common import TMP_DIR, BASE_DIR
from common.exception import SharlyChessException
from common.i18n import _
from common.logger import get_logger
from data.board import Board
from data.pairings.settings import BergerNumbersSetting
from database.access.papi.papi_store import StoredBoard
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
        """Generate the pairings of the round *round_* for tournament *tournament*.
        Generated pairings are stored in the player pairings and in the Papi DB."""
        if self.pairings_generation_disabled_message(tournament, round_):
            raise ValueError(
                f'Pairings generation not allowed for round {round_} '
                f'of tournament [{tournament.uniq_id}].'
            )
        stored_boards = self._generate_stored_boards(
            tournament, round_, partial_pairings
        )

        boards = [
            Board(tournament, round_, stored_board) for stored_board in stored_boards
        ]
        pab_board = tournament.get_round_pab_board(round_)
        if pab_board:
            pab_board.stored_board.index += len(stored_boards)
        if self.reorder_boards:
            index_delta = max(
                [
                    board.index
                    for board in tournament.get_round_boards(round_)
                    if board.black_player
                ]
                or [0]
            )
            for index, board in enumerate(sorted(boards, reverse=True)):
                board.stored_board.index = index_delta + index
        next_board_id = max(tournament.boards_by_id.keys() or [0]) + 1

        for stored_board in stored_boards:
            id_ = next_board_id
            next_board_id += 1
            stored_board.id = id_
            board = Board(tournament, round_, stored_board)
            tournament.boards_by_id[id_] = board
            white_stored_pairing = board.white_pairing.stored_pairing
            white_stored_pairing.board_id = id_
            if black_pairing := board.black_pairing:
                black_pairing.stored_pairing.board_id = id_
            else:
                white_stored_pairing.result = self.pab_result.value
        tournament.update_round_pairings(round_)

    def pairings_generation_disabled_message(
        self, tournament: 'Tournament', at_round: int
    ) -> str | None:
        """Determines if the pairings generation for round *at_round* is disabled.
        Returns an explanation message if it is, None if it is not."""
        if tournament.check_in_open:
            return _('Pairings disabled while check-in is open.')
        return self.invalid_player_count_message(tournament)

    def pairings_diff(
        self, tournament: 'Tournament', round_: int, ignore_order: bool = False
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
        expected_boards = sorted(
            (
                Board(tournament, round_, stored_board)
                for stored_board in self._generate_stored_boards(tournament, round_)
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
    version: Version = Version('5.0.1')

    BYE_ID = 0

    bbp_pairings_dir: Path = BASE_DIR / 'tools' / 'bbpPairings'

    @property
    def executable_dir(self) -> Path:
        return self.bbp_pairings_dir / f'bbpPairings-v{self.version}'

    @property
    def executable_path(self) -> Path:
        return self.executable_dir / 'bbpPairings.exe'

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
        trf_file_path = pairings_dir / f'{tournament.uniq_id}.trfx'
        pairings_file_path = pairings_dir / f'{tournament.uniq_id}-pairings.txt'
        trf_tournament = tournament.to_trf(
            TrfType.TRF_BX,
            after_round=round_ - 1,
            next_round_pairings_as_zpb=partial_pairings,
        )
        with open(trf_file_path, 'w', encoding='utf-8') as trf_file:
            trf.dump(trf_file, trf_tournament)
        result = subprocess.run(
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
            white_player = tournament.players_by_starting_rank[white_trf_id]
            if black_trf_id != cls.BYE_ID:
                black_player_id = tournament.players_by_starting_rank[black_trf_id].id
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
