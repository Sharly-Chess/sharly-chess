import csv
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import override

from packaging.version import Version

from database.sqlite.national.national_database import (
    NationalPlayerDatabase,
    NationalPlayerRow,
)
from utils.enum import PlayerGender


class ChessaDatabase(NationalPlayerDatabase):
    """The rating lists of Chess South Africa (CHESSA): one CSV file per
    rate of play, the classical one ("main") carrying the players.

    Columns: UNIQUE_NO,SURNAME,FIRSTNAME,BDATE,SEX,TITLE,RATING,FED, the
    federation being the regional one; a date of birth of 1900/01/01
    stands for none."""

    federation = 'RSA'
    acronym = 'CHESSA'

    _DOWNLOADS_URL = 'https://ratings.chessa.co.za/downloads/'
    _LISTS: tuple[str, ...] = ('main', 'rapid', 'blitz')

    @staticmethod
    def static_id() -> str:
        return 'chessa'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'ratings_main.csv'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        return all(
            self._download_and_unzip(
                f'{self._DOWNLOADS_URL}ratings_{list_}.zip', source_file_dir
            )
            for list_ in self._LISTS
        )

    @staticmethod
    def _read_rows(file: Path) -> Iterator[dict[str, str]]:
        with open(file, encoding='utf-8', errors='replace', newline='') as f:
            yield from csv.DictReader(f)

    @classmethod
    def _read_ratings(cls, file: Path) -> dict[str, int | None]:
        return {
            row['UNIQUE_NO'].strip(): cls._int_or_none(row['RATING'])
            for row in cls._read_rows(file)
        }

    @staticmethod
    def _date_or_none(value: str) -> date | None:
        try:
            date_ = datetime.strptime(value.strip(), '%Y/%m/%d').date()
        except ValueError:
            return None
        return None if date_.year <= 1900 else date_

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        rapid_ratings = self._read_ratings(
            source_file_path.with_name('ratings_rapid.csv')
        )
        blitz_ratings = self._read_ratings(
            source_file_path.with_name('ratings_blitz.csv')
        )
        for row in self._read_rows(source_file_path):
            national_id = row['UNIQUE_NO'].strip()
            if not national_id:
                continue
            date_of_birth = self._date_or_none(row['BDATE'])
            yield NationalPlayerRow(
                national_id=national_id,
                last_name=row['SURNAME'].strip(),
                first_name=row['FIRSTNAME'].strip(),
                year_of_birth=date_of_birth.year if date_of_birth else None,
                date_of_birth=date_of_birth,
                gender=(
                    PlayerGender.WOMAN
                    if row['SEX'].strip().upper() == 'F'
                    else PlayerGender.MAN
                    if row['SEX'].strip().upper() == 'M'
                    else PlayerGender.NONE
                ),
                title=row['TITLE'].strip(),
                federation=self.federation,
                club=row['FED'].strip() or None,
                standard_rating=self._int_or_none(row['RATING']),
                rapid_rating=rapid_ratings.get(national_id),
                blitz_rating=blitz_ratings.get(national_id),
            )
