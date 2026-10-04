import csv
from collections.abc import Iterator
from pathlib import Path
from typing import override

from packaging.version import Version

from database.sqlite.national.national_database import (
    NationalPlayerDatabase,
    NationalPlayerRow,
)
from utils.enum import PlayerGender


class KnsbDatabase(NationalPlayerDatabase):
    """The rating lists of the Royal Dutch Chess Federation (KNSB): one
    file per rate of play, the classical one carrying the players.

    Columns: Relatienummer;Naam;Titel;FED;Rating;Nv;Geboren;S, with the
    name written Last name, First name and S set to w for the women."""

    federation = 'NED'
    acronym = 'KNSB'

    _DOWNLOADS_URL = 'https://schaakbond.nl/wp-content/uploads/'
    _LISTS: tuple[tuple[str, str], ...] = (
        ('KLASSIEK', '2024/12/KLASSIEK.zip'),
        ('RAPID', '2024/10/RAPID.zip'),
        ('SNEL', '2024/10/SNEL.zip'),
    )

    @staticmethod
    def static_id() -> str:
        return 'knsb'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'KLASSIEK.csv'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        return all(
            self._download_and_unzip(self._DOWNLOADS_URL + path, source_file_dir)
            for _, path in self._LISTS
        )

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
