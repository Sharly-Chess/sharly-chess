import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from common.logger import (
    get_logger,
    print_interactive_info,
    print_interactive_success,
    print_interactive_error,
    print_interactive_warning,
)
from data.board import Board
from data.pairings.engines import BbpPairings
from data.player import TournamentPlayer
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase

logger = get_logger()


@dataclass
class CheckerPlayer:
    id: int
    last_name: str
    first_name: str
    rating: int
    points: float

    @classmethod
    def from_object(
        cls,
        tournament_player: TournamentPlayer,
    ) -> Optional['CheckerPlayer']:
        return (
            CheckerPlayer(
                tournament_player.id,
                tournament_player.last_name,
                tournament_player.first_name,
                tournament_player.rating,
                tournament_player.points or 0.0,
            )
            if tournament_player
            else None
        )

    @classmethod
    def from_dict(
        cls,
        d: dict,
    ) -> Optional['CheckerPlayer']:
        return (
            CheckerPlayer(
                d['id'],
                d['last_name'],
                d['first_name'],
                d['rating'],
                d['points'],
            )
            if d
            else None
        )

    @property
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'last_name': self.last_name,
            'first_name': self.first_name,
            'rating': self.rating,
            'points': self.points,
        }

    def __str__(self):
        return f'({self.id}) {self.last_name} {self.first_name} {self.rating} [{self.points:.1f}]'


@dataclass
class CheckerBoard:
    id: int
    white: CheckerPlayer | None
    black: CheckerPlayer | None

    @classmethod
    def from_object(
        cls,
        board: Board | None,
    ) -> Optional['CheckerBoard']:
        return (
            CheckerBoard(
                board.id,
                CheckerPlayer.from_object(board.white_tournament_player)
                if board.white_tournament_player
                else None,
                CheckerPlayer.from_object(board.black_tournament_player)
                if board.black_tournament_player
                else None,
            )
            if board
            else None
        )

    @classmethod
    def from_dict(
        cls,
        d: dict,
    ) -> Optional['CheckerBoard']:
        return (
            CheckerBoard(
                d['id'],
                CheckerPlayer.from_dict(d['white']),
                CheckerPlayer.from_dict(d['black']),
            )
            if d
            else None
        )

    @property
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'white': self.white.to_dict if self.white else None,
            'black': self.black.to_dict if self.black else None,
        }


@dataclass
class BoardDiff:
    read_board: CheckerBoard | None
    expected_board: CheckerBoard | None

    @classmethod
    def from_objects(
        cls,
        read_board: Board | None,
        expected_board: Board | None,
    ) -> 'BoardDiff':
        return BoardDiff(
            CheckerBoard.from_object(read_board) if read_board else None,
            CheckerBoard.from_object(expected_board) if expected_board else None,
        )

    @classmethod
    def from_dict(
        cls,
        d: dict,
    ) -> 'BoardDiff':
        return BoardDiff(
            CheckerBoard.from_dict(d['read_board']),
            CheckerBoard.from_dict(d['expected_board']),
        )

    @property
    def to_dict(self) -> dict:
        return {
            'read_board': self.read_board.to_dict if self.read_board else None,
            'expected_board': self.expected_board.to_dict
            if self.expected_board
            else None,
        }


