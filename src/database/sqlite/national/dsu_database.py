import csv
from collections.abc import Iterator
from pathlib import Path
from typing import override

from packaging.version import Version

from database.sqlite.national.national_database import (
    NationalPlayerDatabase,
    NationalPlayerRow,
)


class DsuDatabase(NationalPlayerDatabase):
    """The rating list of the Danish Chess Federation (DSU), the CSV report
    of the active members of its tournament site.

    Columns: Nr;Født;Alder;Navn;Klub;Titel;Rat.;Hur.;Lyn;Fide;Nr;K — the
    DSU number, the year of birth, the age, the name written First name
    Last name, the club, the title, the national standard, rapid and blitz
    ratings (0 for none), the FIDE rating (- for none), id and K factor.
    The list carries no gender."""

    federation = 'DEN'
    acronym = 'DSU'

    _URL = (
        'https://turnering.skak.dk/ClubAndMembers/AllMemberReport'
        '?memType=ActiveMembersAjax&format=csv'
    )

    @staticmethod
    def static_id() -> str:
        return 'dsu'

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'members.csv'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        return self._download_file(self._URL, source_file_dir / self._source_file_name)

    @override
    def _read_players(self, source_file_path: Path) -> Iterator[NationalPlayerRow]:
        with open(source_file_path, encoding='cp1252', newline='') as f:
            reader = csv.reader(f, delimiter=';')
            for values in reader:
                if len(values) < 12 or not values[0].strip().isdigit():
                    continue
                (
                    national_id,
                    year_of_birth,
                    _age,
                    name,
                    club,
                    title,
                    standard,
                    rapid,
                    blitz,
                    fide_rating,
                    fide_id,
                    _k_factor,
                ) = (value.strip() for value in values[:12])
                *first_names, last_name = name.split() or ['']
                yield NationalPlayerRow(
                    national_id=national_id,
                    last_name=last_name,
                    first_name=' '.join(first_names),
                    year_of_birth=self._int_or_none(year_of_birth),
                    title=title.upper(),
                    federation=self.federation,
                    club=club or None,
                    fide_id=self._int_or_none(fide_id),
                    standard_rating=self._int_or_none(standard),
                    rapid_rating=self._int_or_none(rapid),
                    blitz_rating=self._int_or_none(blitz),
                    fide_standard_rating=self._int_or_none(fide_rating),
                )
