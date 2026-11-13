from copy import copy
from operator import itemgetter
from typing import Annotated, Any

from litestar import post, get, delete, patch
from litestar.exceptions import ClientException
from litestar.plugins.htmx import HTMXRequest
from litestar.enums import RequestEncodingType
from litestar.params import Body, FromPath, FromQuery
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from data.access_levels.actions import AuthAction
from data.screens.family import Family
from data.screens.menu import Menu
from data.screens.manager import ScreenTypeManager
from database.sqlite.event.event_store import StoredMenu
from utils.enum import FormAction, MenuSubmenuMode
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard, ManageScreenEntityGuard
from web.messages import Message
from web.session import SessionMenusShowDetails
from web.utils import RequestUtils, SelectOption, paged_screen_option


class MenuAdminWebContext(BaseEventAdminWebContext):
    def __init__(self, request: HTMXRequest):
        super().__init__(request)
        self.admin_menu = RequestUtils.get_optional_menu(request)

    def get_admin_menu(self) -> Menu:
        assert self.admin_menu is not None
        return self.admin_menu

    @property
    def template_context(self) -> dict[str, Any]:
        event = self.get_admin_event()
        admin_menus: list[Menu] = []
        if self.client.can_manage_screens:
            admin_menus = event.sorted_menus
        elif self.client.can_view_public_screens:
            admin_menus = event.menus_for(self.client.can_view_private_screens)
        return super().template_context | {
            'admin_event_tab': 'admin-event-menus-tab',
            'show_details': SessionMenusShowDetails(self.request).get(),
            'admin_menus': admin_menus,
            'admin_menu': self.admin_menu,
        }


