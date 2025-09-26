from copy import copy
from operator import attrgetter
from typing import Annotated, Any

from litestar import post, get, delete, patch
from litestar.exceptions import ClientException
from litestar.plugins.htmx import HTMXRequest
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from data.access_levels.actions import AuthAction
from data.family import Family
from data.rotator import Rotator
from data.screen import Screen
from database.sqlite.event.event_store import StoredRotator
from utils.enum import FormAction, ScreenType
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard, ManageScreenEntityGuard
from web.messages import Message
from web.session import SessionHandler
from web.utils import RequestUtils


class RotatorAdminWebContext(BaseEventAdminWebContext):
    def __init__(self, request: HTMXRequest):
        super().__init__(request)
        self.admin_rotator = RequestUtils.get_optional_rotator(request)

    def get_admin_rotator(self) -> Rotator:
        assert self.admin_rotator is not None
        return self.admin_rotator

    @property
    def template_context(self) -> dict[str, Any]:
        event = self.get_admin_event()
        admin_rotators: list[Rotator] = []
        if self.client.can_view_private_screens:
            admin_rotators = event.rotators_sorted_by_uniq_id
        elif self.client.can_view_public_screens:
            admin_rotators = event.public_rotators_sorted_by_uniq_id
        return super().template_context | {
            'admin_event_tab': 'admin-event-rotators-tab',
            'admin_rotators_show_details': (
                SessionHandler.get_session_admin_rotators_show_details(self.request)
            ),
            'admin_rotators': admin_rotators,
            'admin_rotator': self.admin_rotator,
        }


