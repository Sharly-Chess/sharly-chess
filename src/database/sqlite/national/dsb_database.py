import csv
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar, override

from packaging.version import Version

from database.sqlite.config.config_store import StoredLocalSourceDatabase
from database.sqlite.local_source_database.actions import NotifOutdatedAction
from database.sqlite.local_source_database.delays import WeeklyOutdatedDelay
from database.sqlite.national.national_database import (
    NationalPlayerDatabase,
    NationalPlayerRow,
)
from utils.enum import PlayerGender


class DsbDatabase(NationalPlayerDatabase):
    """The DWZ list of the German Chess Federation (DSB): the daily export
    of the Wertungsportal, players and clubs in separate files.

    spieler.csv: ID,ZPS,Mitgliedsnummer,Status,"Name,Vorname",Geschlecht,
    Spielberechtigung,Geburtsjahr,"Letzte Auswertung",DWZ,Index,FIDE-Elozahl,
    FIDE-Titel,FIDE-ID,FIDE-Land,Vorname,Nachname,FIDE-Frauentitel,
    FIDE-Elozahl-Schnellschach,FIDE-Elozahl-Blitz. A player belonging to
    several clubs has one row per club: the active membership (Status A)
    wins over a passive one (P), which wins over none.
    vereine.csv: ZPS-Nummer,Landesverband,UebergeordneterVerband,Vereinsname."""

    federation = 'GER'
    acronym = 'DSB'

    _URL = (
        'https://www.schachbund.de/download-dwz-daten.html'
        '?file=files/wertungsportal/downloads/export/csv/LV-0-csv.zip'
    )
    _STATUS_PRECEDENCE: ClassVar[dict[str, int]] = {'A': 2, 'P': 1, '': 0}

    @staticmethod
    def static_id() -> str:
        return 'dsb'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'spieler.csv'

    @override
    @property
    def default_stored_database(self) -> StoredLocalSourceDatabase:
        return StoredLocalSourceDatabase(
            name=self.id,
            outdate_delay=WeeklyOutdatedDelay.static_id(),
            outdate_action=NotifOutdatedAction.static_id(),
        )

    def _download_source_file(self, source_file_dir: Path) -> bool:
        return self._download_and_unzip(self._URL, source_file_dir)

    @staticmethod
    def _read_clubs(file: Path) -> dict[str, str]:
        with open(file, encoding='cp1252', newline='') as f:
            return {
                row['ZPS-Nummer'].strip(): row['Vereinsname'].strip()
                for row in csv.DictReader(f)
            }

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        clubs = self._read_clubs(source_file_path.with_name('vereine.csv'))
        rows: dict[str, tuple[int, NationalPlayerRow]] = {}
        with open(source_file_path, encoding='cp1252', newline='') as f:
            for row in csv.DictReader(f):
                national_id = row['ID'].strip()
                if not national_id:
                    continue
                precedence = self._STATUS_PRECEDENCE.get(row['Status'].strip(), 0)
                if national_id in rows and rows[national_id][0] >= precedence:
                    continue
                rows[national_id] = (
                    precedence,
                    NationalPlayerRow(
                        national_id=national_id,
                        last_name=row['Nachname'].strip(),
                        first_name=row['Vorname'].strip(),
                        year_of_birth=self._int_or_none(row['Geburtsjahr']),
                        gender=(
                            PlayerGender.WOMAN
                            if row['Geschlecht'].strip() == 'W'
                            else PlayerGender.MAN
                            if row['Geschlecht'].strip() == 'M'
                            else PlayerGender.NONE
                        ),
                        title=row['FIDE-Titel'].strip()
                        or row['FIDE-Frauentitel'].strip(),
                        federation=row['FIDE-Land'].strip() or self.federation,
                        club=clubs.get(row['ZPS'].strip()),
                        fide_id=self._int_or_none(row['FIDE-ID']),
                        standard_rating=self._int_or_none(row['DWZ']),
                        fide_standard_rating=self._int_or_none(row['FIDE-Elozahl']),
                        fide_rapid_rating=self._int_or_none(
                            row['FIDE-Elozahl-Schnellschach']
                        ),
                        fide_blitz_rating=self._int_or_none(row['FIDE-Elozahl-Blitz']),
                    ),
                )
        for _precedence, player_row in rows.values():
            yield player_row
