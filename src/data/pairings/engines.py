from abc import ABC, abstractmethod
import subprocess
from pathlib import Path
from typing import TextIO, TYPE_CHECKING

import trf
from packaging.version import Version

from common import TMP_DIR, BASE_DIR
from common.exception import PapiWebException
from common.logger import get_logger
from data.board import Board
from data.pairing import Pairing
from utils.enum import TrfType, Result, BoardColor

if TYPE_CHECKING:
    from data.tournament import Tournament

logger = get_logger()


class PairingEngine(ABC):
    @abstractmethod
    def _generate_boards(self, tournament: 'Tournament', round_: int) -> list[Board]:
        """Generate a list of boards matching all the pairings of tournament
        *tournament* at round *at_round*.
        Bye players should not be taken into account.
        If the pairing generation fails, raise a PapiWebException."""

    def generate_pairings(self, tournament: 'Tournament', round_: int):
        """Generate the pairings of the round *round_* for tournament *tournament*.
        Generated pairings are stored in the player pairings and in the Papi DB."""
        if round_ > tournament.current_round + 1:
            raise ValueError('Impossible to generate the pairings for a future round')
        boards = self._generate_boards(tournament, round_)
        for board in boards:
            white_player = board.white_player
            black_player = board.black_player
            if white_player:
                white_player.pairings[round_] = Pairing(
                    BoardColor.WHITE,
                    black_player.id if black_player else None,
                    board.result,
                )
            if black_player:
                black_player.pairings[round_] = Pairing(
                    BoardColor.BLACK,
                    white_player.id if white_player else None,
                    board.result,
                )
        tournament.update_round_pairings(round_)

    def pairings_diff(
        self, tournament: 'Tournament', round_: int
    ) -> list[tuple[Board | None, Board | None]]:
        """For round *round_* of tournament *tournament*, get the diff between
        the real pairings and the expected ones.
        Returns a list of real board / expected board when the boards differ."""
        if round_ > tournament.current_round:
            raise ValueError(f'No pairings for round {round_}')
        pairings_diff: list[tuple[Board | None, Board | None]] = []
        for player in tournament.players:
            tournament.set_player_points(player, before_round=round_)
        real_boards = tournament.build_boards(round_)
        expected_boards = sorted(
            self._generate_boards(tournament, round_), reverse=True
        )
        for i in range(len(real_boards)):
            real = real_boards[i]
            if i >= len(expected_boards):
                pairings_diff.append((real, None))
                continue
            expected = expected_boards[i]
            if (
                real.white_player_id != expected.white_player_id
                or real.black_player_id != expected.black_player_id
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

    def _generate_boards(self, tournament: 'Tournament', round_: int) -> list[Board]:
        """Generate the pairings of a tournament's round"""

        if not tournament.pairings_generation_allowed(round_):
            raise ValueError(
                f'Pairings generation not allowed for round {round_} '
                f'of tournament [{tournament.uniq_id}].'
            )

        pairings_dir = TMP_DIR / 'pairings'
        pairings_dir.mkdir(exist_ok=True)
        trf_file_path = pairings_dir / f'{tournament.uniq_id}.trfx'
        pairings_file_path = pairings_dir / f'{tournament.uniq_id}-pairings.txt'
        with open(trf_file_path, 'w', encoding='utf-8') as trf_file:
            trf.dump(
                trf_file, tournament.to_trf(TrfType.TRF_BX, after_round=round_ - 1)
            )
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
            raise PapiWebException(
                f'{tournament.log_prefix}round {round_} - Pairing generation '
                f'with BbpPairings failed with status {result.returncode}.\n'
                f'stdout: {result.stdout}\nstderr: {result.stderr}'
            )
        with open(pairings_file_path, encoding='utf-8') as pairing_file:
            return self._boards_from_file(pairing_file, tournament, round_)

    @classmethod
    def _boards_from_file(
        cls, file: TextIO, tournament: 'Tournament', round_: int
    ) -> list[Board]:
        boards: list[Board] = []
        file.readline()  # table_count
        for raw_pairing in file.readlines():
            (white_trf_id, black_trf_id) = map(int, raw_pairing.split(' '))
            white_player = tournament.players_by_trf_id[white_trf_id]
            if black_trf_id != cls.BYE_ID:
                boards.append(
                    Board(
                        white_player=white_player,
                        black_player=tournament.players_by_trf_id[black_trf_id],
                    )
                )
            elif not white_player.pairings[round_].next_round_bye:
                boards.append(
                    Board(
                        white_player=white_player,
                        result=Result.PAIRING_ALLOCATED_BYE,
                    )
                )
        return boards


class RoundRobinPairingEngine(PairingEngine):
    def _generate_boards(self, tournament: 'Tournament', round_: int) -> list[Board]:
        # TODO implement Round-Robin pairings
        raise NotImplementedError()
