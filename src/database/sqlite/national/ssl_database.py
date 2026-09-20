import csv
from collections.abc import Iterator
from pathlib import Path
from typing import override

from packaging.version import Version

from database.sqlite.national.national_database import (
    NationalPlayerDatabase,
    NationalPlayerRow,
)


class SslDatabase(NationalPlayerDatabase):
    """The SELO rating list of the Finnish Chess Federation (Suomen
    Shakkiliitto), the CSV export of shakki.net.

    Columns: Id;Sukunimi;Etunimi;Seura;Selo;Selopelejä;Ikäryhmä;Maa;Lisenssi.
    The list carries neither the birth year nor the gender."""

    federation = 'FIN'
    acronym = 'SELO'

    _URL = (
        'https://www.shakki.net/cgi-bin/selo?do=selo&haku=&maa=&ehto=ja&akt=&ar=&yr='
        '&ika=&muoto=csv&sp=&seurat=0&listaus=vahvuus&max=&lista=selo&listapvm='
        '&sivpit=10000'
    )

    @staticmethod
    def static_id() -> str:
        return 'ssl'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'selo.csv'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        return self._download_file(self._URL, source_file_dir / self._source_file_name)

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        with open(source_file_path, encoding='cp1252', newline='') as f:
            for row in csv.DictReader(f, delimiter=';'):
                national_id = row['Id'].strip()
                if not national_id:
                    continue
                yield NationalPlayerRow(
                    national_id=national_id,
                    last_name=row['Sukunimi'].strip(),
                    first_name=row['Etunimi'].strip(),
                    federation=row['Maa'].strip() or self.federation,
                    club=row['Seura'].strip() or None,
                    standard_rating=self._int_or_none(row['Selo']),
                )
