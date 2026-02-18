import os.path
import re
import tempfile
import zipfile
from contextlib import suppress
from datetime import datetime, date
from logging import Logger
from pathlib import Path
from typing import Any, override

import pytds
from packaging.version import Version
from requests import Response, get
from requests.exceptions import ConnectionError
from text_unidecode import unidecode

from common import TMP_DIR
from common.i18n import _
from common.i18n.utils import unicode_normalize
from common.logger import get_logger
from data.player import PlayerRating
from database.sqlite.config.config_store import StoredLocalSourceDatabase
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.local_source_database import LocalSourcePlayerDatabase
from database.sqlite.local_source_database.actions import NotifOutdatedAction
from database.sqlite.local_source_database.databases import DatabaseLoaderProgress
from database.sqlite.local_source_database.delays import Days2OutdatedDelay
from plugins import ffe
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_session import FFEArbitersLoader
from plugins.ffe.papi_converter import PapiConverter
from plugins.ffe.utils import PlayerFFELicence, FfePlayerPluginData, FFEArbiterTitle
from utils.enum import (
    TournamentRating,
    PlayerRatingType,
    PlayerGender,
    PlayerTitle,
)

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
        return 'Data.mdb'

    @override
    @property
    def default_stored_database(self) -> StoredLocalSourceDatabase:
        return StoredLocalSourceDatabase(
            name=self.id,
            outdate_delay=Days2OutdatedDelay.static_id(),
            outdate_action=NotifOutdatedAction.static_id(),
        )

    def _download_source_file(self, source_file_dir: Path) -> bool:
        with tempfile.TemporaryDirectory(dir=TMP_DIR) as tmpdir:
            tmp_dir: Path = Path(tmpdir)
            ffe_database_url: str = 'https://www.echecs.asso.fr/Papi/PapiData.zip'
            local_zip_file: Path = tmp_dir / os.path.basename(ffe_database_url)
            try:
                response: Response = get(
                    ffe_database_url, allow_redirects=True, timeout=10
                )
                if response.status_code != 200:
                    logger.error(
                        self.log_prefix + 'Could not download [%s], error code [%d].',
                        ffe_database_url,
                        response.status_code,
                    )
                    return False
            except ConnectionError as ex:
                logger.error(
                    self.log_prefix + 'Could not download [%s]: %s.',
                    ffe_database_url,
                    ex,
                )
                return False
            local_zip_file.write_bytes(response.content)
            if not local_zip_file.exists():
                logger.error(
                    self.log_prefix + 'No data received from [%s].', ffe_database_url
                )
                return False
            with zipfile.ZipFile(local_zip_file, 'r') as zip_ref:
                zip_ref.extractall(source_file_dir)
            if not Path(source_file_dir / self._source_file_name).exists():
                logger.error(self.log_prefix + 'Could not unzip data.')
                return False
            return True

    def _use_external_generator(self):
        return True

    def _generate_from_source_file(
        self, source_file_path: Path, tmp_file: Path
    ) -> bool:
        try:
            PapiConverter().convert_player_database(source_file_path, tmp_file)
            return True
        except pytds.DatabaseError as e:
            logger.error(self.log_prefix + 'Papi-converter failed: %s', e)
            return False

    def _post_generation(self) -> bool:
        logger.debug(self.log_prefix + 'Scrapping FFE arbiters from the FFE website...')
        ffe_arbiter_titles_by_ffe_licence_number: dict[str, FFEArbiterTitle] = (
            FFEArbitersLoader().load_ffe_arbiter_titles_by_ffe_licence_number()
        )
        logger.debug(
            self.log_prefix + '%d arbiters to add.',
            len(ffe_arbiter_titles_by_ffe_licence_number),
        )
        logger.debug(self.log_prefix + 'Storing the arbiters...')
        progress: DatabaseLoaderProgress = DatabaseLoaderProgress(
            log_prefix=self.log_prefix,
            total_count=len(ffe_arbiter_titles_by_ffe_licence_number),
        )
        self.write = True
        with self:
            self.execute('ALTER TABLE `player` ADD `ffe_arbiter_title` TEXT')
            self.commit()
            query = """UPDATE `player` SET `ffe_arbiter_title` = :ffe_arbiter_title WHERE ffe_licence_number = :ffe_licence_number"""
            arbiter_count: int = 0
            to_write: list[dict[str, Any]] = []
            for (
                ffe_licence_number,
                ffe_arbiter_title,
            ) in ffe_arbiter_titles_by_ffe_licence_number.items():
                to_write.append(
                    {
                        'ffe_licence_number': ffe_licence_number,
                        'ffe_arbiter_title': ffe_arbiter_title,
                    }
                )
                arbiter_count += 1
                if arbiter_count % 100 == 0:
                    self.executemany(query, to_write)
                    to_write.clear()
                    if self.stop_event.is_set():
                        return False
                    progress.log(arbiter_count)
                    self.commit()
            if to_write:
                self.executemany(query, to_write)
                self.commit()
                progress.log(arbiter_count)
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
