import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from datetime import date
from logging import Logger
from pathlib import Path
from typing import Any, ClassVar, override

from text_unidecode import unidecode

from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from utils.types import PlayerRating
from database.sqlite.config.config_store import StoredLocalSourceDatabase
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.local_source_database import LocalSourcePlayerDatabase
from database.sqlite.local_source_database.actions import NotifOutdatedAction
from database.sqlite.local_source_database.delays import MonthFirstDayOutdatedDelay
from database.sqlite.sqlite_database import SQLiteDatabase
from utils.enum import TournamentRating

logger: Logger = get_logger()


def search_key(string: str) -> str:
    """What the names are searched on: Latin letters without accents, no
    case (SQLite's LIKE ignores the case of ASCII letters only), so that a
    Cyrillic name is found from a Latin keyboard."""
    return str(unidecode(string)).casefold()


@dataclass
class NationalPlayerRow:
    """A player read from a federation's rating list, the way it is stored
    in the local database."""

    national_id: str
    last_name: str
    first_name: str = ''
    year_of_birth: int | None = None
    date_of_birth: date | None = None
    gender: str = ''
    title: str = ''
    federation: str = ''
    club: str | None = None
    fide_id: int | None = None
    standard_rating: int | None = None
    rapid_rating: int | None = None
    blitz_rating: int | None = None
    fide_standard_rating: int | None = None
    fide_rapid_rating: int | None = None
    fide_blitz_rating: int | None = None

    @property
    def params(self) -> tuple:
        return (
            self.national_id,
            self.last_name,
            self.first_name,
            search_key(self.last_name),
            search_key(self.first_name),
            self.year_of_birth,
            SQLiteDatabase.dump_date_to_database_field(self.date_of_birth),
            self.gender,
            self.title,
            self.federation,
            self.club,
            self.fide_id,
            self.standard_rating,
            self.rapid_rating,
            self.blitz_rating,
            self.fide_standard_rating,
            self.fide_rapid_rating,
            self.fide_blitz_rating,
        )


