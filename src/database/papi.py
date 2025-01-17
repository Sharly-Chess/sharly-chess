import re
from contextlib import suppress
from datetime import datetime, timedelta, date
from itertools import product
from logging import Logger
from pathlib import Path
from typing import NamedTuple, Pattern

from common.logger import get_logger
from data.chessevent_player import ChessEventPlayer
from data.chessevent_tournament import ChessEventTournament
from data.pairing import Pairing
from data.player import Player
from data.util import Result, TournamentPairing, PlayerGender, PlayerTitle, TournamentRating, PlayerFFELicence, \
    PlayerRatingType, BoardColor
from database.access import AccessDatabase

logger: Logger = get_logger()


class TournamentInfo(NamedTuple):
    """Basic tournament information tuple."""
    rounds: int
    pairing: TournamentPairing
    rating: TournamentRating
    rating_limit1: int
    rating_limit2: int


class PapiDatabase(AccessDatabase):
    """The database class, using the Papi format of the French Chess Federation
    Tournament manager."""

    def __init__(self, file: Path, write: bool = False):
        super().__init__(file, write)
        self.date_of_birth_pattern: Pattern = re.compile(r'^\d{1,2}/\d{1,2}/(\d{1,4})$')

    def commit(self):
        self._commit()

    def _read_var(self, name: str) -> str:
        query: str = 'SELECT `Value` FROM `info` WHERE `Variable` = ?'
        self._execute(query, (name,))
        return self._fetchval()

    def read_info(self) -> TournamentInfo:
        """Reads the database and returns basic information about the
        tournament."""
        rounds: int = int(self._read_var('NbrRondes'))
        pairing: TournamentPairing = TournamentPairing.from_papi_value(self._read_var('Pairing'))
        rating: TournamentRating = TournamentRating.from_papi_value(self._read_var('ClassElo'))
        rating_limit1: int = int(self._read_var('EloBase1'))
        rating_limit2: int = int(self._read_var('EloBase2'))
        return TournamentInfo(rounds, pairing, rating, rating_limit1, rating_limit2)

    def read_player_dict(
            self, player_papi_id: int
    ) -> dict[str, str | int | float | None]:
        """Reads the database and return the information of the player with the given Papi ID. """
        self._execute(f'SELECT * FROM joueur WHERE Ref = ?', (player_papi_id, ))
        return self._fetchone()

    def delete_player(
            self, player_papi_id: int,
            return_deleted_data: bool = False,
    ) -> dict[str, str | int | float | None] | None:
        """Reads the database and fetches the information of the player with the given Papi ID,
        returns Papi ID of the deleted player if needed. """
        data: dict[str, str | int | float | None] | None = None
        if return_deleted_data:
            data = self.read_player_dict(player_papi_id)
        self._execute(f'DELETE FROM joueur WHERE Ref = ?', (player_papi_id, ))
        return data

    @property
    def next_player_papi_id(self) -> int:
        """Returns the next Papi ID to use when adding a player to the database. """
        self._execute(f'SELECT Max(Ref) AS max FROM joueur')
        return self._fetchone()['max'] + 1

    def write_player_dict(
            self,
            data: dict[str, str | int | float | None],
    ) -> int:
        """Writes the information of a Papi player extracted from another database to this database,
        returns the papi_id. """
        field_names: list[str] = list(data.keys())
        params: tuple = tuple([data[field] for field in field_names])
        fields = ', '.join(f'`{f}`' for f in field_names)
        values = ', '.join(['?'] * len(field_names))
        self._execute(f'INSERT INTO `joueur`({fields}) VALUES ({values})', tuple(params))
        return data['Ref']

    def update_player(self, player: Player):
        """Updates the event database with the information in the provided player."""
        fields: list[str] = ([
            'RefFFE',
            'Nom',
            'Prenom',
            'NeLe',
            'Sexe',
            'FideTitre',
            'FideCode',
            'Federation',
            'Ligue',
            'Club',
            'AffType',
            'NrFFE',
            'EMail',
            'Tel',
            'Commentaire',
            'InscriptionDu',
            'InscriptionRegle',
        ] + [
           tr.papi_value_field for tr in TournamentRating
        ] + [
            tr.papi_type_field for tr in TournamentRating
        ])
        params = [
            player.ffe_id,
            player.last_name,
            player.first_name,
            self._date_to_papi_date(player.date_of_birth),
            player.gender.to_papi_value,
            player.title.to_papi_value,
            player.fide_id,
            player.federation,
            player.league,
            player.club,
            player.ffe_licence.to_papi_value,
            player.ffe_licence_number,
            player.mail,
            player.phone,
            player.comment,
            player.owed,
            player.paid,
        ] + [
            player.ratings[tr] for tr in TournamentRating
        ] + [
            player.rating_types[tr].to_papi_value for tr in TournamentRating
        ] + [
            player.ref_id,
        ]
        field_sets = (f"`{f}` = ?" for f in fields)
        self._execute(f'UPDATE `joueur` SET {", ".join(field_sets)} WHERE `Ref` = ?', tuple(params))

    def read_players(self, tournament_id: int, tournament_rating: TournamentRating, rounds: int) -> dict[int, Player]:
        """Reads the database and fetches the Player identification, pairings and results.
        The tournament_id is used to make the players' id unique for an event. """
        players: dict[int, Player] = {}
        player_fields: list[str] = [
            'Ref', 'RefFFE', 'Nom', 'Prenom', 'NeLe', 'Sexe', 'EMail', 'Tel', 'Commentaire', 'InscriptionDu',
            'InscriptionRegle', 'FideTitre', 'Fixe',
        ] + [
            tr.papi_value_field for tr in TournamentRating
        ] + [
            tr.papi_type_field for tr in TournamentRating
        ] + [
            'Pointe', 'AffType', 'NrFFE', 'Federation', 'Ligue', 'Club', 'FideCode',
        ]
        for rd, suffix in product(range(1, rounds + 1), ['Cl', 'Adv', 'Res']):
            player_fields.append(f'Rd{rd:0>2}{suffix}')
        query: str = f'SELECT {", ".join(player_fields)} FROM joueur WHERE Ref <> 1 ORDER BY Ref'
        self._execute(query)
        for row in self._fetchall():
            pairings: dict[int, Pairing] = {}
            for round_ in range(1, rounds + 1):
                round_str = f'Rd{round_:0>2}'
                color_str: str = row[f'{round_str}Cl']
                color: BoardColor | None = None
                with suppress(ValueError):
                    color = BoardColor.from_papi_value(color)
                opponent_papi_id: int | None = row[f'{round_str}Adv']
                pairings[round_] = Pairing(
                    color,
                    Player.player_papi_web_id_from_papi_id(tournament_id, opponent_papi_id)
                    if opponent_papi_id else None,
                    Result.from_papi_value(
                        row[f'{round_str}Res'],
                        opponent_papi_id is None,
                        opponent_papi_id == 1,
                        color_str == 'F'))
            player_papi_web_id: int = Player.player_papi_web_id_from_papi_id(tournament_id, row['Ref'])
            fide_id: int | None = None
            if row['FideCode']:
                fide_id = int(str(row['FideCode']).strip())
            players[player_papi_web_id] = Player(
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
                ratings={
                    tr: row[tr.papi_value_field] or 0 for tr in TournamentRating
                },
                rating_types={
                    tr: PlayerRatingType.from_papi_value(row[tr.papi_type_field])
                    for tr in TournamentRating
                },
                fide_id=fide_id,
                ffe_id=row['RefFFE'] or '',
                ffe_licence=PlayerFFELicence.from_papi_value(row['AffType'] or ''),
                ffe_licence_number=row['NrFFE'] or '',
                federation=row['Federation'] or '',
                league=row['Ligue'] or '',
                club=row['Club'] or '',
                fixed=row['Fixe'] or 0,
                check_in=row['Pointe'] or False,
                pairings=pairings,
            )
        return players

    def add_board_result(self, player_papi_id: int, round_: int, result: Result):
        """Writes the given result to the database."""
        query: str = f'UPDATE `joueur` SET `Rd{round_:0>2}Res` = ? WHERE `Ref` = ?'
        self._execute(query, (result.value, player_papi_id,))

    def remove_board_result(self, player_papi_id: int, round_: int):
        """Writes the empty result for the given player in the database."""
        query: str = f'UPDATE `joueur` SET `Rd{round_:0>2}Res` = 0 WHERE `Ref` = ?'
        self._execute(query, (player_papi_id,))

    @staticmethod
    def _timestamp_to_papi_date(ts: float) -> str:
        dt: datetime
        if ts >= 0:
            dt = datetime.fromtimestamp(ts)
        else:
            dt = datetime(1970, 1, 1) + timedelta(seconds=ts)
        return dt.strftime('%d/%m/%Y')

    @staticmethod
    def _date_to_papi_date(d: date | None) -> str | None:
        return datetime(d.year, d.month, d.day).strftime('%d/%m/%Y') if d else None

    def __write_var(self, name: str, value):
        query: str = 'UPDATE `info` SET `Value` = ? WHERE `Variable` = ?'
        self._execute(query, (value, name, ))

    def write_chessevent_info(self, chessevent_tournament: ChessEventTournament):
        """Creates the tournament data from the ChessEvent Tournament data."""
        default_rounds: int = 7
        if not chessevent_tournament.rounds:
            logger.warning(
                'Number of rounds not set in ChessEvent, %d set by default.',
                default_rounds)
            chessevent_tournament.rounds = default_rounds
        data: dict[str, str | int] = {
            'Nom': chessevent_tournament.name,
            'Genre': chessevent_tournament.type.to_papi_value,
            'NbrRondes': chessevent_tournament.rounds,
            'Pairing': chessevent_tournament.pairing.to_papi_value,
            'Cadence': chessevent_tournament.time_control,
            'Lieu': chessevent_tournament.location,
            'Arbitre': chessevent_tournament.arbiter,
            'DateDebut': self._timestamp_to_papi_date(chessevent_tournament.start),
            'DateFin': self._timestamp_to_papi_date(chessevent_tournament.end),
            'Dep1': chessevent_tournament.tie_breaks[0].to_papi_value,
            'Dep2': chessevent_tournament.tie_breaks[1].to_papi_value,
            'Dep3': chessevent_tournament.tie_breaks[2].to_papi_value,
            'ClassElo': chessevent_tournament.rating.to_papi_value,
            'Homologation': str(chessevent_tournament.ffe_id),
        }
        # queries: list[str] = []
        # params: list[str] = []
        # for name, value in data.items():
        #     queries.append('UPDATE `info` SET `Value` = ? WHERE `Variable` = ?')
        #     params.extend([value, name, ])
        # self._execute('; '.join(queries), tuple(params))
        for name, value in data.items():
            query: str = 'UPDATE `info` SET `Value` = ? WHERE `Variable` = ?'
            self._execute(query, (value, name, ))

    def add_chessevent_player(self, player_papi_id: int, player: ChessEventPlayer, check_in_started: bool):
        """Creates a player in the database from the given ChessEvent player.
        If the player is not checked in when `check_in_started` is True,
        removes the player from play for subsequent rounds which are not
        specifically unplayed rounds."""
        data: dict[str, str | int | float | None] = {
            'Ref': player_papi_id,
            'RefFFE': player.ffe_id,
            'NrFFE': player.ffe_license_number if player.ffe_license_number else None,
            'Nom': player.last_name,
            'Prenom': player.first_name,
            'Sexe': player.gender.to_papi_value,
            'NeLe': self._timestamp_to_papi_date(player.birth),
            'Cat': player.category.to_papi_value,
            'AffType': player.ffe_license.to_papi_value,
            'Elo': player.standard_rating,
            'Rapide': player.rapid_rating,
            'Blitz': player.blitz_rating,
            'Federation': player.federation,
            'ClubRef': player.ffe_club_id,
            'Club': player.ffe_club,
            'Ligue': player.ffe_league,
            'Fide': player.standard_rating_type.to_papi_value,
            'RapideFide': player.rapide_rating_type.to_papi_value,
            'BlitzFide': player.blitz_rating_type.to_papi_value,
            'FideCode': player.fide_id if player.fide_id else None,
            'FideTitre': player.title.to_papi_value,
            'Pointe': check_in_started and player.check_in,
            'InscriptionRegle': player.paid,
            'InscriptionDu': player.fee,
            'Tel': player.phone,
            'EMail': player.email,
            'Fixe': player.board,
            'Flotteur': 'X' * 24,
            'Pts': 0,
            'PtA': 0,
        }
        for round_ in range(1, 25):
            data[f'Rd{round_:0>2}Adv'] = None
            if round_ not in player.skipped_rounds:
                data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                if player.check_in or not check_in_started:
                    data[f'Rd{round_:0>2}Cl'] = 'R'
                else:
                    data[f'Rd{round_:0>2}Cl'] = 'F'
            else:
                data[f'Rd{round_:0>2}Cl'] = 'F'
                match player.skipped_rounds[round_]:
                    case 0.0:
                        data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                    case 0.5:
                        data[f'Rd{round_:0>2}Res'] = Result.HALF_POINT_BYE.to_papi_value
                    case _:
                        raise ValueError
        query: str = f'INSERT INTO `joueur`({", ".join(data.keys())}) VALUES ({", ".join(["?"] * len(data))})'
        params = tuple(data.values())
        self._execute(query, params)

    def delete_players_personal_data(self):
        """Delete all personal data (email and phone number) from the database."""
        query: str = 'UPDATE `joueur` SET Tel = ?, EMail = ?'
        self._execute(query, ('', '', ))

    def remove_forfeits_if_no_pairings(self):
        """Delete all forfeits if no pairing is found (at round #1).
        This fixes a display issue on the FFE website."""
        query: str = 'SELECT COUNT(`Ref`) FROM `joueur` WHERE `Rd01Adv` IS NOT NULL'
        self._execute(query)
        if self._fetchval() == 0:
            logger.info('Deleting forfeits...')
            data: dict[str, str | int | None] = {}
            for round_ in range(1, 25):
                data[f'Rd{round_:0>2}Adv'] = None
                data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                data[f'Rd{round_:0>2}Cl'] = 'R'
            actions: str = ', '.join([f'`{key}` = ?' for key in data.keys()])
            query: str = f'UPDATE `joueur` SET {actions} WHERE Ref > 1'
            params = tuple(data.values())
            self._execute(query, params)
            logger.info('Done.')
        else:
            logger.info('No forfeits to delete.')

    def get_checked_in_players_number(self) -> int:
        """Return the number players already checked in."""
        query: str = 'SELECT COUNT(`Ref`) FROM `joueur` WHERE `Pointe` AND `Ref` > 1'
        self._execute(query)
        return self._fetchval()

    def _check_in_player(self, player_papi_id: int, tournament_skipped_rounds_dict: dict[int, dict[int, float]]):
        logger.debug('Checking in player %d', player_papi_id)
        checked_in_players_number: int = self.get_checked_in_players_number()
        player_skipped_rounds: dict[int, float]
        if not checked_in_players_number:
            logger.debug('Setting all players forfeit for all rounds (except player [%d])', player_papi_id)
            data: dict[str, str | int | float | None] = {
            }
            for round_ in range(1, 25):
                data[f'Rd{round_:0>2}Adv'] = None
                data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                data[f'Rd{round_:0>2}Cl'] = 'F'
            actions: str = ', '.join([f'`{key}` = ?' for key in data.keys()])
            query: str = f'UPDATE `joueur` SET {actions} WHERE Ref NOT IN (1, ?)'
            params = tuple(list(data.values()) + [player_papi_id, ])
            self._execute(query, params)
            # set byes (no need for forfeits, already set)
            player_skipped_rounds: dict[int, float] = tournament_skipped_rounds_dict.get(player_papi_id, {})
            for other_player_id in tournament_skipped_rounds_dict:
                if other_player_id != player_papi_id:
                    data: dict[str, str | int | float | None] = {
                    }
                    for round_, result in tournament_skipped_rounds_dict[other_player_id].items():
                        if round_ in range(1, 25):
                            match result:
                                case 0.0:
                                    pass
                                case 0.5:
                                    data[f'Rd{round_:0>2}Res'] = Result.HALF_POINT_BYE.to_papi_value
                                case _:
                                    raise ValueError
                    if data:
                        logger.debug('Setting byes for player [%d]: %s', other_player_id, data)
                        actions: str = ', '.join([f'`{key}` = ?' for key in data.keys()])
                        query: str = f'UPDATE `joueur` SET {actions} WHERE Ref = ?'
                        params = tuple(list(data.values()) + [other_player_id, ])
                        self._execute(query, params)
                    else:
                        logger.debug('No byes for player %d', other_player_id)
                else:
                    logger.debug('do skipped round for player %d', other_player_id)
        else:
            player_skipped_rounds = tournament_skipped_rounds_dict.get(player_papi_id, {})
        # Set the player checked in and unpaired for all rounds
        logger.debug('Byes and forfeits for player [%d]: %s', player_papi_id, player_skipped_rounds)
        logger.debug('Setting player [%d] checked in and unpaired for all rounds...', player_papi_id)
        data: dict[str, str | int | float | None] = {
            'Pointe': True,
        }
        for round_ in range(1, 25):
            data[f'Rd{round_:0>2}Adv'] = None
            if round_ not in player_skipped_rounds:
                data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                data[f'Rd{round_:0>2}Cl'] = 'R'
            else:
                data[f'Rd{round_:0>2}Cl'] = 'F'
                match player_skipped_rounds[round_]:
                    case 0.0:
                        data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                    case 0.5:
                        data[f'Rd{round_:0>2}Res'] = Result.HALF_POINT_BYE.to_papi_value
                    case _:
                        raise ValueError
        actions: str = ', '.join([f'`{key}` = ?' for key in data.keys()])
        query: str = f'UPDATE `joueur` SET {actions} WHERE Ref = ?'
        params = tuple(data.values()) + (player_papi_id, )
        self._execute(query, params)

    def _check_out_player(self, player_papi_id: int, tournament_skipped_rounds_dict: dict[int, dict[int, float]]):
        logger.debug('Checking out player [%d]...', player_papi_id)
        checked_in_players_number: int = self.get_checked_in_players_number()
        if checked_in_players_number == 1:
            logger.debug('Setting all players unpaired for all rounds...')
            data: dict[str, str | int | float | None] = {
                'Pointe': False,
            }
            for round_ in range(1, 25):
                data[f'Rd{round_:0>2}Adv'] = None
                data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                data[f'Rd{round_:0>2}Cl'] = 'R'
            actions: str = ', '.join([f'`{key}` = ?' for key in data.keys()])
            query: str = f'UPDATE `joueur` SET {actions} WHERE Ref > 1'
            params = tuple(list(data.values()))
            self._execute(query, params)
            # set byes and forfeits
            for other_player_id, player_skipped_rounds in tournament_skipped_rounds_dict.items():
                other_player_papi_id: int = Player.player_papi_id_from_papi_web_id(other_player_id)
                data: dict[str, str | int | float | None] = {
                }
                for round_, score in player_skipped_rounds.items():
                    if round_ in range(1, 25):
                        data[f'Rd{round_:0>2}Cl'] = 'F'
                        match score:
                            case 0.0:
                                data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                                pass
                            case 0.5:
                                data[f'Rd{round_:0>2}Res'] = Result.HALF_POINT_BYE.to_papi_value
                            case _:
                                raise ValueError
                if data:
                    actions: str = ', '.join([f'`{key}` = ?' for key in data.keys()])
                    query: str = f'UPDATE `joueur` SET {actions} WHERE Ref = ?'
                    params = tuple(list(data.values()) + [other_player_papi_id, ])
                    self._execute(query, params)
        else:
            logger.debug('Setting player [%d] checked out and forfeit for all rounds...', player_papi_id)
            player_skipped_rounds: dict[int, float] = tournament_skipped_rounds_dict.get(player_papi_id, {})
            data: dict[str, str | int | float | None] = {
                'Pointe': False,
            }
            for round_ in range(1, 25):
                data[f'Rd{round_:0>2}Adv'] = None
                data[f'Rd{round_:0>2}Cl'] = 'F'
                if round_ not in player_skipped_rounds:
                    data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                else:
                    match player_skipped_rounds[round_]:
                        case 0.0:
                            data[f'Rd{round_:0>2}Res'] = Result.NO_RESULT.to_papi_value
                        case 0.5:
                            data[f'Rd{round_:0>2}Res'] = Result.HALF_POINT_BYE.to_papi_value
                        case _:
                            raise ValueError
            actions: str = ', '.join([f'`{key}` = ?' for key in data.keys()])
            query: str = f'UPDATE `joueur` SET {actions} WHERE Ref = ?'
            params = tuple(list(data.values()) + [player_papi_id, ])
            self._execute(query, params)
        logger.debug('Done.')

    def check_in_player(self, player_id: int, check_in: bool, skipped_rounds_dict: dict[int, dict[int, float]]):
        """Toggles the check in status of the player, depending on `check_in`.
        Takes into account the given `skipped_rounds_dict`."""
        player_papi_id: int = Player.player_papi_id_from_papi_web_id(player_id)
        if check_in:
            self._check_in_player(player_papi_id, skipped_rounds_dict)
        else:
            self._check_out_player(player_papi_id, skipped_rounds_dict)

    def open_check_in(self, round: int):
        """Sets all the present players (at the given round) as not checked-in. """
        data: dict[str, str | int | float | None] = {
            'Pointe': False,
        }
        actions: str = ', '.join([f'`{key}` = ?' for key in data.keys()])
        query: str = f'UPDATE `joueur` SET {actions} WHERE Ref > 1 AND Rd{round:0>2}Cl <> ?'
        params = tuple(list(data.values()) + ['F', ])
        self._execute(query, params)

    def close_check_in(self, round: int, last_round: int | None):
        """Sets all the players present at the given round as not checked-in for the given round
        (and for the rest of the rounds if last_round is set). """
        data: dict[str, str | int | float | None] = {
            f'Rd{round:0>2}Cl': 'F',
        }
        if last_round:
            data |= {
                f'Rd{r:0>2}Cl': 'F' for r in range(round, last_round + 1)
            }
        actions: str = ', '.join([f'`{key}` = ?' for key in data.keys()])
        query: str = f'UPDATE `joueur` SET {actions} WHERE (Ref > 1) AND NOT (`Pointe`) AND (`Rd{round:0>2}Cl` = ?)'
        params = tuple(list(data.values()) + ['R', ])
        self._execute(query, params)


