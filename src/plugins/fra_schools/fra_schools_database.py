import json
import re
import urllib
from contextlib import suppress
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import Any, Callable, override

import requests

from database.sqlite.sqlite_database import SQLiteDatabase
from packaging.version import Version

from common.logger import get_logger
from database.sqlite.local_source_database import LocalSourceDatabase
from database.sqlite.local_source_database.actions import AutoUpdateOutdatedAction
from database.sqlite.local_source_database.delays import MonthFirstDayOutdatedDelay
from database.sqlite.config.config_store import StoredLocalSourceDatabase

from plugins import fra_schools
from plugins.fra_schools import _, PLUGIN_DIR
from utils import Utils

logger: Logger = get_logger()


@dataclass
class StoredSchool:
    code: str
    name: str
    department: str
    city: str
    type: str
    private: int


class FRASchoolsDatabase(LocalSourceDatabase):
    DEPARTMENTS: dict[str, str] | None = None

    def __init__(self, write: bool = False):
        super().__init__(write)
        if self.exists() and not self.DEPARTMENTS:
            with self as database:
                database.execute('SELECT * FROM `department`')
                self.__class__.DEPARTMENTS = {
                    row['id']: row['name'] for row in database.fetchall()
                }

    @staticmethod
    def static_id() -> str:
        return 'fra_schools'

    @staticmethod
    def static_name() -> str:
        return _('French Schools')

    @staticmethod
    def _dir() -> Path:
        return fra_schools.TMP_DIR

    @property
    def min_recovery_version(self) -> Version:
        return Version('3.3.0')

    @property
    def _schema_file_path(self) -> Path:
        return PLUGIN_DIR / 'create.sql'

    @property
    def _source_file_path(self) -> Path:
        return fra_schools.TMP_DIR / 'fra_schools.json'

    @override
    @property
    def default_stored_database(self) -> StoredLocalSourceDatabase:
        return StoredLocalSourceDatabase(
            name=self.id,
            outdate_delay=MonthFirstDayOutdatedDelay.static_id(),
            outdate_action=AutoUpdateOutdatedAction.static_id(),
        )

    @property
    def age_in_months(self) -> int:
        """The number of months since the database has been updated."""
        if not self.updated_at:
            return 0
        return Utils.age_in_months(self.updated_at)

    def _download_source_file(self) -> bool:
        types: list[str] = ['Ecole', 'Collège']
        # See https://data.education.gouv.fr/api/v2/console
        base_url: str = 'https://data.education.gouv.fr/api/v2/catalog/datasets/fr-en-annuaire-education/exports/json'
        url: str = (
            base_url
            + '?'
            + urllib.parse.urlencode(
                {
                    'select': ','.join(
                        [
                            'code_departement',
                            'libelle_departement',
                            'nom_commune',
                            'type_etablissement',
                            'statut_public_prive',
                            'identifiant_de_l_etablissement',
                            'nom_etablissement',
                        ]
                    ),
                    'where': 'type_etablissement IN ("' + '" ,"'.join(types) + '")',
                    'order_by': ','.join(
                        [
                            'code_departement',
                            'nom_commune',
                            'type_etablissement',
                            'statut_public_prive',
                            'identifiant_de_l_etablissement',
                        ]
                    ),
                    'limit': -1,
                    'offset': 0,
                    'timezone': 'UTC',
                }
            )
        )

        json_file: Path = self._source_file_path
        with suppress(FileNotFoundError):
            json_file.unlink()

        response: requests.Response = requests.get(url)
        json_file.write_bytes(response.content)
        if not json_file.exists():
            logger.error(self.log_prefix + 'No data received from [%s].', url)
            return False
        return True

    @classmethod
    def normalize_name(cls, name: str) -> str:
        name = cls.protect_string(name)
        name = name.lower().title()
        name = re.sub(
            r'\b(D\'|De|Du|Des|L\'|La|Le|Les|Au|Aux|Et|En|Sur)\b',
            lambda m: m.group(1).lower(),
            name,
        )
        name = re.sub(r'[\s\t\n]+', ' ', name)
        # All the SEGPA are written in full letters, breaking the layout.
        # This replaces them by the acronym, taking all the misspellings into account
        name = re.sub(
            r'\bSection\s(d[\'])?Enseigne(me)?ment(\sProfessionnel)?\s'
            r'Générale?(\set)?(\sProfess?ionn?el(le)?)?(\sAdaptée?)?\b',
            'SEGPA',
            name,
            flags=re.IGNORECASE,
        )
        return name

    @staticmethod
    def protect_string(string: str) -> str:
        return string.replace('`', "'")

    def _populate_from_source_file(self, database: SQLiteDatabase) -> bool:
        fields: dict[str, tuple[str, Callable[[Any], Any] | None]] = {
            'identifiant_de_l_etablissement': ('code', None),
            'nom_etablissement': ('name', self.normalize_name),
            'code_departement': (
                'department',
                lambda s: s[1:] if s.startswith('0') else s,
            ),
            'libelle_departement': ('department_name', None),
            'nom_commune': ('city', self.protect_string),
            'type_etablissement': ('type', None),
            'statut_public_prive': ('private', lambda s: s == 'Privé'),
        }

        # Prepare insert queries
        school_columns = [
            'code',
            'name',
            'department',
            'city',
            'type',
            'private',
        ]
        school_query = (
            f'INSERT INTO school({", ".join(school_columns)}) '
            f'VALUES({", ".join([f":{c}" for c in school_columns])})'
        )

        department_query = (
            'INSERT OR IGNORE INTO department(id, name) VALUES(:id, :name)'
        )

        school_count = 0
        to_write_schools: list[dict[str, Any]] = []
        to_write_departments: list[dict[str, Any]] = []

        data: list[dict[str, Any]] = []
        with open(self._source_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        with database:
            for school in data:
                row = {}
                for src_field, (db_field, transform) in fields.items():
                    value = school.get(src_field)
                    if transform is not None:
                        value = transform(value)
                    row[db_field] = value

                to_write_departments.append(
                    {
                        'id': row['department'],
                        'name': row['department_name'],
                    }
                )

                to_write_schools.append(
                    {
                        'code': row['code'],
                        'name': row['name'],
                        'department': row['department'],
                        'city': row['city'],
                        'type': row['type'],
                        'private': row['private'],
                    }
                )

                school_count += 1
                if school_count % 1000 == 0:
                    database.executemany(department_query, to_write_departments)
                    database.executemany(school_query, to_write_schools)
                    to_write_departments.clear()
                    to_write_schools.clear()
                    if self.stop_event.is_set():
                        return False
                if school_count % 100_000 == 0:
                    database.commit()

            if to_write_departments:
                database.executemany(department_query, to_write_departments)
            if to_write_schools:
                database.executemany(school_query, to_write_schools)
            database.commit()

        logger.info(
            self.log_prefix + '%d schools written to the database.', school_count
        )
        return True

    def _create_indexes(self):
        self.write = True
        with self:
            self.execute(
                """
                INSERT INTO school_fts(rowid, search_text)
                SELECT s.id,
                    lower(
                        s.code || ' ' ||
                        s.name || ' ' ||
                        s.city || ' ' ||
                        s.type || ' ' ||
                        s.department || ' ' ||
                        d.name
                    )
                FROM school s
                LEFT JOIN department d ON s.department = d.id;
            """
            )
            self.commit()
