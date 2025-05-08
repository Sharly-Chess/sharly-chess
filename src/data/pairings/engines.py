from abc import ABC, abstractmethod
import subprocess
from pathlib import Path
from typing import TextIO, TYPE_CHECKING

import trf
from packaging.version import Version

from common import TMP_DIR, BASE_DIR
from common.exception import PapiWebException
from common.i18n import _
from common.logger import get_logger
from data.board import Board
from data.pairing import Pairing
from data.pairings.settings import BergerNumbersSetting
from data.player import Player
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

    @abstractmethod
    def invalid_player_count_message(self, tournament: 'Tournament') -> str | None:
        """Returns an explanation message if the player count is invalid, or None if it is."""

    def generate_pairings(self, tournament: 'Tournament', round_: int):
        """Generate the pairings of the round *round_* for tournament *tournament*.
        Generated pairings are stored in the player pairings and in the Papi DB."""
        if self.pairings_generation_disabled_message(tournament, round_):
            raise ValueError(
                f'Pairings generation not allowed for round {round_} '
                f'of tournament [{tournament.uniq_id}].'
            )
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

    def pairings_generation_disabled_message(
        self, tournament: 'Tournament', at_round: int
    ) -> str | None:
        """Determines if the pairings generation for round *at_round* is disabled.
        Returns an explanation message if it is, None if it is not."""
        if tournament.check_in_open:
            return _('Pairings disabled while check-in is open.')
        if not tournament.are_pairing_settings_valid:
            return _('Settings must be configured before generating the pairings.')
        return self.invalid_player_count_message(tournament)

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

    def invalid_player_count_message(self, tournament: 'Tournament') -> str | None:
        """Returns an explanation message if the player count is invalid, or None if it is."""
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

    def _generate_boards(self, tournament: 'Tournament', round_: int) -> list[Board]:
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
            white_player = tournament.players_by_starting_rank[white_trf_id]
            if black_trf_id != cls.BYE_ID:
                boards.append(
                    Board(
                        white_player=white_player,
                        black_player=tournament.players_by_starting_rank[black_trf_id],
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


class BergerTables:
    """Tables defining pairings in the Berger system
    (FIDE handbook C.05.Annex 1: Details of Berger Table)"""

    BERGER_TABLE_4_PLAYERS: dict[int, list[tuple[int, int]]] = {
        1: [(1, 4), (2, 3)],
        2: [(4, 3), (1, 2)],
        3: [(2, 4), (3, 1)],
    }

    BERGER_TABLE_6_PLAYERS: dict[int, list[tuple[int, int]]] = {
        1: [(1, 6), (2, 5), (3, 4)],
        2: [(6, 4), (5, 3), (1, 2)],
        3: [(2, 6), (3, 1), (4, 5)],
        4: [(6, 5), (1, 4), (2, 3)],
        5: [(3, 6), (4, 2), (5, 1)],
    }

    BERGER_TABLE_8_PLAYERS: dict[int, list[tuple[int, int]]] = {
        1: [(1, 8), (2, 7), (3, 6), (4, 5)],
        2: [(8, 5), (6, 4), (7, 3), (1, 2)],
        3: [(2, 8), (3, 1), (4, 7), (5, 6)],
        4: [(8, 6), (7, 5), (1, 4), (2, 3)],
        5: [(3, 8), (4, 2), (5, 1), (6, 7)],
        6: [(8, 7), (1, 6), (2, 5), (3, 4)],
        7: [(4, 8), (5, 3), (6, 2), (7, 1)],
    }

    BERGER_TABLE_10_PLAYERS: dict[int, list[tuple[int, int]]] = {
        1: [(1, 10), (2, 9), (3, 8), (4, 7), (5, 6)],
        2: [(10, 6), (7, 5), (8, 4), (9, 3), (1, 2)],
        3: [(2, 10), (3, 1), (4, 9), (5, 8), (6, 7)],
        4: [(10, 7), (8, 6), (9, 5), (1, 4), (2, 3)],
        5: [(3, 10), (4, 2), (5, 1), (6, 9), (7, 8)],
        6: [(10, 8), (9, 7), (1, 6), (2, 5), (3, 4)],
        7: [(4, 10), (5, 3), (6, 2), (7, 1), (8, 9)],
        8: [(10, 9), (1, 8), (2, 7), (3, 6), (4, 5)],
        9: [(5, 10), (6, 4), (7, 3), (8, 2), (9, 1)],
    }

    BERGER_TABLE_12_PLAYERS: dict[int, list[tuple[int, int]]] = {
        1: [(1, 12), (2, 11), (3, 10), (4, 9), (5, 8), (6, 7)],
        2: [(12, 7), (8, 6), (9, 5), (10, 4), (11, 3), (1, 2)],
        3: [(2, 12), (3, 1), (4, 11), (5, 10), (6, 9), (7, 8)],
        4: [(12, 8), (9, 7), (10, 6), (11, 5), (1, 4), (2, 3)],
        5: [(3, 12), (4, 2), (5, 1), (6, 11), (7, 10), (8, 9)],
        6: [(12, 9), (10, 8), (11, 7), (1, 6), (2, 5), (3, 4)],
        7: [(4, 12), (5, 3), (6, 2), (7, 1), (8, 11), (9, 10)],
        8: [(12, 10), (11, 9), (1, 8), (2, 7), (3, 6), (4, 5)],
        9: [(5, 12), (6, 4), (7, 3), (8, 2), (9, 1), (10, 11)],
        10: [(12, 11), (1, 10), (2, 9), (3, 8), (4, 7), (5, 6)],
        11: [(6, 12), (7, 5), (8, 4), (9, 3), (10, 2), (11, 1)],
    }

    BERGER_TABLE_14_PLAYERS: dict[int, list[tuple[int, int]]] = {
        1: [(1, 14), (2, 13), (3, 12), (4, 11), (5, 10), (6, 9), (7, 8)],
        2: [(14, 8), (9, 7), (10, 6), (11, 5), (12, 4), (13, 3), (1, 2)],
        3: [(2, 14), (3, 1), (4, 13), (5, 12), (6, 11), (7, 10), (8, 9)],
        4: [(14, 9), (10, 8), (11, 7), (12, 6), (13, 5), (1, 4), (2, 3)],
        5: [(3, 14), (4, 2), (5, 1), (6, 13), (7, 12), (8, 11), (9, 10)],
        6: [(14, 10), (11, 9), (12, 8), (13, 7), (1, 6), (2, 5), (3, 4)],
        7: [(4, 14), (5, 3), (6, 2), (7, 1), (8, 13), (9, 12), (10, 11)],
        8: [(14, 11), (12, 10), (13, 9), (1, 8), (2, 7), (3, 6), (4, 5)],
        9: [(5, 14), (6, 4), (7, 3), (8, 2), (9, 1), (10, 13), (11, 12)],
        10: [(14, 12), (13, 11), (1, 10), (2, 9), (3, 8), (4, 7), (5, 6)],
        11: [(6, 14), (7, 5), (8, 4), (9, 3), (10, 2), (11, 1), (12, 13)],
        12: [(14, 13), (1, 12), (2, 11), (3, 10), (4, 9), (5, 8), (6, 7)],
        13: [(7, 14), (8, 6), (9, 5), (10, 4), (11, 3), (12, 2), (13, 1)],
    }

    BERGER_TABLE_16_PLAYERS: dict[int, list[tuple[int, int]]] = {
        1: [(1, 16), (2, 15), (3, 14), (4, 13), (5, 12), (6, 11), (7, 10), (8, 9)],
        2: [(16, 9), (10, 8), (11, 7), (12, 6), (13, 5), (14, 4), (15, 3), (1, 2)],
        3: [(2, 16), (3, 1), (4, 15), (5, 14), (6, 13), (7, 12), (8, 11), (9, 10)],
        4: [(16, 10), (11, 9), (12, 8), (13, 7), (14, 6), (15, 5), (1, 4), (2, 3)],
        5: [(3, 16), (4, 2), (5, 1), (6, 15), (7, 14), (8, 13), (9, 12), (10, 11)],
        6: [(16, 11), (12, 10), (13, 9), (14, 8), (15, 7), (1, 6), (2, 5), (3, 4)],
        7: [(4, 16), (5, 3), (6, 2), (7, 1), (8, 15), (9, 14), (10, 13), (11, 12)],
        8: [(16, 12), (13, 11), (14, 10), (15, 9), (1, 8), (2, 7), (3, 6), (4, 5)],
        9: [(5, 16), (6, 4), (7, 3), (8, 2), (9, 1), (10, 15), (11, 14), (12, 13)],
        10: [(16, 13), (14, 12), (15, 11), (1, 10), (2, 9), (3, 8), (4, 7), (5, 6)],
        11: [(6, 16), (7, 5), (8, 4), (9, 3), (10, 2), (11, 1), (12, 15), (13, 14)],
        12: [(16, 14), (15, 13), (1, 12), (2, 11), (3, 10), (4, 9), (5, 8), (6, 7)],
        13: [(7, 16), (8, 6), (9, 5), (10, 4), (11, 3), (12, 2), (13, 1), (14, 15)],
        14: [(16, 15), (1, 14), (2, 13), (3, 12), (4, 11), (5, 10), (6, 9), (7, 8)],
        15: [(8, 16), (9, 7), (10, 6), (11, 5), (12, 4), (13, 3), (14, 2), (15, 1)],
    }

    BERGER_TABLES: dict[int, dict[int, list[tuple[int, int]]]] = {
        4: BERGER_TABLE_4_PLAYERS,
        6: BERGER_TABLE_6_PLAYERS,
        8: BERGER_TABLE_8_PLAYERS,
        10: BERGER_TABLE_10_PLAYERS,
        12: BERGER_TABLE_12_PLAYERS,
        14: BERGER_TABLE_14_PLAYERS,
        16: BERGER_TABLE_16_PLAYERS,
    }

    @classmethod
    def table_from_player_count(
        cls, player_count: int
    ) -> dict[int, list[tuple[int, int]]]:
        return cls.BERGER_TABLES[
            player_count if player_count % 2 == 0 else player_count + 1
        ]


class BergerPairingEngine(PairingEngine):
    MIN_PLAYERS = 3
    MAX_PLAYERS = 16

    def invalid_player_count_message(self, tournament: 'Tournament') -> str | None:
        player_count = tournament.player_count
        if player_count < self.MIN_PLAYERS:
            return _(
                'Too few players to generate the pairings (minimum: {min})'
            ).format(min=self.MIN_PLAYERS)
        if player_count > self.MAX_PLAYERS:
            return _(
                'Too many players to generate the pairings (maximum: {max})'
            ).format(max=self.MAX_PLAYERS)
        expected_rounds = player_count if player_count % 2 == 1 else player_count - 1
        if tournament.rounds != expected_rounds:
            return _(
                'The round count is incompatible with the '
                'number of players (expected: {expected}).'
            ).format(expected=expected_rounds)
        return None

    @staticmethod
    def player_from_pairing_number(
        pairing_number: int, tournament: 'Tournament'
    ) -> Player | None:
        player_id = BergerNumbersSetting.get_value(tournament).get(pairing_number, None)
        if player_id:
            return tournament.players_by_id[player_id]
        return None

    def _generate_boards(self, tournament: 'Tournament', round_: int) -> list[Board]:
        boards: list[Board] = []
        round_pairings = BergerTables.table_from_player_count(tournament.player_count)[
            round_
        ]
        player_by_pairing_number = {
            pairing_number: tournament.players_by_id[player_id]
            for player_id, pairing_number in BergerNumbersSetting.get_value(
                tournament
            ).items()
        }
        for pairing in round_pairings:
            white_player = player_by_pairing_number.get(pairing[0], None)
            black_player = player_by_pairing_number.get(pairing[1], None)
            if not white_player or not black_player:
                board = Board(
                    white_player=white_player or black_player,
                    result=Result.PAIRING_ALLOCATED_BYE,
                )
            else:
                board = Board(
                    white_player=white_player,
                    black_player=black_player,
                )
            boards.append(board)
        return boards
