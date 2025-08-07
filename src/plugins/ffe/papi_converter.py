import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
import subprocess
import glob
import sqlite3

from common.exception import SharlyChessException
from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from common.tool_installer import PapiConverterInstaller
from data.input_output.dict_reader import dict_to_dataclass, DictReaderException
from database.sqlite.event.event_store import (
    StoredTournament,
    StoredPlayer,
    StoredBoard,
    StoredTournamentPlayer,
    StoredPairing,
)
from plugins.ffe import TMP_DIR, PLUGIN_NAME
from plugins.ffe.papi_mappers import (
    PapiPairingVariation,
    PapiTournamentRating,
    PapiTieBreakMapper,
    PapiThreePointsForAWin,
)
from utils.enum import TournamentRating


@dataclass
class PapiVariables:
    name: str
    type: str | None = None
    rounds: str | None = None
    pairing: str | None = None
    timeControl: str | None = None
    ratingClass: str | None = None
    minRating: str | None = None
    maxRating: str | None = None
    tiebreak1: str | None = None
    tiebreak2: str | None = None
    tiebreak3: str | None = None
    pointSystem: str | None = None
    venue: str | None = None
    startDate: str | None = None
    endDate: str | None = None
    arbiter: str | None = None
    homologation: str | None = None


@dataclass
class PapiRound:
    color: str
    opponent: int | None = None
    result: int = 0


@dataclass
class PapiPlayer:
    lastName: str
    firstName: str | None = None
    birthDate: str | None = None
    category: str | None = None
    gender: str | None = None
    email: str | None = None
    phone: str | None = None
    comment: str | None = None
    owed: int | float | None = None
    paid: int | float | None = None
    fideTitle: str | None = None
    elo: int = 0
    fideElo: str = 'E'
    rapidElo: int = 0
    fideRapidElo: str = 'E'
    blitzElo: int = 0
    fideBlitzElo: str = 'E'
    fideCode: str | None = None
    federation: str = 'FID'
    licenceType: str = 'N'
    nrFFE: str | None = None
    refFFE: int | None = None
    league: str | None = None
    club: str | None = None
    fixedBoard: int | None = None
    checkedIn: bool = False
    rounds: dict[int, PapiRound] = field(default_factory=dict[int, PapiRound])


@dataclass
class PapiData:
    variables: PapiVariables
    players: list[PapiPlayer]


