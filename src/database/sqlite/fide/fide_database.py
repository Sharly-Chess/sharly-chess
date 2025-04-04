import os.path
from xml.etree import ElementTree
import zipfile
from contextlib import suppress
from datetime import datetime
from logging import Logger
from pathlib import Path
from typing import Iterator, Any, Callable, override

from requests import Response, get
from requests.exceptions import ConnectionError

from common import TMP_DIR
from common.i18n import _
from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from data.player import Player, Federation, Club
from utils.enum import (
    PlayerGender,
    PlayerTitle,
    TournamentRating,
    PlayerRatingType,
)
from database.sqlite.config.config_store import StoredLocalSourceDatabase
from database.sqlite.local_source_database import (
    LocalSourceDatabase,
    NotifOutdateAction,
    MonthFirstDayOutdateDelay,
)
from database.sqlite.sqlite_database import SQLiteDatabase

logger: Logger = get_logger()


class FideDatabase(LocalSourceDatabase):
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
        return 'FIDE'

    @property
    def _schema_file_path(self) -> Path:
        return PapiWebConfig.database_sql_path / 'create_fide.sql'

    @property
    def _source_file_path(self) -> Path:
        return TMP_DIR / 'players_list_xml.xml'

    @override
    @property
    def default_stored_database(self) -> StoredLocalSourceDatabase:
        return StoredLocalSourceDatabase(
            name=self.id,
            outdate_delay=MonthFirstDayOutdateDelay.static_id(),
            outdate_action=NotifOutdateAction.static_id(),
        )

    def _download_source_file(self) -> bool:
        fide_database_url: str = (
            'https://ratings.fide.com/download/players_list_xml_legacy.zip'
        )
        local_zip_file: Path = TMP_DIR / os.path.basename(fide_database_url)
        with suppress(FileNotFoundError):
            local_zip_file.unlink()
        try:
            response: Response = get(fide_database_url, allow_redirects=True, timeout=5)
            if response.status_code != 200:
                logger.error(
                    self.log_prefix
                    + _('Could not download [{url}], error code [{code}].').format(
                        url=fide_database_url, code=response.status_code
                    )
                )
                return False
        except ConnectionError as ex:
            logger.error(
                self.log_prefix
                + _('Could not download [{url}]: {error}.').format(
                    url=fide_database_url, error=ex
                )
            )
            return False
        local_zip_file.write_bytes(response.content)
        if not local_zip_file.exists():
            logger.error(
                self.log_prefix
                + _('No data received from [{url}].').format(url=fide_database_url)
            )
            return False

        self._source_file_path.unlink(missing_ok=True)
        with zipfile.ZipFile(local_zip_file, 'r') as zip_ref:
            zip_ref.extractall(TMP_DIR)
        local_zip_file.unlink()
        if not self._source_file_path.exists():
            logger.error(self.log_prefix + _('Could not unzip data.'))
            return False
        return True

    def _populate_from_source_file(self, database: SQLiteDatabase) -> bool:
        fields: dict[str, tuple[str, Callable[[Any], Any] | None]] = {
            'fideid': ('fide_id', lambda s: int(s.strip())),
            'name': ('name', None),
            'country': ('federation', lambda s: s.upper()),
            'sex': ('gender', PlayerGender.from_fide_value),
            # exception for 1001710 Vreeken, Corry
            'title': (
                'fide_title',
                lambda s: PlayerTitle.from_fide_value('' if s == 'WH' else s),
            ),
            'rating': ('standard_rating', int),
            'rapid_rating': ('rapid_rating', int),
            'blitz_rating': ('blitz_rating', int),
            'birthday': ('year_of_birth', lambda s: int(s) if s else 0),
        }
        db_columns = [field[0] for field in fields.values() if field[0] != 'name']
        db_columns += ['first_name', 'last_name']
        query = f"""INSERT INTO player({', '.join(db_columns)}) VALUES({', '.join([f':{c}' for c in db_columns])})"""
        player_count: int = 0
        to_write = []
        data: dict[str, Any] = {}
        context = ElementTree.iterparse(self._source_file_path, events=('start', 'end'))
        root = next(context)[1]
        with database:
            for event, elem in context:
                if event == 'start' and elem.tag == 'player':
                    data = {}

                if event == 'end' and elem.tag == 'player':
                    to_write.append(data)
                    player_count += 1
                    if player_count % 1000 == 0:
                        database.executemany(query, to_write)
                        to_write.clear()
                        if self.stop_event.is_set():
                            return False
                    if player_count % 100_000 == 0:
                        database.commit()

                elif event == 'end' and elem.tag in fields:
                    (field_name, field_function) = fields[elem.tag]
                    data[field_name] = elem.text or ''
                    elem.clear()
                    root.clear()
                    if field_function:
                        data[field_name] = field_function(data[field_name])

                    if field_name == 'name':
                        if ',' in data['name']:
                            last_name, first_name = data['name'].split(',', maxsplit=1)
                            data['last_name'] = last_name.strip()
                            data['first_name'] = first_name.strip()
                        else:
                            data['last_name'] = data['name'].strip()
                            data['first_name'] = None
                        del data['name']
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
                'CREATE INDEX `player_first_name` ON `player` (`first_name` COLLATE NOCASE)'
            )
            self.execute(
                'CREATE INDEX `player_last_name` ON `player` (`last_name` COLLATE NOCASE)'
            )
            self.execute('CREATE INDEX `player_fide_id` ON `player` (`fide_id`)')
            self.commit()

    def read_federation_ids(self) -> Iterator[str]:
        self.execute(
            'SELECT DISTINCT federation FROM `player` ORDER BY `federation`',
            (),
        )
        yield from map(lambda row: row['federation'], self.fetchall())

    @staticmethod
    def _get_player_from_row(row: dict[str, Any]) -> Player:
        return Player(
            id=0,
            first_name=row['first_name'].title() if row['first_name'] else '',
            last_name=row['last_name'].upper(),
            date_of_birth=datetime.strptime(
                f'{row["year_of_birth"] or 1900}-01-01', '%Y-%m-%d'
            ).date(),
            gender=PlayerGender(row['gender']),
            mail='',
            phone='',
            comment='',
            owed=0.0,
            paid=0.0,
            title=PlayerTitle(row['fide_title']),
            ratings={
                TournamentRating.STANDARD: row['standard_rating'],
                TournamentRating.RAPID: row['rapid_rating'],
                TournamentRating.BLITZ: row['blitz_rating'],
            },
            rating_types={
                TournamentRating.STANDARD: PlayerRatingType.FIDE
                if row['standard_rating']
                else PlayerRatingType.ESTIMATED,
                TournamentRating.RAPID: PlayerRatingType.FIDE
                if row['rapid_rating']
                else PlayerRatingType.ESTIMATED,
                TournamentRating.BLITZ: PlayerRatingType.FIDE
                if row['blitz_rating']
                else PlayerRatingType.ESTIMATED,
            },
            fide_id=row['fide_id'],
            federation=Federation(row['federation']),
            club=Club(''),
            fixed=0,
            check_in=False,  # not taken into account when updating/creating/deleting the player
            pairings={},  # Pairings are read from Papi but not used
            tournament=None,
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
        return (self._get_player_from_row(row) for row in self.fetchall())

    def get_player_by_fide_id(self, player_fide_id: int) -> Player | None:
        self.execute('SELECT * FROM player WHERE fide_id = ?', (player_fide_id,))
        if player_row := self.fetchone():
            return self._get_player_from_row(player_row)
        return None

    def get_players_by_fide_id(self, player_fide_ids: list[int]) -> list[Player]:
        query_array = ', '.join('?' for _ in player_fide_ids)
        self.execute(
            f'SELECT * FROM player WHERE fide_id IN ({query_array})',
            tuple(player_fide_ids),
        )
        return [self._get_player_from_row(row) for row in self.fetchall()]
