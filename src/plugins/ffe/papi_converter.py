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
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from common.tool_installer import PapiConverterInstaller
from data.input_output.dict_reader import dict_to_dataclass, DictReaderException
from data.pairings.engines import DoubleBergerPairingEngine
from data.pairings.variations import (
    BergerRoundRobinVariation,
    DoubleBergerRoundRobinVariation,
)
from data.player import PlayerRating
from data.player import Player
from data.tournament import Tournament
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
    PapiPlayerCategory,
    PapiTournamentRating,
    PapiTieBreak,
    PapiThreePointsForAWin,
    PapiPlayerGender,
    PapiPlayerRatingType,
    PapiPlayerFFELicence,
    PapiRound,
    PapiColor,
    PapiPlayerTitle,
    PapiPairingSystem,
)
from plugins.ffe.utils import FfePlayerPluginData, PlayerFFELicence
from plugins.pairing_acceleration.pairing_settings import (
    DualRatingLimitsSetting,
    RatingLimitSetting,
)
from utils.enum import (
    TournamentRating,
    PlayerGender,
    PlayerTitle,
    PlayerRatingType,
    Result,
)


logger = get_logger()


@dataclass
class PapiVariables:
    name: str
    type: str | None = None
    rounds: str | None = None
    pairing: str | None = None
    timeControl: str | None = None
    ratingClass: str | None = None
    ratingThreshold1: str | None = None
    ratingThreshold2: str | None = None
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
    fideElo: str | None = None
    rapidElo: int = 0
    fideRapidElo: str | None = None
    blitzElo: int = 0
    fideBlitzElo: str | None = None
    fideCode: str | None = None
    federation: str = 'FID'
    licenceType: str | None = None
    nrFFE: str | None = None
    refFFE: int | None = None
    league: str | None = None
    club: str | None = None
    fixedBoard: int | None = None
    checkedIn: bool = False

    # Unused
    nr: str | None = None
    address: str | None = None
    postalCode: str | None = None

    rounds: dict[int, PapiRound] = field(default_factory=dict[int, PapiRound])


@dataclass
class PapiData:
    variables: PapiVariables
    players: list[PapiPlayer]


