import re
import zipfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any, ClassVar, override

import xlrd
from packaging.version import Version

from database.sqlite.national.national_database import (
    NationalPlayerDatabase,
    NationalPlayerRow,
)
from utils.enum import PlayerGender


class UcfDatabase(NationalPlayerDatabase):
    """The national rating list of the Ukrainian Chess Federation, the
    Swiss-Manager spreadsheet of its qualification commission, published
    monthly under a dated path found from the federation's home page.

    Columns: Fide_No, Name, Fed, Sex, Rtg_Nat, Rtg_Int, Birthday, with the
    name written Last name First name in Cyrillic, followed by the titles
    of the player in lower case (мг/змс: grandmaster, honoured master of
    sport…), the regional federation as Fed, Sex carrying a w for the
    women (and an н for the inactive players) and the birthday as a
    spreadsheet date. The FIDE id is the identifier of the players."""

    _TITLES: ClassVar[dict[str, str]] = {'мг': 'GM', 'мм': 'IM', 'мф': 'FM'}

    federation = 'UKR'
    acronym = 'UCF'

    _HOME_URL = 'https://www.ukrchess.org.ua/'
    _PAGE_PATTERN = re.compile(r'kvalif/(\d{4})/(\d{2})/rating\.html')

    @staticmethod
    def static_id() -> str:
        return 'ucf'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'national_ratings.zip'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        page = self._fetch_page(self._HOME_URL)
        if page is None:
            return False
        dates = sorted(
            (int(year), int(month)) for year, month in self._PAGE_PATTERN.findall(page)
        )
        if not dates:
            return False
        year, month = dates[-1]
        url = f'{self._HOME_URL}kvalif/{year}/{month:02d}/nat{year % 100:02d}{month:02d}s.zip'
        return self._download_file(url, source_file_dir / self._source_file_name)

    @classmethod
    def _split_name(cls, name: str) -> tuple[str, str, str]:
        """The last name, the first name and the FIDE title of a name of
        the list: the titles follow the name in lower case, the highest
        first, national ones after a slash."""
        tokens = name.split()
        names = [
            token
            for token in tokens
            if '/' not in token and not token.startswith('(') and token != token.lower()
        ]
        titles = [
            cls._TITLES[fide_title]
            for token in tokens
            if (fide_title := token.split('/')[0]) in cls._TITLES
        ]
        last_name, *first_names = names or ['']
        return last_name, ' '.join(first_names), titles[0] if titles else ''

    @staticmethod
    def _cell_int(value: Any) -> int | None:
        try:
            return int(float(value)) or None
        except (TypeError, ValueError):
            return None

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        with zipfile.ZipFile(source_file_path) as archive:
            names = [name for name in archive.namelist() if name.endswith('.xls')]
            if not names:
                return
            book = xlrd.open_workbook(file_contents=archive.read(names[0]))
        sheet = book.sheet_by_index(0)
        headers = [str(sheet.cell_value(0, column)) for column in range(sheet.ncols)]
        for index in range(1, sheet.nrows):
            row: dict[str, Any] = dict(
                zip(
                    headers,
                    (sheet.cell_value(index, column) for column in range(sheet.ncols)),
                    strict=True,
                )
            )
            fide_id = self._cell_int(row['Fide_No'])
            if fide_id is None:
                continue
            last_name, first_name, title = self._split_name(str(row['Name']))
            date_of_birth: date | None = None
            birthday = row['Birthday']
            if isinstance(birthday, float) and birthday > 0:
                date_of_birth = xlrd.xldate.xldate_as_datetime(
                    birthday, book.datemode
                ).date()
            yield NationalPlayerRow(
                national_id=str(fide_id),
                last_name=last_name,
                first_name=first_name.strip(),
                year_of_birth=date_of_birth.year if date_of_birth else None,
                date_of_birth=date_of_birth,
                gender=(
                    PlayerGender.WOMAN
                    if 'w' in str(row['Sex']).lower()
                    else PlayerGender.MAN
                ),
                title=title,
                federation=self.federation,
                club=str(row['Fed']).strip() or None,
                fide_id=fide_id,
                standard_rating=self._cell_int(row['Rtg_Nat']),
                fide_standard_rating=self._cell_int(row['Rtg_Int']),
            )
