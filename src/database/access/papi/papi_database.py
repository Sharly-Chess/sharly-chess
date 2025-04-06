import re
from datetime import datetime, timedelta, date
from itertools import product
from logging import Logger
from pathlib import Path
from typing import NamedTuple, Pattern

from common.logger import get_logger
from data.pairing import Pairing
from data.player import Player, Federation, Club
from data.tie_breaks import TieBreak, PapiTieBreakManager
from utils.enum import (
    Result,
    TournamentPairing,
    PlayerGender,
    PlayerTitle,
    TournamentRating,
    PlayerRatingType,
    BoardColor,
    PointValueType,
)
from database.access.access_database import AccessDatabase
from database.access.papi.papi_template import create_empty_papi_database
from plugins.manager import plugin_manager

logger: Logger = get_logger()


class TournamentInfo(NamedTuple):
    """Basic tournament information tuple."""

    rounds: int
    pairing: TournamentPairing
    rating: TournamentRating
    rating_limit1: int
    rating_limit2: int
    tie_breaks: list[TieBreak]
    point_value_type: PointValueType
    location: str
    start_date: str
    end_date: str
    arbiter: str


class PapiDatabase(AccessDatabase):
    """The database class, using the Papi format of the French Chess Federation
    Tournament manager."""

    def __init__(self, file: Path, write: bool = False):
        super().__init__(file, write)
        self.date_of_birth_pattern: Pattern = re.compile(r'^\d{1,2}/\d{1,2}/(\d{1,4})$')

    def create_empty(self):
        assert not self.file.exists()
        create_empty_papi_database(self.file)

    def commit(self):
        self._commit()

    def _read_var(self, name: str) -> str:
        query: str = 'SELECT `Value` FROM `info` WHERE `Variable` = ?'
        self._execute(query, (name,))
        return self._fetchval()

    def _update_var(self, name: str, value: str | int):
        query: str = 'UPDATE `info` SET `Value` = ? WHERE `Variable` = ?'
        self._execute(query, (value, name))

    def read_info(self) -> TournamentInfo:
        """Reads the database and returns basic information about the
        tournament."""
        rounds: int = int(self._read_var('NbrRondes'))
        pairing: TournamentPairing = TournamentPairing.from_papi_value(
            self._read_var('Pairing')
        )
        rating: TournamentRating = TournamentRating.from_papi_value(
            self._read_var('ClassElo')
        )
        rating_limit1: int = int(self._read_var('EloBase1'))
        rating_limit2: int = int(self._read_var('EloBase2'))
        tie_break_type_by_id = PapiTieBreakManager.type_by_papi_id()
        tie_breaks: list[TieBreak] = []
        for index in range(1, 4):
            papi_id = self._read_var(f'Dep{index}')
            if tie_break_type := tie_break_type_by_id.get(papi_id, None):
                tie_breaks.append(tie_break_type())
        point_value_type: PointValueType = PointValueType.from_papi_value(
            self._read_var('DecomptePoints')
        )
        location: str = self._read_var('Lieu')
        start_date: str = self._read_var('DateDebut')
        end_date: str = self._read_var('DateFin')
        arbiter: str = self._read_var('Arbitre')
        return TournamentInfo(
            rounds,
            pairing,
            rating,
            rating_limit1,
            rating_limit2,
            tie_breaks,
            point_value_type,
            location,
            start_date,
            end_date,
            arbiter,
        )

    def write_info(self, info: dict[str, str | int]):
        for name, value in info.items():
            self._update_var(name, value)

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
            ]
            + [player.ratings[tr] for tr in TournamentRating]
            + [player.rating_types[tr].to_papi_value for tr in TournamentRating]
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

    def update_player_pairing(self, player: Player, round_nb: int, pairing: Pairing):
        field_sets = [
            f'`Rd{round_nb:0>2}{field}` = ?' for field in ('Cl', 'Adv', 'Res')
        ]
        opponent_id = (
            Player.player_papi_id_from_papi_web_id(pairing.opponent_id)
            if pairing.opponent_id
            else None
        )
        result = (
            pairing.result.to_papi_value
            if pairing.result
            else Result.NO_RESULT.to_papi_value
        )
        self._execute(
            f'UPDATE `joueur` SET {", ".join(field_sets)} WHERE `Ref` = ?',
            (pairing.color_papi_value, opponent_id, result, player.ref_id),
        )

    def update_tie_breaks(self, tie_breaks: list[TieBreak]):
        for key in ('Dep1', 'Dep2', 'Dep3'):
            while tie_breaks and tie_breaks[0].papi_id is None:
                tie_breaks.pop(0)
            self._update_var(
                key, (tie_breaks.pop(0).papi_id or '') if tie_breaks else ''
            )

    def update_point_values(self, point_value_type: PointValueType):
        self._update_var('DecomptePoints', point_value_type.to_papi_value)

    def read_players(self, tournament_id: int, rounds: int) -> dict[int, Player]:
        """Reads the database and fetches the Player identification, pairings and results.
        The tournament_id is used to make the players' id unique for an event."""
        players: dict[int, Player] = {}

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
        for rd, suffix in product(range(1, rounds + 1), ['Cl', 'Adv', 'Res']):
            player_fields.append(f'Rd{rd:0>2}{suffix}')

        query: str = (
            f'SELECT {", ".join(player_fields)} FROM joueur WHERE Ref <> 1 ORDER BY Ref'
        )
        self._execute(query)
        for row in self._fetchall():
            pairings: dict[int, Pairing] = {}
            for round_ in range(1, rounds + 1):
                round_str = f'Rd{round_:0>2}'
                color: BoardColor | None
                color_str: str = row[f'{round_str}Cl']
                try:
                    color = BoardColor.from_papi_value(color_str)
                except ValueError:
                    color = None
                opponent_papi_id: int | None = row[f'{round_str}Adv']
                pairings[round_] = Pairing(
                    color,
                    Player.player_papi_web_id_from_papi_id(
                        tournament_id, opponent_papi_id
                    )
                    if opponent_papi_id and opponent_papi_id != 1
                    else None,
                    Result.from_papi_value(
                        row[f'{round_str}Res'],
                        opponent_papi_id is None,
                        opponent_papi_id == 1,
                        color_str == 'F',
                    ),
                )
            player_papi_web_id: int = Player.player_papi_web_id_from_papi_id(
                tournament_id, row['Ref']
            )
            fide_id: int | None = None
            if row['FideCode']:
                fide_id = int(str(row['FideCode']).strip())
            player = Player(
                id=player_papi_web_id,
                last_name=row['Nom'] or '',
                first_name=row['Prenom'] or '',
                date_of_birth=row['NeLe'].date() if row['NeLe'] else None,
                gender=PlayerGender.from_papi_value(row['Sexe'] or ''),
                mail=row['EMail'] or '',
                phone=row['Tel'] or '',
                comment=row['Commentaire'] or '',
                owed=float(row['InscriptionDu']) or 0.0,
                paid=float(row['InscriptionRegle']) or 0.0,
                title=PlayerTitle.from_papi_value(row['FideTitre'] or ''),
                ratings={tr: row[tr.papi_value_field] or 0 for tr in TournamentRating},
                rating_types={
                    tr: PlayerRatingType.from_papi_value(row[tr.papi_type_field])
                    for tr in TournamentRating
                },
                fide_id=fide_id,
                federation=Federation(row['Federation'] or ''),
                club=Club(row['Club'] or ''),
                fixed=row['Fixe'] or 0,
                check_in=row['Pointe'] or False,
                pairings=pairings,
            )

            plugin_manager.hook.augment_player_after_db_fetch(player=player, row=row)
            players[player_papi_web_id] = player
        return players

    def set_player_result(self, player_papi_id: int, round_: int, result: Result):
        """Writes the given result to the database."""
        data: dict[str, str | int] = {
            f'Rd{round_:0>2}Res': result.to_papi_value,
        }
        match result:
            case Result.NO_RESULT:
                data[f'Rd{round_:0>2}Cl'] = 'R'
            case Result.ZERO_POINT_BYE | Result.HALF_POINT_BYE | Result.FULL_POINT_BYE:
                data[f'Rd{round_:0>2}Cl'] = 'F'
        actions: str = ', '.join([f'`{key}` = ?' for key in data])
        query: str = f'UPDATE `joueur` SET {actions} WHERE `Ref` = ?'
        params: tuple = tuple(
            list(data.values())
            + [
                player_papi_id,
            ]
        )
        self._execute(query, params)

    def reset_player_result(self, player_papi_id: int, round_: int):
        """Writes the empty result for the given player in the database."""
        self.set_player_result(player_papi_id, round_, Result.NO_RESULT)

    @staticmethod
    def timestamp_to_papi_date(ts: float) -> str:
        dt: datetime
        if ts >= 0:
            dt = datetime.fromtimestamp(ts)
        else:
            dt = datetime(1970, 1, 1) + timedelta(seconds=ts)
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

    def remove_forfeits_if_no_pairings(self):
        """Delete all forfeits if no pairings are found (at any round).
        This fixes a display issue on the FFE website."""
        condition: str = ' OR '.join(
            f'`Rd{round_:0>2}Adv` IS NOT NULL' for round_ in range(1, 25)
        )
        query: str = f'SELECT COUNT(`Ref`) FROM `joueur` WHERE {condition}'
        self._execute(query)
        if self._fetchval() == 0:
            logger.info('Deleting forfeits...')
            data: dict[str, str | int | None] = {}
            for round_ in range(1, 25):
                data[f'Rd{round_:0>2}Adv'] = None
                data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                data[f'Rd{round_:0>2}Cl'] = 'R'
            actions: str = ', '.join([f'`{key}` = ?' for key in data])
            query: str = f'UPDATE `joueur` SET {actions} WHERE Ref > 1'
            params = tuple(data.values())
            self._execute(query, params)
            logger.info('Done.')
        else:
            logger.info('No forfeits to delete.')

    def get_checked_in_player_count(self) -> int:
        """Return the number players already checked in."""
        query: str = 'SELECT COUNT(`Ref`) FROM `joueur` WHERE `Pointe` AND `Ref` > 1'
        self._execute(query)
        return self._fetchval()

    def check_in_player(self, player_id: int, check_in: bool):
        """Toggles the check in status of the player, depending on `check_in`."""
        player_papi_id: int = Player.player_papi_id_from_papi_web_id(player_id)
        data: dict[str, str | int | float | None] = {
            'Pointe': check_in,
        }
        actions: str = ', '.join([f'`{key}` = ?' for key in data])
        query: str = f'UPDATE `joueur` SET {actions} WHERE Ref = ?'
        params = tuple(data.values()) + (player_papi_id,)
        self._execute(query, params)

    def open_check_in(self, round_: int):
        """Sets all the present players (at the given round) as not checked-in."""
        data: dict[str, str | int | float | None] = {
            'Pointe': False,
        }
        actions: str = ', '.join([f'`{key}` = ?' for key in data])
        query: str = (
            f'UPDATE `joueur` SET {actions} WHERE Ref > 1 AND Rd{round_:0>2}Cl <> ?'
        )
        params = tuple(
            list(data.values())
            + [
                'F',
            ]
        )
        self._execute(query, params)

    def close_check_in(self, round_: int, last_round: int | None):
        """Sets all the players present at the given round as not checked-in for the given round
        (and for the rest of the rounds if last_round is set)."""
        data: dict[str, str | int | float | None] = {
            f'Rd{round_:0>2}Cl': 'F',
        }
        if last_round:
            data |= {f'Rd{r:0>2}Cl': 'F' for r in range(round_, last_round + 1)}
        actions: str = ', '.join([f'`{key}` = ?' for key in data.keys()])
        query: str = f'UPDATE `joueur` SET {actions} WHERE (Ref > 1) AND NOT (`Pointe`) AND (`Rd{round_:0>2}Cl` = ?)'
        params = tuple(
            list(data.values())
            + [
                'R',
            ]
        )
        self._execute(query, params)
