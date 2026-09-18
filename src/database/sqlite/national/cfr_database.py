import csv
from collections.abc import Iterator
from pathlib import Path
from typing import override

from packaging.version import Version

from database.sqlite.config.config_store import StoredLocalSourceDatabase
from database.sqlite.local_source_database.actions import NotifOutdatedAction
from database.sqlite.local_source_database.delays import WeeklyOutdatedDelay
from database.sqlite.national.national_database import (
    NationalPlayerDatabase,
    NationalPlayerRow,
)
from utils.enum import PlayerGender


class CfrDatabase(NationalPlayerDatabase):
    """The rating lists of the Chess Federation of Russia (ФШР), the
    Swiss-Manager exports of ratings.ruchess.ru: one file per rate of play,
    the classical one carrying the players.

    Columns: ID_No,Name,Sex,Fed,Clubnumber,ClubName,Birthday,Rtg_Nat,
    Fide_No,Rtg_Int, with the name written Last name First name Patronymic
    and Sex set to f for the women."""

    federation = 'RUS'
    acronym = 'CFR'

    _API_URL = 'https://ratings.ruchess.ru/api/'
    _LISTS: tuple[str, ...] = ('standard', 'rapid', 'blitz')

    @staticmethod
    def static_id() -> str:
        return 'cfr'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'smanager_standard.csv'

    @override
    @property
    def default_stored_database(self) -> StoredLocalSourceDatabase:
        return StoredLocalSourceDatabase(
            name=self.id,
            outdate_delay=WeeklyOutdatedDelay.static_id(),
            outdate_action=NotifOutdatedAction.static_id(),
        )

    def _download_source_file(self, source_file_dir: Path) -> bool:
        return all(
            self._download_and_unzip(
                f'{self._API_URL}smanager_{list_}.csv.zip', source_file_dir
            )
            for list_ in self._LISTS
        )

    @staticmethod
    def _read_rows(file: Path) -> Iterator[dict[str, str]]:
        with open(file, encoding='utf-8-sig', newline='') as f:
            yield from csv.DictReader(f)

    @classmethod
    def _read_ratings(cls, file: Path) -> dict[str, int | None]:
        return {
            row['ID_No']: cls._int_or_none(row['Rtg_Nat'])
            for row in cls._read_rows(file)
        }

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        rapid_ratings = self._read_ratings(
            source_file_path.with_name('smanager_rapid.csv')
        )
        blitz_ratings = self._read_ratings(
            source_file_path.with_name('smanager_blitz.csv')
        )
        for row in self._read_rows(source_file_path):
            national_id = row['ID_No'].strip()
            if not national_id:
                continue
            last_name, _sep, first_name = row['Name'].strip().partition(' ')
            yield NationalPlayerRow(
                national_id=national_id,
                last_name=last_name,
                first_name=first_name.strip(),
                year_of_birth=self._int_or_none(row['Birthday']),
                gender=(
                    PlayerGender.WOMAN
                    if row['Sex'].strip().lower() == 'f'
                    else PlayerGender.MAN
                ),
                federation=row['Fed'].strip() or self.federation,
                club=row['ClubName'].strip() or None,
                fide_id=self._int_or_none(row['Fide_No']),
                standard_rating=self._int_or_none(row['Rtg_Nat']),
                rapid_rating=rapid_ratings.get(national_id),
                blitz_rating=blitz_ratings.get(national_id),
                fide_standard_rating=self._int_or_none(row['Rtg_Int']),
            )
