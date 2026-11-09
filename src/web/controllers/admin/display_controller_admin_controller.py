from operator import attrgetter
from typing import Annotated, Any
from urllib.parse import urlsplit

from litestar import post, get, patch, delete
from litestar.enums import RequestEncodingType
from litestar.exceptions import ClientException, NotFoundException
from litestar.params import Body, FromPath
from litestar.plugins.htmx import HTMXRequest
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXTemplate

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.access_levels.actions import AuthAction
from data.event import Event
from data.screens.display_controller import DisplayController
from data.screens.family import Family
from data.screens.rotator import Rotator
from data.screens.screen import Screen
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredDisplayController
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.channels import mark_screens_change_announced, publish_ws_event
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
                ) from None

    def get_admin_display_controller(self) -> DisplayController:
        assert self.admin_display_controller is not None
        return self.admin_display_controller

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_display_controller': self.admin_display_controller,
        }


class DisplayControllerAdminController(BaseEventAdminController):
    # Litestar declares `guards` on `Controller` as an instance variable, so
    # it cannot be narrowed to a class variable here.
    guards = [  # noqa: RUF012
        EventGuard(),
        ActionGuard(AuthAction.VIEW_PUBLIC_SCREENS),
        ManageScreenEntityGuard(RequestUtils.DISPLAY_CONTROLLER_ID_PARAM),
    ]

    @classmethod
    def _admin_validate_display_controller_update_data(
        cls,
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
                    used_names = list(event.display_controllers_by_name.keys())
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

        item_screen_ids: list[int] = []
        item_family_ids: list[int] = []
        item_rotator_ids: list[int] = []
        item_menu_ids: list[int] = []
        if action in ('create', 'update'):
            item_screen_ids, item_family_ids, item_rotator_ids, item_menu_ids = (
                cls._read_item_ids(data, errors, event)
            )

        display_controller_id: int | None = None
        screen_id: int | None = None
        rotator_id: int | None = None
        family_id: int | None = None
        family_page: int | None = None
        menu_id: int | None = None
        if action == 'update':
            display_controller = web_context.get_admin_display_controller()
            display_controller_id = display_controller.id
            screen_id = display_controller.screen_id
            rotator_id = display_controller.rotator_id
            family_id = display_controller.family_id
            family_page = display_controller.family_page
            menu_id = display_controller.menu_id

        return StoredDisplayController(
            id=display_controller_id,
            public=public,
            name=name,
            screen_id=screen_id,
            rotator_id=rotator_id,
            family_id=family_id,
            family_page=family_page,
            menu_id=menu_id,
            item_screen_ids=item_screen_ids,
            item_family_ids=item_family_ids,
            item_rotator_ids=item_rotator_ids,
            item_menu_ids=item_menu_ids,
            errors=errors,
        )

    @staticmethod
    def _read_item_ids(
        data: dict[str, str],
        errors: dict[str, str],
        event: Event,
    ) -> tuple[list[int], list[int], list[int], list[int]]:
        field = 'item_ids'
        screen_ids: list[int] = []
        family_ids: list[int] = []
        rotator_ids: list[int] = []
        menu_ids: list[int] = []
        for item_id in WebContext.form_data_to_list_str(data, field):
            kind, _separator, raw_id = item_id.partition(':')
            match kind:
                case 'screen' if raw_id.isdigit() and (
                    int(raw_id) in event.basic_screens_by_id
                ):
                    screen_ids.append(int(raw_id))
                case 'family' if raw_id.isdigit() and (
                    int(raw_id) in event.families_by_id
                ):
                    family_ids.append(int(raw_id))
                case 'rotator' if raw_id.isdigit() and (
                    int(raw_id) in event.rotators_by_id
                ):
                    rotator_ids.append(int(raw_id))
                case 'menu' if raw_id.isdigit() and (int(raw_id) in event.menus_by_id):
                    menu_ids.append(int(raw_id))
                case _:
                    errors[field] = _('Invalid value.')
        return (
            list(dict.fromkeys(screen_ids)),
            list(dict.fromkeys(family_ids)),
            list(dict.fromkeys(rotator_ids)),
            list(dict.fromkeys(menu_ids)),
        )

    @staticmethod
    def _item_options(event: Event) -> dict[str, dict[str, str]]:
        options: dict[str, dict[str, str]] = {}
        if screens := event.sorted_basic_screens:
            options[_('Single Screens')] = {
                f'screen:{screen.id}': screen.name for screen in screens
            }
        families = sorted(event.families_by_id.values(), key=attrgetter('display_name'))
        if families:
            options[_('Paged Screens')] = {
                f'family:{family.id}': family.display_name for family in families
            }
        if rotators := event.sorted_rotators:
            options[_('Rotators')] = {
                f'rotator:{rotator.id}': rotator.name for rotator in rotators
            }
        if menus := event.sorted_menus:
            options[_('Menus')] = {f'menu:{menu.id}': menu.name for menu in menus}
        return options

    @classmethod
    def _admin_event_display_controllers_render(
        cls,
        request: HTMXRequest,
        modal: str | None = None,
        action: str | None = None,
        display_controller_id: int | None = None,
        reload_event: bool = False,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template:
        web_context = DisplayControllerAdminWebContext(
            request,
            display_controller_id,
            reload_event=reload_event,
        )
        event = web_context.get_admin_event()

        admin_sorted_display_controllers: list[DisplayController]
        if web_context.client.can_view_private_screens:
            admin_sorted_display_controllers = (
                web_context.get_admin_event().sorted_display_controllers
            )
        elif web_context.client.can_view_public_screens:
            admin_sorted_display_controllers = (
                web_context.get_admin_event().sorted_public_display_controllers
            )
        else:
            admin_sorted_display_controllers = []

        template_context: dict[str, Any] = web_context.template_context | {
            'admin_event_tab': 'admin-event-display-controllers-tab',
            'admin_display_controllers': admin_sorted_display_controllers,
        }

        match modal:
            case None:
                pass
            case 'display_controller':
                if data is None:
                    name: str | None = None
                    public: bool | None = None
                    item_ids: list[str] = []
                    match action:
                        case 'update':
                            display_controller = (
                                web_context.get_admin_display_controller()
                            )
                            stored = display_controller.stored_display_controller
                            name = stored.name
                            item_ids = (
                                [
                                    f'screen:{screen_id}'
                                    for screen_id in stored.item_screen_ids
                                ]
                                + [
                                    f'family:{family_id}'
                                    for family_id in stored.item_family_ids
                                ]
                                + [
                                    f'rotator:{rotator_id}'
                                    for rotator_id in stored.item_rotator_ids
                                ]
                                + [
                                    f'menu:{menu_id}'
                                    for menu_id in stored.item_menu_ids
                                ]
                            )
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
                        'item_ids': WebContext.value_to_form_data(item_ids),
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
                    'item_options': cls._item_options(event),
                }
            case 'screens_map':
                template_context |= {
                    'modal': modal,
                    'screens_map_active': request.query_params.get('active', ''),
                }
            case 'display_controller_connect':
                path = request.url_for(
                    'user-display-controller',
                    event_uniq_id=event.uniq_id,
                    display_controller_id=web_context.get_admin_display_controller().id,
                )
                path = urlsplit(path).path
                template_context |= {
                    'modal': modal,
                    'connect_links': [
                        {
                            'url': f'{SharlyChessConfig().app_url(iface["ip"])}{path}',
                            'label': iface['label'],
                            'qrcode_ip': iface['ip'],
                            'qrcode_path': path,
                        }
                        for iface in SharlyChessConfig().lan_ifaces
                    ],
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
        return cls._admin_base_event_render(template_context)

    @staticmethod
    def _announce_display_controller_update(
        event_uniq_id: str, display_controller_id: int
    ) -> None:
        """Tells the device of the channel that what it shows has changed, the
        other screens having nothing to draw again."""
        mark_screens_change_announced(event_uniq_id)
        publish_ws_event(
            f'display-controller-updated|{event_uniq_id}|{display_controller_id}',
            event_uniq_id=event_uniq_id,
        )

    @get(
        path='/event/{event_uniq_id:str}/display_controllers',
        name='admin-event-display-controllers-tab',
    )
    async def htmx_admin_event_display_controllers_tab(
        self, request: HTMXRequest
    ) -> Template | Redirect:
        if not WebContext(request).client.can_manage_screens:
            return Redirect(
                request.app.route_reverse(
                    'admin-event-display-tab',
                    event_uniq_id=request.path_params['event_uniq_id'],
                )
                + ''
            )
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
        path='/screens-map-modal/{event_uniq_id:str}',
        name='admin-screens-map-modal',
        guards=[ActionGuard(AuthAction.MANAGE_SCREENS)],
    )
    async def htmx_admin_screens_map_modal(self, request: HTMXRequest) -> Template:
        return self._admin_event_display_controllers_render(
            request, modal='screens_map'
        )

    @get(
        path='/display-controller-connect-modal/{event_uniq_id:str}/{display_controller_id:int}',
        name='admin-display-controller-connect-modal',
    )
    async def htmx_admin_display_controller_connect_modal(
        self,
        request: HTMXRequest,
        display_controller_id: FromPath[int],
    ) -> Template:
        return self._admin_event_display_controllers_render(
            request,
            modal='display_controller_connect',
            display_controller_id=display_controller_id,
        )

    @get(
        path='/display-controller-modal/{action:str}/{event_uniq_id:str}/{display_controller_id:int}',
        name='admin-display-controller-modal',
    )
    async def htmx_admin_display_controller_modal(
        self,
        request: HTMXRequest,
        action: FromPath[str],
        display_controller_id: FromPath[int | None],
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
        item_ids = (
            stored_display_controller.item_screen_ids,
            stored_display_controller.item_family_ids,
            stored_display_controller.item_rotator_ids,
            stored_display_controller.item_menu_ids,
        )
        with EventDatabase(event.uniq_id, write=True) as event_database:
            match action:
                case 'create':
                    stored_display_controller = (
                        event_database.add_stored_display_controller(
                            stored_display_controller
                        )
                    )
                    assert stored_display_controller.id is not None
                    event_database.set_stored_display_controller_items(
                        stored_display_controller.id, *item_ids
                    )
                    Message.success(
                        request,
                        _('Channel [{display_controller}] has been created.').format(
                            display_controller=stored_display_controller.name
                        ),
                    )
                case 'update':
                    stored_display_controller = (
                        event_database.update_stored_display_controller(
                            stored_display_controller
                        )
                    )
                    assert stored_display_controller.id is not None
                    event_database.set_stored_display_controller_items(
                        stored_display_controller.id, *item_ids
                    )
                    Message.success(
                        request,
                        _('Channel [{display_controller}] has been updated.').format(
                            display_controller=stored_display_controller.name
                        ),
                    )
                case 'delete':
                    display_controller = web_context.get_admin_display_controller()
                    event_database.delete_stored_display_controller(
                        display_controller.id
                    )
                    Message.success(
                        request,
                        _('Channel [{display_controller}] has been deleted.').format(
                            display_controller=display_controller.name
                        ),
                    )
                case _:
                    raise ValueError(f'action=[{action}]')
        if action != 'create' and display_controller_id is not None:
            self._announce_display_controller_update(
                event.uniq_id, display_controller_id
            )

        return self._admin_event_display_controllers_render(request, reload_event=True)

    @post(
        path='/display-controller-create/{event_uniq_id:str}',
        name='admin-display-controller-create',
    )
    async def htmx_admin_display_controller_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        return self._admin_display_controller_update(
            request,
            action='create',
            display_controller_id=None,
            data=WebContext.flatten_list_data(data),
        )

    @patch(
        path='/display-controller-update/{event_uniq_id:str}/{display_controller_id:int}',
        name='admin-display-controller-update',
    )
    async def htmx_admin_display_controller_update(
        self,
        request: HTMXRequest,
        display_controller_id: FromPath[int | None],
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        return self._admin_display_controller_update(
            request,
            action='update',
            display_controller_id=display_controller_id,
            data=WebContext.flatten_list_data(data),
        )

    @delete(
        path='/display-controller-delete/{event_uniq_id:str}/{display_controller_id:int}',
        name='admin-display-controller-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_display_controller_delete(
        self,
        request: HTMXRequest,
        display_controller_id: FromPath[int | None],
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
        display_controller_id: FromPath[int | None],
        type: FromPath[str],
        object_uniq_id: FromPath[str],
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
                    'Screen [{screen_uniq_id}] has been sent to channel [{display_controller}].'
                ).format(
                    display_controller=web_context.admin_display_controller.name,
                    screen_uniq_id=screen.uniq_id,
                )
            case 'family':
                family: Family = web_context.admin_event.families_by_uniq_id[
                    object_uniq_id
                ]
                if not family.allowed_in_rotators:
                    raise ClientException(
                        f'Multi-screen [{family.uniq_id}] cannot be sent to a destination.'
                    )
                web_context.admin_display_controller.family_id = family.id
                message = _(
                    'Paged Screen [{family}] has been sent to channel [{display_controller}].'
                ).format(
                    display_controller=web_context.admin_display_controller.name,
                    family=family.display_name,
                )
            case 'family-page':
                page_screen: Screen | None = None
                for family in web_context.admin_event.families_by_id.values():
                    if page_screen := family.screens_by_uniq_id.get(object_uniq_id):
                        break
                if page_screen is None or page_screen.family_part is None:
                    raise NotFoundException(f'Page [{object_uniq_id}] not found.')
                web_context.admin_display_controller.show_family_page(
                    family.id, page_screen.family_part
                )
                message = _(
                    'Page {page} of [{family}] has been sent to channel [{display_controller}].'
                ).format(
                    display_controller=web_context.admin_display_controller.name,
                    family=family.display_name,
                    page=page_screen.family_part,
                )
            case 'menu':
                menu = web_context.admin_event.menus_by_id[int(object_uniq_id)]
                web_context.admin_display_controller.menu_id = menu.id
                message = _(
                    'Menu [{menu}] has been sent to channel [{display_controller}].'
                ).format(
                    display_controller=web_context.admin_display_controller.name,
                    menu=menu.name,
                )
            case 'rotator':
                rotator: Rotator = web_context.admin_event.rotators_by_name[
                    object_uniq_id
                ]
                web_context.admin_display_controller.rotator_id = rotator.id
                message = _(
                    'Rotator [{rotator}] has been sent to channel [{display_controller}].'
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
        self._announce_display_controller_update(
            web_context.admin_event.uniq_id, web_context.admin_display_controller.id
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
        display_controller_id: FromPath[int | None],
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
        self._announce_display_controller_update(
            web_context.admin_event.uniq_id, web_context.admin_display_controller.id
        )

        return self._admin_event_display_controllers_render(request, reload_event=True)
