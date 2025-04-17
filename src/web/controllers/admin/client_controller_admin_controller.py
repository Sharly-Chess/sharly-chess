from typing import Annotated, Any

from litestar import post, get, patch, delete
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from data.client_controller import ClientController
from data.family import Family
from data.loader import EventLoader
from data.rotator import Rotator
from data.screen import Screen
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredClientController
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.messages import Message


class ClientControllerAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        client_controller_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None,
    ):
        super().__init__(
            request,
            data=data,
            event_uniq_id=event_uniq_id,
        )
        if self.admin_event is None:
            raise RuntimeError('admin_event not defined')
        self.admin_client_controller: ClientController | None = None
        if self.error:
            return
        if client_controller_id:
            try:
                self.admin_client_controller = (
                    self.admin_event.client_controllers_by_id[client_controller_id]
                )
            except KeyError:
                self._redirect_error(
                    f'Client controller [{client_controller_id}] not found.'
                )
                return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_client_controller': self.admin_client_controller,
        }


class ClientControllerAdminController(BaseEventAdminController):
    @staticmethod
    def _admin_validate_client_controller_update_data(
        action: str,
        web_context: ClientControllerAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> StoredClientController:
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        field: str
        match action:
            case 'create':
                pass
            case 'update' | 'clone' | 'delete':
                if web_context.admin_client_controller is None:
                    raise RuntimeError(
                        f'{web_context.admin_client_controller=} for [{action=}]'
                    )
            case _:
                raise ValueError(f'action=[{action}]')
        field = 'uniq_id'
        uniq_id: str | None = WebContext.form_data_to_str(data, field)
        name: str | None = None
        public: bool | None = None

        if action in [
            'delete',
        ]:
            pass
        else:
            if not uniq_id:
                errors[field] = _('Please enter the client controller ID.')
            else:
                match action:
                    case 'create' | 'clone':
                        if web_context.admin_event is None:
                            raise RuntimeError(
                                f'{web_context.admin_event=} for [{action=}]'
                            )
                        if (
                            uniq_id
                            in web_context.admin_event.client_controllers_by_uniq_id
                        ):
                            errors[field] = _(
                                'Client controller [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
                    case 'update':
                        if web_context.admin_client_controller is None:
                            raise RuntimeError(
                                f'{web_context.admin_client_controller=} for [{action=}]'
                            )
                        if web_context.admin_event is None:
                            raise RuntimeError(
                                f'{web_context.admin_event=} for [{action=}]'
                            )
                        if (
                            uniq_id != web_context.admin_client_controller.uniq_id
                            and uniq_id
                            in web_context.admin_event.client_controllers_by_uniq_id
                        ):
                            errors[field] = _(
                                'Client controller [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
                    case _:
                        raise ValueError(f'action=[{action}]')
            name = WebContext.form_data_to_str(data, 'name')
            public = bool(WebContext.form_data_to_bool(data, 'public'))
        match action:
            case 'create' | 'clone' | 'update':
                pass
            case 'delete':
                if web_context.admin_client_controller is None:
                    raise RuntimeError(
                        f'{web_context.admin_client_controller=} for [{action=}]'
                    )
                uniq_id = uniq_id or ''
                name = web_context.admin_client_controller.stored_client_controller.name
            case _:
                raise ValueError(f'action=[{action}]')

        assert uniq_id is not None

        id: int | None = None
        if web_context.admin_client_controller and action not in [
            'create',
            'clone',
        ]:
            id = web_context.admin_client_controller.id

        return StoredClientController(
            id=id,
            uniq_id=uniq_id,
            public=bool(public),
            name=name,
            errors=errors,
        )

    @classmethod
    def _admin_event_client_controllers_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        modal: str | None = None,
        action: str | None = None,
        client_controller_id: int | None = None,
        data: dict[str, str] | None = None,  # type: ignore
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: ClientControllerAdminWebContext = ClientControllerAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            client_controller_id=client_controller_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context
        ) | {
            'admin_event_tab': 'admin-event-client-controllers-tab',
        }

        match modal:
            case None:
                pass
            case 'client_controller':
                if data is None:
                    uniq_id: str | None = None
                    name: str | None = None
                    public: bool | None = None
                    match action:
                        case 'update':
                            assert web_context.admin_client_controller is not None
                            uniq_id = web_context.admin_client_controller.stored_client_controller.uniq_id
                            name = web_context.admin_client_controller.stored_client_controller.name
                        case 'create':
                            uniq_id = web_context.admin_event.get_unused_client_controller_uniq_id()
                            name = web_context.admin_event.get_unused_client_controller_name()
                        case 'clone':
                            assert web_context.admin_client_controller is not None
                            uniq_id = web_context.admin_event.get_unused_client_controller_uniq_id(
                                base_uniq_id=web_context.admin_client_controller.stored_client_controller.uniq_id
                            )
                            name = web_context.admin_event.get_unused_client_controller_name(
                                base_name=web_context.admin_client_controller.stored_client_controller.name,
                            )
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update' | 'clone':
                            if web_context.admin_client_controller is None:
                                raise RuntimeError(
                                    f'{web_context.admin_client_controller=} for [{action=}]'
                                )
                            public = web_context.admin_client_controller.stored_client_controller.public
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
                    stored_client_controller: StoredClientController = (
                        cls._admin_validate_client_controller_update_data(
                            action, web_context, data
                        )
                    )
                    errors = stored_client_controller.errors
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
        return cls._admin_event_render(template_context)

    @get(
        path='/admin/event/{event_uniq_id:str}/client_controllers',
        name='admin-event-client-controllers-tab',
        cache=1,
    )
    async def htmx_admin_event_client_controllers_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_client_controllers_render(
            request,
            event_uniq_id=event_uniq_id,
        )

    @get(
        path='/admin/client-controller-modal/create/{event_uniq_id:str}',
        name='admin-client-controller-create-modal',
        cache=1,
    )
    async def htmx_admin_client_controller_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_client_controllers_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='client_controller',
            action='create',
            client_controller_id=None,
        )

    @get(
        path='/admin/client-controller-modal/{action:str}/{event_uniq_id:str}/{client_controller_id:int}',
        name='admin-client-controller-modal',
        cache=1,
    )
    async def htmx_admin_client_controller_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        action: str,
        client_controller_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_client_controllers_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='client_controller',
            action=action,
            client_controller_id=client_controller_id,
        )

    def _admin_client_controller_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        action: str,
        client_controller_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'delete' | 'clone' | 'create':
                web_context: ClientControllerAdminWebContext = (
                    ClientControllerAdminWebContext(
                        request,
                        event_uniq_id=event_uniq_id,
                        client_controller_id=client_controller_id,
                        data=data,
                    )
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        stored_client_controller: StoredClientController = (
            self._admin_validate_client_controller_update_data(
                action, web_context, data
            )
        )
        if stored_client_controller.errors:
            return self._admin_event_client_controllers_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='family',
                action=action,
                client_controller_id=client_controller_id,
                data=data,
                errors=stored_client_controller.errors,
            )
        event_loader: EventLoader = EventLoader.get(request=request)
        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            match action:
                case 'create' | 'clone':
                    stored_client_controller = (
                        event_database.add_stored_client_controller(
                            stored_client_controller
                        )
                    )
                    event_database.commit()
                    Message.success(
                        request,
                        _(
                            'Client controller [{client_controller_uniq_id}] has been created.'
                        ).format(
                            client_controller_uniq_id=stored_client_controller.uniq_id
                        ),
                    )
                case 'update':
                    stored_client_controller = (
                        event_database.update_stored_client_controller(
                            stored_client_controller
                        )
                    )
                    event_database.commit()
                    Message.success(
                        request,
                        _(
                            'Client controller [{client_controller_uniq_id}] has been updated.'
                        ).format(
                            client_controller_uniq_id=stored_client_controller.uniq_id
                        ),
                    )
                case 'delete':
                    assert web_context.admin_client_controller is not None
                    event_database.delete_stored_client_controller(
                        web_context.admin_client_controller.id
                    )
                    event_database.commit()
                    Message.success(
                        request,
                        _(
                            'Client controller [{client_controller_uniq_id}] has been deleted.'
                        ).format(
                            client_controller_uniq_id=web_context.admin_client_controller.uniq_id
                        ),
                    )
                case _:
                    raise ValueError(f'action=[{action}]')
        event_loader.clear_cache(event_uniq_id)
        return self._admin_event_client_controllers_render(
            request, event_uniq_id=event_uniq_id
        )

    @post(
        path='/admin/client-controller-create/{event_uniq_id:str}',
        name='admin-client-controller-create',
    )
    async def htmx_admin_client_controller_create(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_client_controller_update(
            request,
            event_uniq_id=event_uniq_id,
            action='create',
            client_controller_id=None,
            data=data,
        )

    @post(
        path='/admin/client-controller-clone/{event_uniq_id:str}/{client_controller_id:int}',
        name='admin-client-controller-clone',
    )
    async def htmx_admin_client_controller_clone(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        client_controller_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_client_controller_update(
            request,
            event_uniq_id=event_uniq_id,
            action='clone',
            client_controller_id=client_controller_id,
            data=data,
        )

    @patch(
        path='/admin/client-controller-update/{event_uniq_id:str}/{client_controller_id:int}',
        name='admin-client-controller-update',
    )
    async def htmx_admin_client_controller_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        client_controller_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_client_controller_update(
            request,
            event_uniq_id=event_uniq_id,
            action='update',
            client_controller_id=client_controller_id,
            data=data,
        )

    @delete(
        path='/admin/client-controller-delete/{event_uniq_id:str}/{client_controller_id:int}',
        name='admin-client-controller-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_client_controller_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        client_controller_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_client_controller_update(
            request,
            event_uniq_id=event_uniq_id,
            action='delete',
            client_controller_id=client_controller_id,
            data=data,
        )

    @patch(
        path='/admin/client-controller-assign/{event_uniq_id:str}/{client_controller_id:int}/{type:str}/{object_uniq_id:str}',
        name='admin-client-controller-assign',
    )
    async def htmx_admin_client_controller_assign(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        client_controller_id: int | None,
        type: str,
        object_uniq_id: str,
    ) -> Template | ClientRedirect:
        web_context: ClientControllerAdminWebContext = ClientControllerAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            client_controller_id=client_controller_id,
            data=None,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        if web_context.admin_client_controller is None:
            raise RuntimeError('admin_client_controller not defined')
        message: str | None = None
        match type:
            case 'screen':
                screen: Screen = web_context.admin_event.screens_by_uniq_id[
                    object_uniq_id
                ]
                web_context.admin_client_controller.screen_id = screen.id
                message = _(
                    'Screen [{screen_uniq_id}] has been assigned to controller [{client_controller_uniq_id}].'
                ).format(
                    client_controller_uniq_id=web_context.admin_client_controller.uniq_id,
                    screen_uniq_id=screen.uniq_id,
                )
            case 'family':
                family: Family = web_context.admin_event.families_by_uniq_id[
                    object_uniq_id
                ]
                web_context.admin_client_controller.family_id = family.id
                message = _(
                    'Family [{family_uniq_id}] has been assigned to controller [{client_controller_uniq_id}].'
                ).format(
                    client_controller_uniq_id=web_context.admin_client_controller.uniq_id,
                    family_uniq_id=family.uniq_id,
                )
            case 'rotator':
                rotator: Rotator = web_context.admin_event.rotators_by_uniq_id[
                    object_uniq_id
                ]
                web_context.admin_client_controller.rotator_id = rotator.id
                message = _(
                    'Rotator [{rotator_uniq_id}] has been assigned to controller [{client_controller_uniq_id}].'
                ).format(
                    client_controller_uniq_id=web_context.admin_client_controller.uniq_id,
                    rotator_uniq_id=rotator.uniq_id,
                )
            case _:
                raise ValueError(f'type=[{type}]')

        if message:
            event_loader: EventLoader = EventLoader.get(request=request)
            with EventDatabase(
                web_context.admin_event.uniq_id, write=True
            ) as event_database:
                event_database.update_stored_client_controller(
                    web_context.admin_client_controller.stored_client_controller
                )
                event_database.commit()
            event_loader.clear_cache(event_uniq_id)

            Message.success(
                request,
                message,
            )
        else:
            Message.error(
                request,
                _('Failed to assign the object to the controller.'),
            )

        return self.render_messages(request)
