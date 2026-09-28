import json
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Optional, TYPE_CHECKING

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
from utils.enum import EventType

if TYPE_CHECKING:
    from data.event import Event
    from data.input_output.trf.trf_data import TrfTournament

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

    def __str__(self) -> str:
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
                CheckerPlayer.from_object(board.optional_white_tournament_player)
                if board.optional_white_tournament_player
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
class StandingsDiff:
    """Two participants the file orders one way and the tie-breaks it names
    order the other: the file puts ``player`` at ``position``, ahead of
    ``next_player``, and applying the criteria gives the later one the
    better standing.

    Reported as a pair rather than as a rank, because the rank field
    allows ties and programs number a shared rank differently; what can be
    checked without knowing the convention is the order itself.
    """

    position: int
    player: CheckerPlayer
    next_position: int
    next_player: CheckerPlayer

    @classmethod
    def from_dict(cls, d: dict) -> 'StandingsDiff':
        player = CheckerPlayer.from_dict(d['player'])
        next_player = CheckerPlayer.from_dict(d['next_player'])
        assert player is not None and next_player is not None
        return StandingsDiff(d['position'], player, d['next_position'], next_player)

    @property
    def to_dict(self) -> dict:
        return {
            'position': self.position,
            'player': self.player.to_dict,
            'next_position': self.next_position,
            'next_player': self.next_player.to_dict,
        }


@dataclass
class TournamentCheck:
    name: str
    player_count: int
    rounds: int
    diff: dict[int, list[BoardDiff]]
    #: Positions of the file's standings the tie-breaks it names do not give.
    standings_diff: list[StandingsDiff] = field(default_factory=list)
    #: Tie-breaks the file names that this program cannot apply, so the
    #: standings could not be reproduced from the list as written.
    unapplied_tie_breaks: list[str] = field(default_factory=list)
    #: The criteria the standings were checked against, in order.
    tie_breaks: list[str] = field(default_factory=list)
    #: The round the standings were checked for.
    standings_round: int = 0
    #: Why the pairings were not checked, when the pairing system has no
    #: way of being asked what it would have paired.
    pairings_unchecked: str = ''
    #: Why the standings were not checked.
    standings_unchecked: str = ''

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
            [
                StandingsDiff.from_dict(standings_diff)
                for standings_diff in d.get('standings_diff', [])
            ],
            d.get('unapplied_tie_breaks', []),
            d.get('tie_breaks', []),
            d.get('standings_round', 0),
            d.get('pairings_unchecked', ''),
            d.get('standings_unchecked', ''),
        )

    @classmethod
    def load_from_file(
        cls,
        input_file: Path,
    ) -> 'TournamentCheck':
        with open(input_file, encoding='utf-8') as file:
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
            'standings_diff': [
                standings_diff.to_dict for standings_diff in self.standings_diff
            ],
            'unapplied_tie_breaks': self.unapplied_tie_breaks,
            'tie_breaks': self.tie_breaks,
            'standings_round': self.standings_round,
            'pairings_unchecked': self.pairings_unchecked,
            'standings_unchecked': self.standings_unchecked,
        }

    def dump_to_file(
        self,
        output_file: Path,
    ) -> None:
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

    @property
    def standings_error_count(self) -> int:
        """Returns the number of positions the tie-breaks do not give."""
        return len(self.standings_diff)

    def print_standings(self) -> None:
        criteria = ', '.join(self.tie_breaks) or '(none named)'
        if self.standings_unchecked:
            print_interactive_warning(
                f'Tournament [{self.name}]: the standings were not checked, '
                f'{self.standings_unchecked}.'
            )
            return
        if self.unapplied_tie_breaks:
            print_interactive_warning(
                f'Tournament [{self.name}]: the standings were not checked. '
                f'The file ranks on {", ".join(self.unapplied_tie_breaks)}, '
                f'which this program does not apply.'
            )
            return
        if self.standings_diff:
            print_interactive_error(
                f'Tournament [{self.name}]: {self.standings_error_count} '
                f'position(s) of the standings after round {self.standings_round} '
                f'are not the order given by {criteria}.'
            )
            for standings_diff in self.standings_diff:
                print_interactive_warning(
                    f'{standings_diff.position:4d}. {standings_diff.player} is '
                    f'placed above {standings_diff.next_position}. '
                    f'{standings_diff.next_player}, which the criteria reverse.'
                )
        else:
            print_interactive_success(
                f'Tournament [{self.name}]: the standings after round '
                f'{self.standings_round} are the order given by {criteria}.'
            )

    def print(self) -> None:
        self.print_standings()
        if self.pairings_unchecked:
            print_interactive_warning(
                f'Tournament [{self.name}]: the pairings were not checked, '
                f'{self.pairings_unchecked}.'
            )
        if self.diff:
            print_interactive_error(
                f'Tournament [{self.name}]: {self.board_error_count} error(s) found on {self.round_error_count} round(s) (rounds: {self.rounds}, players: {self.player_count}).'
            )
            player_len: int = 0
            for round_diff in self.diff.values():
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
        elif not self.pairings_unchecked:
            found = (
                'no errors in the pairings'
                if self.standings_diff or self.unapplied_tie_breaks
                else 'no errors'
            )
            print_interactive_success(
                f'Tournament [{self.name}]: {found} (rounds: {self.rounds}, players: {self.player_count}).'
            )