class NationalPlayerDatabase(LocalSourcePlayerDatabase, ABC):
    """A federation's rating list, downloaded from the federation and
    converted locally. The subclasses download the federation's file and
    read its players; the storage and the searches are shared."""

    #: The acronym of the federation, what the database is called.
    acronym: ClassVar[str] = ''

    _INSERT_BATCH_SIZE = 5000

    @classmethod
    def static_name(cls) -> str:
        assert cls.federation is not None
        return f'{cls.acronym} ({SharlyChessConfig().federations[cls.federation]})'

    @classmethod
    def national_source_id(cls) -> str:
        """The `national_source` of the players read from the database."""
        return cls.static_id()

    @property
    def _schema(self) -> str:
        return """
            CREATE TABLE `player` (
                `national_id` TEXT NOT NULL,
                `last_name` TEXT NOT NULL,
                `first_name` TEXT NOT NULL,
                `last_name_key` TEXT NOT NULL,
                `first_name_key` TEXT NOT NULL,
                `year_of_birth` INTEGER,
                `date_of_birth` TEXT,
                `gender` TEXT NOT NULL,
                `title` TEXT NOT NULL,
                `federation` TEXT NOT NULL,
                `club` TEXT,
                `fide_id` INTEGER,
                `standard_rating` INTEGER,
                `rapid_rating` INTEGER,
                `blitz_rating` INTEGER,
                `fide_standard_rating` INTEGER,
                `fide_rapid_rating` INTEGER,
                `fide_blitz_rating` INTEGER,
                PRIMARY KEY(`national_id`)
            );
        """

    @override
    @property
    def default_stored_database(self) -> StoredLocalSourceDatabase:
        return StoredLocalSourceDatabase(
            name=self.id,
            outdate_delay=MonthFirstDayOutdatedDelay.static_id(),
            outdate_action=NotifOutdatedAction.static_id(),
        )

    @abstractmethod
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        """Reads the players of the federation's file at *source_file_path*
        (the other files downloaded next to it are available too)."""

    @override
    def _populate_from_source_file(
        self, source_file_path: Path, database: SQLiteDatabase
    ) -> bool:
        query = (
            'INSERT OR REPLACE INTO `player` ('
            '`national_id`, `last_name`, `first_name`, '
            '`last_name_key`, `first_name_key`, `year_of_birth`, '
            '`date_of_birth`, `gender`, `title`, `federation`, `club`, `fide_id`, '
            '`standard_rating`, `rapid_rating`, `blitz_rating`, '
            '`fide_standard_rating`, `fide_rapid_rating`, `fide_blitz_rating`'
            ') VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
        )
        batch: list[tuple] = []
        count = 0
        for row in self._read_players(source_file_path):
            if self.stop_event.is_set():
                return False
            batch.append(row.params)
            if len(batch) >= self._INSERT_BATCH_SIZE:
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

    @classmethod
    @override
    def _create_indexes(cls, database: SQLiteDatabase) -> None:
        database.execute(
            'CREATE INDEX `player_last_name_key` ON `player`(`last_name_key`)'
        )
        database.execute(
            'CREATE INDEX `player_first_name_key` ON `player`(`first_name_key`)'
        )
        database.execute('CREATE INDEX `player_fide_id` ON `player`(`fide_id`)')

    # ---------------------------------------------------------------------------------
    # Reading helpers for the subclasses
    # ---------------------------------------------------------------------------------

    @staticmethod
    def _int_or_none(value: str | None) -> int | None:
        """A positive integer of the rating list, None when the field is
        empty or zero (no rating, no identifier)."""
        if value is None:
            return None
        value = value.strip()
        if not value.isdigit():
            return None
        return int(value) or None

    @staticmethod
    def _split_upper_last_name(full_name: str) -> tuple[str, str]:
        """Splits a name written LAST NAME First name; a name written in
        capitals only gives its first word as the last name."""
        tokens = full_name.split()
        if not tokens:
            return '', ''
        last_name_tokens: list[str] = []
        for token in tokens:
            if token != token.upper():
                break
            last_name_tokens.append(token)
        if not last_name_tokens or len(last_name_tokens) == len(tokens):
            last_name_tokens = tokens[:1]
        return (
            ' '.join(last_name_tokens),
            ' '.join(tokens[len(last_name_tokens) :]),
        )

    # ---------------------------------------------------------------------------------
    # Searches
    # ---------------------------------------------------------------------------------

    @classmethod
    def _get_player_from_row(cls, row: dict[str, Any]) -> StoredPlayer:
        rating_keys = {
            TournamentRating.STANDARD: ('standard_rating', 'fide_standard_rating'),
            TournamentRating.RAPID: ('rapid_rating', 'fide_rapid_rating'),
            TournamentRating.BLITZ: ('blitz_rating', 'fide_blitz_rating'),
        }
        ratings = {
            tournament_rating.value: PlayerRating(
                national=row[national_key] or None,
                fide=row[fide_key] or None,
            ).stored_value
            for tournament_rating, (national_key, fide_key) in rating_keys.items()
        }
        return StoredPlayer(
            id=None,
            first_name=row['first_name'].title(),
            last_name=row['last_name'].upper(),
            year_of_birth=row['year_of_birth'],
            date_of_birth=SQLiteDatabase.load_optional_date_from_database_field(
                row['date_of_birth']
            ),
            gender=row['gender'],
            title=row['title'],
            ratings=ratings,
            fide_id=row['fide_id'],
            national_id=row['national_id'],
            national_source=cls.national_source_id(),
            federation=row['federation'] or cls.federation or '',
            club=row['club'],
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
            search_key(token) for token in re.split(r'\s+', string.strip())
        ]
        filter_conditions, filter_params = self._process_filters(filters or {})
        token_conditions: list[str] = []
        params: list[Any] = list(filter_params)
        for token in tokens:
            expressions = ['(last_name_key LIKE ?)', '(first_name_key LIKE ?)']
            params += [f'%{token}%', f'%{token}%']
            expressions.append('(national_id = ?)')
            params.append(token)
            with suppress(ValueError):
                fide_id = int(token)
                expressions.append('(fide_id = ?)')
                params.append(fide_id)
            token_conditions.append(f'({" OR ".join(expressions)})')
        conditions = ' AND '.join(filter_conditions + token_conditions) or '1'
        order_clauses: list[str] = []
        for token in tokens:
            order_clauses.append(
                'CASE'
                ' WHEN last_name_key LIKE ? THEN 0'
                ' WHEN first_name_key LIKE ? THEN 1'
                ' ELSE 2'
                ' END'
            )
            params += [f'{token}%', f'{token}%']
        order_expr = ' + '.join(order_clauses) or '0'
        query = (
            f'SELECT * FROM player WHERE {conditions} '
            f'ORDER BY {order_expr}, last_name, first_name'
        )
        if limit:
            query += ' LIMIT ?'
            params.append(limit)
            if page:
                query += ' OFFSET ?'
                params.append(page * limit)
        self.execute(query, tuple(params))
        return [self._get_player_from_row(row) for row in self.fetchall()]

    def get_stored_player_by_national_id(self, national_id: str) -> StoredPlayer | None:
        self.execute('SELECT * FROM `player` WHERE `national_id` = ?', (national_id,))
        if row := self.fetchone():
            return self._get_player_from_row(row)
        return None

    def get_stored_players_by_national_id(
        self, national_ids: list[str]
    ) -> list[StoredPlayer]:
        if not national_ids:
            return []
        placeholders = ', '.join('?' for _ in national_ids)
        self.execute(
            f'SELECT * FROM `player` WHERE `national_id` IN ({placeholders})',
            tuple(national_ids),
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
        if 'club_filter' in filters:
            conditions.append('LOWER(club) LIKE LOWER(?)')
            params.append(f'%{filters["club_filter"]}%')
        if filters.get('year_of_birth_filter'):
            age_conditions: list[str] = []
            for min_year, max_year in filters['year_of_birth_filter']:
                match min_year, max_year:
                    case None, None:
                        continue
                    case None, _:
                        age_conditions.append('year_of_birth <= ?')
                        params.append(max_year)
                    case _, None:
                        age_conditions.append('year_of_birth >= ?')
                        params.append(min_year)
                    case _, _:
                        age_conditions.append('year_of_birth BETWEEN ? AND ?')
                        params += [min_year, max_year]
            if age_conditions:
                conditions.append(f'({" OR ".join(age_conditions)})')
        return conditions, params
