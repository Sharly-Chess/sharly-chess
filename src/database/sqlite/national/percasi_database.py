import csv
import re
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import override

from packaging.version import Version

from database.sqlite.national.national_database import (
    NationalPlayerDatabase,
    NationalPlayerRow,
)
from utils.enum import PlayerGender, PlayerTitle


class PercasiDatabase(NationalPlayerDatabase):
    """The national rating list (DRN) of the Indonesian Chess Federation
    (Percasi), the Google Sheet linked from its site, published twice a
    year.

    Columns, after two title rows: ID., FIDE-ID, PROVINSI, NAMA, L/P
    (P for the women), Tgl.Lahir (m/d/Y), Gelar (FIDE or national title),
    Standar, Cepat, Kilat. The names are kept whole."""

    federation = 'INA'
    acronym = 'Percasi'

    _PAGE_URL = 'https://www.pb-percasi.com/p/blog-page_22.html'
    _SHEET_PATTERN = re.compile(r'docs\.google\.com/spreadsheets/d/([\w-]+)')

    @staticmethod
    def static_id() -> str:
        return 'percasi'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'drn.csv'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        page = self._fetch_page(self._PAGE_URL)
        if page is None:
            return False
        match = self._SHEET_PATTERN.search(page)
        if match is None:
            return False
        url = (
            f'https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv'
        )
        return self._download_file(url, source_file_dir / self._source_file_name)

    @staticmethod
    def _date_or_none(value: str) -> date | None:
        try:
            return datetime.strptime(value.strip(), '%m/%d/%Y').date()
        except ValueError:
            return None

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        with open(
            source_file_path, encoding='utf-8', errors='replace', newline=''
        ) as f:
            headers: list[str] | None = None
            for values in csv.reader(f):
                if headers is None:
                    if values and values[0].strip().upper().startswith('ID'):
                        headers = [value.strip() for value in values]
                    continue
                row = dict(zip(headers, values, strict=False))
                national_id = row.get('ID.', '').strip()
                if not national_id.isdigit():
                    continue
                date_of_birth = self._date_or_none(row.get('Tgl.Lahir', ''))
                title = row.get('Gelar', '').strip().upper()
                yield NationalPlayerRow(
                    national_id=national_id,
                    last_name=row.get('NAMA', '').strip(),
                    year_of_birth=date_of_birth.year if date_of_birth else None,
                    date_of_birth=date_of_birth,
                    gender=(
                        PlayerGender.WOMAN
                        if row.get('L/P', '').strip().upper() == 'P'
                        else PlayerGender.MAN
                    ),
                    title=title if title in {t.value for t in PlayerTitle} else '',
                    federation=self.federation,
                    club=row.get('PROVINSI', '').strip() or None,
                    fide_id=self._int_or_none(row.get('FIDE-ID')),
                    standard_rating=self._int_or_none(row.get('Standar')),
                    rapid_rating=self._int_or_none(row.get('Cepat')),
                    blitz_rating=self._int_or_none(row.get('Kilat')),
                )
