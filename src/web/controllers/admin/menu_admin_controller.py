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
from data.menu import Menu
from database.sqlite.event.event_store import StoredMenu
from utils.enum import FormAction, ScreenType
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard, ManageScreenEntityGuard
from web.messages import Message
from web.session import SessionMenusShowDetails
from web.utils import RequestUtils, SelectOption


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
        if self.client.can_view_public_screens:
            admin_menus = event.sorted_menus
        return super().template_context | {
            'admin_event_tab': 'admin-event-menus-tab',
            'show_details': SessionMenusShowDetails(self.request).get(),
            'admin_menus': admin_menus,
            'admin_menu': self.admin_menu,
        }


class MenuAdminController(BaseEventAdminController):
    guards = [
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
        return WebContext.values_dict_to_form_data({'name': menu.name})

    @get(
        path='/event/{event_uniq_id:str}/menus',
        name='admin-event-menus-tab',
    )
    async def htmx_admin_event_menus_tab(
        self,
        request: HTMXRequest,
        show_details: bool | None,
    ) -> Template:
        if show_details is not None:
            SessionMenusShowDetails(request).set(show_details)
        return self._admin_event_menu_render(MenuAdminWebContext(request))

    # -------------------------------------------------------------------------
    # Modals
    # -------------------------------------------------------------------------

    @classmethod
    def _menu_form_modal_context(
        cls,
        action: FormAction,
        data: dict[str, str],
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        default_data = WebContext.values_dict_to_form_data({'name': ''})
        return {
            'modal': 'menu',
            'action': action,
            'data': default_data | data,
            'errors': errors or {},
        }

    @classmethod
    def _menu_items_modal_context(
        cls,
        web_context: MenuAdminWebContext,
        success_message: str | None = None,
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        return {
            'modal': 'menu_items',
            'screen_options': cls._screen_options(event),
            'family_options': cls._family_options(event),
            'screen_type_options': cls._screen_type_options(event),
            'success_message': success_message,
        }

    # A screen, family or screen type may only belong to a single menu, so an
    # entity already claimed by any menu is offered greyed-out with a reason.
    @staticmethod
    def _screen_options(event: Any) -> dict[str, dict[str, Any]]:
        claimed_ids = event.menu_claimed_screen_ids
        claimed_types = event.menu_claimed_screen_types
        options: dict[str, dict[str, Any]] = {}
        for screen_type, screens in event.sorted_basic_screens_by_screen_type.items():
            group: dict[str, Any] = {}
            for screen in sorted(screens, key=attrgetter('name')):
                if screen.type in claimed_types:
                    group[str(screen.id)] = SelectOption(
                        name=screen.name,
                        disabled=True,
                        tooltip=_(
                            'All %(screen_type)s screens already belong to a menu.'
                        )
                        % {'screen_type': screen_type.name},
                    )
                elif screen.id in claimed_ids:
                    group[str(screen.id)] = SelectOption(
                        name=screen.name,
                        disabled=True,
                        tooltip=_('This screen already belongs to a menu.'),
                    )
                else:
                    group[str(screen.id)] = screen.name
            if group:
                options[screen_type.name] = group
        return options

    @staticmethod
    def _family_options(event: Any) -> dict[str, dict[str, Any]]:
        claimed_family_ids = event.menu_claimed_family_ids
        claimed_types = event.menu_claimed_screen_types
        options: dict[str, dict[str, Any]] = {}
        for screen_type, families in event.families_by_screen_type.items():
            group: dict[str, Any] = {}
            for family in sorted(families, key=attrgetter('name')):
                if family.type in claimed_types:
                    group[str(family.id)] = SelectOption(
                        name=family.name,
                        disabled=True,
                        tooltip=_(
                            'All %(screen_type)s screens already belong to a menu.'
                        )
                        % {'screen_type': screen_type.name},
                    )
                elif family.id in claimed_family_ids:
                    group[str(family.id)] = SelectOption(
                        name=family.name,
                        disabled=True,
                        tooltip=_('This family already belongs to a menu.'),
                    )
                else:
                    group[str(family.id)] = family.name
            if group:
                options[screen_type.name] = group
        return options

    @staticmethod
    def _screen_type_options(event: Any) -> dict[str, dict[str, Any]]:
        claimed_types = event.menu_claimed_screen_types
        claimed_ids = event.menu_claimed_screen_ids
        claimed_family_ids = event.menu_claimed_family_ids
        options: dict[str, Any] = {}
        for screen_type in ScreenType:
            label = _('All %(screen_type)s screens') % {'screen_type': screen_type.name}
            if screen_type in claimed_types:
                options[screen_type.value] = SelectOption(
                    name=label,
                    disabled=True,
                    tooltip=_('This screen type already belongs to a menu.'),
                )
            elif any(
                screen.id in claimed_ids
                for screen in event.sorted_basic_screens_by_screen_type[screen_type]
            ) or any(
                family.id in claimed_family_ids
                for family in event.families_by_screen_type[screen_type]
            ):
                options[screen_type.value] = SelectOption(
                    name=label,
                    disabled=True,
                    tooltip=_('Some screens of this type already belong to a menu.'),
                )
            else:
                options[screen_type.value] = label
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
            FormAction.CREATE, {'name': name}
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
        template_context = self._menu_form_modal_context(FormAction.UPDATE, data)
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
        template_context = self._menu_form_modal_context(FormAction.CLONE, data)
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
        name = WebContext.form_data_to_str(data, field := 'name') or ''
        if not name:
            errors[field] = _('This field is required.')
        else:
            used_names = list(event.menus_by_name.keys())
            if action == FormAction.UPDATE:
                used_names.remove(web_context.get_admin_menu().name)
            if name in used_names:
                errors[field] = _('This name is already used.')
        if errors:
            return None, errors
        stored_menu = StoredMenu(id=None, name=name)
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
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = MenuAdminWebContext(request)
        stored_menu, errors = self._read_menu_form_data(
            data, web_context, FormAction.CREATE
        )
        if not stored_menu:
            return self._admin_event_menu_render(
                web_context,
                self._menu_form_modal_context(FormAction.CREATE, data, errors),
            )
        event = web_context.get_admin_event()
        web_context.admin_menu = event.create_menu(stored_menu)
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
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = MenuAdminWebContext(request)
        stored_menu, errors = self._read_menu_form_data(
            data, web_context, FormAction.CLONE
        )
        if not stored_menu:
            return self._admin_event_menu_render(
                web_context,
                self._menu_form_modal_context(FormAction.CLONE, data, errors),
            )
        event = web_context.get_admin_event()
        cloned_menu = web_context.get_admin_menu()
        stored_menu.stored_menu_items = copy(cloned_menu.stored_menu_items)
        event.create_menu(stored_menu)
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
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = MenuAdminWebContext(request)
        stored_menu, errors = self._read_menu_form_data(
            data, web_context, FormAction.UPDATE
        )
        if not stored_menu:
            return self._admin_event_menu_render(
                web_context,
                self._menu_form_modal_context(FormAction.UPDATE, data, errors),
            )
        event = web_context.get_admin_event()
        menu = web_context.get_admin_menu()
        stored_menu.id = menu.id
        stored_menu.default_type = menu.stored_menu.default_type
        stored_menu.stored_menu_items = menu.stored_menu_items
        # Keep a seeded default's name NULL (so it stays translatable) unless
        # the admin actually changed it away from the derived label.
        if menu.stored_menu.name is None and stored_menu.name == menu.name:
            stored_menu.name = None
        event.update_menu(stored_menu)
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
        menu_item_id: int,
    ) -> Template:
        web_context = MenuAdminWebContext(request)
        menu = web_context.get_admin_menu()
        try:
            menu.delete_menu_item(menu_item_id)
        except ValueError as error:
            raise ClientException(error)
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
        # Re-render the whole modal so it returns to the add buttons and the
        # freshly-claimed entities become greyed-out in the select lists.
        return self._admin_event_menu_render(
            web_context, self._menu_items_modal_context(web_context)
        )

    @post(
        path='/menu-items/create-screen/{event_uniq_id:str}/{menu_id:int}',
        name='admin-menu-items-create-screen',
    )
    async def htmx_admin_menu_items_create_screen(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        screen_id = WebContext.form_data_to_int(data, 'screen_id') or 0
        return self._create_menu_item(request, screen_id=screen_id)

    @post(
        path='/menu-items/create-family/{event_uniq_id:str}/{menu_id:int}',
        name='admin-menu-items-create-family',
    )
    async def htmx_admin_menu_items_create_family(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        family_id = WebContext.form_data_to_int(data, 'family_id') or 0
        return self._create_menu_item(request, family_id=family_id)

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
        return self._create_menu_item(request, screen_type=ScreenType(raw))
