import re
import zipfile
from contextlib import suppress
from datetime import date
from enum import StrEnum
from logging import Logger
from pathlib import Path
from xml.etree import ElementTree
from xml.etree.ElementTree import Element
from typing import Any, override
from collections.abc import Iterator

from packaging.version import Version

from common import BASE_DIR
from common.i18n import _
from common.i18n.utils import unicode_normalize
from common.logger import get_logger
from data.player import PlayerRating
from database.sqlite.config.config_store import StoredLocalSourceDatabase
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.local_source_database import GitHubLocalSourcePlayerDatabase
from database.sqlite.sqlite_database import SQLiteDatabase
from database.sqlite.local_source_database.actions import NotifOutdatedAction
from database.sqlite.local_source_database.delays import MonthFirstDayOutdatedDelay
from utils.enum import (
    TournamentRating,
)

logger: Logger = get_logger()


#: Where the FIDE database comes from, until one way is settled: converted
#: by the application from the XML list FIDE publishes (`OFFICIAL_LIST`),
#: or downloaded ready-made, built by the Sharly Chess GitHub workflow
#: (`GITHUB_RELEASE`, which needs the decryption credentials).
class FideSource(StrEnum):
    OFFICIAL_LIST = 'official_list'
    GITHUB_RELEASE = 'github_release'


FIDE_SOURCE = FideSource.OFFICIAL_LIST