@dataclass
class TournamentCheck:
    name: str
    player_count: int
    rounds: int
    diff: dict[int, list[BoardDiff]]

    @classmethod
    def from_object(
        cls,
        tournament: Tournament,
    ) -> 'TournamentCheck':
        return TournamentCheck(
            tournament.name,
            tournament.player_count,
            tournament.rounds,
            {},
        )

    @classmethod
    def from_dict(
        cls,
        d: dict,
    ) -> 'TournamentCheck':
        return TournamentCheck(
            d['name'],
            d['player_count'],
            d['rounds'],
            {
                int(round_): [
                    BoardDiff.from_dict(board_diff) for board_diff in round_board_diffs
                ]
                for round_, round_board_diffs in d['diff'].items()
            },
        )

    @classmethod
    def load_from_file(
        cls,
        input_file: Path,
    ) -> 'TournamentCheck':
        with open(input_file, 'r', encoding='utf-8') as file:
            return TournamentCheck.from_dict(json.load(file))

    @property
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'player_count': self.player_count,
            'rounds': self.rounds,
            'diff': {
                round_: [
                    round_board_diff.to_dict for round_board_diff in round_board_diffs
                ]
                for round_, round_board_diffs in self.diff.items()
            },
        }

    def dump_to_file(
        self,
        output_file: Path,
    ):
        with open(output_file, 'w', encoding='utf-8') as file:
            json.dump(self.to_dict, file, ensure_ascii=False, indent=2)

    @property
    def round_error_count(self) -> int:
        """Returns the number of rounds with errors."""
        return len(self.diff)

    @property
    def board_error_count(self) -> int:
        """Returns the number of boards with errors."""
        return sum(len(round_board_diffs) for round_board_diffs in self.diff.values())

    def print(self):
        if self.diff:
            print_interactive_error(
                f'Tournament [{self.name}]: {self.board_error_count} error(s) found on {self.round_error_count} round(s) (rounds: {self.rounds}, players: {self.player_count}).'
            )
            player_len: int = 0
            for round_, round_diff in self.diff.items():
                for board_diff in round_diff:
                    for board in (board_diff.read_board, board_diff.expected_board):
                        if board:
                            for player in (board.white, board.black):
                                if player:
                                    player_len = max(player_len, len(str(player)))
            print_interactive_warning(
                f'Rd.Brd | {"Read".ljust(2 * player_len + 4)} | {"Expected".ljust(2 * player_len + 4)} |'
            )
            last_round: int = 0
            for round_, round_diff in self.diff.items():
                for board_diff in round_diff:
                    round_string = (
                        f'{round_:02d}.' if round_ != last_round else ''.ljust(3)
                    )
                    board_id = (
                        board_diff.read_board.id
                        if board_diff.read_board
                        else board_diff.expected_board.id
                        if board_diff.expected_board
                        else 0
                    )
                    board_string = f'{board_id:03d}'
                    read_white_string: str = (
                        str(board_diff.read_board.white)
                        if board_diff.read_board and board_diff.read_board.white
                        else ''
                    ).ljust(player_len)
                    read_black_string: str = (
                        str(board_diff.read_board.black)
                        if board_diff.read_board and board_diff.read_board.black
                        else ''
                    ).ljust(player_len)
                    expected_white_string: str = (
                        str(board_diff.expected_board.white)
                        if board_diff.expected_board and board_diff.expected_board.white
                        else ''
                    ).ljust(player_len)
                    expected_black_string: str = (
                        str(board_diff.expected_board.black)
                        if board_diff.expected_board and board_diff.expected_board.black
                        else ''
                    ).ljust(player_len)
                    print_interactive_warning(
                        f'{round_string}{board_string} | {read_white_string} vs {read_black_string} | {expected_white_string} vs {expected_black_string} |'
                    )
                    last_round = round_
        else:
            print_interactive_success(
                f'Tournament [{self.name}]: no errors (rounds: {self.rounds}, players: {self.player_count}).'
            )


class BbpPairingsChecker(BbpPairings):
    @staticmethod
    def check_tournament(
        trf_input_file_path: Path,
        cache: bool = False,
    ) -> TournamentCheck:
        """Checks a tournament by looking at the differences
        between the pairings of the input file and those
        made by the engine."""
        check_file_path = trf_input_file_path.with_suffix('.json')
        try:
            tournament_check: TournamentCheck
            if cache and check_file_path.exists():
                tournament_check = TournamentCheck.load_from_file(check_file_path)
                print_interactive_info(
                    f'Loaded pairing analysis of tournament [{trf_input_file_path.name}] from cache.'
                )
            else:
                check_file_path.unlink(missing_ok=True)
                print_interactive_info(
                    f'Loading TRFX file [{trf_input_file_path.name}]...'
                )

                from data.input_output.tournament_importer_options import FileOption
                from data.input_output.trf.trf_importer import TrfTournamentImporter
                from data.loader import EventLoader

                event_loader = EventLoader()
                event_uniq_id: str = event_loader.get_unused_event_uniq_id('checker')
                EventDatabase(event_uniq_id).create()
                event = EventLoader().load_event(event_uniq_id)
                tournament_id = TrfTournamentImporter(
                    [FileOption(trf_input_file_path)]
                ).load_tournament(event)
                event = EventLoader().load_event(event_uniq_id)
                tournament = event.tournaments_by_id[tournament_id]
                tournament_check = TournamentCheck.from_object(tournament)
                print_interactive_info(
                    f'Analysing pairings for tournament [{tournament_check.name}]...'
                )
                for round_ in range(1, tournament.rounds + 1):
                    if (
                        round_pairings_diff
                        := tournament.pairing_variation.engine.pairings_diff(
                            tournament,
                            round_,
                            ignore_order=True,
                        )
                    ):
                        tournament_check.diff[round_] = [
                            BoardDiff.from_objects(
                                read_board,
                                expected_board,
                            )
                            for read_board, expected_board in round_pairings_diff
                        ]
                EventDatabase(event_uniq_id).file.unlink()
                if cache:
                    tournament_check.dump_to_file(check_file_path)

            tournament_check.print()

            return tournament_check
        except BaseException as be:
            print_interactive_error(f'Exception: {be}')
            check_file_path.unlink(missing_ok=True)
            raise
