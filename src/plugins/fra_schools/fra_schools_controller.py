import re
from functools import partial
from operator import attrgetter
from typing import Any, Annotated

from litestar import get, post
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate

from common.i18n import _
from data.access_levels.actions import AuthAction
from database.sqlite.event.event_database import EventDatabase
from plugins.fra_schools import PLUGIN_NAME
from plugins.fra_schools.fra_schools_database import FRASchoolsDatabase, StoredSchool
from plugins.fra_schools.utils import FRASchoolsUtils, FRASchool
from plugins.utils import PluginUtils
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.guards import EventGuard, ActionGuard
from web.utils import SelectOption

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FRASchoolsController(BaseEventAdminController):
    guards = []

    @staticmethod
    def _get_school_from_row(row: dict[str, Any]) -> StoredSchool:
        return StoredSchool(
            code=row['code'],
            name=row['name'],
            department=row['department'],
            postal_code=row['postal_code'],
            city=row['city'],
            type=row['type'],
            private=bool(row['private']),
        )

    @classmethod
    def get_fra_school_template_context(
        cls, web_context: BaseEventAdminWebContext
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        schools = FRASchoolsUtils.get_event_plugin_data(event).fra_schools
        school_counts = FRASchoolsUtils.get_event_school_counts(event)
        school_options: dict[str, SelectOption] = {'': SelectOption('-')}
        for school in sorted(schools, key=attrgetter('sort_key')):
            option_name = school.short_name
            if school.id in school_counts:
                option_name += f' ({school_counts[school.id]})'
            school_options[str(school.id)] = SelectOption(
                option_name, school.tooltip, search=school.full_name
            )
        database = FRASchoolsDatabase()
        return {
            'fra_schools_database': database,
            'fra_school_options': school_options,
        }

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

        words = re.findall(r'\w+', fra_schools_search.strip().lower())
        fts_query = ' '.join(f'{w}*' for w in words)
        if fra_schools_search and database.file_path().exists():
            with database:
                query: str = """
                    SELECT
                        s.code,
                        s.name,
                        s.department,
                        s.postal_code,
                        s.city,
                        s.type,
                        s.private
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

                database.execute(query, tuple(params))
                rows = database.fetchall()
                schools = [self._get_school_from_row(row) for row in rows]

        return HTMXTemplate(
            template_name='/fra_schools_search_results.html',
            context=web_context.template_context
            | {
                'search': fra_schools_search,
                'search_results': schools,
                'has_more_results': len(schools) == limit,
                'page': page,
                'connection_error': None,
            },
        )

    @post(
        path='fra-schools/add-school/{event_uniq_id:str}',
        name='fra-schools-add-school',
        guards=[EventGuard(), ActionGuard(AuthAction.UPDATE_PLAYERS)],
    )
    async def fra_schools_add_school(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        plugin_data = FRASchoolsUtils.get_event_plugin_data(event)
        school = FRASchool.from_form_data(data)
        errors: dict[str, str] = {}
        if not school.name:
            errors['fra_school_name'] = _('This field is required.')
        if school.postal_code and not (
            school.postal_code.isdigit() and len(school.postal_code) == 5
        ):
            errors['fra_school_postal_code'] = _('Invalid format (expected: 5 digits).')
        if not errors:
            school_id = next(
                (s.id for s in plugin_data.fra_schools if s.code == school.code),
                None,
            )
            if not school_id:
                school_id = (
                    max(plugin_data.fra_schools_by_id | {0: ''}) + 1
                    if plugin_data.fra_schools_by_id
                    else 1
                )
            school.id = school_id
            plugin_data.fra_schools_by_id[school_id] = school
            event.stored_event.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
            with EventDatabase(event.uniq_id, True) as database:
                database.update_stored_event(event.stored_event)
            data |= FRASchool().to_form_data() | {
                'fra_school': str(school_id),
            }
        return HTMXTemplate(
            template_name='/fra_schools_player_form_fields.html',
            context=(
                web_context.template_context
                | self.get_fra_school_template_context(web_context)
                | {
                    'data': data,
                    'errors': errors,
                    'show_fra_school_form': bool(errors),
                }
            ),
        )
