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
from plugins.fra_schools import PLUGIN_NAME
from plugins.fra_schools.fra_schools_database import FRASchoolsDatabase
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

    SEARCH_LIMIT = 25

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
        schools: list[FRASchool] = []

        if fra_schools_search and database.file_path().exists():
            with database:
                schools = database.search_school(
                    fra_schools_search, page, self.SEARCH_LIMIT
                )

        return HTMXTemplate(
            template_name='/fra_schools_search_results.html',
            context=web_context.template_context
            | {
                'search': fra_schools_search,
                'search_results': schools,
                'has_more_results': len(schools) == self.SEARCH_LIMIT,
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
        school = FRASchool.from_form_data(data)
        errors: dict[str, str] = {}
        if not school.name:
            errors['fra_school_name'] = _('This field is required.')
        if school.postal_code and not (
            school.postal_code.isdigit() and len(school.postal_code) == 5
        ):
            errors['fra_school_postal_code'] = _('Invalid format (expected: 5 digits).')
        if not errors:
            school_id = FRASchoolsUtils.add_event_school(
                event, school, update_existing=True
            )
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
