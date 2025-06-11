from collections.abc import AsyncIterator
from contextlib import suppress
from logging import Logger
from pathlib import Path
from typing import Any

from common.exception import SharlyChessException
from common.i18n import _
from common.logger import get_logger
from common.network import NetworkMonitor
from data.player import Player, Federation, Club, PlayerRating
from utils.enum import PlayerGender, PlayerTitle, TournamentRating, PlayerRatingType
from database.sql_server.sql_server import SqlServer, SqlServerCredentials
from plugins import PLUGINS_DIR
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.utils import PlayerFFELicence

logger: Logger = get_logger()


class FFESqlServer(SqlServer):
    CREDENTIALS_FILE: Path = PLUGINS_DIR / 'ffe' / '.credentials'

    def __init__(
        self,
    ):
        super().__init__(self.CREDENTIALS_FILE, timeout=3)
        if not NetworkMonitor.connected():
            error: str = _('Not connected to internet')
            logger.error(error)
            raise SharlyChessException(error)

    @classmethod
    def dump_credentials(
        cls,
        host: str,
        user: str,
        password: str,
        database: str,
    ):
        SqlServerCredentials.dump(
            cls.CREDENTIALS_FILE,
            host,
            user,
            password,
            database,
        )

    PLAYER_FIELDS: tuple[str, ...] = (
        'Ref',
        'NrFFE',
        'Nom',
        'Prenom',
        'Sexe',
        'NeLe',
        'Cat',
        # not allowed: 'EC', 'Adresse', 'CP', 'TelDom', 'TelBur', 'TelPort', 'Fax', 'EMail',
        'Federation',
        'ClubRef',
        # not allowed: 'OldClubRef', 'Mute',
        'Elo',
        # not allowed: 'Elo10', 'Fide10', 'Elo01', 'Fide01',
        # not needed 'Elo03',
        'Fide03',  # RapideFide
        'Elo06',  # Blitz
        'Fide06',  # BlitzFide
        'Rapide',
        # not allowed: 'Perf', 'NbrParties', 'FideNbrParties',
        'Fide',
        'FideCode',
        'FideTitre',
        'AffType',
        # not needed 'Actif',
        # not allowed: 'BordereauRef', 'OldAffType', 'OldBordereauRef',
        # not allowed: 'Suspendu', 'MuteState', 'AJoue',
        # not allowed: 'Revue', 'RevueDu', 'RevueDuParClub', 'RevueDebut', 'NewsLetter',
        # not allowed: 'Password', 'MaJ',
    )

    CLUB_FIELDS: tuple[str, ...] = (
        # unused 'Ref',
        # unused 'NrFFE',
        'Nom',
        # not allowed: 'Intitule',
        'Commune',
        # not allowed: 'CommuneRef', 'ComiteRef',
        'Ligue',
        # not allowed: 'Adresse', 'CP', 'SalleAdresse', 'SalleCP', 'Latitude', 'Longitude',
        # not allowed: 'Tel', 'Fax', 'EMail', 'URL',
        # not needed 'Actif',
        # not allowed: 'Ouverture', 'President', 'Secretaire', 'Tresorier', 'Technique', 'Jeune',
        # not allowed: 'WebAdmin', 'WebAdminEMail', 'WebAutorisation',
        # not allowed: 'Repport', 'Nouveau', 'Electeur', 'Situation', 'PrefNr', 'PrefDate', 'Prefecture',
        # not allowed: 'NbrAffPrecedent', 'NbrBPrecedent', 'NbrAffA', 'NbrAffB', 'NbrJourOuvre',
        # not allowed: 'DivisionAdulte', 'DivisionJeune', 'DivisionFeminine', 'Label', 'Imprimer',
        # not allowed: 'Edoc', 'Handicape', 'QPV', 'Palmares', 'Login', 'Password', 'MaJ',
    )

    @staticmethod
    def _get_player_from_row(row: dict[str, Any]) -> Player:
        return Player(
            id=0,
            first_name=row['Prenom'].title() if row['Prenom'] else '',
            last_name=row['Nom'].upper(),
            date_of_birth=row['NeLe'],
            gender=PlayerGender.from_papi_value(row['Sexe']),
            mail='',
            phone='',
            comment='',
            owed=0.0,
            paid=0.0,
            title=PlayerTitle.from_papi_value(row['FideTitre'] or ''),
            ratings={
                TournamentRating.STANDARD: PlayerRating(
                    row['Elo'], PlayerRatingType.from_papi_value(row['Fide'])
                ),
                TournamentRating.RAPID: PlayerRating(
                    row['Rapide'], PlayerRatingType.from_papi_value(row['Fide03'])
                ),
                TournamentRating.BLITZ: PlayerRating(
                    row['Elo06'], PlayerRatingType.from_papi_value(row['Fide06'])
                ),
            },
            fide_id=int(row['FideCode'].strip("' ")) if row['FideCode'] else 0,
            federation=Federation(row['Federation']),
            club=Club(row['ClubNom']) if row['ClubNom'] else None,
            fixed=0,
            check_in=False,  # not taken into account when updating/creating/deleting the player
            pairings={},  # Pairings are read from Papi but not used
            tournament=None,
            plugin_data={
                PLUGIN_NAME: {
                    'ffe_id': row['Ref'],
                    'ffe_licence': PlayerFFELicence.from_papi_value(row['AffType']),
                    'ffe_licence_number': row['NrFFE'],
                    'league': row['ClubLigue'],
                }
            },
        )

    def get_player_fields(self) -> list[str]:
        return [f'joueur.{f} AS {f}' for f in self.PLAYER_FIELDS]

    def get_club_fields(self) -> list[str]:
        return [f'club.{f} AS Club{f}' for f in self.CLUB_FIELDS]

    def get_empty_club_fields(self) -> list[str]:
        return [f"'' AS Club{f}" for f in self.CLUB_FIELDS]

    @staticmethod
    def string_matches_ffe_licence_number(string: str) -> str | None:
        return (
            string
            if string.isalnum()
            and len(string) == 6
            and string[0].isalpha()
            and string[1:].isdecimal()
            else None
        )

    @staticmethod
    def string_matches_fide_id(string: str) -> int | None:
        return int(string) if string.isdecimal() else None

    async def search_player(
        self,
        string: str,
        limit: int = 0,  # no limit set if no param or null param passed
    ) -> AsyncIterator[Player]:
        """Searches the SQL server for the given tokens, raises SharlyChessException on error."""
        # NOTE(Amaras): Quicken search if the string looks like a complete FFE
        # licence number, so that it skips a more complex request
        string = string.upper().strip()
        # TODO: fix magic number
        if ffe_licence_number := self.string_matches_ffe_licence_number(string):
            return await self.get_players_by_ffe_licence_number(
                [
                    ffe_licence_number,
                ]
            )
        if fide_id := self.string_matches_fide_id(string):
            return await self.get_players_by_fide_id(
                [
                    fide_id,
                ]
            )
        tokens: list[str] = string.split(' ')
        str_fields: tuple[tuple[str, str, str], ...] = (
            ('joueur.Nom', '%', '%'),
            ('joueur.Prenom', '', '%'),
            ('joueur.NrFFE', '', ''),
        )
        conditions: list[str] = []
        params: list[Any] = []
        for token in tokens:
            token_expressions: list[str] = [
                f'(UPPER({field[0]}) LIKE ?)' for field in str_fields
            ]
            token_params: list[str | int] = [
                f'{field[1]}{token}{field[2]}' for field in str_fields
            ]
            with suppress(ValueError):
                int_value = int(token.strip())
                token_expressions.append('(joueur.FideCode IN (?, ?))')
                token_params += [
                    str(int_value).rjust(8, '0').ljust(10, ' '),
                    f"'{int_value}'",
                ]
            conditions += [
                ' OR '.join(token_expressions),
            ]
            params += token_params
        condition: str = ' AND '.join(map(lambda c: f'({c})', conditions))
        order = ' OR '.join(
            [
                '(UPPER(joueur.Nom) LIKE ?)',
            ]
            * len(tokens)
        )
        params += [f'{token}%' for token in tokens]
        query: str = (
            f'SELECT {", ".join(self.get_player_fields() + self.get_club_fields())} '
            f'FROM joueur LEFT JOIN club on joueur.ClubRef = club.Ref '
            f'WHERE {condition} '
            f'ORDER BY (CASE WHEN {order} THEN 0 ELSE 1 END), Joueur.Nom, Joueur.Prenom'
        )
        if limit:
            query += ' OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY'
            params += [
                limit,
            ]
        await self.execute(
            query,
            tuple(params),
        )
        return (self._get_player_from_row(row) async for row in self.fetchall())

    async def _get_player_by_id(
        self,
        field: str,
        id_: int | str,
    ) -> Player | None:
        query: str = (
            f'SELECT {", ".join(self.get_player_fields() + self.get_club_fields())} '
            f'FROM joueur LEFT JOIN club on joueur.ClubRef = club.Ref WHERE {field} = ?'
        )
        await self.execute(
            query,
            (str(id_),),
        )
        if row := await self.fetchone():
            return self._get_player_from_row(row)
        else:
            return None

    async def get_player_by_ffe_id(
        self,
        player_ffe_id: int,
    ) -> Player | None:
        return await self._get_player_by_id('joueur.Ref', player_ffe_id)

    async def get_player_by_fide_id(
        self,
        player_fide_id: int,
    ) -> Player | None:
        return await self._get_player_by_id('joueur.FideCode', player_fide_id)

    async def get_players_by_ffe_licence_number(
        self,
        player_ffe_licence_numbers: list[str],
    ) -> AsyncIterator[Player]:
        query_array = ', '.join('?' for _ in player_ffe_licence_numbers)
        query: str = (
            f'SELECT {", ".join(self.get_player_fields() + self.get_club_fields())} '
            f'FROM joueur LEFT JOIN club on joueur.ClubRef = club.Ref '
            f'WHERE joueur.NrFFE IN ({query_array})'
        )
        await self.execute(query, tuple(player_ffe_licence_numbers))
        return (self._get_player_from_row(row) async for row in self.fetchall())

    async def get_players_by_fide_id(
        self,
        player_fide_ids: list[int],
    ) -> AsyncIterator[Player]:
        query: str = (
            f'SELECT {", ".join(self.get_player_fields() + self.get_club_fields())} '
            f'FROM joueur LEFT JOIN club on joueur.ClubRef = club.Ref '
            f'WHERE joueur.FideCode IN ({", ".join(["?"] * 2 * len(player_fide_ids))})'
        )
        await self.execute(
            query,
            tuple(
                str(player_fide_id).rjust(8, '0').ljust(10, ' ')
                for player_fide_id in player_fide_ids
            )
            + tuple(f"'{player_fide_id}'" for player_fide_id in player_fide_ids),
        )
        return (self._get_player_from_row(row) async for row in self.fetchall())
