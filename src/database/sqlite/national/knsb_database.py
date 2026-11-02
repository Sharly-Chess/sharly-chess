import csv
import json
import re
from collections.abc import Iterator
from logging import Logger
from pathlib import Path
from typing import Any, override

from packaging.version import Version

from common.logger import get_logger

from database.sqlite.national.national_database import (
    NationalPlayerDatabase,
    NationalPlayerRow,
)
from utils.enum import PlayerGender

logger: Logger = get_logger()


class KnsbDatabase(NationalPlayerDatabase):
    """The rating lists of the Royal Dutch Chess Federation (KNSB): one
    file per rate of play, the classical one carrying the players.

    Columns: Relatienummer;Naam;Titel;FED;Rating;Nv;Geboren;S, with the
    name written Last name, First name and S set to w for the women."""

    federation = 'NED'
    acronym = 'KNSB'

    _MEDIA_URL = 'https://schaakbond.nl/wp-json/wp/v2/media'
    _LISTS: tuple[str, ...] = ('KLASSIEK', 'RAPID', 'SNEL')

    @staticmethod
    def static_id() -> str:
        return 'knsb'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'KLASSIEK.csv'

    @staticmethod
    def _latest_list_url(media: Any, name: str) -> str | None:
        """The address of the latest upload of the list *name* among the
        *media* of the federation's site, given most recently modified
        first: the list is uploaded each month into the folder of the month
        of its upload, as NAME.zip and as YYYY-MM-NAME.zip."""
        pattern = re.compile(rf'/(?:\d{{4}}-\d{{2}}-)?{name}\.zip$')
        if not isinstance(media, list):
            return None
        return next(
            (
                url
                for item in media
                if isinstance(item, dict)
                and isinstance(url := item.get('source_url'), str)
                and pattern.search(url)
            ),
            None,
        )

    def _download_list(self, name: str, source_file_dir: Path) -> bool:
        """Downloads the list *name* to NAME.csv in *source_file_dir*,
        returns False on failure."""
        page = self._fetch_page(
            f'{self._MEDIA_URL}?search={name}&mime_type=application/zip'
            '&orderby=modified&order=desc&per_page=100&_fields=source_url'
        )
        if page is None:
            return False
        try:
            media = json.loads(page)
        except ValueError:
            logger.error(self.log_prefix + 'Unreadable list of the uploads.')
            return False
        url = self._latest_list_url(media, name)
        if url is None:
            logger.error(self.log_prefix + 'No upload of [%s] found.', name)
            return False
        list_dir = source_file_dir / name
        list_dir.mkdir()
        if not self._download_and_unzip(url, list_dir):
            return False
        csv_files = list(list_dir.glob('*.csv'))
        if len(csv_files) != 1:
            logger.error(self.log_prefix + 'No single CSV file in [%s].', url)
            return False
        csv_files[0].replace(source_file_dir / f'{name}.csv')
        list_dir.rmdir()
        return True

    def _download_source_file(self, source_file_dir: Path) -> bool:
        return all(self._download_list(name, source_file_dir) for name in self._LISTS)

    @classmethod
    def _read_ratings(cls, file: Path) -> dict[str, int | None]:
        with open(file, encoding='cp1252', newline='') as f:
            return {
                row['Relatienummer']: cls._int_or_none(row['Rating'])
                for row in csv.DictReader(f, delimiter=';')
            }

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        rapid_ratings = self._read_ratings(source_file_path.with_name('RAPID.csv'))
        blitz_ratings = self._read_ratings(source_file_path.with_name('SNEL.csv'))
        with open(source_file_path, encoding='cp1252', newline='') as f:
            for row in csv.DictReader(f, delimiter=';'):
                national_id = row['Relatienummer'].strip()
                if not national_id:
                    continue
                last_name, _sep, first_name = row['Naam'].partition(',')
                yield NationalPlayerRow(
                    national_id=national_id,
                    last_name=last_name.strip(),
                    first_name=first_name.strip(),
                    year_of_birth=self._int_or_none(row['Geboren']),
                    gender=(
                        PlayerGender.WOMAN
                        if row['S'].strip().lower() == 'w'
                        else PlayerGender.MAN
                    ),
                    title=row['Titel'].strip(),
                    federation=row['FED'].strip() or self.federation,
                    standard_rating=self._int_or_none(row['Rating']),
                    rapid_rating=rapid_ratings.get(national_id),
                    blitz_rating=blitz_ratings.get(national_id),
                )
