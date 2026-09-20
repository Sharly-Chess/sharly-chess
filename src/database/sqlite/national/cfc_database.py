import csv
from collections.abc import Iterator
from pathlib import Path
from typing import override

from packaging.version import Version

from database.sqlite.national.national_database import (
    NationalPlayerDatabase,
    NationalPlayerRow,
)


class CfcDatabase(NationalPlayerDatabase):
    """The rating list of the Chess Federation of Canada (CFC), its
    tdlist.txt file.

    Columns: CFC#,Expiry,Last,First,Prov,City,Rating,High,Active Rtg,
    Active High,FIDE Number,FIDE Rating; the regular rating applies to
    the classical games, the active (quick) one to rapid and blitz. The
    quoting of the file is broken (the city carries a stray quote), so
    every field is stripped of its quotes."""

    federation = 'CAN'
    acronym = 'CFC'

    _URL = 'https://storage.googleapis.com/cfc-public/data/tdlist.txt'

    @staticmethod
    def static_id() -> str:
        return 'cfc'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'tdlist.txt'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        return self._download_file(self._URL, source_file_dir / self._source_file_name)

    @staticmethod
    def _clean(value: str | None) -> str:
        return (value or '').strip().strip('"').strip()

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        with open(
            source_file_path, encoding='utf-8', errors='replace', newline=''
        ) as f:
            for row in csv.DictReader(f):
                national_id = self._clean(row['CFC#'])
                last_name = self._clean(row['Last'])
                if not national_id or not last_name or last_name == '---':
                    continue
                quick_rating = self._int_or_none(self._clean(row['Active Rtg']))
                yield NationalPlayerRow(
                    national_id=national_id,
                    last_name=last_name,
                    first_name=self._clean(row['First']),
                    federation=self.federation,
                    club=self._clean(row['City']) or None,
                    fide_id=self._int_or_none(self._clean(row['FIDE Number'])),
                    standard_rating=self._int_or_none(self._clean(row['Rating'])),
                    rapid_rating=quick_rating,
                    blitz_rating=quick_rating,
                    fide_standard_rating=self._int_or_none(
                        self._clean(row['FIDE Rating'])
                    ),
                )
