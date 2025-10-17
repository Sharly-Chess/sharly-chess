from functools import partial
import re
from typing import Annotated, Any
from data.input_output.managers import DataSourceManager
from litestar import get, post
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body

from common import format_timestamp_date_time
from common.i18n import _
from common.network import NetworkMonitor
from data.access_levels.actions import AuthAction
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_background_uploader import FfeBackgroundUploader
from plugins.ffe.ffe_session import FFESession
from plugins.ffe.ffe_session_handler import FFESessionHandler
from plugins.ffe.utils import FFEUtils, PlayerFFELicence
from plugins.fra.fra_schools.fra_schools_database import FRASchoolsDatabase
from plugins.fra.fra_schools.utils import StoredSchool
from plugins.utils import PluginUtils
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.admin.player_admin_controller import PlayerAdminController
from web.controllers.admin.tournament_admin_controller import TournamentAdminWebContext
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard, TournamentActionGuard

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FRASchoolsController(BaseEventAdminController):
    guards = []

    @staticmethod
    def _get_school_from_row(row: dict[str, Any]) -> StoredSchool:
        return StoredSchool(
            school_id=row['school_id'],
            school_name=row['school_name'],
            department=row['department'],
            department_name=row['name'],
            commune=row['commune'],
            type=row['type'],
            private=bool(row['private']),
        )

    @get(
        path=[
            'fra-schools/search-player/{event_uniq_id:str}',
            'fra-schools/search-player/{event_uniq_id:str}/{page:int}',
        ],
        name='fra-schools-search',
    )
    async def htmx_fra_schools_search(
        self,
        request: HTMXRequest,
        fra_schools_search: str,
        page: int = 0,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        database = FRASchoolsDatabase()
        schools: list[StoredSchool] = []
        limit: int = 25

        words = re.findall(r"\w+", fra_schools_search.strip().lower())
        fts_query = " ".join(f"{w}*" for w in words)
        if fra_schools_search and database.file_path().exists():
            with database:
                query: str = f"""
                    SELECT s.school_id, s.school_name, s.department, s.commune, d.name, s.type, s.private
                    FROM school s
                    JOIN department d ON s.department = d.id
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

                database.execute(query, tuple(params))
                rows = database.fetchall()
                schools = [self._get_school_from_row(row) for row in rows]

        return HTMXTemplate(
            template_name='/fra_schools_search_results.html',
            context=web_context.template_context | {
                'search': fra_schools_search,
                'search_results': schools,
                'has_more_results': len(schools) == limit,
                'page': page,
                'connection_error': None,
            },
        )
