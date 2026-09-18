import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, override

import openpyxl
from packaging.version import Version

from database.sqlite.national.national_database import (
    NationalPlayerDatabase,
    NationalPlayerRow,
)


class NzcfDatabase(NationalPlayerDatabase):
    """The rating list of the New Zealand Chess Federation, the alphabetical
    spreadsheet linked from its ratings page under a dated name.

    Two header rows: Code, Name (two columns: last and first name), Club,
    Year, the standard and rapid blocks (Rating, T, G, ∑G, Active) and the
    FIDE block (Code, Fed, Title); an unrated player has "unr"."""

    federation = 'NZL'
    acronym = 'NZCF'

    _PAGE_URL = 'https://compete.newzealandchess.co.nz/new-zealand-ratings-list/'
    _FILE_PATTERN = re.compile(
        r'https://compete\.newzealandchess\.co\.nz/wp-content/uploads/\S*?'
        r'(\d{4}-\d)-Alphabetical-(\d{8})\.xlsx'
    )

    @staticmethod
    def static_id() -> str:
        return 'nzcf'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'rating_list.xlsx'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        page = self._fetch_page(self._PAGE_URL)
        if page is None:
            return False
        matches = [
            (match.group(2), match.group(0))
            for match in self._FILE_PATTERN.finditer(page)
        ]
        if not matches:
            return False
        return self._download_file(
            max(matches)[1], source_file_dir / self._source_file_name
        )

    @staticmethod
    def _cell_int(value: Any) -> int | None:
        try:
            return int(float(str(value).strip())) or None
        except (TypeError, ValueError):
            return None

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        workbook = openpyxl.load_workbook(source_file_path, read_only=True)
        sheet = workbook.worksheets[0]
        columns: dict[str, int] = {}
        for values in sheet.iter_rows(values_only=True):
            if not columns:
                if values and values[0] == 'Code':
                    # The blocks of the first header row start at their label;
                    # the second row only details them.
                    labels = [str(value or '').strip() for value in values]
                    columns = {
                        label: index for index, label in enumerate(labels) if label
                    }
                continue
            if values and values[0] is None and columns and 'rating_row' not in columns:
                columns['rating_row'] = 1
                continue
            national_id = self._cell_int(values[columns['Code']])
            if national_id is None:
                continue
            fide_block = columns['FIDE']
            yield NationalPlayerRow(
                national_id=str(national_id),
                last_name=str(values[columns['Name']] or '').strip(),
                first_name=str(values[columns['Name'] + 1] or '').strip(),
                year_of_birth=self._cell_int(values[columns['Year']]),
                title=str(values[fide_block + 2] or '').strip(),
                federation=str(values[fide_block + 1] or '').strip() or self.federation,
                club=str(values[columns['Club']] or '').strip() or None,
                fide_id=self._cell_int(values[fide_block]),
                standard_rating=self._cell_int(values[columns['Standard']]),
                rapid_rating=self._cell_int(values[columns['Rapid']]),
            )
