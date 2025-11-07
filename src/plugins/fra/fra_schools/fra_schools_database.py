import json
import re
import urllib
from contextlib import suppress
from logging import Logger
from pathlib import Path
from typing import Any, Callable, override

import requests

from database.sqlite.sqlite_database import SQLiteDatabase
from packaging.version import Version

from common.i18n import _
from common.logger import get_logger
from database.sqlite.local_source_database import LocalSourceDatabase
from database.sqlite.local_source_database.actions import NotifOutdatedAction
from database.sqlite.local_source_database.delays import DisabledOutdatedDelay
from database.sqlite.config.config_store import StoredLocalSourceDatabase

from plugins.fra import fra_schools
from plugins.fra.fra_schools import PLUGIN_DIR

logger: Logger = get_logger()


class FRASchoolsDatabase(LocalSourceDatabase):
    @staticmethod
    def static_id() -> str:
        return 'fra_schools'

    @staticmethod
    def static_name() -> str:
        return _('FRA Schools')

    @staticmethod
    def _dir() -> Path:
        return fra_schools.TMP_DIR

    @property
    def min_recovery_version(self) -> Version:
        # Last change done in https://github.com/Sharly-Chess/sharly-chess/pull/713
        return Version('2.7.8')

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
            outdate_delay=DisabledOutdatedDelay.static_id(),
            outdate_action=NotifOutdatedAction.static_id(),
        )

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

    def _use_external_generator(self):
        return False

    @staticmethod
    def normalize_name(name: str) -> str:
        name = name.lower().title()
        name = re.sub(
            r'\b(De|Du|Des|La|Le|Les|Au|Aux|Et|En|Sur)\b',
            lambda m: m.group(1).lower(),
            name,
        )
        return name

    def _populate_from_source_file(self, database: SQLiteDatabase) -> bool:
        fields: dict[str, tuple[str, Callable[[Any], Any] | None]] = {
            'identifiant_de_l_etablissement': ('school_id', None),
            'nom_etablissement': ('school_name', self.normalize_name),
            'code_departement': ('department', lambda s: s.lstrip('0')),
            'libelle_departement': ('department_name', None),
            'nom_commune': ('commune', None),
            'type_etablissement': ('type', None),
            'statut_public_prive': ('private', lambda s: s == 'Privé'),
        }

        # Prepare insert queries
        school_columns = [
            'school_id',
            'school_name',
            'department',
            'commune',
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
                        'school_id': row['school_id'],
                        'school_name': row['school_name'],
                        'department': row['department'],
                        'commune': row['commune'],
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
                        s.school_id || ' ' ||
                        s.school_name || ' ' ||
                        s.commune || ' ' ||
                        s.type || ' ' ||
                        s.department || ' ' ||
                        d.name
                    )
                FROM school s
                LEFT JOIN department d ON s.department = d.id;
            """
            )
            self.commit()
