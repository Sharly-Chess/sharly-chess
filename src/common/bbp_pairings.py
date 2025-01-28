import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import TextIO

import requests
import trf

from common import TMP_DIR
from common.i18n import _
from common.logger import print_interactive_info, print_interactive_error
from data.pairing import Pairing
from data.tournament import Tournament
from data.util import TrfType, Result, BoardColor


class BbpPairings:
    EXEMPT_ID = 0
    PROJECT_URL = "https://github.com/BieremaBoyzProgramming/bbpPairings"
    VERSION = "v5.0.1"
    WINDOWS_BUILD = "x86_64-pc-windows.zip"
    LINUX_BUILD = "x86_64-pc-linux.tar.gz"

    @property
    def is_installed(self) -> bool:
        return os.path.exists(self._executable_path)

    @property
    def _executable_path(self) -> str:
        return os.path.join(
            TMP_DIR, f'bbpPairings-{self.VERSION}', 'bbpPairings.exe')

    @property
    def _build(self) -> str:
        return (
            self.WINDOWS_BUILD
            if platform.system() == 'Windows'
            else self.LINUX_BUILD)

    def check_installed(self) -> bool:
        """Check if BBP pairings is installed, and installs if not.
        returns True if BBP pairings is available after the call, False otherwise."""
        if self.is_installed:
            return True

        build_url = (
            f'{self.PROJECT_URL}/releases/download/{self.VERSION}/'
            f'bbpPairings-{self.VERSION}-{self._build}')
        target_dir = TMP_DIR
        archive_path = os.path.join(
            target_dir,
            "bbp_pairings.zip"
            if self._build == self.WINDOWS_BUILD
            else "bbp_pairings.tar.gz")
        print_interactive_info(_('Downloading BBP Pairings...'))
        try:
            response = requests.get(build_url)
            if response.status_code != 200:
                print_interactive_error(
                    _('Could not download [{url}], error code [{code}].').format(
                        url=build_url, code=response.status_code))
                return False
        except ConnectionError as ex:
            print_interactive_error(
                _('Could not download [{url}]: {ex}.').format(
                    url=build_url, ex=ex))
            return False
        Path(archive_path).write_bytes(response.content)
        if not os.path.exists(archive_path):
            print_interactive_error(_('No data received from [{url}].').format(url=build_url))
            return False
        shutil.unpack_archive(archive_path, target_dir)
        os.remove(archive_path)
        return self.is_installed

    def generate_pairings(self, tournament: Tournament):
        """Generate the pairings of a tournament's next round"""
        if not self.is_installed:
            raise FileNotFoundError('BBP Pairings is not installed.')
        if tournament.finished or tournament.playing:
            raise ValueError(
                'Impossible to generate pairings '
                'if tournament is finished '
                'or if a round is ongoing.')

        trf_file_path = os.path.join(TMP_DIR, 'tournament.trfx')
        pairings_file_path = os.path.join(TMP_DIR, 'pairings.txt')
        with open(trf_file_path, 'w') as trf_file:
            trf.dump(trf_file, tournament.to_trf(TrfType.PAIRING))
        try:
            subprocess.run(
                [
                    self._executable_path,
                    "--dutch", trf_file_path,
                    "-p", pairings_file_path],
                check=True)
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
                    BoardColor.WHITE, black_player.id, Result.NO_RESULT)
                black_player.pairings[next_round] = Pairing(
                    BoardColor.BLACK, white_player.id, Result.NO_RESULT)
            else:
                white_player.pairings[next_round] = Pairing(
                    BoardColor.WHITE, 1, Result.PAIRING_ALLOCATED_BYE)
