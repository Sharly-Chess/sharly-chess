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


class EcfDatabase(NationalPlayerDatabase):
    """The rating list of the English Chess Federation (ECF), the CSV of
    its rating API.

    Columns: ECF_code,full_name,member_no,FIDE_no,gender,nation,
    original_standard,…,revised_standard,…,revised_rapid,…,revised_blitz,…
    (the online ratings too),club_code,club_name,title, with the name
    written Last name, First name. The list carries no year of birth."""

    federation = 'ENG'
    acronym = 'ECF'

    _URL = 'https://rating.englishchess.org.uk/api/rating-list/csv'

    @staticmethod
    def static_id() -> str:
        return 'ecf'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'ecf.csv'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        return self._download_file(self._URL, source_file_dir / self._source_file_name)

    @staticmethod
    def _gender(value: str) -> str:
        try:
            return PlayerGender.from_fide_value(value.strip())
        except ValueError:
            return PlayerGender.NONE

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        with open(
            source_file_path, encoding='utf-8', errors='replace', newline=''
        ) as f:
            for row in csv.DictReader(f):
                national_id = row['ECF_code'].strip()
                if not national_id:
                    continue
                last_name, _sep, first_name = row['full_name'].partition(',')
                yield NationalPlayerRow(
                    national_id=national_id,
                    last_name=last_name.strip(),
                    first_name=first_name.strip(),
                    gender=self._gender(row['gender']),
                    title=row['title'].strip(),
                    federation=row['nation'].strip() or self.federation,
                    club=row['club_name'].strip() or None,
                    fide_id=self._int_or_none(row['FIDE_no']),
                    standard_rating=self._int_or_none(row['revised_standard']),
                    rapid_rating=self._int_or_none(row['revised_rapid']),
                    blitz_rating=self._int_or_none(row['revised_blitz']),
                )