class RotatorAdminController(BaseEventAdminController):
    guards = [
        EventGuard(),
        ActionGuard(AuthAction.VIEW_PUBLIC_SCREENS),
        ManageScreenEntityGuard(RequestUtils.ROTATOR_ID_PARAM),
    ]

    @classmethod
    def _admin_event_rotator_render(
        cls,
        web_context: RotatorAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template:
        return cls._admin_base_event_render(
            web_context.template_context | (template_context or {})
        )

    @staticmethod
    def _rotator_form_data_from_rotator(rotator: Rotator) -> dict[str, str]:
        stored_rotator = rotator.stored_rotator
        return WebContext.values_dict_to_form_data(
            {
                'name': stored_rotator.name,
                'public': stored_rotator.public,
                'delay': stored_rotator.delay,
                'message_text_checkbox': stored_rotator.message_default,
                'message_text': stored_rotator.message_text,
            }
        )

    @get(
        path='/admin/event/{event_uniq_id:str}/rotators',
        name='admin-event-rotators-tab',
    )
    async def htmx_admin_event_rotators_tab(
        self,
        request: HTMXRequest,
        admin_rotators_show_details: bool | None,
    ) -> Template:
        if admin_rotators_show_details is not None:
            SessionHandler.set_session_admin_rotators_show_details(
                request, admin_rotators_show_details
            )
        return self._admin_event_rotator_render(RotatorAdminWebContext(request))

    # -------------------------------------------------------------------------
    # Modals
    # -------------------------------------------------------------------------

    @staticmethod
    def _rotator_form_modal_context(
        action: FormAction,
        data: dict[str, str],
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        default_data = WebContext.values_dict_to_form_data(
            {
                'name': '',
                'public': True,
                'delay': None,
                'message_text_checkbox': True,
                'message_text': '',
            }
        )
        return {
            'modal': 'rotator',
            'action': action,
            'data': default_data | data,
            'errors': errors or {},
        }

    @classmethod
    def _rotator_screens_modal_context(
        cls,
        web_context: RotatorAdminWebContext,
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        rotator = web_context.get_admin_rotator()
        return {
            'modal': 'rotator_screens',
            'screen_options': cls._screen_or_family_options(
                event.basic_screens_by_screen_type_sorted_by_uniq_id,
                rotator.screens,
            ),
            'family_options': cls._screen_or_family_options(
                event.families_by_screen_type, rotator.families
            ),
        }

    @staticmethod
    def _screen_or_family_options[T: Screen | Family](
        entities_by_screen_type: dict[ScreenType, list[T]],
        rotator_entities: list[T],
    ) -> dict[str, dict[str, str]]:
        options: dict[str, dict[str, str]] = {
            screen_type.name: {} for screen_type in ScreenType
        }
        rotator_ids = [entity.id for entity in rotator_entities]
        for screen_type, entities in entities_by_screen_type.items():
            if screen_type == ScreenType.INPUT:
                continue
            for entity in sorted(entities, key=attrgetter('name')):
                suffix = ''
                if rotator_count := rotator_ids.count(getattr(entity, 'id')):
                    suffix = f' (x{rotator_count})'
                options[screen_type.name][str(entity.id)] = entity.name + suffix
        for screen_type in ScreenType:
            if not options[screen_type.name]:
                del options[screen_type.name]
        return options

    @get(
        path='/admin/rotator-modal/create/{event_uniq_id:str}',
        name='admin-rotator-create-modal',
    )
    async def htmx_admin_rotator_create_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = RotatorAdminWebContext(request)
        name = web_context.get_admin_event().get_unused_rotator_name()
        template_context = self._rotator_form_modal_context(
            FormAction.CREATE, {'name': name}
        )
        return self._admin_event_rotator_render(web_context, template_context)

    @get(
        path='/admin/rotator-modal/update/{event_uniq_id:str}/{rotator_id:int}',
        name='admin-rotator-update-modal',
    )
    async def htmx_admin_rotator_update_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = RotatorAdminWebContext(request)
        rotator = web_context.get_admin_rotator()
        data = self._rotator_form_data_from_rotator(rotator)
        template_context = self._rotator_form_modal_context(FormAction.UPDATE, data)
        return self._admin_event_rotator_render(web_context, template_context)

    @get(
        path='/admin/rotator-modal/clone/{event_uniq_id:str}/{rotator_id:int}',
        name='admin-rotator-clone-modal',
    )
    async def htmx_admin_rotator_clone_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = RotatorAdminWebContext(request)
        event = web_context.get_admin_event()
        rotator = web_context.get_admin_rotator()
        data = self._rotator_form_data_from_rotator(rotator)
        data |= {'name': event.get_unused_rotator_name(rotator.name)}
        template_context = self._rotator_form_modal_context(FormAction.CLONE, data)
        return self._admin_event_rotator_render(web_context, template_context)

    @get(
        path='/admin/rotator-modal/delete/{event_uniq_id:str}/{rotator_id:int}',
        name='admin-rotator-delete-modal',
    )
    async def htmx_admin_rotator_delete_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        return self._admin_event_rotator_render(
            RotatorAdminWebContext(request),
            {'modal': 'rotator_delete'},
        )

    @get(
        path='/admin/rotator-screens-modal/{event_uniq_id:str}/{rotator_id:int}',
        name='admin-rotator-screens-modal',
    )
    async def htmx_admin_rotator_screens_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = RotatorAdminWebContext(request)
        return self._admin_event_rotator_render(
            web_context, self._rotator_screens_modal_context(web_context)
        )

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    @staticmethod
    def _read_rotator_form_data(
        data: dict[str, str],
        web_context: RotatorAdminWebContext,
        action: FormAction,
    ) -> tuple[StoredRotator | None, dict[str, str]]:
        event = web_context.get_admin_event()
        errors: dict[str, str] = {}
        name = WebContext.form_data_to_str(data, field := 'name') or ''
        if not name:
            errors[field] = _('This field is required.')
        else:
            used_names = list(event.rotators_by_uniq_id.keys())
            if action == FormAction.UPDATE:
                used_names.remove(web_context.get_admin_rotator().name)
            if name in used_names:
                errors[field] = _('This name is already used.')
        delay: int | None = None
        try:
            delay = WebContext.form_data_to_int(data, field := 'delay', minimum=1)
        except ValueError:
            errors[field] = _('A positive integer is expected.')
        if errors:
            return None, errors
        stored_rotator = StoredRotator(
            id=None,
            name=name,
            delay=delay,
            message_default=WebContext.form_data_to_bool(data, 'message_text_checkbox'),
            message_text=WebContext.form_data_to_str(data, 'message_text'),
        )
        return stored_rotator, errors

    @post(
        path='/admin/rotator-create/{event_uniq_id:str}',
        name='admin-rotator-create',
        guards=[ActionGuard(AuthAction.MANAGE_SCREENS)],
    )
    async def htmx_admin_rotator_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = RotatorAdminWebContext(request)
        stored_rotator, errors = self._read_rotator_form_data(
            data, web_context, FormAction.CREATE
        )
        if not stored_rotator:
            return self._admin_event_rotator_render(
                web_context,
                self._rotator_form_modal_context(FormAction.CREATE, data, errors),
            )
        event = web_context.get_admin_event()
        event.create_rotator(stored_rotator)
        Message.success(
            request,
            _('Rotator [{rotator}] has been created.').format(
                rotator=stored_rotator.name
            ),
        )
        return self._admin_event_rotator_render(web_context)

    @post(
        path='/admin/rotator-clone/{event_uniq_id:str}/{rotator_id:int}',
        name='admin-rotator-clone',
    )
    async def htmx_admin_rotator_clone(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = RotatorAdminWebContext(request)
        stored_rotator, errors = self._read_rotator_form_data(
            data, web_context, FormAction.CLONE
        )
        if not stored_rotator:
            return self._admin_event_rotator_render(
                web_context,
                self._rotator_form_modal_context(FormAction.CLONE, data, errors),
            )
        event = web_context.get_admin_event()
        cloned_rotator = web_context.get_admin_rotator()
        stored_rotator.stored_rotating_screens = copy(
            cloned_rotator.stored_rotating_screens
        )
        event.create_rotator(stored_rotator)
        Message.success(
            request,
            _('Rotator [{rotator}] has been created.').format(
                rotator=stored_rotator.name
            ),
        )
        return self._admin_event_rotator_render(web_context)

    @patch(
        path='/admin/rotator-update/{event_uniq_id:str}/{rotator_id:int}',
        name='admin-rotator-update',
    )
    async def htmx_admin_rotator_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = RotatorAdminWebContext(request)
        new_stored_rotator, errors = self._read_rotator_form_data(
            data, web_context, FormAction.UPDATE
        )
        if not new_stored_rotator:
            return self._admin_event_rotator_render(
                web_context,
                self._rotator_form_modal_context(FormAction.UPDATE, data, errors),
            )
        event = web_context.get_admin_event()
        stored_rotator = web_context.get_admin_rotator().stored_rotator
        stored_rotator.public = new_stored_rotator.public
        stored_rotator.name = new_stored_rotator.name
        stored_rotator.delay = new_stored_rotator.delay
        stored_rotator.message_default = new_stored_rotator.message_default
        stored_rotator.message_text = new_stored_rotator.message_text
        event.update_rotator(stored_rotator)
        Message.success(
            request,
            _('Rotator [{rotator}] has been updated.').format(
                rotator=stored_rotator.name
            ),
        )
        return self._admin_event_rotator_render(web_context)

    @delete(
        path='/admin/rotator-delete/{event_uniq_id:str}/{rotator_id:int}',
        name='admin-rotator-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_rotator_delete(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = RotatorAdminWebContext(request)
        event = web_context.get_admin_event()
        rotator = web_context.get_admin_rotator()
        event.delete_rotator(rotator)
        Message.success(
            request,
            _('Rotator [{rotator}] has been deleted.').format(rotator=rotator.name),
        )
        return self._admin_event_rotator_render(web_context)

    @delete(
        path=(
            '/admin/rotator-screen-delete/{event_uniq_id:str}/'
            '{rotator_id:int}/{rotating_screen_id:int}'
        ),
        name='admin-rotator-screen-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_rotator_screen_delete(
        self,
        request: HTMXRequest,
        rotating_screen_id: int,
    ) -> Template:
        web_context = RotatorAdminWebContext(request)
        rotator = web_context.get_admin_rotator()
        try:
            rotator.delete_rotating_screen(rotating_screen_id)
        except ValueError as error:
            raise ClientException(error)
        return self._admin_event_rotator_render(
            web_context, self._rotator_screens_modal_context(web_context)
        )

    @patch(
        path='/admin/rotator-reorder-screens/{event_uniq_id:str}/{rotator_id:int}',
        name='admin-rotator-reorder-screens',
    )
    async def htmx_admin_rotator_reorder_screens(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = RotatorAdminWebContext(request)
        rotator = web_context.get_admin_rotator()
        rotator.reorder_rotating_screens(data.get('rotating_screen_ids', []))
        return self._admin_event_rotator_render(
            web_context, self._rotator_screens_modal_context(web_context)
        )

    @post(
        path='/admin/rotating-screens-create/{event_uniq_id:str}/{rotator_id:int}',
        name='admin-rotating-screens-create',
    )
    async def htmx_admin_rotating_screens_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = RotatorAdminWebContext(request)
        rotator = web_context.get_admin_rotator()
        flat_data = WebContext.flatten_list_data(data)
        screen_ids = WebContext.form_data_to_list_int(flat_data, 'screen_ids', [])
        family_ids = WebContext.form_data_to_list_int(flat_data, 'family_ids', [])
        try:
            rotator.add_rotating_screens(screen_ids, family_ids)
        except ValueError as error:
            raise ClientException(error)
        return self._admin_event_rotator_render(
            web_context, self._rotator_screens_modal_context(web_context)
        )
