from typing import Annotated, Any

from litestar import post, get, patch, delete
from litestar.exceptions import NotFoundException
from litestar.plugins.htmx import HTMXRequest
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXTemplate

from common.i18n import _
from data.access_levels.actions import AuthAction
from data.display_controller import DisplayController
from data.rotator import Rotator
from data.screen import Screen
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredDisplayController
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard, ManageScreenEntityGuard
from web.messages import Message
from web.utils import RequestUtils


class DisplayControllerAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        display_controller_id: int | None = None,
        reload_event: bool = False,
    ):
        super().__init__(request, reload_event)
        if self.admin_event is None:
            raise RuntimeError('admin_event not defined')
        self.admin_display_controller: DisplayController | None = None
        if display_controller_id:
            try:
                self.admin_display_controller = (
                    self.admin_event.display_controllers_by_id[display_controller_id]
                )
            except KeyError:
                raise NotFoundException(
                    f'Display controller [{display_controller_id}] not found.'
                )

    def get_admin_display_controller(self) -> DisplayController:
        assert self.admin_display_controller is not None
        return self.admin_display_controller

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_display_controller': self.admin_display_controller,
        }


class DisplayControllerAdminController(BaseEventAdminController):
    guards = [
        EventGuard(),
        ActionGuard(AuthAction.VIEW_PUBLIC_SCREENS),
        ManageScreenEntityGuard(RequestUtils.DISPLAY_CONTROLLER_ID_PARAM),
    ]

    @staticmethod
    def _admin_validate_display_controller_update_data(
        action: str,
        web_context: DisplayControllerAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> StoredDisplayController:
        event = web_context.get_admin_event()
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        name = ''
        public = WebContext.form_data_to_bool(data, 'public')
        match action:
            case 'create' | 'update':
                name = WebContext.form_data_to_str(data, field := 'name') or ''
                if not name:
                    errors[field] = _('This field is required.')
                else:
                    used_names = list(event.display_controllers_by_uniq_id.keys())
                    if action == 'update':
                        used_names.remove(
                            web_context.get_admin_display_controller().name
                        )
                    if name in used_names:
                        errors[field] = _('This name is already used.')
            case 'delete':
                pass
            case _:
                raise ValueError(f'action=[{action}]')

        display_controller_id: int | None = None
        if action == 'update':
            display_controller_id = web_context.get_admin_display_controller().id

        return StoredDisplayController(
            id=display_controller_id,
            public=public,
            name=name,
            errors=errors,
        )

    @classmethod
    def _admin_event_display_controllers_render(
        cls,
        request: HTMXRequest,
        modal: str | None = None,
        action: str | None = None,
        display_controller_id: int | None = None,
        reload_event: bool = False,
        data: dict[str, str] | None = None,  # type: ignore
        errors: dict[str, str] | None = None,
    ) -> Template:
        web_context = DisplayControllerAdminWebContext(
            request,
            display_controller_id,
            reload_event=reload_event,
        )
        event = web_context.get_admin_event()
        sorted_screens: list[Screen] = sorted(
            event.basic_screens_by_id.values(),
            key=lambda screen: (
                screen.stored_screen.type if screen.stored_screen else '',
                screen.stored_screen.uniq_id if screen.stored_screen else '',
            ),
        )

        admin_display_controllers_sorted_by_uniq_id: list[DisplayController]
        if web_context.client.can_view_private_screens:
            admin_display_controllers_sorted_by_uniq_id = (
                web_context.get_admin_event().display_controllers_sorted_by_uniq_id
            )
        elif web_context.client.can_view_public_screens:
            admin_display_controllers_sorted_by_uniq_id = web_context.get_admin_event().public_display_controllers_sorted_by_uniq_id
        else:
            admin_display_controllers_sorted_by_uniq_id = []

        template_context: dict[str, Any] = web_context.template_context | {
            'admin_event_tab': 'admin-event-display-controllers-tab',
            'sorted_screens': sorted_screens,
            'admin_display_controllers': admin_display_controllers_sorted_by_uniq_id,
        }

        match modal:
            case None:
                pass
            case 'display_controller':
                if data is None:
                    name: str | None = None
                    public: bool | None = None
                    match action:
                        case 'update':
                            display_controller = (
                                web_context.get_admin_display_controller()
                            )
                            name = display_controller.stored_display_controller.name
                        case 'create':
                            name = event.get_unused_display_controller_name()
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update':
                            public = web_context.get_admin_display_controller().stored_display_controller.public
                        case 'create':
                            public = True
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    data = {
                        'public': WebContext.value_to_form_data(public),
                        'name': WebContext.value_to_form_data(name),
                    }
                    stored_display_controller = (
                        cls._admin_validate_display_controller_update_data(
                            action, web_context, data
                        )
                    )
                    errors = stored_display_controller.errors
                if errors is None:
                    errors = {}

                template_context |= {
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
        return cls._admin_base_event_render(template_context)

    @get(
        path='/event/{event_uniq_id:str}/display_controllers',
        name='admin-event-display-controllers-tab',
    )
    async def htmx_admin_event_display_controllers_tab(
        self, request: HTMXRequest
    ) -> Template:
        return self._admin_event_display_controllers_render(request)

    @get(
        path='/display-controller-modal/create/{event_uniq_id:str}',
        name='admin-display-controller-create-modal',
    )
    async def htmx_admin_display_controller_create_modal(
        self, request: HTMXRequest
    ) -> Template:
        return self._admin_event_display_controllers_render(
            request,
            modal='display_controller',
            action='create',
            display_controller_id=None,
        )

    @get(
        path='/display-controller-modal/{action:str}/{event_uniq_id:str}/{display_controller_id:int}',
        name='admin-display-controller-modal',
    )
    async def htmx_admin_display_controller_modal(
        self,
        request: HTMXRequest,
        action: str,
        display_controller_id: int | None,
    ) -> Template:
        return self._admin_event_display_controllers_render(
            request,
            modal='display_controller',
            action=action,
            display_controller_id=display_controller_id,
        )

    def _admin_display_controller_update(
        self,
        request: HTMXRequest,
        action: str,
        display_controller_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        match action:
            case 'update' | 'delete' | 'create':
                web_context = DisplayControllerAdminWebContext(
                    request, display_controller_id
                )
            case _:
                raise ValueError(f'action=[{action}]')
        event = web_context.get_admin_event()
        stored_display_controller = self._admin_validate_display_controller_update_data(
            action, web_context, data
        )
        if stored_display_controller.errors:
            return self._admin_event_display_controllers_render(
                request,
                modal='display_controller',
                action=action,
                display_controller_id=display_controller_id,
                data=data,
                errors=stored_display_controller.errors,
            )
        with EventDatabase(event.uniq_id, write=True) as event_database:
            match action:
                case 'create':
                    stored_display_controller = (
                        event_database.add_stored_display_controller(
                            stored_display_controller
                        )
                    )
                    Message.success(
                        request,
                        _(
                            'Display controller [{display_controller}] has been created.'
                        ).format(display_controller=stored_display_controller.name),
                    )
                case 'update':
                    stored_display_controller = (
                        event_database.update_stored_display_controller(
                            stored_display_controller
                        )
                    )
                    Message.success(
                        request,
                        _(
                            'Display controller [{display_controller}] has been updated.'
                        ).format(display_controller=stored_display_controller.name),
                    )
                case 'delete':
                    display_controller = web_context.get_admin_display_controller()
                    event_database.delete_stored_display_controller(
                        display_controller.id
                    )
                    Message.success(
                        request,
                        _(
                            'Display controller [{display_controller}] has been deleted.'
                        ).format(display_controller=display_controller.name),
                    )
                case _:
                    raise ValueError(f'action=[{action}]')

        return self._admin_event_display_controllers_render(request, reload_event=True)

    @post(
        path='/display-controller-create/{event_uniq_id:str}',
        name='admin-display-controller-create',
    )
    async def htmx_admin_display_controller_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        return self._admin_display_controller_update(
            request,
            action='create',
            display_controller_id=None,
            data=data,
        )

    @patch(
        path='/display-controller-update/{event_uniq_id:str}/{display_controller_id:int}',
        name='admin-display-controller-update',
    )
    async def htmx_admin_display_controller_update(
        self,
        request: HTMXRequest,
        display_controller_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        return self._admin_display_controller_update(
            request,
            action='update',
            display_controller_id=display_controller_id,
            data=data,
        )

    @delete(
        path='/display-controller-delete/{event_uniq_id:str}/{display_controller_id:int}',
        name='admin-display-controller-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_display_controller_delete(
        self,
        request: HTMXRequest,
        display_controller_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        return self._admin_display_controller_update(
            request,
            action='delete',
            display_controller_id=display_controller_id,
            data=data,
        )

    @patch(
        path='/display-controller-assign/{event_uniq_id:str}/{display_controller_id:int}/{type:str}/{object_uniq_id:str}',
        name='admin-display-controller-assign',
    )
    async def htmx_admin_display_controller_assign(
        self,
        request: HTMXRequest,
        display_controller_id: int | None,
        type: str,
        object_uniq_id: str,
    ) -> Template:
        web_context = DisplayControllerAdminWebContext(request, display_controller_id)
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        if web_context.admin_display_controller is None:
            raise RuntimeError('admin_display_controller not defined')
        message: str
        match type:
            case 'screen':
                screen: Screen = web_context.admin_event.screens_by_uniq_id[
                    object_uniq_id
                ]
                web_context.admin_display_controller.screen_id = screen.id
                message = _(
                    'Screen [{screen_uniq_id}] has been assigned to controller [{display_controller}].'
                ).format(
                    display_controller=web_context.admin_display_controller.name,
                    screen_uniq_id=screen.uniq_id,
                )
            case 'rotator':
                rotator: Rotator = web_context.admin_event.rotators_by_uniq_id[
                    object_uniq_id
                ]
                web_context.admin_display_controller.rotator_id = rotator.id
                message = _(
                    'Rotator [{rotator}] has been assigned to controller [{display_controller}].'
                ).format(
                    display_controller=web_context.admin_display_controller.name,
                    rotator=rotator.name,
                )
            case _:
                raise ValueError(f'type=[{type}]')

        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            event_database.update_stored_display_controller(
                web_context.admin_display_controller.stored_display_controller
            )

        Message.success(request, message)
        return HTMXTemplate(
            template_name='common/empty.html',
            re_swap='none',
            trigger_event='request_refresh',
            after='receive',
        )

    @patch(
        path='/display-controller-clear/{event_uniq_id:str}/{display_controller_id:int}',
        name='admin-display-controller-clear',
    )
    async def htmx_admin_display_controller_clear(
        self,
        request: HTMXRequest,
        display_controller_id: int | None,
    ) -> Template:
        web_context = DisplayControllerAdminWebContext(request, display_controller_id)
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        if web_context.admin_display_controller is None:
            raise RuntimeError('admin_display_controller not defined')

        web_context.admin_display_controller.screen_id = None
        web_context.admin_display_controller.rotator_id = None
        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            event_database.update_stored_display_controller(
                web_context.admin_display_controller.stored_display_controller
            )

        return self._admin_event_display_controllers_render(request, reload_event=True)
