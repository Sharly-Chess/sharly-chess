from functools import partial
from operator import attrgetter
from typing import Any, Annotated

from litestar import get, post, patch, delete
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXRequest, HTMXTemplate

from common.i18n import _
from data.access_levels.actions import AuthAction
from plugins.fra_schools import PLUGIN_NAME
from plugins.fra_schools.fra_schools_database import FRASchoolsDatabase
from plugins.fra_schools.utils import FRASchoolsUtils, FRASchool
from plugins.utils import PluginUtils
from utils.enum import FormAction
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.guards import EventGuard, ActionGuard
from web.utils import SelectOption

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FraSchoolsWebContext(BaseEventAdminWebContext):
    def __init__(self, request: HTMXRequest, fra_school_id: int | None = None):
        super().__init__(request)
        self.fra_school: FRASchool | None = None
        if fra_school_id:
            self.fra_school = FRASchoolsUtils.get_school_by_id(
                self.get_admin_event(), fra_school_id
            )
            if not self.fra_school:
                raise NotFoundException(f'Unknown school [{fra_school_id}].')

    def get_fra_school(self) -> FRASchool:
        assert self.fra_school is not None
        return self.fra_school

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'fra_school': self.fra_school,
        }


class FRASchoolsController(BaseEventAdminController):
    guards = []
    SEARCH_LIMIT = 25

    @classmethod
    def get_fra_school_template_context(
        cls,
        web_context: BaseEventAdminWebContext,
        action: FormAction = FormAction.CREATE,
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        schools = FRASchoolsUtils.get_event_plugin_data(event).fra_schools
        school_counts = FRASchoolsUtils.get_event_school_counts(
            web_context.client.allowed_players
        )
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
            'fra_schools_action': action,
            'fra_schools_database': database,
            'fra_school_options': school_options,
        }

    @get(
        path=[
            '/fra-schools/search-player/{event_uniq_id:str}',
            '/fra-schools/search-player/{event_uniq_id:str}/{page:int}',
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

    @classmethod
    def _render_fra_schools_form(
        cls,
        web_context: FraSchoolsWebContext,
        action: FormAction = FormAction.CREATE,
        show_form: bool = False,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> HTMXTemplate:
        event = web_context.get_admin_event()
        template_context = cls.get_fra_school_template_context(web_context, action)
        show_delete_button = False
        if action == FormAction.UPDATE:
            school = web_context.get_fra_school()
            show_delete_button = all(
                school.id
                != getattr(FRASchoolsUtils.get_player_school(player), 'id', None)
                for player in event.players
            )

        template_context |= {
            'show_fra_school_form': show_form or bool(errors),
            'data': data,
            'errors': errors or {},
            'show_fra_school_delete_button': show_delete_button,
        }
        return HTMXTemplate(
            template_name='/fra_schools_player_form_fields.html',
            context=web_context.template_context | template_context,
            re_target='#fra-schools-container',
            re_swap='outerHTML',
        )

    @get(
        path='/fra-schools/add-school-form/{event_uniq_id:str}',
        name='fra-schools-add-school-form',
        guards=[EventGuard()],
    )
    async def fra_schools_add_school_form(
        self,
        request: HTMXRequest,
        fra_school_id: str,
    ) -> Template:
        web_context = FraSchoolsWebContext(request)
        data = FRASchool().to_form_data() | {
            'fra_school_id': fra_school_id,
        }
        return self._render_fra_schools_form(
            web_context, FormAction.CREATE, show_form=True, data=data
        )

    @get(
        path='/fra-schools/update-school-form/{event_uniq_id:str}',
        name='fra-schools-update-school-form',
        guards=[EventGuard()],
    )
    async def fra_schools_update_schools_form(
        self,
        request: HTMXRequest,
        fra_school_id: int,
    ) -> Template:
        web_context = FraSchoolsWebContext(request, fra_school_id)
        data = web_context.get_fra_school().to_form_data() | {
            'fra_school_id': str(fra_school_id),
        }
        return self._render_fra_schools_form(
            web_context, FormAction.UPDATE, show_form=True, data=data
        )

    @staticmethod
    def _validate_school_form(school: FRASchool) -> dict[str, str]:
        errors: dict[str, str] = {}
        if not school.name:
            errors['fra_school_name'] = _('This field is required.')
        if school.postal_code and not (
            school.postal_code.isdigit() and len(school.postal_code) == 5
        ):
            errors['fra_school_postal_code'] = _(
                'Invalid format (expected: {format}).'
            ).format(format=12345)
        return errors

    @post(
        path='/fra-schools/add-school/{event_uniq_id:str}',
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
        web_context = FraSchoolsWebContext(request)
        event = web_context.get_admin_event()
        school = FRASchool.from_form_data(data)
        errors = self._validate_school_form(school)
        if not errors:
            school_id = FRASchoolsUtils.add_event_school(
                event, school, update_existing=True
            )
            data |= FRASchool().to_form_data() | {
                'fra_school_id': str(school_id),
            }

        return self._render_fra_schools_form(web_context, data=data, errors=errors)

    @patch(
        path='/fra-schools/update-school/{event_uniq_id:str}/{fra_school_id:int}',
        name='fra-schools-update-school',
        guards=[EventGuard(), ActionGuard(AuthAction.UPDATE_PLAYERS)],
    )
    async def fra_schools_update_school(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        fra_school_id: int,
    ) -> Template:
        web_context = FraSchoolsWebContext(request, fra_school_id)
        current_school = web_context.get_fra_school()
        event = web_context.get_admin_event()
        school = FRASchool.from_form_data(data)
        errors = self._validate_school_form(school)
        if school.code and school.code != current_school.code:
            for existing_school in FRASchoolsUtils.get_event_plugin_data(
                event
            ).fra_schools:
                if school.code == existing_school.code:
                    errors['fra_school_code'] = _(
                        'The school with that code already exists.'
                    )
        if not errors:
            school.id = current_school.id
            FRASchoolsUtils.update_event_school(event, school)
            data |= FRASchool().to_form_data() | {
                'fra_school_id': str(school.id),
            }
        return self._render_fra_schools_form(
            web_context, FormAction.UPDATE, data=data, errors=errors
        )

    @delete(
        path='/fra-schools/delete-school/{event_uniq_id:str}/{fra_school_id:int}',
        name='fra-schools-delete-school',
        status_code=HTTP_200_OK,
    )
    async def fra_schools_delete_school(
        self,
        request: HTMXRequest,
        fra_school_id: int,
    ) -> Template:
        web_context = FraSchoolsWebContext(request, fra_school_id)
        event = web_context.get_admin_event()
        FRASchoolsUtils.delete_event_school(event, fra_school_id)
        return self._render_fra_schools_form(web_context)
