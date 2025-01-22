import os.path
import subprocess
from typing import TextIO

import trf
from data.board import Board
from data.pairing import Pairing
from data.tournament import Tournament
from data.util import TrfType, Result, BoardColor

BBP_PATH = os.path.join('resources', 'bbpPairings-v5.0.1', 'bbpPairings.exe')
EXEMPT_ID = 0

def generate_pairings(tournament: Tournament):
    """Generate the pairings of a tournament's next round"""
    if tournament.started and (tournament.finished or tournament.playing):
        raise ValueError(
            'Impossible to generate pairings '
            'if tournament is finished '
            'or if a round is ongoing.')
    trf_file_path = os.path.join('tmp', 'tournament.trfx')
    pairings_file_path = os.path.join('tmp', 'pairings.txt')
    with open(trf_file_path, 'w') as trf_file:
        trf.dump(trf_file, tournament.to_trf(TrfType.PAIRING))
    try:
        subprocess.run([BBP_PATH, "--dutch", trf_file_path, "-p", pairings_file_path], check=True)
    finally:
        os.remove(trf_file_path)
    try:
        with open(pairings_file_path) as pairing_file:
            _pairings_from_file(pairing_file, tournament)
    finally:
        os.remove(pairings_file_path)
    tournament.update_round_pairings(tournament.current_round + 1)


def _pairings_from_file(file: TextIO, tournament: Tournament):
    file.readline()  # table_count
    next_round = tournament.current_round + 1
    for raw_pairing in file.readlines():
        (white_trf_id, black_trf_id) = map(int, raw_pairing.split(' '))
        white_player = tournament.players_by_trf_id[white_trf_id]
        if black_trf_id != EXEMPT_ID:
            black_player = tournament.players_by_trf_id[black_trf_id]
            white_player.pairings[next_round] = Pairing(
                BoardColor.WHITE, black_player.id, Result.NO_RESULT)
            black_player.pairings[next_round] = Pairing(
                BoardColor.BLACK, white_player.id, Result.NO_RESULT)
        else:
            white_player.pairings[next_round] = Pairing(
                BoardColor.WHITE, 1, Result.PAIRING_ALLOCATED_BYE)
