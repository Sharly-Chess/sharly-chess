from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any, override

import xlrd
from packaging.version import Version

from database.sqlite.national.national_database import (
    NationalPlayerDatabase,
    NationalPlayerRow,
)
from utils.enum import PlayerGender


class LokDatabase(NationalPlayerDatabase):
    """The LOK (list of personal coefficients) of the Czech Chess Federation
    (ŠSČR), the Swiss-Manager exports of elo.miramal.com: one spreadsheet
    per rate of play, the classical one carrying the players.

    Columns: ID_no, Name, ClubName, BirthDay, Sex, Rtg_nat, Rtg_int, Title,
    FIDE_no, Fed, ClubNo, Status, PARTIE, BODY, SUMA_ELO, with the name
    written Last name First name, the birthday dd.mm.yyyy (00.00.yyyy for a
    year alone) and Sex set to f for the women."""

    federation = 'CZE'
    acronym = 'LOK'

    _DOWNLOADS_URL = 'https://elo.miramal.com/download/'

    @staticmethod
    def static_id() -> str:
        return 'lok'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'lok_sm_cz.xls'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        return all(
            self._download_file(self._DOWNLOADS_URL + name, source_file_dir / name)
            for name in (self._source_file_name, 'rapid_lok_sm_cz.xls')
        )

    @staticmethod
    def _read_rows(file: Path) -> Iterator[dict[str, Any]]:
        sheet = xlrd.open_workbook(str(file)).sheet_by_index(0)
        headers = [str(sheet.cell_value(0, column)) for column in range(sheet.ncols)]
        for row in range(1, sheet.nrows):
            yield dict(
                zip(
                    headers,
                    (sheet.cell_value(row, column) for column in range(sheet.ncols)),
                    strict=True,
                )
            )

    @staticmethod
    def _cell_int(value: Any) -> int | None:
        try:
            return int(float(value)) or None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _birth(value: Any) -> tuple[int | None, date | None]:
        day, _sep, rest = str(value).strip().partition('.')
        month, _sep, year = rest.partition('.')
        if not year.isdigit() or int(year) == 0:
            return None, None
        if day.isdigit() and month.isdigit() and int(day) and int(month):
            try:
                return int(year), date(int(year), int(month), int(day))
            except ValueError:
                pass
        return int(year), None

    @classmethod
    def _read_ratings(cls, file: Path) -> dict[str, int | None]:
        return {
            str(cls._cell_int(row['ID_no']) or ''): cls._cell_int(row['Rtg_nat'])
            for row in cls._read_rows(file)
        }

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        rapid_ratings = self._read_ratings(
            source_file_path.with_name('rapid_lok_sm_cz.xls')
        )
        for row in self._read_rows(source_file_path):
            national_id = self._cell_int(row['ID_no'])
            if national_id is None:
                continue
            last_name, _sep, first_name = str(row['Name']).strip().partition(' ')
            year_of_birth, date_of_birth = self._birth(row['BirthDay'])
            yield NationalPlayerRow(
                national_id=str(national_id),
                last_name=last_name,
                first_name=first_name.strip(),
                year_of_birth=year_of_birth,
                date_of_birth=date_of_birth,
                gender=(
                    PlayerGender.WOMAN
                    if str(row['Sex']).strip().lower() == 'f'
                    else PlayerGender.MAN
                ),
                title=str(row['Title']).strip().upper(),
                federation=str(row['Fed']).strip() or self.federation,
                club=str(row['ClubName']).strip() or None,
                fide_id=self._cell_int(row['FIDE_no']),
                standard_rating=self._cell_int(row['Rtg_nat']),
                rapid_rating=rapid_ratings.get(str(national_id)),
                fide_standard_rating=self._cell_int(row['Rtg_int']),
            )