class MenuAdminController(BaseEventAdminController):
    # Litestar declares `guards` on `Controller` as an instance variable, so
    # it cannot be narrowed to a class variable here.
    guards = [  # noqa: RUF012
        EventGuard(),
        ActionGuard(AuthAction.VIEW_PUBLIC_SCREENS),
        ManageScreenEntityGuard(RequestUtils.MENU_ID_PARAM),
    ]

    @classmethod
    def _admin_event_menu_render(
        cls,
        web_context: MenuAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template:
        return cls._admin_base_event_render(
            web_context.template_context | (template_context or {})
        )

    @staticmethod
    def _menu_form_data_from_menu(menu: Menu) -> dict[str, str]:
        # The raw stored name (empty for an automatically-named menu) so the
        # field shows blank with the "Automatic" placeholder.
        return WebContext.values_dict_to_form_data(
            {
                'name': menu.stored_menu.name or '',
                'submenu_mode': menu.stored_menu.submenu_mode,
                'display_controller_ids': [
                    display_controller.id
                    for display_controller in menu.display_controllers
                ],
            }
        )

    @get(
        path='/event/{event_uniq_id:str}/menus',
        name='admin-event-menus-tab',
    )
    async def htmx_admin_event_menus_tab(
        self,
        request: HTMXRequest,
        show_details: FromQuery[bool | None],
    ) -> Template | Redirect:
        if not WebContext(request).client.can_manage_screens:
            return Redirect(
                request.app.route_reverse(
                    'admin-event-display-tab',
                    event_uniq_id=request.path_params['event_uniq_id'],
                )
                + '?browse=true&kind=menus'
            )
        if show_details is not None:
            SessionMenusShowDetails(request).set(show_details)
        return self._admin_event_menu_render(MenuAdminWebContext(request))

    # -------------------------------------------------------------------------
    # Modals
    # -------------------------------------------------------------------------

    @classmethod
    def _menu_form_modal_context(
        cls,
        web_context: MenuAdminWebContext,
        action: FormAction,
        data: dict[str, str],
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        default_data = WebContext.values_dict_to_form_data(
            {'name': '', 'submenu_mode': MenuSubmenuMode.AUTOMATIC.value}
        )
        return {
            'modal': 'menu',
            'action': action,
            'data': default_data | data,
            'errors': errors or {},
            'submenu_mode_options': {
                mode.value: SelectOption(mode.name, tooltip=mode.tooltip)
                for mode in MenuSubmenuMode
            },
            **cls._display_controller_destination_context(
                web_context.get_admin_event()
            ),
        }

    @classmethod
    def _menu_items_modal_context(
        cls,
        web_context: MenuAdminWebContext,
        success_message: str | None = None,
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        menu = web_context.get_admin_menu()
        return {
            'modal': 'menu_items',
            'screen_options': cls._screen_options(event, menu),
            'screen_type_options': cls._screen_type_options(event, menu),
            'success_message': success_message,
        }

    @staticmethod
    def _screen_options(event: Any, menu: Menu) -> dict[str, dict[str, Any]]:
        """The screens and paged screens by screen type, what the menu already
        holds greyed out with the reason."""
        own_ids = {f'screen:{screen.id}' for screen in menu.screens} | {
            f'family:{family.id}' for family in menu.families
        }
        options: dict[str, dict[str, Any]] = {}
        for screen_type in ScreenTypeManager(event).objects():
            group: dict[str, Any] = {}
            entities: list[tuple[str, str, Family | None]] = [
                (screen.name, f'screen:{screen.id}', None)
                for screen in event.sorted_basic_screens_by_screen_type.get(
                    screen_type.id, []
                )
            ] + [
                (family.display_name, f'family:{family.id}', family)
                for family in event.families_by_screen_type.get(screen_type.id, [])
            ]
            for name, item_id, family in sorted(entities, key=itemgetter(0)):
                tooltip: str | None = None
                if screen_type.id in menu.screen_types:
                    tooltip = _(
                        'All "%(screen_type)s" screens already belong to this menu.'
                    ) % {'screen_type': screen_type.name}
                elif item_id in own_ids:
                    tooltip = _('This screen already belongs to this menu.')
                if family is not None:
                    group[item_id] = paged_screen_option(
                        family, disabled=tooltip is not None, tooltip=tooltip
                    )
                elif tooltip is not None:
                    group[item_id] = SelectOption(
                        name=name, disabled=True, tooltip=tooltip
                    )
                else:
                    group[item_id] = name
            if group:
                options[screen_type.name] = group
        return options

    @staticmethod
    def _screen_type_options(event: Any, menu: Menu) -> dict[str, dict[str, Any]]:
        options: dict[str, Any] = {}
        for screen_type in ScreenTypeManager(event).objects():
            label = _('All "%(screen_type)s" screens') % {
                'screen_type': screen_type.name
            }
            if screen_type.id in menu.screen_types:
                options[screen_type.id] = SelectOption(
                    name=label,
                    disabled=True,
                    tooltip=_('This screen type already belongs to this menu.'),
                )
            else:
                options[screen_type.id] = label
        return {_('Screen types'): options}

    @get(
        path='/menu-modal/create/{event_uniq_id:str}',
        name='admin-menu-create-modal',
    )
    async def htmx_admin_menu_create_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = MenuAdminWebContext(request)
        name = web_context.get_admin_event().get_unused_menu_name()
        template_context = self._menu_form_modal_context(
            web_context, FormAction.CREATE, {'name': name}
        )
        return self._admin_event_menu_render(web_context, template_context)

    @get(
        path='/menu-modal/update/{event_uniq_id:str}/{menu_id:int}',
        name='admin-menu-update-modal',
    )
    async def htmx_admin_menu_update_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = MenuAdminWebContext(request)
        menu = web_context.get_admin_menu()
        data = self._menu_form_data_from_menu(menu)
        template_context = self._menu_form_modal_context(
            web_context, FormAction.UPDATE, data
        )
        return self._admin_event_menu_render(web_context, template_context)

    @get(
        path='/menu-modal/clone/{event_uniq_id:str}/{menu_id:int}',
        name='admin-menu-clone-modal',
    )
    async def htmx_admin_menu_clone_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = MenuAdminWebContext(request)
        event = web_context.get_admin_event()
        menu = web_context.get_admin_menu()
        data = self._menu_form_data_from_menu(menu)
        data |= {'name': event.get_unused_menu_name(menu.name)}
        template_context = self._menu_form_modal_context(
            web_context, FormAction.CLONE, data
        )
        return self._admin_event_menu_render(web_context, template_context)

    @get(
        path='/menu-modal/delete/{event_uniq_id:str}/{menu_id:int}',
        name='admin-menu-delete-modal',
    )
    async def htmx_admin_menu_delete_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        return self._admin_event_menu_render(
            MenuAdminWebContext(request),
            {'modal': 'menu_delete'},
        )

    @get(
        path='/menu-items-modal/{event_uniq_id:str}/{menu_id:int}',
        name='admin-menu-items-modal',
    )
    async def htmx_admin_menu_items_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = MenuAdminWebContext(request)
        return self._admin_event_menu_render(
            web_context, self._menu_items_modal_context(web_context)
        )

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    @staticmethod
    def _read_menu_form_data(
        data: dict[str, str],
        web_context: MenuAdminWebContext,
        action: FormAction,
    ) -> tuple[StoredMenu | None, dict[str, str]]:
        event = web_context.get_admin_event()
        errors: dict[str, str] = {}
        # The name is optional: an empty name means the menu is named
        # automatically from its content.
        name = WebContext.form_data_to_str(data, field := 'name') or ''
        if name:
            used_names = list(event.menus_by_name.keys())
            if action == FormAction.UPDATE:
                used_names.remove(web_context.get_admin_menu().name)
            if name in used_names:
                errors[field] = _('This name is already used.')
        BaseEventAdminController._read_display_controller_ids(data, errors, event)
        raw_mode = WebContext.form_data_to_str(data, 'submenu_mode') or ''
        try:
            submenu_mode = MenuSubmenuMode(raw_mode)
        except ValueError:
            submenu_mode = MenuSubmenuMode.AUTOMATIC
        if errors:
            return None, errors
        stored_menu = StoredMenu(
            id=None, name=name or None, submenu_mode=submenu_mode.value
        )
        return stored_menu, errors

    @post(
        path='/menu-create/{event_uniq_id:str}',
        name='admin-menu-create',
        guards=[ActionGuard(AuthAction.MANAGE_SCREENS)],
    )
    async def htmx_admin_menu_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        form_data = WebContext.flatten_list_data(data)
        web_context = MenuAdminWebContext(request)
        stored_menu, errors = self._read_menu_form_data(
            form_data, web_context, FormAction.CREATE
        )
        if not stored_menu:
            return self._admin_event_menu_render(
                web_context,
                self._menu_form_modal_context(
                    web_context, FormAction.CREATE, form_data, errors
                ),
            )
        event = web_context.get_admin_event()
        web_context.admin_menu = event.create_menu(stored_menu)
        event.set_menu_display_controllers(
            web_context.admin_menu.id,
            self._read_display_controller_ids(form_data, errors, event),
        )
        template_context = self._menu_items_modal_context(
            web_context,
            _('Menu [{menu}] has been created.').format(menu=stored_menu.name),
        )
        return self._admin_event_menu_render(web_context, template_context)

    @post(
        path='/menu-clone/{event_uniq_id:str}/{menu_id:int}',
        name='admin-menu-clone',
    )
    async def htmx_admin_menu_clone(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        form_data = WebContext.flatten_list_data(data)
        web_context = MenuAdminWebContext(request)
        stored_menu, errors = self._read_menu_form_data(
            form_data, web_context, FormAction.CLONE
        )
        if not stored_menu:
            return self._admin_event_menu_render(
                web_context,
                self._menu_form_modal_context(
                    web_context, FormAction.CLONE, form_data, errors
                ),
            )
        event = web_context.get_admin_event()
        cloned_menu = web_context.get_admin_menu()
        stored_menu.stored_menu_items = copy(cloned_menu.stored_menu_items)
        new_menu = event.create_menu(stored_menu)
        event.set_menu_display_controllers(
            new_menu.id,
            self._read_display_controller_ids(form_data, errors, event),
        )
        Message.success(
            request,
            _('Menu [{menu}] has been created.').format(menu=stored_menu.name),
        )
        return self._admin_event_menu_render(web_context)

    @patch(
        path='/menu-update/{event_uniq_id:str}/{menu_id:int}',
        name='admin-menu-update',
    )
    async def htmx_admin_menu_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        form_data = WebContext.flatten_list_data(data)
        web_context = MenuAdminWebContext(request)
        stored_menu, errors = self._read_menu_form_data(
            form_data, web_context, FormAction.UPDATE
        )
        if not stored_menu:
            return self._admin_event_menu_render(
                web_context,
                self._menu_form_modal_context(
                    web_context, FormAction.UPDATE, form_data, errors
                ),
            )
        event = web_context.get_admin_event()
        menu = web_context.get_admin_menu()
        stored_menu.id = menu.id
        stored_menu.default_type = menu.stored_menu.default_type
        stored_menu.stored_menu_items = menu.stored_menu_items
        event.update_menu(stored_menu)
        event.set_menu_display_controllers(
            menu.id,
            self._read_display_controller_ids(form_data, errors, event),
        )
        menu.stored_menu = stored_menu
        Message.success(
            request,
            _('Menu [{menu}] has been updated.').format(menu=stored_menu.name),
        )
        return self._admin_event_menu_render(web_context)

    @delete(
        path='/menu-delete/{event_uniq_id:str}/{menu_id:int}',
        name='admin-menu-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_menu_delete(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = MenuAdminWebContext(request)
        event = web_context.get_admin_event()
        menu = web_context.get_admin_menu()
        event.delete_menu(menu)
        Message.success(
            request,
            _('Menu [{menu}] has been deleted.').format(menu=menu.name),
        )
        return self._admin_event_menu_render(web_context)

    @delete(
        path=('/menu-item-delete/{event_uniq_id:str}/{menu_id:int}/{menu_item_id:int}'),
        name='admin-menu-item-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_menu_item_delete(
        self,
        request: HTMXRequest,
        menu_item_id: FromPath[int],
    ) -> Template:
        web_context = MenuAdminWebContext(request)
        menu = web_context.get_admin_menu()
        try:
            menu.delete_menu_item(menu_item_id)
        except ValueError as error:
            raise ClientException(error) from error
        return self._admin_event_menu_render(
            web_context, self._menu_items_modal_context(web_context)
        )

    @patch(
        path='/menu-reorder-items/{event_uniq_id:str}/{menu_id:int}',
        name='admin-menu-reorder-items',
    )
    async def htmx_admin_menu_reorder_items(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = MenuAdminWebContext(request)
        menu = web_context.get_admin_menu()
        menu.reorder_menu_items(data.get('menu_item_ids', []))
        return self._admin_event_menu_render(
            web_context, self._menu_items_modal_context(web_context)
        )

    def _create_menu_item(self, request: HTMXRequest, **kwargs: Any) -> Template:
        web_context = MenuAdminWebContext(request)
        menu = web_context.get_admin_menu()
        menu.add_menu_item(**kwargs)
        # Re-render the whole modal so it returns to the add buttons and what
        # was just added becomes greyed-out in the select lists.
        return self._admin_event_menu_render(
            web_context, self._menu_items_modal_context(web_context)
        )

    @post(
        path='/menu-items/create/{event_uniq_id:str}/{menu_id:int}',
        name='admin-menu-items-create',
    )
    async def htmx_admin_menu_items_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        event = RequestUtils.get_event(request)
        item_id = WebContext.form_data_to_str(data, 'item_id') or ''
        kind, _separator, raw_id = item_id.partition(':')
        object_id = int(raw_id) if raw_id.isdigit() else 0
        match kind:
            case 'screen' if object_id in event.basic_screens_by_id:
                return self._create_menu_item(request, screen_id=object_id)
            case 'family' if object_id in event.families_by_id:
                return self._create_menu_item(request, family_id=object_id)
        raise ClientException(f'[{item_id}] cannot be added to a menu.')

    @post(
        path='/menu-items/create-screen-type/{event_uniq_id:str}/{menu_id:int}',
        name='admin-menu-items-create-screen-type',
    )
    async def htmx_admin_menu_items_create_screen_type(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        raw = WebContext.form_data_to_str(data, 'screen_type')
        if not raw:
            raise ClientException('Missing screen type.')
        return self._create_menu_item(request, screen_type=raw)
