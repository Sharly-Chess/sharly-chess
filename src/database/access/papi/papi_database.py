import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from enum import StrEnum
from logging import Logger
from pathlib import Path
from typing import Pattern, Any

from common.logger import get_logger
from data.pairing import Pairing
from data.pairings import PairingVariation
from data.pairings.variations import StandardSwissVariation
from data.player import Player, PlayerRating
from data.tie_breaks import TieBreak, PapiTieBreakManager
from database.access.papi.papi_store import (
    StoredPlayer,
    StoredTournamentPlayer,
    StoredPairing,
    StoredBoard,
)
from utils.enum import (
    Result,
    PlayerGender,
    PlayerTitle,
    TournamentRating,
    PlayerRatingType,
    BoardColor,
    PointValueType,
    PapiResult,
)
from database.access.access_database import AccessDatabase
from database.access.papi.papi_template import create_empty_papi_database
from plugins.manager import plugin_manager

logger: Logger = get_logger()


EXEMPT_PLAYER_ID = 1
BYE_COLOR = 'F'
UNPLAYED_COLOR = 'R'


class RoundFields:
    def __init__(self, round_: int):
        assert 1 <= round_ <= 24
        self.color = f'Rd{round_:0>2}Cl'
        self.opponent = f'Rd{round_:0>2}Adv'
        self.result = f'Rd{round_:0>2}Res'

    @property
    def all(self) -> list[str]:
        return [self.color, self.opponent, self.result]

    @property
    def field_sets(self) -> str:
        return ', '.join(f'`{field}` = ?' for field in self.all)


@dataclass
class PapiTournamentInfo:
    """Basic tournament information tuple."""

    rounds: int = 1
    pairing_variation: PairingVariation = field(default_factory=StandardSwissVariation)
    rating: TournamentRating = TournamentRating.STANDARD
    rating_limit1: int = 0
    rating_limit2: int = 0
    tie_breaks: list[TieBreak] = field(default_factory=list[TieBreak])
    point_value_type: PointValueType = PointValueType.STANDARD
    arbiter: str = ''


class PapiVariable(StrEnum):
    NAME = 'Nom'
    TYPE = 'Genre'
    ROUNDS = 'NbrRondes'
    PAIRING_SYSTEM = 'Genre'
    PAIRING_VARIATION = 'Pairing'
    TIME_CONTROL = 'Cadence'
    RATING = 'ClassElo'
    RATING_LIMIT1 = 'EloBase1'
    RATING_LIMIT2 = 'EloBase2'
    TIE_BREAK1 = 'Dep1'
    TIE_BREAK2 = 'Dep2'
    TIE_BREAK3 = 'Dep3'
    POINT_VALUE_TYPE = 'DecomptePoints'
    LOCATION = 'Lieu'
    START_DATE = 'DateDebut'
    END_DATE = 'DateFin'
    ARBITER = 'Arbitre'
    FFE_ID = 'Homologation'