def check_standings(
    tournament: Tournament,
    trf_tournament: 'TrfTournament',
    event: 'Event',
) -> tuple[list[StandingsDiff], list[str], list[str], int]:
    """Check the standings a TRF states against the order the tie-breaks it
    names produce (FIDE C.04.A Annex 3, question 21).

    Returns the positions that disagree, the tie-breaks named that cannot be
    applied here, the criteria the check was made against, and the round it
    was made for.

    The comparison is on the order, not on the rank numbers: the rank field
    allows ties and programs number a shared rank differently, so what can
    be checked without knowing the convention is whether the file ever puts
    one participant above another that the criteria place higher. A file
    naming a criterion this program does not implement is reported rather
    than checked against a shorter list, which would pass for the wrong
    reason.
    """
    from data.input_output.trf.trf_importer import TrfTournamentImporter

    if trf_tournament.teams:
        # A team tournament's standings are its teams', and the rank field of
        # the player records is the individual order within the team. Ranking
        # the players against the team criteria would report differences that
        # say nothing about the file.
        return [], [], [], 0
    acronyms = trf_tournament.standings_tie_breaks or trf_tournament.tie_breaks
    applied, unapplied = TrfTournamentImporter.read_tie_breaks(list(acronyms), event)
    after_round = tournament.ranking.correct_round()
    tournament.compute_tournament_player_ranks(after_round=after_round)
    # The criteria alone, without the pairing number this program falls back
    # on: participants the criteria leave level may be ordered any way at all
    # (C.07 Art. 4.2 has such ties drawn by lot), so only a pair the criteria
    # actively reverse is a position the file states wrongly.
    # The file's own order, as its rank field gives it. Participants sharing
    # a rank are not ordered by the file, so nothing between them can
    # contradict it.
    stated = sorted(
        (
            (trf_player.rank, trf_player.id)
            for trf_player in trf_tournament.players
            if trf_player.rank is not None
        ),
    )
    diffs: list[StandingsDiff] = []
    if not unapplied:
        players_by_number = tournament.tournament_players_by_pairing_number
        for (rank, number), (next_rank, next_number) in pairwise(stated):
            if rank == next_rank:
                continue
            player = players_by_number.get(number)
            next_player = players_by_number.get(next_number)
            if player is None or next_player is None:
                continue
            if (
                next_player.rank_sort_key_without_pairing_number
                < player.rank_sort_key_without_pairing_number
            ):
                checker_player = CheckerPlayer.from_object(player)
                next_checker_player = CheckerPlayer.from_object(next_player)
                assert checker_player is not None
                assert next_checker_player is not None
                diffs.append(
                    StandingsDiff(rank, checker_player, next_rank, next_checker_player)
                )
    return (
        diffs,
        unapplied,
        [tie_break.trf_acronym for tie_break in applied],
        after_round,
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
                from data.input_output.trf.trf_serializer import TrfSerializer
                from data.loader import EventLoader

                with open(trf_input_file_path, encoding='utf-8') as file:
                    trf_tournament = TrfSerializer.load(file)

                event_loader = EventLoader()
                event_uniq_id: str = event_loader.get_unused_event_uniq_id('checker')
                EventDatabase(event_uniq_id).create()
                if trf_tournament.teams:
                    # A team file is only readable by a team event, so the
                    # event it is read into is the kind it describes.
                    with EventDatabase(event_uniq_id, write=True) as database:
                        stored_event = database.load_stored_event()
                        stored_event.event_type = EventType.TEAM
                        database.update_stored_event(stored_event)
                    EventLoader.unload_event(event_uniq_id)
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
                engine = tournament.pairing_variation.engine
                try:
                    for round_ in range(1, tournament.rounds + 1):
                        if round_pairings_diff := engine.pairings_diff(
                            tournament,
                            round_,
                            ignore_order=True,
                        ):
                            tournament_check.diff[round_] = [
                                BoardDiff.from_objects(
                                    read_board,
                                    expected_board,
                                )
                                for read_board, expected_board in round_pairings_diff
                            ]
                except NotImplementedError:
                    # A pairing system that cannot be asked what it would
                    # have paired says so, rather than the file passing for
                    # having had its pairings checked.
                    tournament_check.diff.clear()
                    tournament_check.pairings_unchecked = (
                        f'{tournament.pairing_variation.name} cannot be asked to '
                        f'reproduce a round'
                    )
                if trf_tournament.teams:
                    tournament_check.standings_unchecked = (
                        'a team tournament ranks its teams and this ranks the players'
                    )
                print_interactive_info(
                    f'Analysing standings for tournament [{tournament_check.name}]...'
                )
                (
                    tournament_check.standings_diff,
                    tournament_check.unapplied_tie_breaks,
                    tournament_check.tie_breaks,
                    tournament_check.standings_round,
                ) = check_standings(tournament, trf_tournament, event)
                EventDatabase(event_uniq_id).file.unlink()
                if cache:
                    tournament_check.dump_to_file(check_file_path)

            tournament_check.print()

            return tournament_check
        except BaseException as be:
            print_interactive_error(f'Exception: {be}')
            check_file_path.unlink(missing_ok=True)
            raise
