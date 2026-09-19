from collections.abc import Iterator
from pathlib import Path
from typing import Any, override

import xlrd
from packaging.version import Version

from database.sqlite.national.national_database import (
    NationalPlayerDatabase,
    NationalPlayerRow,
)
from utils.enum import PlayerGender


class McfDatabase(NationalPlayerDatabase):
    """The rating list of the Malaysian Chess Federation (MCF), the
    Swiss-Manager spreadsheet its rating portal serves.

    Columns: ID_No, Name, Sex, FED, Clubnumber (the state), Clubname,
    birthday (year), rtg_nat, fide_no, rating_int, Title, K. The names
    are Malay names, kept whole."""

    federation = 'MAS'
    acronym = 'MCF'

    _URL = 'https://rating.malaysiachess.my/api/mcfratinglist.ashx'

    @staticmethod
    def static_id() -> str:
        return 'mcf'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'mcf_rating_list.xls'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        return self._download_file(self._URL, source_file_dir / self._source_file_name)

    @staticmethod
    def _cell_int(value: Any) -> int | None:
        try:
            return int(float(value)) or None
        except (TypeError, ValueError):
            return None

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        sheet = xlrd.open_workbook(str(source_file_path)).sheet_by_index(0)
        headers = [str(sheet.cell_value(0, column)) for column in range(sheet.ncols)]
        for index in range(1, sheet.nrows):
            row: dict[str, Any] = dict(
                zip(
                    headers,
                    (sheet.cell_value(index, column) for column in range(sheet.ncols)),
                    strict=True,
                )
            )
            national_id = str(row['ID_No']).strip()
            if not national_id:
                continue
            yield NationalPlayerRow(
                national_id=national_id,
                last_name=str(row['Name']).strip(),
                year_of_birth=self._cell_int(row['birthday']),
                gender=(
                    PlayerGender.WOMAN
                    if str(row['Sex']).strip().upper() == 'F'
                    else PlayerGender.MAN
                    if str(row['Sex']).strip().upper() == 'M'
                    else PlayerGender.NONE
                ),
                title=str(row['Title']).strip().upper(),
                federation=str(row['FED']).strip() or self.federation,
                club=str(row['Clubname']).strip()
                or str(row['Clubnumber']).strip()
                or None,
                fide_id=self._cell_int(row['fide_no']),
                standard_rating=self._cell_int(row['rtg_nat']),
                fide_standard_rating=self._cell_int(row['rating_int']),
            )
