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


class FsiDatabase(NationalPlayerDatabase):
    """The rating list of the Italian Chess Federation (FSI), the ALLIN
    export of torneionline.com.

    The name is written LAST NAME First name; the players without an FSI
    id are placeholders of the export."""

    federation = 'ITA'
    acronym = 'FSI'

    _URL = 'https://www.torneionline.com/dwn/allin.csv'

    @staticmethod
    def static_id() -> str:
        return 'fsi'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'allin.csv'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        return self._download_file(self._URL, source_file_dir / self._source_file_name)

    @staticmethod
    def _gender(value: str) -> str:
        try:
            return PlayerGender.from_fide_value(value.strip())
        except ValueError:
            return PlayerGender.NONE

    @staticmethod
    def _date_or_none(value: str) -> date | None:
        try:
            return datetime.strptime(value.strip(), '%d-%m-%Y').date()
        except ValueError:
            return None

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        with open(
            source_file_path, encoding='utf-8', errors='replace', newline=''
        ) as f:
            for row in csv.DictReader(f, delimiter=';'):
                national_id = self._int_or_none(row['ID FSI'])
                if national_id is None:
                    continue
                last_name, first_name = self._split_upper_last_name(row['Nominativo'])
                date_of_birth = self._date_or_none(row['Data Nascita'])
                yield NationalPlayerRow(
                    national_id=str(national_id),
                    last_name=last_name,
                    first_name=first_name,
                    year_of_birth=(
                        date_of_birth.year
                        if date_of_birth
                        else self._int_or_none(row['Anno Nascita'])
                    ),
                    date_of_birth=date_of_birth,
                    gender=self._gender(row['Sex']),
                    federation=row['Federazione'].strip() or self.federation,
                    fide_id=self._int_or_none(row['FIN']),
                    standard_rating=self._int_or_none(row['Elo']),
                    fide_standard_rating=self._int_or_none(row['Elo FIDE Std']),
                    fide_rapid_rating=self._int_or_none(row['Elo FIDE Rapid']),
                    fide_blitz_rating=self._int_or_none(row['Elo FIDE Blitz']),
                )
