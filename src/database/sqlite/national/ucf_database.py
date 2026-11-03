import re
import zipfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any, ClassVar, Literal, override

import xlrd
from packaging.version import Version

from common.logger import get_logger
from database.sqlite.national.national_database import (
    NationalPlayerDatabase,
    NationalPlayerRow,
)
from utils.enum import Cadence
from utils.enum import PlayerGender

logger = get_logger()


class UcfDatabase(NationalPlayerDatabase):
    """The national rating list of the Ukrainian Chess Federation, the
    spreadsheet of its qualification commission, published monthly under a
    dated path found from the federation's home page. The list comes in one
    of two formats, read from its first sheet.

    The Swiss-Manager format has the columns Fide_No, Name, Fed, Sex,
    Rtg_Nat, Rtg_Int and Birthday, with the name written Last name First
    name in Cyrillic, followed by the titles of the player in lower case
    (мг/змс: grandmaster, honoured master of sport…), the region as Fed,
    Sex carrying a w for the women (and an н for the inactive players) and
    the birthday as a spreadsheet date.

    The general list of the players has a title and a legend, then the
    header row starting with Номер, a row giving the source of each column
    (UCF or FIDE), a row numbering the columns, and the players. The
    columns come in pairs, UCF then FIDE: the id, the name (Last First in
    Cyrillic, then Last, First in Latin), the region, the title (мг/змс,
    then the FIDE title), the number of games, the rating, the date of
    birth as a spreadsheet date, the year of birth and the gender (м or ж,
    then M or F).

    In both, the id is the FIDE id of the players known to FIDE, and a
    national id of 4 or 5 digits otherwise."""

    _TITLES: ClassVar[dict[str, str]] = {'мг': 'GM', 'мм': 'IM', 'мф': 'FM'}
    _SWISS_MANAGER_COLUMNS = frozenset(
        {'Fide_No', 'Name', 'Fed', 'Sex', 'Rtg_Nat', 'Rtg_Int', 'Birthday'}
    )
    _COLUMNS = 15
    _MIN_FIDE_ID = 100000
    # The start of the header and of the source of each column read.
    _LAYOUT: ClassVar[dict[int, tuple[str, str]]] = {
        0: ('Номер', ''),
        1: ("Ім'я", 'українське'),
        2: ('', 'ФІДЕ'),
        3: ('Федерація', ''),
        4: ('Звання', 'українське'),
        5: ('', 'ФІДЕ'),
        7: ('Рейтинг', 'ФШУ'),
        8: ('', 'ФІДЕ'),
        9: ('дата народження', 'ФШУ'),
        10: ('', 'ФІДЕ'),
        11: ('Рік народження', 'ФШУ'),
        12: ('', 'ФІДЕ'),
        13: ('Стать', 'ФШУ'),
        14: ('', 'ФІДЕ'),
    }

    federation = 'UKR'
    acronym = 'UCF'
    fide_cadences = frozenset({Cadence.STANDARD})
    national_cadences = frozenset({Cadence.STANDARD})

    _HOME_URL = 'https://www.ukrchess.org.ua/'
    _PAGE_PATTERN = re.compile(r'kvalif/(\d{4})/(\d{2})/rating\.html')

    @staticmethod
    def static_id() -> str:
        return 'ucf'

    @staticmethod
    def version() -> Version:
        return Version('2')

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

    @staticmethod
    def _split_name(name: str) -> tuple[str, str]:
        """The last name and the first name of a name of the list, without
        the junior and senior marks (мл., ст., (мол)…) that may follow it."""
        names = [
            token
            for token in name.split()
            if not token.startswith('(') and token != token.lower()
        ]
        last_name, *first_names = names or ['']
        return last_name, ' '.join(first_names)

    @classmethod
    def _title(cls, fide_title: str, national_title: str) -> str:
        """The FIDE title of the player, else the one matching the highest
        national title, written first before a slash."""
        return fide_title or cls._TITLES.get(national_title.split('/')[0], '')

    @staticmethod
    def _cell_int(value: Any) -> int | None:
        try:
            return int(float(value)) or None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _has_layout(cls, sheet: xlrd.sheet.Sheet, header_index: int) -> bool:
        """Whether the header and source rows name the columns read, and
        the row numbering the columns follows them."""
        if sheet.ncols < cls._COLUMNS or sheet.nrows < header_index + 3:
            return False
        header, source, numbers = (
            [str(value).strip() for value in sheet.row_values(index, 0, cls._COLUMNS)]
            for index in range(header_index, header_index + 3)
        )
        return all(
            header[column].startswith(expected_header)
            and source[column].startswith(expected_source)
            for column, (expected_header, expected_source) in cls._LAYOUT.items()
        ) and all(
            cls._cell_int(number) == column + 1
            for column, number in enumerate(numbers[: cls._COLUMNS - 1])
        )

    @staticmethod
    def _date(value: Any, datemode: Literal[0, 1]) -> date | None:
        if isinstance(value, float) and value > 0:
            return xlrd.xldate.xldate_as_datetime(value, datemode).date()
        return None

    def _player(
        self,
        player_id: int,
        name: str,
        club: str,
        title: str,
        date_of_birth: date | None,
        year_of_birth: int | None,
        woman: bool,
        rating: Any,
        fide_rating: Any,
    ) -> NationalPlayerRow:
        last_name, first_name = self._split_name(name)
        return NationalPlayerRow(
            national_id=str(player_id),
            last_name=last_name,
            first_name=first_name,
            year_of_birth=year_of_birth,
            date_of_birth=date_of_birth,
            gender=PlayerGender.WOMAN if woman else PlayerGender.MAN,
            title=title,
            federation=self.federation,
            club=club.strip() or None,
            fide_id=player_id if player_id >= self._MIN_FIDE_ID else None,
            standard_rating=self._cell_int(rating),
            fide_standard_rating=self._cell_int(fide_rating),
        )

    @classmethod
    def _swiss_manager_columns(cls, sheet: xlrd.sheet.Sheet) -> dict[str, int] | None:
        """The index of each column of a list in the Swiss-Manager format,
        named by its first row, None if the list is not in that format."""
        headers = [str(value).strip() for value in sheet.row_values(0)]
        if not set(headers) >= cls._SWISS_MANAGER_COLUMNS:
            return None
        return {header: headers.index(header) for header in cls._SWISS_MANAGER_COLUMNS}

    @classmethod
    def _general_list_header_index(cls, sheet: xlrd.sheet.Sheet) -> int | None:
        """The index of the header row of the general list of the players,
        None if the list is not laid out as expected."""
        header_index = next(
            (
                index
                for index in range(sheet.nrows)
                if str(sheet.cell_value(index, 0)).strip() == 'Номер'
            ),
            None,
        )
        if header_index is None or not cls._has_layout(sheet, header_index):
            return None
        return header_index

    def _read_swiss_manager_list(
        self, sheet: xlrd.sheet.Sheet, columns: dict[str, int], datemode: Literal[0, 1]
    ) -> Iterator[NationalPlayerRow]:
        for index in range(1, sheet.nrows):
            row = sheet.row_values(index)
            player_id = self._cell_int(row[columns['Fide_No']])
            if player_id is None:
                continue
            name = str(row[columns['Name']])
            date_of_birth = self._date(row[columns['Birthday']], datemode)
            yield self._player(
                player_id,
                name=name,
                club=str(row[columns['Fed']]),
                title=next(
                    (
                        self._TITLES[national_title]
                        for token in name.split()
                        if (national_title := token.split('/')[0]) in self._TITLES
                    ),
                    '',
                ),
                date_of_birth=date_of_birth,
                year_of_birth=date_of_birth.year if date_of_birth else None,
                woman='w' in str(row[columns['Sex']]).lower(),
                rating=row[columns['Rtg_Nat']],
                fide_rating=row[columns['Rtg_Int']],
            )

    def _read_general_list(
        self, sheet: xlrd.sheet.Sheet, header_index: int, datemode: Literal[0, 1]
    ) -> Iterator[NationalPlayerRow]:
        for index in range(header_index + 3, sheet.nrows):
            row = sheet.row_values(index, 0, self._COLUMNS)
            player_id = self._cell_int(row[0])
            if player_id is None:
                continue
            date_of_birth = self._date(row[9], datemode) or self._date(
                row[10], datemode
            )
            yield self._player(
                player_id,
                name=str(row[1]),
                club=str(row[3]),
                title=self._title(str(row[5]).strip(), str(row[4]).strip()),
                date_of_birth=date_of_birth,
                year_of_birth=(
                    self._cell_int(row[11])
                    or self._cell_int(row[12])
                    or (date_of_birth.year if date_of_birth else None)
                ),
                woman=str(row[13]).strip() == 'ж',
                rating=row[7],
                fide_rating=row[8],
            )

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        with zipfile.ZipFile(source_file_path) as archive:
            names = [name for name in archive.namelist() if name.endswith('.xls')]
            if not names:
                return
            book = xlrd.open_workbook(file_contents=archive.read(names[0]))
        sheet = book.sheet_by_index(0)
        players: Iterator[NationalPlayerRow]
        if not sheet.nrows:
            logger.error(self.log_prefix + 'Empty list.')
            return
        if (columns := self._swiss_manager_columns(sheet)) is not None:
            players = self._read_swiss_manager_list(sheet, columns, book.datemode)
        elif (header_index := self._general_list_header_index(sheet)) is not None:
            players = self._read_general_list(sheet, header_index, book.datemode)
        else:
            logger.error(self.log_prefix + 'Unexpected layout of the list.')
            return
        seen_ids: set[str] = set()
        for player in players:
            if player.national_id not in seen_ids:
                seen_ids.add(player.national_id)
                yield player