@dataclass
class PapiRating:
    value_field: str
    value: int
    type_field: str
    type: str | None
    tournament_rating: TournamentRating


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
        If a StoredTournament object is provided, add the values to this one,
        otherwise creates a new one.
        Raises a SharlyChessException if the conversion fails."""
        if source_file.suffix == '.papi':
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
        elif source_file.suffix == '.json':
            target_file = source_file
        else:
            raise SharlyChessException(
                'PapiConverter only supports .papi and .json files.'
            )

        with open(target_file, 'r', encoding='utf-8') as file:
            papi_data_dict = json.load(file)
        return self.read_papi_data(papi_data_dict, stored_tournament)

    def read_papi_data(
        self,
        papi_data_dict: dict[str, Any],
        stored_tournament: StoredTournament | None = None,
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        """Read a dict in the format of the papi-converter into stored objects."""
        papi_data = dict_to_dataclass(PapiData, papi_data_dict)

        stored_tournament = self._read_papi_variables(
            papi_data.variables, stored_tournament
        )
        is_round_robin = (
            stored_tournament.pairing == BergerRoundRobinVariation.static_id()
        )

        if is_round_robin and stored_tournament.rounds == (
            DoubleBergerPairingEngine().get_round_count(len(papi_data.players))
        ):
            stored_tournament.pairing = DoubleBergerRoundRobinVariation.static_id()

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
            stored_player = self._read_papi_player(player_id, papi_player)
            stored_player.id = player_id
            stored_tournament_player = StoredTournamentPlayer(player_id=player_id)
            round_keys = papi_player.rounds.keys()

            if is_round_robin:
                start_round = 1
                end_round = stored_tournament.rounds
            else:
                start_round = min(round_keys) if round_keys else 1
                end_round = max(round_keys) if round_keys else 0
            for round_nb in range(start_round, end_round + 1):
                papi_round = papi_player.rounds.get(round_nb, None)
                if round_nb > stored_tournament.rounds or (
                    papi_round is None and not is_round_robin
                ):
                    continue
                if papi_round is None:
                    stored_pairing = StoredPairing(
                        tournament_id=0,
                        player_id=player_id,
                        round_=round_nb,
                        result=Result.REST_GAME,
                        board_id=None,
                    )
                    stored_board: StoredBoard | None = StoredBoard(
                        id=None,
                        white_player_id=player_id,
                        black_player_id=None,
                        index=0,
                        last_result_update=None,
                    )
                else:
                    stored_pairing, stored_board = self._read_papi_round(
                        player_id, round_nb, papi_round, max_opponent_id, is_round_robin
                    )
                if stored_board:
                    if player_id in board_id_by_player_id_by_round[round_nb]:
                        board_id = board_id_by_player_id_by_round[round_nb][player_id]
                    else:
                        board_id = next_board_id
                        next_board_id += 1
                        stored_board.id = board_id
                        stored_boards_by_round[round_nb].append(stored_board)
                        if papi_round and papi_round.opponent is not None:
                            board_id_by_player_id_by_round[round_nb][
                                papi_round.opponent
                            ] = board_id
                    stored_pairing.board_id = board_id
                stored_tournament_player.stored_pairings.append(stored_pairing)
            stored_player.stored_tournament_player = stored_tournament_player
            stored_players.append(stored_player)
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
                raise_exception('name', _('A non-empty string is expected'))
            stored_tournament = StoredTournament(
                id=None,
                uniq_id=variables.name.lower().replace('/', '-').replace(' ', '-'),
                name=variables.name,
            )

        rounds = 7
        if variables.rounds:
            if not variables.rounds.isdigit():
                raise_exception('rounds', _('A positive integer is expected.'))
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
        rating_threshold_1 = 0
        if variables.ratingThreshold1:
            if not variables.ratingThreshold1.isdigit():
                raise_exception(
                    'ratingThreshold1', _('A positive integer is expected.')
                )
            rating_threshold_1 = int(variables.ratingThreshold1)
        rating_threshold_2 = 0
        if variables.ratingThreshold2:
            if not variables.ratingThreshold2.isdigit():
                raise_exception(
                    'ratingThreshold2', _('A positive integer is expected.')
                )
            rating_threshold_2 = int(variables.ratingThreshold2)
        if (rating_threshold_1, rating_threshold_2) != (0, 0):
            pairing_settings = stored_tournament.pairing_settings or {}
            if rating_threshold_1 == rating_threshold_2 or rating_threshold_2 == 0:
                pairing_settings[RatingLimitSetting.static_id()] = rating_threshold_1
            else:
                pairing_settings[DualRatingLimitsSetting.static_id()] = (
                    rating_threshold_2,
                    rating_threshold_1,
                )
            stored_tournament.pairing_settings = pairing_settings
        tie_breaks: list[dict[str, Any]] = []
        for index, papi_tie_break in enumerate(
            (variables.tiebreak1, variables.tiebreak2, variables.tiebreak3)
        ):
            if not papi_tie_break:
                continue
            try:
                tie_breaks.append(
                    PapiTieBreak.get_core_object(papi_tie_break).to_dict()
                )
            except KeyError:
                raise_unknown_value(f'tiebreak{index + 1}', papi_tie_break)
        stored_tournament.tie_breaks = tie_breaks
        three_points_for_a_win = False
        if variables.pointSystem:
            try:
                three_points_for_a_win = PapiThreePointsForAWin.get_core_object(
                    variables.pointSystem
                )
            except KeyError:
                raise_unknown_value('pointSystem', variables.pointSystem)
        stored_tournament.three_points_for_a_win = three_points_for_a_win
        stored_tournament.location = variables.venue
        ffe_id = None
        if variables.homologation:
            if not variables.homologation.isdigit():
                # Papi form allows for a non-integer value,
                # so the value is ignored instead of raising
                logger.warning(
                    'Homologation number [%s] is not an integer, its value is ignored.',
                    variables.homologation,
                )
            else:
                ffe_id = int(variables.homologation)
        plugin_data = stored_tournament.plugin_data or {}
        if PLUGIN_NAME not in plugin_data:
            plugin_data[PLUGIN_NAME] = {}
        plugin_data[PLUGIN_NAME] |= {'ffe_id': ffe_id}
        stored_tournament.plugin_data = plugin_data
        return stored_tournament

    @staticmethod
    def _read_papi_player(player_id: int, papi_player: PapiPlayer) -> StoredPlayer:
        def raise_exception(field_: str, message: str):
            raise DictReaderException(['players', str(player_id), field_], message)

        def raise_unknown_value(field_: str, value: Any):
            raise_exception(field_, _('Unknown value [{value}]').format(value=value))

        if not papi_player.lastName:
            raise_exception('name', _('A non-empty string is expected'))

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

        gender = PlayerGender.NONE
        if papi_player.gender:
            try:
                gender = PapiPlayerGender.get_core_object(papi_player.gender)
            except KeyError:
                raise_unknown_value('gender', papi_player.gender)
        title = PlayerTitle.NONE
        if papi_player.fideTitle:
            try:
                title = PapiPlayerTitle.get_core_object(papi_player.fideTitle)
            except KeyError:
                raise_unknown_value('fideTitle', papi_player.fideTitle)

        ratings: dict[int, dict[str, int]] = {}
        papi_ratings = [
            PapiRating(
                'elo',
                papi_player.elo,
                'fideElo',
                papi_player.fideElo,
                TournamentRating.STANDARD,
            ),
            PapiRating(
                'rapidElo',
                papi_player.rapidElo,
                'fideRapidElo',
                papi_player.fideRapidElo,
                TournamentRating.RAPID,
            ),
            PapiRating(
                'blitzElo',
                papi_player.blitzElo,
                'fideBlitzElo',
                papi_player.fideRapidElo,
                TournamentRating.BLITZ,
            ),
        ]
        for papi_rating in papi_ratings:
            if papi_rating.value < 0:
                raise_exception(
                    papi_rating.value_field, _('A positive integer is expected.')
                )
            rating_type = PlayerRatingType.ESTIMATED
            if papi_rating.type:
                try:
                    rating_type = PapiPlayerRatingType.get_core_object(papi_rating.type)
                except KeyError:
                    raise_unknown_value(papi_rating.type_field, papi_rating.type)
            ratings[papi_rating.tournament_rating.value] = PlayerRating(
                papi_rating.value, rating_type
            ).stored_value

        fide_id: int | None = None
        if papi_player.fideCode:
            if not papi_player.fideCode.strip().isdigit():
                raise_exception('fideCode', _('A positive integer is expected.'))
            fide_id = int(papi_player.fideCode.strip())

        ffe_licence = PlayerFFELicence.NONE
        if papi_player.licenceType:
            try:
                ffe_licence = PapiPlayerFFELicence.get_core_object(
                    papi_player.licenceType
                )
            except KeyError:
                raise_unknown_value('licenceType', papi_player.licenceType)
        return StoredPlayer(
            id=None,
            last_name=papi_player.lastName,
            first_name=papi_player.firstName,
            date_of_birth=date_of_birth,
            gender=gender.value,
            mail=papi_player.email,
            phone=papi_player.phone,
            comment=papi_player.comment,
            owed=float(papi_player.owed or 0),
            paid=float(papi_player.paid or 0),
            title=title.value,
            ratings=ratings,
            fide_id=fide_id,
            federation=papi_player.federation,
            club=papi_player.club,
            fixed=papi_player.fixedBoard,
            check_in=papi_player.checkedIn,
            plugin_data={
                PLUGIN_NAME: FfePlayerPluginData(
                    ffe_id=papi_player.refFFE,
                    ffe_licence=ffe_licence,
                    ffe_licence_number=papi_player.nrFFE,
                    league=papi_player.league,
                ).to_stored_value()
            },
        )

    @staticmethod
    def _read_papi_round(
        player_id: int,
        round_nb: int,
        papi_round: PapiRound,
        max_opponent_id: int,
        is_round_robin: bool,
    ) -> tuple[StoredPairing, StoredBoard | None]:
        def raise_exception(field_: str, message: str):
            raise DictReaderException(['players', str(player_id), field_], message)

        if papi_round.opponent is not None:
            if papi_round.opponent > max_opponent_id:
                raise_exception(
                    'opponent',
                    _('Unknown player ID [{player_id}]').format(
                        player_id=papi_round.opponent
                    ),
                )
        stored_board: StoredBoard | None = None
        result = papi_round.to_result(is_round_robin)
        stored_pairing = StoredPairing(
            tournament_id=0,
            player_id=player_id,
            round_=round_nb,
            result=result.value,
            board_id=None,
        )

        color = PapiColor.WHITE if result == Result.REST_GAME else papi_round.color
        if color in (PapiColor.WHITE, PapiColor.BLACK):
            if color == PapiColor.WHITE:
                white_id = player_id
                black_id = papi_round.opponent
            else:
                if papi_round is None:
                    raise_exception(
                        'color',
                        _('Black pairings are supposed to have an opponent'),
                    )
                assert papi_round.opponent is not None
                white_id = papi_round.opponent
                black_id = player_id
            stored_board = StoredBoard(
                id=None,
                white_player_id=white_id,
                black_player_id=black_id,
                index=0,
                last_result_update=None,
            )
        return stored_pairing, stored_board

    @classmethod
    def papi_export_unavailable_message(cls, tournament: Tournament) -> str | None:
        """Return a message if the export to Papi is unavailable, None otherwise."""
        if tournament.pairing_variation not in PapiPairingVariation.core_objects():
            return _('Pairing system [{pairing_system}] is not compatible.').format(
                pairing_system=tournament.pairing_variation.name
            )
        for tie_break in tournament.tie_breaks:
            if tie_break not in PapiTieBreak.core_objects():
                return _('Tie-break [{tie_break}] is not compatible.').format(
                    tie_break=tie_break.name
                )
        return None

    def write_papi_file(
        self,
        tournament: Tournament,
        target_file: Path,
    ) -> bool:
        """Write the tournament data to a papi file.
        Converts a Tournament to JSON format that can be sent to papi-converter.
        Returns True if successful, raises SharlyChessException if conversion fails."""
        papi_data = self._tournament_to_papi_data(tournament)
        papi_data_dict = {
            'variables': {
                key: value or '' for key, value in papi_data.variables.__dict__.items()
            },
            'players': [
                self._papi_player_to_dict(player) for player in papi_data.players
            ],
        }

        # Write JSON to temporary file first
        temp_json_file = TMP_DIR / 'papi-converter-input.json'
        try:
            with open(temp_json_file, 'w', encoding='utf-8') as file:
                json.dump(papi_data_dict, file, ensure_ascii=False, indent=2)

            # Use papi-converter to convert JSON to papi format
            result = subprocess.run(
                [
                    self.executable_path,
                    temp_json_file,
                    target_file,
                ],
                capture_output=True,
                encoding='utf-8',
            )

            if result.returncode != 0 or not target_file.exists():
                raise SharlyChessException(
                    f'JSON to Papi file conversion failed.'
                    f'PapiConverter failed with status {result.returncode}.\n'
                    f'stdout: {result.stdout}\nstderr: {result.stderr}'
                )

        finally:
            # Clean up temporary JSON file
            temp_json_file.unlink(missing_ok=True)
            return target_file.exists()

    def _tournament_to_papi_data(self, tournament: Tournament) -> PapiData:
        """Convert a Tournament object to PapiData."""

        pairing_settings = tournament.pairing_settings
        if (
            pairing_settings
            and (setting_id := DualRatingLimitsSetting.static_id()) in pairing_settings
        ):
            sharing_thresholds = pairing_settings[setting_id]
        elif (
            pairing_settings
            and (setting_id := RatingLimitSetting.static_id()) in pairing_settings
        ):
            sharing_thresholds = (pairing_settings[setting_id],) * 2
        else:
            sharing_thresholds = 0, 0

        # Convert tournament variables
        variables = PapiVariables(
            name=tournament.name,
            type=PapiPairingSystem.get_plugin_value(tournament.pairing_system),
            rounds=str(tournament.rounds),
            pairing=PapiPairingVariation.get_plugin_value(tournament.pairing_variation),
            ratingClass=PapiTournamentRating.get_plugin_value(tournament.rating),
            venue=tournament.location,
            startDate=self._format_date_for_papi(tournament.start_timestamp)
            if tournament.start_timestamp
            else None,
            endDate=self._format_date_for_papi(tournament.stop_timestamp)
            if tournament.stop_timestamp
            else None,
            tiebreak1=PapiTieBreak.get_plugin_value(tournament.tie_breaks[0])
            if tournament.tie_breaks and tournament.tie_breaks[0]
            else None,
            tiebreak2=PapiTieBreak.get_plugin_value(tournament.tie_breaks[1])
            if len(tournament.tie_breaks) > 1 and tournament.tie_breaks[1]
            else None,
            tiebreak3=PapiTieBreak.get_plugin_value(tournament.tie_breaks[2])
            if len(tournament.tie_breaks) > 2 and tournament.tie_breaks[2]
            else None,
            pointSystem=PapiThreePointsForAWin.get_plugin_value(
                tournament.three_points_for_a_win
            ),
            arbiter='',
            timeControl='',
            ratingThreshold1=str(sharing_thresholds[1]),
            ratingThreshold2=str(sharing_thresholds[0]),
            homologation=tournament.plugin_data.get(PLUGIN_NAME, {}).get(
                'ffe_id', None
            ),
        )

        # Create mapping from internal player ID to index in PapiPlayer list
        player_id_to_index = {
            player.id: index for index, player in enumerate(tournament.players)
        }

        # Convert players
        papi_players: list[PapiPlayer] = []
        for player in tournament.players:
            papi_player = self._player_to_papi_player(
                player, tournament, player_id_to_index
            )
            papi_players.append(papi_player)

        return PapiData(variables=variables, players=papi_players)

    def _player_to_papi_player(
        self, player: Player, tournament: Tournament, player_id_to_index: dict[int, int]
    ) -> PapiPlayer:
        """Convert a Player object to PapiPlayer."""

        plugin_data = player.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, FfePlayerPluginData)

        papi_player = PapiPlayer(
            lastName=player.last_name,
            firstName=player.first_name,
            birthDate=player.date_of_birth.strftime('%d/%m/%Y')
            if player.date_of_birth
            else None,
            category=PapiPlayerCategory.get_plugin_value(player.category),
            gender=PapiPlayerGender.get_plugin_value(player.gender),
            email=player.mail,
            phone=player.phone,
            comment=player.comment,
            owed=player.owed if player.owed != 0 else None,
            paid=player.paid if player.paid != 0 else None,
            fideTitle=PapiPlayerTitle.get_plugin_value(player.title),
            fideCode=str(player.fide_id) if player.fide_id else None,
            federation=player.federation.name,
            club=player.club.name,
            fixedBoard=player.fixed,
            checkedIn=player.check_in,
            elo=self._get_papi_elo(player, TournamentRating.STANDARD),
            fideElo=self._get_papi_elo_type(player, TournamentRating.STANDARD),
            rapidElo=self._get_papi_elo(player, TournamentRating.RAPID),
            fideRapidElo=self._get_papi_elo_type(player, TournamentRating.RAPID),
            blitzElo=self._get_papi_elo(player, TournamentRating.BLITZ),
            fideBlitzElo=self._get_papi_elo_type(player, TournamentRating.BLITZ),
            licenceType=PapiPlayerFFELicence.get_plugin_value(plugin_data.ffe_licence),
            refFFE=plugin_data.ffe_id,
            nrFFE=plugin_data.ffe_licence_number,
            league=plugin_data.league,
        )

        # Convert rounds/pairings
        for round, pairing in player.pairings_by_round.items():
            papi_round = PapiRound.from_pairing(pairing)

            # Get opponent index using the mapping from internal player ID to list index
            opponent_index = None
            if pairing.opponent_id is not None:
                opponent_index = player_id_to_index.get(pairing.opponent_id)
            papi_round.opponent = opponent_index
            papi_player.rounds[round] = papi_round

        return papi_player

    def _get_papi_elo(self, player: Player, tournament_rating: TournamentRating) -> int:
        # Override unrated rapid/blitz rating in the export
        if player.rating_is_overridden(tournament_rating):
            tournament_rating = TournamentRating.STANDARD
        if player.ratings and tournament_rating in player.ratings:
            return player.ratings[tournament_rating].value
        return 0

    def _get_papi_elo_type(
        self, player: Player, tournament_rating: TournamentRating
    ) -> str:
        # If we're overriding, export it as estimated
        rating_type: PlayerRatingType | None
        if player.rating_is_overridden(tournament_rating):
            rating_type = PlayerRatingType.ESTIMATED
        else:
            rating = player.ratings.get(tournament_rating, None)
            rating_type = rating.type if rating else None
        default_rating = PapiPlayerRatingType.get_plugin_value(
            PlayerRatingType.ESTIMATED
        )
        assert default_rating is not None
        if rating_type:
            return PapiPlayerRatingType.get_plugin_value(rating_type) or default_rating
        return default_rating

    def _papi_player_to_dict(self, papi_player: PapiPlayer) -> dict:
        """Convert PapiPlayer to dictionary for JSON serialization."""
        player_dict = {k: v for k, v in papi_player.__dict__.items() if v is not None}
        # Convert rounds dict to proper format
        rounds_dict = {}
        for round_nb, papi_round in papi_player.rounds.items():
            rounds_dict[str(round_nb)] = {
                k: v for k, v in papi_round.__dict__.items() if v is not None
            }
        player_dict['rounds'] = rounds_dict
        return player_dict

    def _format_date_for_papi(self, timestamp: float) -> str:
        """Format timestamp to DD/MM/YYYY format for papi."""
        return datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y')
