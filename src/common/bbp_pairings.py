import os
import subprocess
from pathlib import Path
from typing import TextIO

import trf

from common import TMP_DIR, BASE_DIR
from data.pairing import Pairing
from data.tournament import Tournament
from data.util import TrfType, Result, BoardColor


class BbpPairings:
    EXEMPT_ID = 0
    PROJECT_URL = 'https://github.com/BieremaBoyzProgramming/bbpPairings'
    VERSION = 'v5.0.1'
    WINDOWS_BUILD = 'x86_64-pc-windows.zip'
    LINUX_BUILD = 'x86_64-pc-linux.tar.gz'

    @property
    def is_installed(self) -> bool:
        return self.executable_path.exists()

    @property
    def executable_path(self) -> Path:
        return (
            BASE_DIR / 'resources' / f'bbpPairings-{self.VERSION}' / 'bbpPairings.exe'
        )

    def generate_pairings(self, tournament: Tournament):
        """Generate the pairings of a tournament's next round"""
        if tournament.finished or tournament.playing:
            raise ValueError(
                'Impossible to generate pairings '
                'if tournament is finished '
                'or if a round is ongoing.'
            )

        trf_file_path = TMP_DIR / 'tournament.trfx'
        pairings_file_path = TMP_DIR / 'pairings.txt'
        with open(trf_file_path, 'w') as trf_file:
            trf.dump(trf_file, tournament.to_trf(TrfType.PAIRING))
        try:
            subprocess.run(
                [
                    self.executable_path,
                    '--dutch',
                    trf_file_path,
                    '-p',
                    pairings_file_path,
                ],
                check=True,
            )
        finally:
            os.remove(trf_file_path)
        try:
            with open(pairings_file_path) as pairing_file:
                self._pairings_from_file(pairing_file, tournament)
        finally:
            os.remove(pairings_file_path)
        tournament.update_round_pairings(tournament.current_round + 1)

    def _pairings_from_file(self, file: TextIO, tournament: Tournament):
        file.readline()  # table_count
        next_round = tournament.current_round + 1
        for raw_pairing in file.readlines():
            (white_trf_id, black_trf_id) = map(int, raw_pairing.split(' '))
            white_player = tournament.players_by_trf_id[white_trf_id]
            if black_trf_id != self.EXEMPT_ID:
                black_player = tournament.players_by_trf_id[black_trf_id]
                white_player.pairings[next_round] = Pairing(
                    BoardColor.WHITE, black_player.id, Result.NO_RESULT
                )
                black_player.pairings[next_round] = Pairing(
                    BoardColor.BLACK, white_player.id, Result.NO_RESULT
                )
            else:
                white_player.pairings[next_round] = Pairing(
                    BoardColor.WHITE, 1, Result.PAIRING_ALLOCATED_BYE
                )