class FideDatabase(GitHubLocalSourcePlayerDatabase):
    """
    The SQLite database class for FIDE players, see `FIDE_SOURCE` for
    where it comes from. Usage:
    1. Check if the database exists and is up-to-date.
        If outdated, the outdate action is executed:
    FideDatabase().check()
    2. Search the database:
    with FideDatabase() as fide_database:
        for player in fide_database.search_player('my name'):
            ...
    """

    _URL = 'https://ratings.fide.com/download/players_list_xml_legacy.zip'
    _INSERT_BATCH_SIZE = 10_000
    _OPEN_TITLES = ('CM', 'FM', 'IM', 'GM')
    _WOMEN_TITLES = ('WCM', 'WFM', 'WIM', 'WGM')
    _ARBITER_TITLES = ('NA', 'FA', 'IA')

    @staticmethod
    def static_id() -> str:
        return 'fide'

    @staticmethod
    def static_name() -> str:
        return _('FIDE')

    @staticmethod
    def version() -> Version:
        return Version('2')

    @property
    def _source_file_name(self) -> str:
        if FIDE_SOURCE == FideSource.GITHUB_RELEASE:
            return 'fide_players_v2.db'
        return 'players_list_xml_legacy.zip'

    @classmethod
    def credentials_file(cls) -> Path:
        return BASE_DIR / 'src' / '.fide-database-enc-credentials'

    @classmethod
    def github_tag(cls) -> str:
        return 'fide-latest'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        if FIDE_SOURCE == FideSource.GITHUB_RELEASE:
            return self._download_enc_source_file(source_file_dir)
        return self._download_file(self._URL, source_file_dir / self._source_file_name)

    @override
    def _use_external_generator(self) -> bool:
        return FIDE_SOURCE == FideSource.GITHUB_RELEASE

    @property
    def _schema(self) -> str:
        return """
            CREATE TABLE `player` (
                `id` INTEGER NOT NULL,
                `fide_id` INTEGER NOT NULL,
                `last_name` TEXT NOT NULL,
                `first_name` TEXT,
                `federation` TEXT NOT NULL,
                `gender` TEXT NOT NULL,
                `fide_title` TEXT,
                `fide_women_title` TEXT,
                `standard_rating` INTEGER NOT NULL,
                `rapid_rating` INTEGER NOT NULL,
                `blitz_rating` INTEGER NOT NULL,
                `year_of_birth` INTEGER NOT NULL,
                `k_standard` INTEGER NOT NULL,
                `k_rapid` INTEGER NOT NULL,
                `k_blitz` INTEGER NOT NULL,
                `fide_arbiter_title` TEXT NOT NULL,
                PRIMARY KEY(`id` AUTOINCREMENT),
                UNIQUE(`fide_id`)
            );
        """

    @classmethod
    @override
    def _create_indexes(cls, database: SQLiteDatabase) -> None:
        if FIDE_SOURCE == FideSource.GITHUB_RELEASE:
            # The release carries its indices.
            return
        database.execute(
            'CREATE INDEX `player_first_name` ON `player` (`first_name` COLLATE NOCASE)'
        )
        database.execute(
            'CREATE INDEX `player_last_name` ON `player` (`last_name` COLLATE NOCASE)'
        )
        database.execute('CREATE INDEX `player_fide_id` ON `player` (`fide_id`)')

    @classmethod
    def _player_params(cls, player: Element) -> tuple | None:
        """The row of a `<player>` element of the FIDE list, None for an
        element without a FIDE id."""
        text = player.findtext
        fide_id = (text('fideid') or '').strip()
        if not fide_id.isdigit():
            return None
        last_name, _sep, first_name = (text('name') or '').partition(',')
        # The `<title>` field holds the player's highest title, which may be
        # a women's title; the women's title has its own field.
        title = (text('title') or '').strip().upper()
        arbiter_title = next(
            (
                string
                for string in (text('o_title') or '').split(',')
                if string in cls._ARBITER_TITLES
            ),
            '',
        )
        return (
            int(fide_id),
            last_name.strip(),
            first_name.strip() or None,
            (text('country') or '').strip().upper(),
            (text('sex') or '').strip().upper(),
            title if title in cls._OPEN_TITLES else '',
            (text('w_title') or '').strip().upper(),
            int(text('rating') or 0),
            int(text('rapid_rating') or 0),
            int(text('blitz_rating') or 0),
            int(text('birthday') or 0),
            int(text('k') or 0),
            int(text('rapid_k') or 0),
            int(text('blitz_k') or 0),
            arbiter_title,
        )

    @override
    def _populate_from_source_file(
        self, source_file_path: Path, database: SQLiteDatabase
    ) -> bool:
        """Reads the players straight out of the archive: the XML is too
        big to be worth extracting."""
        query = (
            'INSERT OR REPLACE INTO `player` ('
            '`fide_id`, `last_name`, `first_name`, `federation`, `gender`, '
            '`fide_title`, `fide_women_title`, `standard_rating`, `rapid_rating`, '
            '`blitz_rating`, `year_of_birth`, `k_standard`, `k_rapid`, `k_blitz`, '
            '`fide_arbiter_title`) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
        )
        count = 0
        batch: list[tuple] = []
        with zipfile.ZipFile(source_file_path) as archive:
            xml_names = [name for name in archive.namelist() if name.endswith('.xml')]
            if len(xml_names) != 1:
                logger.error(
                    self.log_prefix + 'Expected one XML file in the archive, got %s.',
                    xml_names,
                )
                return False
            with archive.open(xml_names[0]) as stream:
                context = ElementTree.iterparse(stream, events=('start', 'end'))
                _event, root = next(context)
                for event, element in context:
                    if event != 'end' or element.tag != 'player':
                        continue
                    if (params := self._player_params(element)) is not None:
                        batch.append(params)
                    # The parsed players would otherwise pile up under the root.
                    root.clear()
                    if len(batch) >= self._INSERT_BATCH_SIZE:
                        if self.stop_event.is_set():
                            return False
                        database.executemany(query, batch)
                        count += len(batch)
                        batch = []
                        self._report_players_stored(count)
                        if count % (self._INSERT_BATCH_SIZE * 20) == 0:
                            logger.info(self.log_prefix + '%d players stored…', count)
        if batch:
            database.executemany(query, batch)
            count += len(batch)
        logger.info(self.log_prefix + '%d players stored.', count)
        return count > 0

    @override
    @property
    def default_is_active(self) -> bool:
        return True

    @override
    @property
    def default_stored_database(self) -> StoredLocalSourceDatabase:
        return StoredLocalSourceDatabase(
            name=self.id,
            outdate_delay=MonthFirstDayOutdatedDelay.static_id(),
            outdate_action=NotifOutdatedAction.static_id(),
        )

    def read_federation_ids(self) -> Iterator[str]:
        self.execute(
            'SELECT DISTINCT federation FROM `player` ORDER BY `federation`',
            (),
        )
        yield from (row['federation'] for row in self.fetchall())

    @staticmethod
    def _get_player_from_row(row: dict[str, Any]) -> StoredPlayer:
        rating_keys = {
            TournamentRating.STANDARD: ('standard_rating', 'k_standard'),
            TournamentRating.RAPID: ('rapid_rating', 'k_rapid'),
            TournamentRating.BLITZ: ('blitz_rating', 'k_blitz'),
        }
        ratings = {
            tournament_rating.value: PlayerRating(
                fide=row[rating_key] or None,
                k_factor=row.get(k_key) or None,
            ).stored_value
            for tournament_rating, (rating_key, k_key) in rating_keys.items()
        }
        return StoredPlayer(
            id=None,
            first_name=row['first_name'].title() if row['first_name'] else '',
            last_name=row['last_name'].upper(),
            year_of_birth=row['year_of_birth'],
            gender=row['gender'],
            title=row['fide_title'],
            women_title=row.get('fide_women_title') or '',
            transient_arbiter_titles={'fide': row['fide_arbiter_title']},
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
        filters: dict | None = None,
    ) -> list[StoredPlayer]:
        tokens: list[str] = [
            unicode_normalize(token) for token in re.split(r'\s+', string)
        ]
        str_fields: tuple[tuple[str, str, str], ...] = (
            ('last_name', '%', '%'),
            ('first_name', '%', '%'),
        )
        int_fields: tuple[str, ...] = ('fide_id',)
        filter_conditions, filter_params = self._process_filters(filters or {})
        token_conditions: dict[str, str] = {}
        params: list[Any] = list(filter_params)
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
            filter_conditions
            + [f'({condition})' for condition in token_conditions.values()]
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

    def get_stored_player_by_fide_id(self, player_fide_id: int) -> StoredPlayer | None:
        self.execute('SELECT * FROM `player` WHERE `fide_id` = ?', (player_fide_id,))
        if player_row := self.fetchone():
            return self._get_player_from_row(player_row)
        return None

    def covers_rating_period(self, day: date) -> bool:
        """Whether the installed database is the rating list of *day*'s period.

        FIDE publishes a rating list on the 1st of every month, so the list
        installed during a given month is the one that applies to the
        tournaments of that month."""
        if not self.exists():
            return False
        updated_at = self.updated_at
        if updated_at is None:
            return False
        return (updated_at.year, updated_at.month) == (day.year, day.month)

    def get_stored_players_by_fide_id(
        self, player_fide_ids: list[int]
    ) -> list[StoredPlayer]:
        query_array = ', '.join('?' for _ in player_fide_ids)
        self.execute(
            f'SELECT * FROM player WHERE fide_id IN ({query_array})',
            tuple(player_fide_ids),
        )
        return [self._get_player_from_row(row) for row in self.fetchall()]

    @staticmethod
    def _process_filters(filters: dict) -> tuple[list[str], list[Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if 'federation_filter' in filters:
            conditions.append('federation = ?')
            params.append(filters['federation_filter'])
        if 'gender_filter' in filters:
            conditions.append('gender = ?')
            params.append(filters['gender_filter'])
        if filters.get('year_of_birth_filter'):
            age_conditions: list[str] = []
            for min_year, max_year in filters['year_of_birth_filter']:
                match min_year, max_year:
                    case None, None:
                        continue
                    case None, _:
                        age_conditions.append('year_of_birth <= ?')
                        params.append(str(max_year))
                    case _, None:
                        age_conditions.append('year_of_birth >= ?')
                        params.append(str(min_year))
                    case _, _:
                        age_conditions.append('year_of_birth BETWEEN ? AND ?')
                        params += [str(min_year), str(max_year)]
            if age_conditions:
                conditions.append(f'({" OR ".join(age_conditions)})')
        return conditions, params

    # ---------------------------------------------------------------------------------
    # Legacy
    # ---------------------------------------------------------------------------------

    @property
    def legacy_min_recovery_version(self) -> Version | None:
        # Pre-version-5 databases use the version 1 schema, which lacks the
        # columns of the current schema, so they cannot be recovered.
        return None
