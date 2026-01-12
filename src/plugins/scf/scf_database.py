import os.path
import re
import sqlite3
import zipfile
import csv
from contextlib import suppress
from logging import Logger
from pathlib import Path
from typing import Any, Callable, override
from html.parser import HTMLParser
from urllib.parse import urljoin

from requests import Response, get
from requests.exceptions import ConnectionError

from common import Version
from common.i18n import _
from common.i18n.utils import unicode_normalize
from common.logger import get_logger
from data.player import PlayerRating
from database.sqlite.config.config_store import StoredLocalSourceDatabase
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.local_source_database import LocalSourcePlayerDatabase
from database.sqlite.local_source_database.actions import NotifOutdatedAction
from database.sqlite.local_source_database.delays import Days2OutdatedDelay
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins import scf
from plugins.scf import PLUGIN_NAME, PLUGIN_DIR
from plugins.scf.utils import ScfPlayerPluginData
from utils.enum import (
    TournamentRating,
    PlayerRatingType,
    PlayerGender,
)

logger: Logger = get_logger()


class SwissClassListParser(HTMLParser):
    """Parse lc-download.html to find the first ZIP href in the first
    <div class="ce_downloads block"> block.
    """

    def __init__(self) -> None:
        super().__init__()
        self.in_target_div = False
        self.div_depth = 0
        self.first_zip_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.first_zip_href is not None:
            # We already found what we need, skip parsing further
            return

        attrs_dict = dict(attrs)

        if tag == 'div':
            class_attr = attrs_dict.get('class', '')
            classes = class_attr.split() if class_attr else []
            if (
                not self.in_target_div
                and 'ce_downloads' in classes
                and 'block' in classes
            ):
                # Entering the first <div class="ce_downloads block">
                self.in_target_div = True
                self.div_depth = 1
            elif self.in_target_div:
                # Nested div inside the target
                self.div_depth += 1

        if self.in_target_div and tag == 'a':
            href = attrs_dict.get('href')
            if href and '.zip' in href:
                # First ZIP link inside the first ce_downloads block
                self.first_zip_href = href

    def handle_endtag(self, tag: str) -> None:
        if self.in_target_div and tag == 'div':
            self.div_depth -= 1
            if self.div_depth == 0:
                # We are leaving the target div
                self.in_target_div = False


