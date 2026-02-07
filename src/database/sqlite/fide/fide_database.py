import os.path
import re
import tempfile
from xml.etree import ElementTree
import zipfile
from contextlib import suppress
from logging import Logger
from pathlib import Path
from typing import Iterator, Any, Callable, override

from packaging.version import Version
from requests import Response, get
from requests.exceptions import ConnectionError

from common.i18n import _
from common.i18n.utils import unicode_normalize
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.player import PlayerRating
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.local_source_database import LocalSourcePlayerDatabase
from database.sqlite.local_source_database.actions import NotifOutdatedAction
from database.sqlite.local_source_database.databases import DatabaseLoaderProgress
from database.sqlite.local_source_database.delays import MonthFirstDayOutdatedDelay
from utils.enum import (
    PlayerGender,
    PlayerTitle,
    TournamentRating,
    FideArbiterTitle,
)
from database.sqlite.config.config_store import StoredLocalSourceDatabase
from database.sqlite.sqlite_database import SQLiteDatabase

logger: Logger = get_logger()


class FideDatabase(LocalSourcePlayerDatabase):
    """
    The SQLite database class for FIDE players. Usage:
    1. Check if the database exists and is up-to-date.
        If outdated, the outdate action is executed:
    FideDatabase().check()
    2. Search the database:
    with FideDatabase() as fide_database:
        for player in fide_database.search_player('my name'):
            ...
    """

    @staticmethod
    def static_id() -> str:
        return 'fide'

    @staticmethod
    def static_name() -> str:
        return _('FIDE')

    @property
    def min_recovery_version(self) -> Version:
        # Last change done in https://github.com/Sharly-Chess/sharly-chess/pull/1739
        return Version('3.6.0')

    @property
    def _schema_file_path(self) -> Path:
        return SharlyChessConfig.database_sql_path / 'create_fide.sql'

    @property
    def _source_file_name(self) -> str:
        return 'players_list_xml.xml'

    @override
    @property
    def default_stored_database(self) -> StoredLocalSourceDatabase:
        return StoredLocalSourceDatabase(
            name=self.id,
            outdate_delay=MonthFirstDayOutdatedDelay.static_id(),
            outdate_action=NotifOutdatedAction.static_id(),
        )

    def _download_source_file(self, source_file_dir: Path) -> bool:
        fide_database_url: str = (
            'https://ratings.fide.com/download/players_list_xml_legacy.zip'
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dir: Path = Path(tmpdir)
            local_zip_file: Path = tmp_dir / os.path.basename(fide_database_url)
            try:
                response: Response = get(
                    fide_database_url, allow_redirects=True, timeout=10
                )
                if response.status_code != 200:
                    logger.error(
                        self.log_prefix + 'Could not download [%s], error code [%d].',
                        fide_database_url,
                        response.status_code,
                    )
                    return False
            except ConnectionError as ex:
                logger.error(
                    self.log_prefix + 'Could not download [%s]: %s.',
                    fide_database_url,
                    ex,
                )
                return False
            local_zip_file.write_bytes(response.content)
            if not local_zip_file.exists():
                logger.error(
                    self.log_prefix + 'No data received from [%s].', fide_database_url
                )
                return False

            with zipfile.ZipFile(local_zip_file, 'r') as zip_ref:
                zip_ref.extractall(source_file_dir)

            if not Path(source_file_dir / self._source_file_name).exists():
                logger.error(self.log_prefix + 'Could not unzip data.')
                return False
            return True

    def _populate_from_source_file(
        self, source_file_path: Path, database: SQLiteDatabase
    ) -> bool:
        # extract the number of items to calculate the ETA
        with open(source_file_path, 'r') as f:
            player_total_count: int = sum(
                1 for line in f if line.startswith('<player>')
            )
        logger.debug(self.log_prefix + '%d players to add.', player_total_count)
        logger.debug(self.log_prefix + 'Loading XML data...')
        context = ElementTree.iterparse(source_file_path, events=('start', 'end'))
        logger.debug(self.log_prefix + 'Storing players...')
        progress: DatabaseLoaderProgress = DatabaseLoaderProgress(
            log_prefix=self.log_prefix,
            total_count=player_total_count,
        )
        player_fields: dict[str, tuple[str, Callable[[Any], Any] | None]] = {
            'fideid': ('fide_id', lambda s: int(s.strip())),
            'name': ('name', None),
            'country': ('federation', lambda s: s.upper()),
            'sex': ('gender', PlayerGender.from_fide_value),
            'title': ('fide_title', PlayerTitle.from_fide_value),
            'o_title': ('fide_arbiter_title', FideArbiterTitle.from_fide_value),
            'rating': ('standard_rating', int),
            'rapid_rating': ('rapid_rating', int),
            'blitz_rating': ('blitz_rating', int),
            'birthday': ('year_of_birth', lambda s: int(s) if s else 0),
            'k': ('k_standard', lambda s: int(s) if s else None),
            'rapid_k': ('k_rapid', lambda s: int(s) if s else None),
            'blitz_k': ('k_blitz', lambda s: int(s) if s else None),
        }
        player_db_columns: list[str] = [
            field[0]
            for field in player_fields.values()
            if field[0]
            not in [
                'name',
                'fide_arbiter_title',
            ]
        ]
        player_db_columns += [
            'first_name',
            'last_name',
        ]
        player_query = f"""INSERT INTO `player`({', '.join(player_db_columns)}) VALUES({', '.join([f':{c}' for c in player_db_columns])})"""
        arbiter_db_columns: list[str] = [
            'player_fide_id',
            'fide_arbiter_title',
        ]
        arbiter_query = f"""INSERT INTO `arbiter`({', '.join(arbiter_db_columns)}) VALUES({', '.join([f':{c}' for c in arbiter_db_columns])})"""
        player_count: int = 0
        arbiter_count: int = 0
        players_to_write: list[dict[str, Any]] = []
        arbiters_to_write: list[dict[str, Any]] = []
        player_data: dict[str, Any] = {}
        arbiter_data: dict[str, FideArbiterTitle] = {}
        root = next(context)[1]
        with database:
            for event, elem in context:
                if event == 'start' and elem.tag == 'player':
                    player_data = {}
                    arbiter_data = {}

                if event == 'end' and elem.tag == 'player':
                    players_to_write.append(player_data)
                    player_count += 1
                    if arbiter_data:
                        arbiters_to_write.append(arbiter_data)
                        arbiter_count += 1
                    if player_count % 1000 == 0:
                        if self.stop_event.is_set():
                            return False
                        database.executemany(player_query, players_to_write)
                        players_to_write.clear()
                        if arbiters_to_write:
                            database.executemany(arbiter_query, arbiters_to_write)
                            arbiters_to_write.clear()
                        progress.log(player_count)
                    if player_count % 100_000 == 0:
                        database.commit()

                elif event == 'end' and elem.tag in player_fields:
                    (field_name, field_function) = player_fields[elem.tag]
                    player_data[field_name] = elem.text or ''
                    elem.clear()
                    root.clear()
                    if field_function:
                        player_data[field_name] = field_function(
                            player_data[field_name]
                        )

                    if field_name == 'name':
                        if ',' in player_data['name']:
                            last_name, first_name = player_data['name'].split(
                                ',', maxsplit=1
                            )
                            player_data['last_name'] = last_name.strip()
                            player_data['first_name'] = first_name.strip()
                        else:
                            player_data['last_name'] = player_data['name'].strip()
                            player_data['first_name'] = None
                        del player_data['name']
                    elif field_name == 'fide_arbiter_title':
                        if player_data['fide_arbiter_title']:
                            arbiter_data['player_fide_id'] = player_data['fide_id']
                            arbiter_data['fide_arbiter_title'] = player_data[
                                'fide_arbiter_title'
                            ]
                            del player_data['fide_arbiter_title']

            if players_to_write:
                database.executemany(player_query, players_to_write)
                database.commit()
                progress.log(player_count)
            if arbiters_to_write:
                database.executemany(arbiter_query, arbiters_to_write)
                database.commit()

        logger.info(
            self.log_prefix
            + '%d players (including %d arbiters) written to the database.',
            player_count,
            arbiter_count,
        )
        return True

    def _create_indexes(self):
        self.write = True
        with self:
            self.execute(
                'CREATE INDEX IF NOT EXISTS `player_first_name` ON `player` (`first_name` COLLATE NOCASE)'
            )
            self.execute(
                'CREATE INDEX IF NOT EXISTS `player_last_name` ON `player` (`last_name` COLLATE NOCASE)'
            )
            self.execute(
                'CREATE INDEX IF NOT EXISTS `player_fide_id` ON `player` (`fide_id`)'
            )
            self.execute(
                'CREATE INDEX IF NOT EXISTS `arbiter_fide_id` ON `arbiter`(`player_fide_id`)'
            )
            self.commit()

    def read_federation_ids(self) -> Iterator[str]:
        self.execute(
            'SELECT DISTINCT federation FROM `player` ORDER BY `federation`',
            (),
        )
        yield from map(lambda row: row['federation'], self.fetchall())

    @staticmethod
    def _get_player_from_row(row: dict[str, Any]) -> StoredPlayer:
        rating_keys = {
            TournamentRating.STANDARD: 'standard_rating',
            TournamentRating.RAPID: 'rapid_rating',
            TournamentRating.BLITZ: 'blitz_rating',
        }
        ratings = {
            tournament_rating.value: PlayerRating(
                fide=row[key] or None,
            ).stored_value
            for tournament_rating, key in rating_keys.items()
        }
        return StoredPlayer(
            id=None,
            first_name=row['first_name'].title() if row['first_name'] else '',
            last_name=row['last_name'].upper(),
            year_of_birth=row['year_of_birth'],
            gender=row['gender'],
            title=row['fide_title'],
            fide_arbiter_title=row.get('fide_arbiter_title', ''),
            ratings=ratings,
            fide_id=row['fide_id'],
            federation=row['federation'],
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

        self.execute(query, tuple(params))
        return [self._get_player_from_row(row) for row in self.fetchall()]

    def get_stored_player_by_fide_id(
        self,
        player_fide_id: int,
        with_arbiter_title: bool,
    ) -> StoredPlayer | None:
        if with_arbiter_title:
            self.execute(
                'SELECT `player`.*, `arbiter`.`fide_arbiter_title` AS `fide_arbiter_title` FROM `player` LEFT JOIN `arbiter` ON `arbiter`.`player_fide_id` = `player`.`fide_id` WHERE `fide_id` = ?',
                (player_fide_id,),
            )
        else:
            self.execute(
                "SELECT `player`.*, '' AS `fide_arbiter_title` FROM `player` WHERE `fide_id` = ?",
                (player_fide_id,),
            )
        if player_row := self.fetchone():
            return self._get_player_from_row(player_row)
        return None

    def get_k_factors_by_fide_id(
        self, player_fide_id: int
    ) -> dict[TournamentRating, int | None] | None:
        self.execute('SELECT * FROM player WHERE fide_id = ?', (player_fide_id,))
        if player_row := self.fetchone():
            return {
                TournamentRating.STANDARD: player_row.get('k_standard', None),
                TournamentRating.RAPID: player_row.get('k_rapid', None),
                TournamentRating.BLITZ: player_row.get('k_blitz', None),
            }
        return None

    def get_stored_players_by_fide_id(
        self, player_fide_ids: list[int]
    ) -> list[StoredPlayer]:
        query_array = ', '.join('?' for _ in player_fide_ids)
        self.execute(
            f'SELECT * FROM player WHERE fide_id IN ({query_array})',
            tuple(player_fide_ids),
        )
        return [self._get_player_from_row(row) for row in self.fetchall()]
