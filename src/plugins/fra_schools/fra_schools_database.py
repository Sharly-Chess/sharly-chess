import re
from logging import Logger
from pathlib import Path
from typing import Any, override

from packaging.version import Version

from common.i18n import _
from common.logger import get_logger
from database.sqlite.config.config_store import StoredLocalSourceDatabase
from database.sqlite.local_source_database.actions import AutoUpdateOutdatedAction
from database.sqlite.local_source_database.databases import GitHubLocalSourceDatabase
from database.sqlite.local_source_database.delays import MonthFirstDayOutdatedDelay
from plugins import fra_schools
from plugins.fra_schools import PLUGIN_NAME
from plugins.fra_schools.utils import FRASchool
from utils import Utils

logger: Logger = get_logger()


class FRASchoolsDatabase(GitHubLocalSourceDatabase):
    @staticmethod
    def static_id() -> str:
        return 'fra_schools'

    @staticmethod
    def static_name() -> str:
        return _('French Schools')

    @staticmethod
    def version() -> Version:
        return Version('1')

    @property
    def _source_file_name(self) -> str:
        return 'fra_schools_v1.db'

    @classmethod
    def credentials_file(cls) -> Path:
        return fra_schools.PLUGIN_DIR / '.database-enc-credentials'

    @classmethod
    def github_tag(cls) -> str:
        return 'fra-schools-latest'

    def _download_source_file(self, source_file_dir: Path) -> bool:
        return self._download_enc_source_file(source_file_dir)

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

    def search_school(
        self, search: str, page: int = 0, limit: int = 25
    ) -> list[FRASchool]:
        words = re.findall(r'\w+', search.strip().lower())
        fts_query = ' '.join(f'{w}*' for w in words)
        query: str = """
            SELECT
                s.code,
                s.name,
                s.department,
                s.postal_code,
                s.city
            FROM school s
            JOIN school_fts ON school_fts.rowid = s.id
            WHERE school_fts MATCH ?
            LIMIT ?
        """
        params: list[Any] = [
            fts_query,
            limit,
        ]
        if page:
            query += ' OFFSET ?'
            params += [
                page * limit,
            ]
        self.execute(query, tuple(params))
        rows = self.fetchall()
        return [FRASchool.from_source_row(row) for row in rows]

    def get_school_by_code(self, school_code: str) -> FRASchool | None:
        self.execute('SELECT * FROM `school` WHERE `code` = ?', (school_code,))
        if row := self.fetchone():
            return FRASchool.from_source_row(row)
        return None

    # ---------------------------------------------------------------------------------
    # Legacy
    # ---------------------------------------------------------------------------------

    @staticmethod
    def _legacy_dir() -> Path:
        return Path('tmp') / PLUGIN_NAME

    @property
    def legacy_min_recovery_version(self) -> Version:
        return Version('3.3.0')
