import os.path
import zipfile
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from logging import Logger
from pathlib import Path
from typing import Iterator, Any, override

from requests import Response, get
from requests.exceptions import ConnectionError

from common import TMP_DIR
from common.i18n import _
from common.logger import get_logger
from data.player import Player, Federation, Club, PlayerRating
from database.sqlite.local_source_database import LocalSourceDatabase
from database.sqlite.local_source_database.actions import NotifOutdatedAction
from database.sqlite.local_source_database.delays import Days2OutdatedDelay
from utils.enum import (
    TournamentRating,
    PlayerRatingType,
    PlayerGender,
    PlayerTitle,
)
from database.sqlite.config.config_store import StoredLocalSourceDatabase

from plugins import ffe
from plugins.ffe import PLUGIN_NAME, PLUGIN_DIR
from plugins.ffe.ffe_access_database import FfeAccessDatabase
from plugins.ffe.utils import PlayerFFELicence
from database.sqlite.sqlite_database import SQLiteDatabase

logger: Logger = get_logger()


class FfeDatabase(LocalSourceDatabase):
    """
    The SQLite database class for FFE players. Usage:
    1. Check if the database exists and is up-to-date.
        If outdated, the outdate action is executed:
    FfeDatabase().check()
    2. Search the database:
    with FfeDatabase() as ffe_database:
        for player in ffe_database.search_player('my name'):
            ...
    """

    @staticmethod
    def static_id() -> str:
        return 'ffe'

    @staticmethod
    def static_name() -> str:
        return 'FFE'

    @property
    def _dir(self) -> Path:
        return ffe.TMP_DIR

    @property
    def legacy_path(self) -> Path | None:
        return TMP_DIR / self.file_name

    @property
    def _schema_file_path(self) -> Path:
        return PLUGIN_DIR / 'create_ffe.sql'

    @property
    def _source_file_path(self) -> Path:
        return ffe.TMP_DIR / 'Data.mdb'

    @override
    @property
    def default_stored_database(self) -> StoredLocalSourceDatabase:
        return StoredLocalSourceDatabase(
            name=self.id,
            outdate_delay=Days2OutdatedDelay.static_id(),
            outdate_action=NotifOutdatedAction.static_id(),
        )

    def _download_source_file(self) -> bool:
        ffe_database_url: str = 'https://www.echecs.asso.fr/Papi/PapiData.zip'
        local_zip_file: Path = ffe.TMP_DIR / os.path.basename(ffe_database_url)
        with suppress(FileNotFoundError):
            local_zip_file.unlink()
        try:
            response: Response = get(ffe_database_url, allow_redirects=True, timeout=5)
            if response.status_code != 200:
                logger.error(
                    self.log_prefix
                    + _('Could not download [{url}], error code [{code}].').format(
                        url=ffe_database_url, code=response.status_code
                    )
                )
                return False
        except ConnectionError as ex:
            logger.error(
                self.log_prefix
                + _('Could not download [{url}]: {error}.').format(
                    url=ffe_database_url, error=ex
                )
            )
            return False
        local_zip_file.write_bytes(response.content)
        if not local_zip_file.exists():
            logger.error(
                self.log_prefix
                + _('No data received from [{url}].').format(url=ffe_database_url)
            )
            return False
        self._source_file_path.unlink(missing_ok=True)
        with zipfile.ZipFile(local_zip_file, 'r') as zip_ref:
            zip_ref.extractall(ffe.TMP_DIR)
        local_zip_file.unlink()
        if not self._source_file_path.exists():
            logger.error(self.log_prefix + _('Could not unzip data.'))
            return False
        return True

    def _populate_from_source_file(self, database: SQLiteDatabase) -> bool:
        translations: dict[str, Callable[[Any], Any] | None] = {
            'ffe_id': None,
            'ffe_licence_number': lambda s: s.strip().upper() if s else None,
            'last_name': lambda s: s.strip().upper(),
            'first_name': lambda s: s.strip().title() if s else '',
            'gender': PlayerGender.from_papi_value,
            'date_of_birth': lambda dt: dt.date() if dt else None,
            'federation': None,
            'standard_rating': int,
            'rapid_rating': int,
            'blitz_rating': int,
            'standard_rating_type': PlayerRatingType.from_papi_value,
            'rapid_rating_type': PlayerRatingType.from_papi_value,
            'blitz_rating_type': PlayerRatingType.from_papi_value,
            'fide_id': lambda s: int(s.strip("' ")) if s else 0,
            'fide_title': PlayerTitle.from_papi_value,
            'ffe_licence': PlayerFFELicence.from_papi_value,
            'league': None,
            'city': None,
            'club': None,
        }
        column_names: list[str] = list(translations.keys())
        bindings: list[str] = [f':{column_name}' for column_name in column_names]
        escaped_column_names: list[str] = list(map(lambda s: f'`{s}`', column_names))
        query: str = (
            f'INSERT INTO player({", ".join(escaped_column_names)}) '
            f'VALUES({", ".join(bindings)})'
        )
        with FfeAccessDatabase(self._source_file_path) as ffe_access_database:
            with database:
                player_count: int = 0
                to_write: list[dict[str, Any]] = []
                data: dict[str, Any]
                for player_dict in ffe_access_database.read_player_dicts():
                    try:
                        data = {
                            field: player_dict[field]
                            if function is None
                            else function(player_dict[field])
                            for field, function in translations.items()
                        }
                        to_write.append(data)
                        player_count += 1
                        if player_count % 1000 == 0:
                            database.executemany(query, to_write)
                            to_write.clear()
                            if self.stop_event.is_set():
                                return False
                        if player_count % 100_000 == 0:
                            database.commit()

                    except ValueError:
                        logger.warning(
                            _(
                                'Error reading the following row '
                                '(player ignored): [{row}].'
                            ).format(row=player_dict)
                        )
                if to_write:
                    database.executemany(query, to_write)
                    database.commit()
        logger.info(
            self.log_prefix
            + _('{number} players written to the database.').format(number=player_count)
        )
        return True

    def _create_indexes(self):
        self.write = True
        with self:
            self.execute(
                'CREATE INDEX IF NOT EXISTS `player_last_name` ON `player`(`last_name` COLLATE NOCASE)'
            )
            self.execute(
                'CREATE INDEX IF NOT EXISTS `player_first_name` ON `player`(`first_name` COLLATE NOCASE)'
            )
            self.execute(
                'CREATE INDEX IF NOT EXISTS `player_fide_id` ON `player`(`fide_id`)'
            )
            self.execute(
                'CREATE INDEX IF NOT EXISTS `player_ffe_licence` ON `player`(`ffe_licence_number` COLLATE NOCASE)'
            )
            self.commit()

    @staticmethod
    def get_player_from_row(row: dict[str, Any]) -> Player:
        return Player(
            id=0,
            first_name=row['first_name'].title() if row['first_name'] else '',
            last_name=row['last_name'].upper(),
            date_of_birth=datetime.strptime(row['date_of_birth'], '%Y-%m-%d').date(),
            gender=PlayerGender(row['gender']),
            mail='',
            phone='',
            comment='',
            owed=0.0,
            paid=0.0,
            title=PlayerTitle(row['fide_title']),
            ratings={
                TournamentRating.STANDARD: PlayerRating(
                    row['standard_rating'],
                    PlayerRatingType(row['standard_rating_type']),
                ),
                TournamentRating.RAPID: PlayerRating(
                    row['rapid_rating'],
                    PlayerRatingType(row['rapid_rating_type']),
                ),
                TournamentRating.BLITZ: PlayerRating(
                    row['blitz_rating'],
                    PlayerRatingType(row['blitz_rating_type']),
                ),
            },
            fide_id=int(row['fide_id']) if row['fide_id'] else None,
            federation=Federation(row['federation']),
            club=Club(row['club']),
            fixed=0,
            check_in=False,  # not taken into account when updating/creating/deleting the player
            pairings={},  # Pairings are read from Papi but not used
            tournament=None,
            plugin_data={
                PLUGIN_NAME: {
                    'ffe_id': row['ffe_id'],
                    'ffe_licence': PlayerFFELicence(row['ffe_licence']),
                    'ffe_licence_number': row['ffe_licence_number'],
                    'league': row['league'],
                }
            },
        )

    def search_player(
        self,
        string: str,
        limit: int = 0,  # no limit set if no param or null param passed
    ) -> Iterator[Player]:
        tokens: list[str] = string.split(' ')
        str_fields: tuple[tuple[str, str, str], ...] = (
            ('last_name', '%', '%'),
            ('first_name', '', '%'),
            ('ffe_licence_number', '', ''),
        )
        int_fields: tuple[str, ...] = ('fide_id',)
        token_conditions: dict[str, str] = {}
        params: list[Any] = []
        for token in tokens:
            expressions = [f'({field[0]} LIKE ?)' for field in str_fields]
            params += [f'{field[1]}{token}{field[2]}' for field in str_fields]
            int_value: int
            with suppress(ValueError):
                int_value = int(token.strip())
                expressions += [f'({field} = ?)' for field in int_fields]
                params += [
                    int_value,
                ] * len(int_fields)
            token_conditions[token] = ' OR '.join(expressions)
        conditions: str = ' AND '.join(
            map(lambda condition: f'({condition})', token_conditions.values())
        )
        order_conditions = ' OR '.join(
            [
                '(last_name LIKE ?)',
            ]
            * len(tokens)
        )
        params += [f'{token}%' for token in tokens]
        query: str = f'SELECT * FROM player WHERE {conditions} ORDER BY (CASE WHEN {order_conditions} THEN 0 ELSE 1 END), last_name'
        if limit:
            query += ' LIMIT ?'
            params += [
                limit,
            ]
        self.execute(
            query,
            tuple(params),
        )
        return (self.get_player_from_row(row) for row in self.fetchall())

    def _get_player_by_id(
        self,
        field: str,
        id_: int,
    ) -> Player | None:
        self.execute(f'SELECT * FROM player WHERE {field} = ?', (id_,))
        if row := self.fetchone():
            return self.get_player_from_row(row)
        else:
            return None

    def get_player_by_ffe_id(
        self,
        player_ffe_id: int,
    ) -> Player | None:
        return self._get_player_by_id('ffe_id', player_ffe_id)

    def get_player_by_fide_id(
        self,
        player_fide_id: int,
    ) -> Player | None:
        return self._get_player_by_id('fide_id', player_fide_id)

    def get_players_by_ffe_licence_number(
        self, player_ffe_licence_numbers: list[str]
    ) -> list[Player]:
        query_array = ', '.join('?' for _ in player_ffe_licence_numbers)
        self.execute(
            f'SELECT * FROM player WHERE ffe_licence_number IN ({query_array})',
            tuple(player_ffe_licence_numbers),
        )
        return [self.get_player_from_row(row) for row in self.fetchall()]