class PapiConverter:
    """Wrapper on the Papi converter
    (see https://github.com/Sharly-Chess/papi-converter)"""

    @property
    def executable_path(self) -> Path:
        return PapiConverterInstaller().executable_path

    def convert_player_database(self, source_file: Path, target_file: Path) -> bool:
        """Converts the .mdb player database to an SQLLite database."""
        # Clean up any existing temporary H2 database files to avoid conflicts
        # H2 creates files with patterns like: filename.mv.db, filename.trace.db

        # Clean up H2 files with various patterns
        cleanup_patterns = [
            str(target_file.parent / f'{target_file.stem}*.mv.db'),
            str(target_file.parent / f'{target_file.stem}*.trace.db'),
            str(target_file.parent / f'{target_file.name}*.mv.db'),
            str(target_file.parent / f'{target_file.name}*.trace.db'),
            str(target_file.with_suffix('.mv.db')),
            str(target_file.with_suffix('.trace.db')),
        ]

        for pattern in cleanup_patterns:
            for file_path in glob.glob(pattern):
                Path(file_path).unlink(missing_ok=True)

        # Also ensure the target file itself is clean
        target_file.unlink(missing_ok=True)

        # Create a temporary SQL dump file
        sql_dump_file = target_file.with_suffix('.sql')

        try:
            # First, create the SQL dump
            subprocess.run(
                [
                    self.executable_path,
                    '--playerdb',
                    str(source_file.resolve()),
                    str(sql_dump_file.resolve()),
                ],
                capture_output=True,
                encoding='utf-8',
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise SharlyChessException(
                f'PapiConverter execution failed with status {e.returncode}.\n'
                f'stdout: {e.stdout}\nstderr: {e.stderr}'
            )

        if not sql_dump_file.exists():
            raise SharlyChessException(
                'Player database conversion error: PapiConverter ran successfully but the SQL dump file was not created.'
            )

        try:
            # Create the SQLite database from the SQL dump using Python's sqlite3 module
            with open(sql_dump_file, 'r', encoding='utf-8') as dump_file:
                sql_content = dump_file.read()

            # Create the SQLite database and execute the SQL dump
            conn = sqlite3.connect(str(target_file))
            try:
                conn.executescript(sql_content)
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            raise SharlyChessException(f'SQLite database creation failed: {e}')
        finally:
            # Clean up the temporary SQL dump file
            sql_dump_file.unlink(missing_ok=True)

        if not target_file.exists():
            raise SharlyChessException(
                'Player database conversion error: SQLite database was not created.'
            )
        return True

    def read_papi_file(
        self,
        source_file: Path,
        stored_tournament: StoredTournament | None = None,
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        """Read the papi file *source_file* into stored objects.
        If a storedTournament object is provided, add the values to this one,
        otherwise creates a new one.
        Raises a SharlyChessException if the conversion fails."""
        target_file = TMP_DIR / 'papi-converter-output.json'
        result = subprocess.run(
            [
                self.executable_path,
                source_file,
                target_file,
            ],
            capture_output=True,
            encoding='utf-8',
        )
        if not target_file.exists():
            raise SharlyChessException(
                f'Papi file conversion to JSON failed.'
                f'PapiConverter failed with status {result.returncode}.\n'
                f'stdout: {result.stdout}\nstderr: {result.stderr}'
            )
        with open(target_file, 'r', encoding='utf-8') as file:
            papi_data_dict = json.load(file)
        return self.read_papi_data(papi_data_dict, stored_tournament)

    def read_papi_data(
        self,
        papi_data_dict: dict[str, Any],
        stored_tournament: StoredTournament | None = None,
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        papi_data = dict_to_dataclass(PapiData, papi_data_dict)

        stored_tournament = self._read_papi_variables(
            papi_data.variables, stored_tournament
        )
        next_board_id = 1
        board_id_by_player_id_by_round: dict[int, dict[int, int]] = {
            round_: {} for round_ in range(1, stored_tournament.rounds + 1)
        }
        stored_boards_by_round: dict[int, list[StoredBoard]] = {
            round_: [] for round_ in range(1, stored_tournament.rounds + 1)
        }
        stored_players: list[StoredPlayer] = []
        max_opponent_id = len(papi_data.players) - 1
        for player_id, papi_player in enumerate(papi_data.players):
            stored_player = self._read_papi_player(papi_player)
            stored_player.id = player_id
            stored_tournament_player = StoredTournamentPlayer(player_id=player_id)
            for round_nb, papi_round in papi_player.rounds.items():
                if round_nb > stored_tournament.rounds:
                    continue
                stored_pairing, stored_board = self._read_papi_round(
                    player_id, round_nb, papi_round, max_opponent_id
                )
                if stored_board:
                    if player_id in board_id_by_player_id_by_round[round_nb]:
                        board_id = board_id_by_player_id_by_round[round_nb][player_id]
                    else:
                        board_id = next_board_id
                        next_board_id += 1
                        stored_board.id = board_id
                        stored_boards_by_round[round_nb].append(stored_board)
                    stored_pairing.board_id = board_id
                stored_tournament_player.stored_pairings.append(stored_pairing)
            stored_player.stored_tournament_player = stored_tournament_player
        stored_tournament.stored_boards_by_round = stored_boards_by_round
        return stored_tournament, stored_players

    @staticmethod
    def _read_papi_variables(
        variables: PapiVariables,
        stored_tournament: StoredTournament | None = None,
    ) -> StoredTournament:
        def raise_exception(field_: str, message: str):
            raise DictReaderException(['variables', field_], message)

        def raise_unknown_value(field_: str, value: Any):
            raise_exception(field_, _('Unknown value [{value}]').format(value=value))

        if not stored_tournament:
            if not variables.name:
                raise_exception('name', _('A none empty string is expected'))
            stored_tournament = StoredTournament(
                id=None,
                uniq_id=variables.name.lower().replace('/', '-').replace(' ', '-'),
                name=variables.name,
                # TODO (Molrn) remove
                path=None,
                filename=None,
            )

        rounds = 7
        if variables.rounds:
            if not variables.rounds.isdigit():
                raise_exception('rounds', _('A positive integer is expected'))
            rounds = int(variables.rounds)
        stored_tournament.rounds = rounds
        pairing = SharlyChessConfig.default_pairing_variation_id
        if variables.pairing:
            try:
                pairing = PapiPairingVariation.get_core_object(variables.pairing).id
            except KeyError:
                raise_unknown_value('pairing', variables.pairing)
        stored_tournament.pairing = pairing
        rating = TournamentRating.STANDARD
        if variables.ratingClass:
            try:
                rating = PapiTournamentRating.get_core_object(variables.ratingClass)
            except KeyError:
                raise_unknown_value('ratingClass', variables.ratingClass)
        stored_tournament.rating = rating.value
        tie_breaks: list[dict[str, Any]] = []
        for index, papi_tie_break in enumerate(
            (variables.tiebreak1, variables.tiebreak2, variables.tiebreak3)
        ):
            if not papi_tie_break:
                continue
            try:
                tie_breaks.append(
                    PapiTieBreakMapper.get_core_object(papi_tie_break).to_dict()
                )
            except KeyError:
                raise_unknown_value(f'tiebreak{index + 1}', papi_tie_break)
        stored_tournament.tie_breaks = tie_breaks
        three_points_for_a_win = False
        if variables.ratingClass:
            try:
                three_points_for_a_win = PapiThreePointsForAWin.get_core_object(
                    variables.pointSystem
                )
            except KeyError:
                raise_unknown_value('pointSystem', variables.pointSystem)
        stored_tournament.three_points_for_a_win = three_points_for_a_win
        stored_tournament.location = variables.venue
        if not stored_tournament.id:
            stored_tournament.plugin_data = {
                PLUGIN_NAME: {'ffe_id': variables.homologation}
            }
        return stored_tournament

    def _read_papi_player(
        self,
        papi_player: PapiPlayer,
    ) -> StoredPlayer:
        def raise_exception(field_: str, message: str):
            raise DictReaderException(['players', field_], message)

        def raise_unknown_value(field_: str, value: Any):
            raise_exception(field_, _('Unknown value [{value}]').format(value=value))

        if not papi_player.lastName:
            raise_exception('name', _('A none empty string is expected'))

        date_of_birth: date | None = None
        if papi_player.birthDate:
            try:
                date_of_birth = datetime.strptime(
                    papi_player.birthDate, '%d/%m/%Y'
                ).date()
            except ValueError:
                raise_exception(
                    'birthDate',
                    _('Invalid date format [{date}] (expected: {format})').format(
                        date=papi_player.birthDate, format='DD/MM/YYYY'
                    ),
                )

        return StoredPlayer(
            id=None,
            last_name=papi_player.lastName,
            first_name=papi_player.firstName,
            date_of_birth=date_of_birth,
        )

    def _read_papi_round(
        self,
        player_id,
        round_nb: int,
        papi_round: PapiRound,
        max_opponent_id: int,
    ) -> tuple[StoredPairing, StoredBoard | None]:
        """
        stored_board: StoredBoard | None = None
        if papi_round.opponent is not None:
            if papi_round.opponent > max_opponent_id:
                raise DictReaderException(
                    ['players', 'opponent'],
                    _('Unknown player ID [{player_id}]').format(
                        player_id=papi_round.opponent
                    ),
                )
        return ()
        """
