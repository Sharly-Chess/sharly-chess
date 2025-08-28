from typing import Annotated, Any

from litestar import post, get, patch, delete
from litestar.plugins.htmx import HTMXRequest, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXTemplate

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.display_controller import DisplayController
from data.rotator import Rotator
from data.screen import Screen
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredDisplayController
from utils import StaticUtils
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.messages import Message


class DisplayControllerAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        display_controller_id: int | None = None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None = None,
    ):
        super().__init__(
            request,
            data=data,
            event_uniq_id=event_uniq_id,
        )
        if self.admin_event is None:
            raise RuntimeError('admin_event not defined')
        self.admin_display_controller: DisplayController | None = None
        if self.error:
            return
        if display_controller_id:
            try:
                self.admin_display_controller = (
                    self.admin_event.display_controllers_by_id[display_controller_id]
                )
            except KeyError:
                self._redirect_error(
                    f'Display controller [{display_controller_id}] not found.'
                )
                return

    def get_admin_display_controller(self) -> DisplayController:
        assert self.admin_display_controller is not None
        return self.admin_display_controller

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_display_controller': self.admin_display_controller,
        }


class DisplayControllerAdminController(BaseEventAdminController):
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
        name: str | None
        public = WebContext.form_data_to_bool(data, 'public')
        match action:
            case 'create' | 'clone' | 'update':
                name = WebContext.form_data_to_str(data, 'name') or ''
                if not name:
                    errors['name'] = _('Please enter the display controller name.')
                if action == 'update':
                    uniq_id = web_context.get_admin_display_controller().uniq_id
                else:
                    uniq_id = event.get_unused_display_controller_uniq_id(
                        StaticUtils.name_to_uniq_id(name)
                    )
            case 'delete':
                uniq_id = ''
                name = web_context.get_admin_display_controller().stored_display_controller.name
            case _:
                raise ValueError(f'action=[{action}]')

        display_controller_id: int | None = None
        if web_context.admin_display_controller and action not in [
            'create',
            'clone',
        ]:
            display_controller_id = web_context.admin_display_controller.id

        return StoredDisplayController(
            id=display_controller_id,
            uniq_id=uniq_id,
            public=bool(public),
            name=name,
            errors=errors,
        )

    @classmethod
    def _admin_event_display_controllers_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        modal: str | None = None,
        action: str | None = None,
        display_controller_id: int | None = None,
        data: dict[str, str] | None = None,  # type: ignore
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context = DisplayControllerAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            display_controller_id=display_controller_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        event = web_context.get_admin_event()
        sorted_screens: list[Screen] = sorted(
            event.basic_screens_by_id.values(),
            key=lambda screen: (
                screen.stored_screen.type if screen.stored_screen else None,
                screen.stored_screen.uniq_id if screen.stored_screen else None,
            ),
        )

        template_context = web_context.template_context | {
            'admin_event_tab': 'admin-event-display-controllers-tab',
            'sorted_screens': sorted_screens,
        }

        match modal:
            case None:
                pass
            case 'display_controller':
                if data is None:
                    uniq_id: str | None = None
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
                        case 'clone':
                            display_controller = (
                                web_context.get_admin_display_controller()
                            )
                            name = event.get_unused_display_controller_name(
                                base_name=display_controller.stored_display_controller.name,
                            )
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update' | 'clone':
                            public = web_context.get_admin_display_controller().stored_display_controller.public
                        case 'create':
                            public = True
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    data = {
                        'uniq_id': WebContext.value_to_form_data(uniq_id),
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
                    'display_controller_uniq_ids': list(
                        event.display_controllers_by_uniq_id.keys()
                    ),
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
        return cls._admin_event_render(template_context)

    @get(
        path='/admin/event/{event_uniq_id:str}/display_controllers',
        name='admin-event-display-controllers-tab',
    )
    async def htmx_admin_event_display_controllers_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_display_controllers_render(
            request,
            event_uniq_id=event_uniq_id,
        )

    @get(
        path='/admin/display-controller-modal/create/{event_uniq_id:str}',
        name='admin-display-controller-create-modal',
    )
    async def htmx_admin_display_controller_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_display_controllers_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='display_controller',
            action='create',
            display_controller_id=None,
        )

    @get(
        path='/admin/display-controller-modal/{action:str}/{event_uniq_id:str}/{display_controller_id:int}',
        name='admin-display-controller-modal',
    )
    async def htmx_admin_display_controller_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        action: str,
        display_controller_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_display_controllers_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='display_controller',
            action=action,
            display_controller_id=display_controller_id,
        )

    def _admin_display_controller_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        action: str,
        display_controller_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'delete' | 'clone' | 'create':
                web_context: DisplayControllerAdminWebContext = (
                    DisplayControllerAdminWebContext(
                        request,
                        event_uniq_id=event_uniq_id,
                        display_controller_id=display_controller_id,
                        data=data,
                    )
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        event = web_context.get_admin_event()
        stored_display_controller = self._admin_validate_display_controller_update_data(
            action, web_context, data
        )
        if stored_display_controller.errors:
            return self._admin_event_display_controllers_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='display_controller',
                action=action,
                display_controller_id=display_controller_id,
                data=data,
                errors=stored_display_controller.errors,
            )
        with EventDatabase(event.uniq_id, write=True) as event_database:
            match action:
                case 'create' | 'clone':
                    stored_display_controller = (
                        event_database.add_stored_display_controller(
                            stored_display_controller
                        )
                    )
                    event_database.commit()
                    Message.success(
                        request,
                        _(
                            'Display controller [{display_controller_uniq_id}] has been created.'
                        ).format(
                            display_controller_uniq_id=stored_display_controller.uniq_id
                        ),
                    )
                case 'update':
                    stored_display_controller = (
                        event_database.update_stored_display_controller(
                            stored_display_controller
                        )
                    )
                    event_database.commit()
                    Message.success(
                        request,
                        _(
                            'Display controller [{display_controller_uniq_id}] has been updated.'
                        ).format(
                            display_controller_uniq_id=stored_display_controller.uniq_id
                        ),
                    )
                case 'delete':
                    display_controller = web_context.get_admin_display_controller()
                    event_database.delete_stored_display_controller(
                        display_controller.id
                    )
                    event_database.commit()
                    Message.success(
                        request,
                        _(
                            'Display controller [{display_controller_uniq_id}] has been deleted.'
                        ).format(display_controller_uniq_id=display_controller.uniq_id),
                    )
                case _:
                    raise ValueError(f'action=[{action}]')

        return self._admin_event_display_controllers_render(
            request, event_uniq_id=event_uniq_id
        )

    @post(
        path='/admin/display-controller-create/{event_uniq_id:str}',
        name='admin-display-controller-create',
    )
    async def htmx_admin_display_controller_create(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_display_controller_update(
            request,
            event_uniq_id=event_uniq_id,
            action='create',
            display_controller_id=None,
            data=data,
        )

    @patch(
        path='/admin/display-controller-update/{event_uniq_id:str}/{display_controller_id:int}',
        name='admin-display-controller-update',
    )
    async def htmx_admin_display_controller_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        display_controller_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_display_controller_update(
            request,
            event_uniq_id=event_uniq_id,
            action='update',
            display_controller_id=display_controller_id,
            data=data,
        )

    @patch(
        path='/admin/display-controller-uniq-id-update/{event_uniq_id:str}/{display_controller_id:int}',
        name='admin-display-controller-uniq-id-update',
    )
    async def htmx_admin_display_controller_uniq_id_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
        display_controller_id: int,
    ) -> HTMXTemplate | ClientRedirect:
        web_context = DisplayControllerAdminWebContext(
            request, event_uniq_id, display_controller_id
        )
        event = web_context.get_admin_event()
        display_controller = web_context.get_admin_display_controller()
        new_uniq_id = WebContext.form_data_to_str(data, 'uniq_id')
        if (
            not new_uniq_id
            or not SharlyChessConfig.uniq_id_regex.match(new_uniq_id)
            or (
                new_uniq_id != display_controller.uniq_id
                and new_uniq_id in event.families_by_uniq_id.keys()
            )
        ):
            # No precise error (validated in JS)
            return self.redirect_error(request, f'Invalid uniq ID [{new_uniq_id}].')
        stored_display_controller = display_controller.stored_display_controller
        stored_display_controller.uniq_id = new_uniq_id
        with EventDatabase(event.uniq_id, True) as database:
            database.update_stored_display_controller(stored_display_controller)
            database.commit()
        return HTMXTemplate(
            template_name='/admin/display_controllers/display_controller_update_modal_header.html',
            context=web_context.template_context
            | {
                'display_controller_uniq_ids': list(
                    event.display_controllers_by_uniq_id.keys()
                )
            },
            re_swap='innerHTML',
            re_target='.modal-header',
        )

    @delete(
        path='/admin/display-controller-delete/{event_uniq_id:str}/{display_controller_id:int}',
        name='admin-display-controller-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_display_controller_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        display_controller_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_display_controller_update(
            request,
            event_uniq_id=event_uniq_id,
            action='delete',
            display_controller_id=display_controller_id,
            data=data,
        )

    @patch(
        path='/admin/display-controller-assign/{event_uniq_id:str}/{display_controller_id:int}/{type:str}/{object_uniq_id:str}',
        name='admin-display-controller-assign',
    )
    async def htmx_admin_display_controller_assign(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        display_controller_id: int | None,
        type: str,
        object_uniq_id: str,
    ) -> Template | ClientRedirect:
        web_context: DisplayControllerAdminWebContext = (
            DisplayControllerAdminWebContext(
                request,
                event_uniq_id=event_uniq_id,
                display_controller_id=display_controller_id,
                data=None,
            )
        )
        if web_context.error:
            return web_context.error
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
                    'Screen [{screen_uniq_id}] has been assigned to controller [{display_controller_uniq_id}].'
                ).format(
                    display_controller_uniq_id=web_context.admin_display_controller.uniq_id,
                    screen_uniq_id=screen.uniq_id,
                )
            case 'rotator':
                rotator: Rotator = web_context.admin_event.rotators_by_uniq_id[
                    object_uniq_id
                ]
                web_context.admin_display_controller.rotator_id = rotator.id
                message = _(
                    'Rotator [{rotator_uniq_id}] has been assigned to controller [{display_controller_uniq_id}].'
                ).format(
                    display_controller_uniq_id=web_context.admin_display_controller.uniq_id,
                    rotator_uniq_id=rotator.uniq_id,
                )
            case _:
                raise ValueError(f'type=[{type}]')

        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            event_database.update_stored_display_controller(
                web_context.admin_display_controller.stored_display_controller
            )
            event_database.commit()

        Message.success(
            request,
            message,
        )
        return HTMXTemplate(
            template_name='common/empty.html',
            re_swap='none',
            trigger_event='request_refresh',
            after='receive',
        )

    @patch(
        path='/admin/admin-display-controller-clear/{event_uniq_id:str}/{display_controller_id:int}',
        name='admin-display-controller-clear',
    )
    async def htmx_admin_display_controller_clear(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        display_controller_id: int | None,
    ) -> Template | ClientRedirect:
        web_context: DisplayControllerAdminWebContext = (
            DisplayControllerAdminWebContext(
                request,
                event_uniq_id=event_uniq_id,
                display_controller_id=display_controller_id,
                data=None,
            )
        )
        if web_context.error:
            return web_context.error
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
            event_database.commit()

        return self._admin_event_display_controllers_render(
            request, event_uniq_id=event_uniq_id
        )