class ScfDatabase(LocalSourcePlayerDatabase):
    """
    The SQLite database class for SCF players. Usage:
    1. Check if the database exists and is up-to-date.
        If outdated, the outdate action is executed:
    ScfDatabase().check()
    2. Search the database:
    with ScfDatabase() as scf_database:
        for player in scf_database.search_player('my name'):
            ...
    """

    @staticmethod
    def static_id() -> str:
        return 'scf'

    @staticmethod
    def static_name() -> str:
        return _('SCF')

    @staticmethod
    def _dir() -> Path:
        return scf.TMP_DIR

    @property
    def min_recovery_version(self) -> Version:
        """The minimal app version for which the database can be recovered."""
        return Version('3.4.0')

    @property
    def _schema_file_path(self) -> Path:
        return PLUGIN_DIR / 'create_scf.sql'

    @property
    def _source_file_name(self) -> str:
        return 'data.csv'

    @override
    @property
    def default_stored_database(self) -> StoredLocalSourceDatabase:
        return StoredLocalSourceDatabase(
            name=self.id,
            outdate_delay=Days2OutdatedDelay.static_id(),
            outdate_action=NotifOutdatedAction.static_id(),
        )

    def _download_source_file(self, source_file_dir: Path) -> bool:
        base_url = 'https://www.swisschess.ch'
        listing_url = f'{base_url}/lc-download.html'

        # Download the listing page (HTML)
        try:
            listing_response: Response = get(
                listing_url, allow_redirects=True, timeout=5
            )
            if listing_response.status_code != 200:
                logger.error(
                    self.log_prefix
                    + 'Could not download listing page [%s], error code [%d].',
                    listing_url,
                    listing_response.status_code,
                )
                return False
        except ConnectionError as ex:
            logger.error(
                self.log_prefix + 'Could not download listing page [%s]: %s.',
                listing_url,
                ex,
            )
            return False

        # Parse the HTML to find first ZIP link in first ce_downloads block
        parser = SwissClassListParser()
        parser.feed(listing_response.text)

        if not parser.first_zip_href:
            logger.error(
                self.log_prefix
                + "Could not find ZIP link in the first <div class='ce_downloads block'>."
            )
            return False

        zip_url = urljoin(listing_url, parser.first_zip_href)

        # Download the ZIP file we just discovered
        local_zip_file: Path = source_file_dir / os.path.basename(zip_url)
        with suppress(FileNotFoundError):
            local_zip_file.unlink()

        try:
            response: Response = get(zip_url, allow_redirects=True, timeout=10)
            if response.status_code != 200:
                logger.error(
                    self.log_prefix + 'Could not download ZIP [%s], error code [%d].',
                    zip_url,
                    response.status_code,
                )
                return False
        except ConnectionError as ex:
            logger.error(
                self.log_prefix + 'Could not download ZIP [%s]: %s.',
                zip_url,
                ex,
            )
            return False

        local_zip_file.write_bytes(response.content)
        if not local_zip_file.exists():
            logger.error(self.log_prefix + 'No data received from [%s].', zip_url)
            return False

        # Unzip into TMP_DIR
        try:
            with zipfile.ZipFile(local_zip_file, 'r') as zip_ref:
                zip_ref.extractall(source_file_dir)
        except zipfile.BadZipFile as ex:
            logger.error(
                self.log_prefix + 'Invalid ZIP file from [%s]: %s.', zip_url, ex
            )
            return False

        # Find the file that is NOT tagged with swisschess or swissmanager
        candidate: Path | None = None

        for f in source_file_dir.iterdir():
            if f.is_file() and f.suffix.lower() in {'.txt', '.csv'}:
                name = f.name.lower()
                if 'swisschess' not in name and 'swissmanager' not in name:
                    candidate = f
                    break

        if candidate is None:
            logger.error(self.log_prefix + 'Could not find untagged Swiss file in ZIP.')
            return False

        # Rename it to the expected source file path
        source_file_name = source_file_dir / self._source_file_name
        try:
            # Ensure destination doesn't exist
            candidate.rename(source_file_name)
        except OSError as ex:
            logger.error(
                self.log_prefix + 'Could not rename [%s] to source file [%s]: %s.',
                candidate,
                source_file_name,
                ex,
            )
            return False

        if not source_file_name.exists():
            logger.error(self.log_prefix + 'Could not unzip data (file not found).')
            return False

        return True

    def _populate_from_source_file(
        self, source_file_path: Path, database: SQLiteDatabase
    ) -> bool:
        fields: dict[str, tuple[str, Callable[[str], Any] | None]] = {
            'Code': ('scf_code', lambda s: s.strip()),
            'Name': ('last_name', lambda s: s.strip()),
            'Vorname': ('first_name', lambda s: s.strip()),
            'Geschlecht': ('gender', PlayerGender.from_fide_value),
            'Jahrgang': ('year_of_birth', lambda s: int(s) if s else 0),
            'Wohnort': ('city', lambda s: s.strip() or None),
            'Federation': ('federation', lambda s: s.strip().upper() if s else None),
            'Verein': ('club', lambda s: s.strip() or None),
            'neue Elo': ('fide_rating', lambda s: int(s) if s else 0),
            'Fide Code': ('fide_id', lambda s: int(s) if s else None),
        }

        # All DB columns we’re going to insert
        db_columns = sorted({field_name for (field_name, _func) in fields.values()})

        placeholders = ', '.join(f':{c}' for c in db_columns)
        columns_sql = ', '.join(db_columns)
        query = f'INSERT INTO player({columns_sql}) VALUES({placeholders})'

        player_count: int = 0
        to_write: list[dict[str, Any]] = []

        with (
            database,
            source_file_path.open('r', encoding='latin-1', newline='') as f,
        ):
            reader = csv.DictReader(f, delimiter=';')

            for row in reader:
                data: dict[str, Any] = {}

                for csv_name, (field_name, transform) in fields.items():
                    raw = (row.get(csv_name) or '').strip()

                    if transform:
                        try:
                            value = transform(raw)
                        except Exception as ex:
                            logger.warning(
                                self.log_prefix
                                + 'Could not parse field %s value %r: %s',
                                csv_name,
                                raw,
                                ex,
                            )
                            # Fallback: store raw string, or None
                            value = None
                    else:
                        value = raw

                    data[field_name] = value

                to_write.append(data)
                player_count += 1

                if player_count % 1000 == 0:
                    database.executemany(query, to_write)
                    to_write.clear()
                    if self.stop_event.is_set():
                        return False

                if player_count % 100_000 == 0:
                    database.commit()

            if to_write:
                database.executemany(query, to_write)
                database.commit()

        logger.info(
            self.log_prefix + '%d players written to the database.', player_count
        )
        return True

    def _create_indexes(self):
        try:
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
                    'CREATE INDEX IF NOT EXISTS `player_scf_code` ON `player`(`scf_code` COLLATE NOCASE)'
                )
                self.commit()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
            logger.error(self.log_prefix + 'Error creating database indexes: %s.', e)
            raise

    @staticmethod
    def get_stored_player_from_row(row: dict[str, Any]) -> StoredPlayer:
        return StoredPlayer(
            id=0,
            first_name=row['first_name'].title() if row['first_name'] else '',
            last_name=row['last_name'].upper(),
            year_of_birth=row['year_of_birth'],
            gender=PlayerGender(row['gender']),
            mail='',
            phone='',
            comment='',
            owed=0.0,
            paid=0.0,
            ratings={
                TournamentRating.STANDARD.value: PlayerRating.from_type(
                    row['fide_rating'],
                    PlayerRatingType.FIDE,
                ).stored_value,
            },
            fide_id=int(row['fide_id']) if row['fide_id'] else None,
            federation=row['federation'] or 'NON',
            club=row['club'],
            fixed=0,
            check_in=False,  # not taken into account when updating/creating/deleting the player
            plugin_data={
                PLUGIN_NAME: ScfPlayerPluginData(
                    scf_code=row['scf_code'],
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
            ('scf_code', '', ''),
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

    def _get_stored_player_by_id(
        self,
        field: str,
        id_: int,
    ) -> StoredPlayer | None:
        self.execute(f'SELECT * FROM player WHERE {field} = ?', (id_,))
        if row := self.fetchone():
            return self.get_stored_player_from_row(row)
        else:
            return None

    def get_stored_player_by_scf_code(
        self,
        player_scf_code: int,
    ) -> StoredPlayer | None:
        return self._get_stored_player_by_id('scf_code', player_scf_code)

    def get_stored_player_by_fide_id(
        self,
        player_fide_id: int,
    ) -> StoredPlayer | None:
        return self._get_stored_player_by_id('fide_id', player_fide_id)

    def get_stored_players_by_scf_code(
        self, scf_codes: list[str]
    ) -> list[StoredPlayer]:
        query_array = ', '.join('?' for _ in scf_codes)
        self.execute(
            f'SELECT * FROM player WHERE scf_code IN ({query_array})',
            tuple(scf_codes),
        )
        return [self.get_stored_player_from_row(row) for row in self.fetchall()]
