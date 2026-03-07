import re
import shutil
from contextlib import suppress
from datetime import datetime, date
from logging import Logger
from pathlib import Path
from typing import Any, override

import zipfile

from packaging.version import Version
from requests import Response, get
from requests.exceptions import ConnectionError
from text_unidecode import unidecode

from common.i18n import _
from common.i18n.utils import unicode_normalize
from common.logger import get_logger
from data.player import PlayerRating
from database.sqlite.config.config_store import StoredLocalSourceDatabase
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.local_source_database import LocalSourcePlayerDatabase
from database.sqlite.local_source_database.actions import NotifOutdatedAction
from database.sqlite.local_source_database.databases import ZipCredentials
from database.sqlite.local_source_database.delays import Days2OutdatedDelay
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins import PLUGINS_DIR, ffe
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.utils import PlayerFFELicence, FfePlayerPluginData
from utils.enum import (
    TournamentRating,
    PlayerRatingType,
    PlayerGender,
    PlayerTitle,
)

FFE_ZIP_URL = 'https://github.com/Sharly-Chess/databases/releases/download/latest/ffe_players_v1.zip'

logger: Logger = get_logger()


class FfeDatabase(LocalSourcePlayerDatabase):
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

    CREDENTIALS_FILE: Path = PLUGINS_DIR / 'ffe' / '.database-zip-credentials'

    @classmethod
    def dump_credentials(
        cls,
        password: str,
    ):
        ZipCredentials.dump(
            cls.CREDENTIALS_FILE,
            password,
        )

    @staticmethod
    def static_id() -> str:
        return 'ffe'

    @staticmethod
    def static_name() -> str:
        return _('FFE')

    @property
    def min_recovery_version(self) -> Version:
        # Last change done in https://github.com/Sharly-Chess/sharly-chess/pull/1739
        return Version('3.6.0')

    @staticmethod
    def _dir() -> Path:
        return ffe.TMP_DIR

    @property
    def _source_file_name(self) -> str:
        return 'ffe_players_v1.db'

    @override
    @property
    def default_stored_database(self) -> StoredLocalSourceDatabase:
        return StoredLocalSourceDatabase(
            name=self.id,
            outdate_delay=Days2OutdatedDelay.static_id(),
            outdate_action=NotifOutdatedAction.static_id(),
        )

    def _download_source_file(self, source_file_dir: Path) -> bool:
        zip_target: Path = source_file_dir / 'ffe_players_v1.zip'
        logger.info(self.log_prefix + 'Downloading [%s]...', FFE_ZIP_URL)
        try:
            response: Response = get(
                FFE_ZIP_URL, allow_redirects=True, timeout=60, stream=True
            )
            if response.status_code != 200:
                logger.error(
                    self.log_prefix + 'Could not download [%s], error code [%d].',
                    FFE_ZIP_URL,
                    response.status_code,
                )
                return False
            total = int(response.headers.get('content-length', 0))
            logger.info(self.log_prefix + 'Receiving %.1f MB...', total / 1_048_576)
            received = 0
            with open(zip_target, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
                    received += len(chunk)
                    logger.debug(
                        self.log_prefix + 'Downloaded %d / %d bytes.', received, total
                    )
        except ConnectionError as ex:
            logger.error(
                self.log_prefix + 'Could not download [%s]: %s.',
                FFE_ZIP_URL,
                ex,
            )
            return False
        logger.info(
            self.log_prefix + 'Download complete (%.1f MB).', received / 1_048_576
        )
        credentials: ZipCredentials = ZipCredentials(self.CREDENTIALS_FILE)
        logger.info(self.log_prefix + 'Extracting zip archive...')
        try:
            with zipfile.ZipFile(zip_target, 'r') as zf:
                zf.extractall(source_file_dir, pwd=credentials.password.encode())
        except Exception as ex:
            logger.error(self.log_prefix + 'Could not extract zip archive: %s.', ex)
            return False
        finally:
            zip_target.unlink(missing_ok=True)
        logger.info(self.log_prefix + 'Extraction complete.')
        return True

    def _use_external_generator(self):
        return True

    def _generate_from_source_file(
        self, source_file_path: Path, tmp_file: Path
    ) -> bool:
        logger.info(self.log_prefix + 'Copying downloaded database to temp file...')
        shutil.copy(source_file_path, tmp_file)
        logger.info(self.log_prefix + 'Copy done.')
        return True

    @classmethod
    def _create_indexes(cls, database: SQLiteDatabase):
        # Indices are created by Papi-converter.
        pass

    @staticmethod
    def get_stored_player_from_row(row: dict[str, Any]) -> StoredPlayer:
        return StoredPlayer(
            id=0,
            first_name=row['first_name'].title() if row['first_name'] else '',
            last_name=row['last_name'].upper(),
            date_of_birth=datetime.strptime(row['date_of_birth'], '%Y-%m-%d').date(),
            gender=PlayerGender(row['gender']),
            title=PlayerTitle(row['fide_title']),
            ratings={
                TournamentRating.STANDARD.value: PlayerRating.from_type(
                    row['standard_rating'],
                    PlayerRatingType(row['standard_rating_type']),
                ).stored_value,
                TournamentRating.RAPID.value: PlayerRating.from_type(
                    row['rapid_rating'], PlayerRatingType(row['rapid_rating_type'])
                ).stored_value,
                TournamentRating.BLITZ.value: PlayerRating.from_type(
                    row['blitz_rating'], PlayerRatingType(row['blitz_rating_type'])
                ).stored_value,
            },
            fide_id=int(row['fide_id']) if row['fide_id'] else None,
            federation=row['federation'],
            club=row['club'],
            transient_arbiter_titles={'ffe': row['ffe_arbiter_title']},
            plugin_data={
                PLUGIN_NAME: FfePlayerPluginData(
                    ffe_id=row['ffe_id'],
                    ffe_licence=PlayerFFELicence(row['ffe_licence']),
                    ffe_licence_number=row['ffe_licence_number'],
                    league=row['league'],
                ).to_stored_value()
            },
        )

    def search_player(
        self,
        string: str,
        federation: str,
        page: int = 0,
        limit: int | None = None,
    ) -> list[StoredPlayer]:
        tokens: list[str] = [
            unicode_normalize(token) for token in re.split(r'\s+', string)
        ]
        str_fields: tuple[tuple[str, str, str], ...] = (
            ('last_name', '%', '%'),
            ('first_name', '%', '%'),
            ('ffe_licence_number', '', ''),
        )
        int_fields: tuple[str, ...] = ('fide_id',)
        token_conditions: dict[str, str] = {}
        params: list[Any] = []
        for token in tokens:
            expressions = [f'({field[0]} LIKE ?)' for field in str_fields]
            params += [f'{field[1]}{token}{field[2]}' for field in str_fields]
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

        # We build one CASE block that sorts best → worst
        order_clauses = []
        for token in tokens:
            order_clauses.append("""
                CASE
                    WHEN last_name LIKE ? AND federation = ? THEN 0
                    WHEN first_name LIKE ? AND federation = ? THEN 1
                    WHEN (last_name LIKE ? OR first_name LIKE ?) THEN 2
                    WHEN federation = ? THEN 3
                    ELSE 4
                END
            """)

            # Params for this token in the same order
            params += [
                f'{token}%',
                federation,
                f'{token}%',
                federation,
                f'{token}%',
                f'{token}%',
                federation,
            ]

        order_expr = ' + '.join(order_clauses)

        query: str = f"""
            SELECT *
            FROM player
            WHERE {conditions}
            ORDER BY {order_expr}, last_name, first_name
        """

        if limit:
            query += ' LIMIT ?'
            params += [
                limit,
            ]
        if page and limit:
            query += ' OFFSET ?'
            params += [
                page * limit,
            ]

        self.execute(
            query,
            tuple(params),
        )

        return [self.get_stored_player_from_row(row) for row in self.fetchall()]

    def _get_stored_player_by_id(self, field: str, id_: int) -> StoredPlayer | None:
        self.execute(f'SELECT * FROM `player` WHERE {field} = ?', (id_,))
        if row := self.fetchone():
            return self.get_stored_player_from_row(row)
        else:
            return None

    def get_stored_player_by_ffe_id(
        self,
        player_ffe_id: int,
    ) -> StoredPlayer | None:
        return self._get_stored_player_by_id('ffe_id', player_ffe_id)

    def get_stored_player_by_fide_id(
        self,
        player_fide_id: int,
    ) -> StoredPlayer | None:
        return self._get_stored_player_by_id('fide_id', player_fide_id)

    def get_stored_players_by_licence_numbers(
        self, licence_numbers: list[str]
    ) -> list[StoredPlayer]:
        query_array = ', '.join('?' for _ in licence_numbers)
        self.execute(
            f'SELECT * FROM `player` WHERE `ffe_licence_number` IN ({query_array})',
            tuple(licence_numbers),
        )
        return [self.get_stored_player_from_row(row) for row in self.fetchall()]

    def get_stored_players_by_fide_ids(self, fide_ids: list[int]) -> list[StoredPlayer]:
        query_array = ', '.join('?' for _ in fide_ids)
        self.execute(
            f'SELECT * FROM player WHERE fide_id IN ({query_array})',
            tuple(fide_ids),
        )
        return [self.get_stored_player_from_row(row) for row in self.fetchall()]

    def get_stored_players_by_name_keys(
        self, name_keys: list[tuple[str, str, date]]
    ) -> list[StoredPlayer]:
        query_array = ', '.join('(?, ?, ?)' for _ in name_keys)
        params: list[str] = []
        for name_key in name_keys:
            params += [
                unidecode(name_key[0]),
                unidecode(name_key[1]),
                self.dump_date_to_database_field(name_key[2]) or '',
            ]
        self.execute(
            'SELECT * FROM player '
            f'WHERE (last_name, first_name, date_of_birth) IN ({query_array})',
            tuple(params),
        )
        return [self.get_stored_player_from_row(row) for row in self.fetchall()]
