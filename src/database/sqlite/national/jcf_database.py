import json
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


class JcfDatabase(NationalPlayerDatabase):
    """The rating list of the Japan Chess Federation, the spreadsheet of
    the monthly post of its site, found through the site's WordPress API.

    Columns: ID, Name, Kanji, ST-K, ST, ST-G, RP-K, RP, RP-G (the standard
    and rapid ratings with their K factors and game counts), the name
    written Last name First name. The list carries no birth year, gender
    or club."""

    federation = 'JPN'
    acronym = 'JCF'

    _MEDIA_URL = (
        'https://japanchess.org/wp-json/wp/v2/media'
        '?search=xlsx&per_page=100&_fields=source_url'
    )
    _FILE_PATTERN = re.compile(r'/(\d{4})-(\d{2})-(\d{2})\.xlsx$')

    @staticmethod
    def static_id() -> str:
        return 'jcf'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'rating_list.xlsx'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        page = self._fetch_page(self._MEDIA_URL)
        if page is None:
            return False
        try:
            urls = [str(media['source_url']) for media in json.loads(page)]
        except (ValueError, KeyError, TypeError):
            return False
        dated = [
            (match.groups(), url)
            for url in urls
            if (match := self._FILE_PATTERN.search(url))
        ]
        if not dated:
            return False
        return self._download_file(
            max(dated)[1], source_file_dir / self._source_file_name
        )

    @staticmethod
    def _cell_int(value: Any) -> int | None:
        try:
            return int(float(value)) or None
        except (TypeError, ValueError):
            return None

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        workbook = openpyxl.load_workbook(source_file_path, read_only=True)
        for sheet in workbook.worksheets:
            headers: list[str] | None = None
            for values in sheet.iter_rows(values_only=True):
                if headers is None:
                    if values and values[0] == 'ID' and 'ST' in values:
                        headers = [str(value) for value in values]
                    continue
                row = dict(zip(headers, values, strict=False))
                national_id = str(row.get('ID') or '').strip()
                if not national_id:
                    continue
                last_name, _sep, first_name = (
                    str(row.get('Name') or '').strip().partition(' ')
                )
                yield NationalPlayerRow(
                    national_id=national_id,
                    last_name=last_name,
                    first_name=first_name.strip(),
                    federation=self.federation,
                    standard_rating=self._cell_int(row.get('ST')),
                    rapid_rating=self._cell_int(row.get('RP')),
                )
            if headers is not None:
                return