class PapiDatabase(AccessDatabase):
    """The database class, using the Papi format of the French Chess Federation
    Tournament manager."""

    def __init__(
        self, file: Path, write: bool = False, on_exit: Callable | None = None
    ):
        super().__init__(file, write)
        self.date_of_birth_pattern: Pattern = re.compile(r'^\d{1,2}/\d{1,2}/(\d{1,4})$')
        self.on_exit = on_exit

    def __exit__(self, exc_type, exc_val, tb):
        super().__exit__(exc_type, exc_val, tb)
        if self.on_exit:
            self.on_exit()

    def create_empty(self):
        assert not self.file.exists()
        create_empty_papi_database(self.file)

    def commit(self):
        self._commit()

    def read_variables(self, variables: list[PapiVariable]) -> dict[PapiVariable, str]:
        if not variables:
            return {}
        self._execute(
            (
                'SELECT `Variable`, `Value` FROM `info` WHERE `Variable` '
                f'IN ({", ".join("?" for _ in range(len(variables)))})'
            ),
            tuple(variable.value for variable in variables),
        )
        return {PapiVariable(row['Variable']): row['Value'] for row in self._fetchall()}

    def update_variable(self, variable: PapiVariable, value: str | int):
        query: str = 'UPDATE `info` SET `Value` = ? WHERE `Variable` = ?'
        self._execute(query, (value, variable.value))

    def read_info(self) -> PapiTournamentInfo:
        """Reads the database and returns basic information about the
        tournament."""
        values = self.read_variables(
            [
                PapiVariable.ROUNDS,
                PapiVariable.PAIRING_VARIATION,
                PapiVariable.RATING,
                PapiVariable.RATING_LIMIT1,
                PapiVariable.RATING_LIMIT2,
                PapiVariable.TIE_BREAK1,
                PapiVariable.TIE_BREAK2,
                PapiVariable.TIE_BREAK3,
                PapiVariable.POINT_VALUE_TYPE,
                PapiVariable.ARBITER,
            ]
        )
        tie_break_type_by_id = PapiTieBreakManager.type_by_papi_id()
        tie_breaks: list[TieBreak] = []
        for variable in (
            PapiVariable.TIE_BREAK1,
            PapiVariable.TIE_BREAK2,
            PapiVariable.TIE_BREAK3,
        ):
            papi_id = values[variable]
            if tie_break_type := tie_break_type_by_id.get(papi_id, None):
                tie_breaks.append(tie_break_type())

        from plugins.ffe.utils import PapiPairingVariation

        return PapiTournamentInfo(
            rounds=int(values[PapiVariable.ROUNDS]),
            pairing_variation=PapiPairingVariation.get_core_object(
                values[PapiVariable.PAIRING_VARIATION]
            ),
            rating=TournamentRating.from_papi_value(values[PapiVariable.RATING]),
            rating_limit1=int(values[PapiVariable.RATING_LIMIT1]),
            rating_limit2=int(values[PapiVariable.RATING_LIMIT2]),
            tie_breaks=tie_breaks,
            point_value_type=PointValueType.from_papi_value(
                values[PapiVariable.POINT_VALUE_TYPE]
            ),
            arbiter=values[PapiVariable.ARBITER],
        )

    def write_info(self, info: dict[PapiVariable, str | int]):
        for name, value in info.items():
            self.update_variable(name, value)

    def read_player_dict(
        self, player_papi_id: int
    ) -> dict[str, str | int | float | None]:
        """Reads the database and return the information of the player with the given Papi ID."""
        self._execute('SELECT * FROM joueur WHERE Ref = ?', (player_papi_id,))
        return self._fetchone()

    def delete_player(
        self,
        player_papi_id: int,
    ):
        """Reads the database and fetches the information of the player with the given Papi ID,
        returns Papi ID of the deleted player if needed."""
        self._execute('DELETE FROM joueur WHERE Ref = ?', (player_papi_id,))

    @property
    def next_player_papi_id(self) -> int:
        """Returns the next Papi ID to use when adding a player to the database."""
        self._execute('SELECT Max(Ref) AS max FROM joueur')
        return self._fetchone()['max'] + 1

    def write_player_dict(
        self,
        data: dict[str, str | int | float | None],
    ) -> int:
        """Writes the information of a Papi player extracted from another database to this database,
        returns the papi_id."""
        field_names: list[str] = list(data.keys())
        params: tuple = tuple([data[field] for field in field_names])
        fields = ', '.join(f'`{f}`' for f in field_names)
        values = ', '.join(['?'] * len(field_names))
        self._execute(f'INSERT INTO `joueur`({fields}) VALUES ({values})', params)
        assert isinstance(data['Ref'], int)
        return data['Ref']

    def update_player(self, player: Player):
        """Updates the event database with the information in the provided player."""

        per_plugin_player_data = plugin_manager.hook.player_data_for_db_write(
            player=player
        )
        plugin_data = {
            key: value for data in per_plugin_player_data for key, value in data.items()
        }

        fields: list[str] = (
            [
                'Nom',
                'Prenom',
                'NeLe',
                'Sexe',
                'FideTitre',
                'FideCode',
                'Federation',
                'Club',
                'EMail',
                'Tel',
                'Commentaire',
                'InscriptionDu',
                'InscriptionRegle',
                'Fixe',
            ]
            + [tr.papi_value_field for tr in TournamentRating]
            + [tr.papi_type_field for tr in TournamentRating]
            + [field for field in plugin_data.keys()]
        )
        params = (
            [
                player.last_name,
                player.first_name,
                self.date_to_papi_date(player.date_of_birth),
                player.gender.to_papi_value,
                player.title.to_papi_value,
                player.fide_id,
                player.federation.name,
                player.club.name if player.club else '',
                player.mail,
                player.phone,
                player.comment,
                player.owed,
                player.paid,
                player.fixed or 0,
            ]
            + [player.get_rating(tr).value for tr in TournamentRating]
            + [player.get_rating(tr).type.to_papi_value for tr in TournamentRating]
            + [value for value in plugin_data.values()]
            + [
                player.ref_id,
            ]
        )
        field_sets = (f'`{f}` = ?' for f in fields)
        self._execute(
            f'UPDATE `joueur` SET {", ".join(field_sets)} WHERE `Ref` = ?',
            tuple(params),
        )

    def _update_player_round(
        self,
        player_id: int,
        round_: int,
        color: str,
        opponent_id: int | None,
        result: Result,
    ):
        self._execute(
            f'UPDATE `joueur` SET {RoundFields(round_).field_sets} WHERE `Ref` = ?',
            (color, opponent_id, result.to_papi_value, player_id),
        )

    def remove_exempt_pairing(self, round_nb: int):
        self._update_player_round(
            EXEMPT_PLAYER_ID, round_nb, UNPLAYED_COLOR, None, Result.NO_RESULT
        )

    def update_player_pairing(self, player: Player, round_nb: int, pairing: Pairing):
        opponent_id = (
            Player.player_papi_id_from_sharly_chess_id(pairing.opponent_id)
            if pairing.opponent_id
            else EXEMPT_PLAYER_ID
            if pairing.exempt
            else None
        )
        if pairing.color:
            color = pairing.color.to_papi_value
        elif pairing.result.is_bye:
            color = BYE_COLOR
        else:
            color = UNPLAYED_COLOR
        self._update_player_round(
            player.ref_id, round_nb, color, opponent_id, pairing.result
        )
        # If the player is exempt, we need to update the pairing of the virtual exempt player
        if opponent_id == EXEMPT_PLAYER_ID:
            self._update_player_round(
                EXEMPT_PLAYER_ID,
                round_nb,
                BoardColor.BLACK.to_papi_value,
                player.ref_id,
                Result.NO_RESULT,
            )

    def remove_player_pairing(self, player: Player, round_nb: int):
        self._update_player_round(
            player.ref_id, round_nb, UNPLAYED_COLOR, None, Result.NO_RESULT
        )

    def update_tie_breaks(self, tie_breaks: list[TieBreak]):
        for variable in (
            PapiVariable.TIE_BREAK1,
            PapiVariable.TIE_BREAK2,
            PapiVariable.TIE_BREAK3,
        ):
            while tie_breaks and tie_breaks[0].papi_id is None:
                tie_breaks.pop(0)
            self.update_variable(
                variable, (tie_breaks.pop(0).papi_id or '') if tie_breaks else ''
            )

    @classmethod
    def _stored_player_from_row(
        cls,
        tournament_id: int,
        row: dict[str, Any],
        stored_pairings: list[StoredPairing],
    ) -> StoredPlayer:
        player_id = Player.player_sharly_chess_id_from_papi_id(
            tournament_id, row['Ref']
        )
        return StoredPlayer(
            id=player_id,
            last_name=row['Nom'] or '',
            first_name=row['Prenom'] or '',
            date_of_birth=row['NeLe'].date() if row['NeLe'] else None,
            gender=PlayerGender.from_papi_value(row['Sexe'] or ''),
            mail=row['EMail'] or '',
            phone=row['Tel'] or '',
            comment=row['Commentaire'] or '',
            owed=float(row['InscriptionDu'] or 0.0),
            paid=float(row['InscriptionRegle'] or 0.0),
            title=PlayerTitle.from_papi_value(row['FideTitre'] or ''),
            ratings={
                tr: PlayerRating(
                    row[tr.papi_value_field] or 0,
                    PlayerRatingType.from_papi_value(row[tr.papi_type_field]),
                ).stored_value
                for tr in TournamentRating
            },
            fide_id=int(str(row['FideCode']).strip()) if row['FideCode'] else None,
            federation=row['Federation'] or '',
            club=row['Club'] or '',
            fixed=row['Fixe'] or 0,
            check_in=row['Pointe'] or False,
            stored_tournament_player=StoredTournamentPlayer(
                tournament_id=tournament_id,
                player_id=player_id,
                stored_pairings=stored_pairings,
            ),
        )

    @staticmethod
    def _rating_type_from_row(row: dict[str, Any], tournament_rating: TournamentRating):
        value = row[tournament_rating.papi_type_field]
        return PlayerRatingType.from_papi_value(value).value

    def read_players(
        self, tournament_id: int, rounds: int
    ) -> tuple[list[StoredPlayer], dict[int, list[StoredBoard]]]:
        """Reads the database and fetches the Player identification, pairings and results.
        The tournament_id is used to make the players' id unique for an event."""

        per_plugin_fields = plugin_manager.hook.get_db_player_fields()
        plugin_fields = [field for fields in per_plugin_fields for field in fields]
        player_fields: list[str] = (
            [
                'Ref',
                'Nom',
                'Prenom',
                'NeLe',
                'Sexe',
                'EMail',
                'Tel',
                'Commentaire',
                'InscriptionDu',
                'InscriptionRegle',
                'FideTitre',
                'Fixe',
            ]
            + [tr.papi_value_field for tr in TournamentRating]
            + [tr.papi_type_field for tr in TournamentRating]
            + [
                'Pointe',
                'Federation',
                'Club',
                'FideCode',
            ]
            + plugin_fields
        )
        for round_ in range(1, rounds + 1):
            player_fields += RoundFields(round_).all

        query: str = (
            f'SELECT {", ".join(player_fields)} FROM joueur WHERE Ref <> ? ORDER BY Ref'
        )
        self._execute(query, (EXEMPT_PLAYER_ID,))
        stored_players: list[StoredPlayer] = []
        stored_boards_by_round: dict[int, list[StoredBoard]] = {
            round_: [] for round_ in range(1, rounds + 1)
        }
        board_ids_by_player_id_by_round: dict[int, dict[int, int]] = {
            round_: {} for round_ in range(1, rounds + 1)
        }
        next_board_id = 1
        for row in self._fetchall():
            stored_pairings: list[StoredPairing] = []
            player_id = Player.player_sharly_chess_id_from_papi_id(
                tournament_id, row['Ref']
            )
            for round_ in range(1, rounds + 1):
                rf = RoundFields(round_)
                color: BoardColor | None
                color_str: str = row[rf.color]
                try:
                    color = BoardColor.from_papi_value(color_str)
                except ValueError:
                    color = None
                opponent_papi_id: int | None = row[rf.opponent]
                result = Result.from_papi_value(
                    row[rf.result] or PapiResult.NOT_PAIRED.value,
                    opponent_papi_id is None,
                    opponent_papi_id == EXEMPT_PLAYER_ID,
                    color_str == BYE_COLOR,
                )
                board_id: int | None = None
                if opponent_papi_id:
                    opponent_id = Player.player_sharly_chess_id_from_papi_id(
                        tournament_id, opponent_papi_id
                    )
                    if player_id in board_ids_by_player_id_by_round[round_]:
                        board_id = board_ids_by_player_id_by_round[round_][player_id]
                    else:
                        board_id = next_board_id
                        next_board_id += 1
                        stored_boards_by_round[round_].append(
                            StoredBoard(
                                id=board_id,
                                white_player_id=(
                                    opponent_id
                                    if color == BoardColor.BLACK
                                    else player_id
                                ),
                                black_player_id=(
                                    None
                                    if opponent_papi_id == EXEMPT_PLAYER_ID
                                    else player_id
                                    if color == BoardColor.BLACK
                                    else opponent_id
                                ),
                                index=0,
                            )
                        )
                        board_ids_by_player_id_by_round[round_][opponent_id] = board_id
                        board_ids_by_player_id_by_round[round_][player_id] = board_id
                stored_pairings.append(
                    StoredPairing(
                        tournament_id=tournament_id,
                        player_id=player_id,
                        round_=round_,
                        result=result.value,
                        board_id=board_id,
                    )
                )
            stored_player = self._stored_player_from_row(
                tournament_id, row, stored_pairings
            )
            plugin_manager.hook.augment_player_after_db_fetch(
                stored_player=stored_player, row=row
            )
            stored_players.append(stored_player)
        return stored_players, stored_boards_by_round

    def set_player_result(
        self,
        player_papi_id: int,
        round_: int,
        result: Result,
        was_paired: bool,
    ):
        """Writes the given result to the database."""
        rf = RoundFields(round_)
        data: dict[str, Any] = {
            rf.result: result.to_papi_value,
        }
        if result == Result.PAIRING_ALLOCATED_BYE:
            data[rf.color] = BoardColor.WHITE.to_papi_value
            data[rf.opponent] = EXEMPT_PLAYER_ID
        elif result.is_bye:
            data[rf.color] = BYE_COLOR
            data[rf.opponent] = None
        elif not was_paired and result == Result.NO_RESULT:
            data[rf.color] = UNPLAYED_COLOR
        actions: str = ', '.join([f'`{key}` = ?' for key in data])
        self._execute(
            f'UPDATE `joueur` SET {actions} WHERE `Ref` = ?',
            tuple(list(data.values())) + (player_papi_id,),
        )

    @staticmethod
    def timestamp_to_papi_date(ts: float) -> str:
        dt: datetime
        if ts >= 0:
            dt = datetime.fromtimestamp(ts)
        else:
            dt = datetime(1970, 1, 2) + timedelta(seconds=ts)
        return dt.strftime('%d/%m/%Y')

    @staticmethod
    def date_to_papi_date(d: date | None) -> str | None:
        return datetime(d.year, d.month, d.day).strftime('%d/%m/%Y') if d else None

    def delete_players_personal_data(self):
        """Delete all personal data (email and phone number) from the database."""
        query: str = 'UPDATE `joueur` SET Tel = ?, EMail = ?'
        self._execute(
            query,
            (
                '',
                '',
            ),
        )

    def remove_zpbs_if_no_pairings(self):
        """Delete all ZPBs if no pairings are found (at any round).
        This fixes a display issue on the FFE website."""
        condition: str = ' OR '.join(
            f'`{RoundFields(round_).opponent}` IS NOT NULL' for round_ in range(1, 25)
        )
        query: str = f'SELECT COUNT(`Ref`) FROM `joueur` WHERE {condition}'
        self._execute(query)
        if self._fetchval() == 0:
            logger.info('Deleting ZPBs...')
            data: dict[str, str | int | None] = {}
            for round_ in range(1, 25):
                rf = RoundFields(round_)
                data |= {
                    rf.color: UNPLAYED_COLOR,
                    rf.opponent: None,
                    rf.result: Result.NO_RESULT.to_papi_value,
                }
            actions: str = ', '.join([f'`{key}` = ?' for key in data])
            query: str = f'UPDATE `joueur` SET {actions} WHERE Ref <> ?'
            params = tuple(data.values()) + (EXEMPT_PLAYER_ID,)
            self._execute(query, params)
            logger.info('Done.')
        else:
            logger.info('No ZPBs to delete.')

    def get_checked_in_player_count(self) -> int:
        """Return the number players already checked in."""
        query: str = 'SELECT COUNT(`Ref`) FROM `joueur` WHERE `Pointe` AND `Ref` > ?'
        self._execute(query, (EXEMPT_PLAYER_ID,))
        return self._fetchval()

    def check_in_player(self, player_id: int, check_in: bool):
        """Toggles the check in status of the player, depending on `check_in`."""
        self._execute(
            'UPDATE `joueur` SET Pointe = ? WHERE Ref = ?',
            (check_in, Player.player_papi_id_from_sharly_chess_id(player_id)),
        )

    def open_check_in(self, round_: int):
        """Sets all the present players (at the given round) as not checked-in."""
        self._execute(
            f'UPDATE `joueur` SET Pointe = ? WHERE '
            f'Ref <> ? AND {RoundFields(round_).color} <> ?',
            (False, EXEMPT_PLAYER_ID, BYE_COLOR),
        )

    def close_check_in(self, round_: int, last_round: int | None):
        """Sets all the players present at the given round as not checked-in for the given round
        (and for the rest of the rounds if last_round is set)."""
        round_color = RoundFields(round_).color
        data: dict[str, str | int | float | None] = {
            round_color: BYE_COLOR,
        }
        if last_round:
            data |= {
                RoundFields(r).color: BYE_COLOR for r in range(round_, last_round + 1)
            }
        actions: str = ', '.join([f'`{key}` = ?' for key in data.keys()])
        self._execute(
            f'UPDATE `joueur` SET {actions} WHERE (Ref <> ?) '
            f'AND NOT (`Pointe`) AND (`{round_color}` = ?)',
            tuple(list(data.values())) + (EXEMPT_PLAYER_ID, UNPLAYED_COLOR),
        )
