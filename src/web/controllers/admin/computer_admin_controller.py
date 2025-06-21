import re
from typing import Annotated, Any

from litestar import post, get, delete, patch
from litestar.plugins.htmx import HTMXRequest, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from data.auth.entities import Computer
from data.auth.roles import Role
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredComputer
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.messages import Message


class ComputerAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        computer_id: int | None,
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
        assert self.admin_event is not None
        self.admin_computer: Computer | None = None
        if self.error:
            return
        if computer_id:
            try:
                self.admin_computer = self.admin_event.computers_by_id[computer_id]
            except KeyError:
                self._redirect_error(f'Computer [{computer_id}] not found.')
                return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_computer': self.admin_computer,
            'roles': Role.roles(),
        }


class ComputerAdminController(BaseEventAdminController):
    @staticmethod
    def _admin_validate_computer_update_data(
        action: str,
        web_context: ComputerAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> StoredComputer:
        assert web_context.admin_event is not None
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        computer_id: int | None = None
        ip: str | None = None
        edit_properties: bool = True
        edit_permissions: bool = True
        active: bool = False
        permissions: dict[int, str | None] = {}
        if web_context.admin_computer and action in [
            'update',
            'delete',
        ]:
            computer_id = web_context.admin_computer.id
            edit_properties = web_context.admin_computer.edit_properties
            edit_permissions = web_context.admin_computer.edit_permissions
        if action in [
            'delete',
        ]:
            pass
        else:
            if web_context.admin_computer and (
                web_context.admin_computer.unknown
                or web_context.admin_computer.localhost
            ):
                ip = web_context.admin_computer.ip
                active = web_context.admin_computer.active
            else:
                ip = WebContext.form_data_to_str(data, field := 'ip')
                if not ip:
                    errors[field] = _('Please enter the IP address.')
                elif matches := re.match(
                    r'^(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|0?[1-9][0-9]|0?0?[1-9])\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|0?[1-9][0-9]|0?0?[1-9])\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|0?[1-9][0-9]|0?0?[1-9])\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|0?[1-9][0-9]|0?0?[1-9])$',
                    ip,
                ):
                    ip = f'{int(matches.group(1))}.{int(matches.group(2))}.{int(matches.group(3))}.{int(matches.group(4))}'
                    data[field] = ip
                    match action:
                        case 'create' | 'clone':
                            if ip in web_context.admin_event.computers_by_ip:
                                errors[field] = _(
                                    'Computer [{ip}] already set.'
                                ).format(ip=ip)
                        case 'update':
                            assert web_context.admin_computer is not None
                            if (
                                ip != web_context.admin_computer.ip
                                and ip in web_context.admin_event.computers_by_ip
                            ):
                                errors[field] = _(
                                    'Computer [{ip}] already set.'
                                ).format(ip=ip)
                        case _:
                            raise ValueError(f'action=[{action}]')
                else:
                    errors[field] = _('The IP address [{ip}] is not valid.').format(
                        ip=ip
                    )
                active = WebContext.form_data_to_bool(data, 'active')
            for role_id in Role.values():
                if WebContext.form_data_to_bool(data, f'role_{role_id}'):
                    permissions[role_id] = WebContext.form_data_to_str(
                        data, f'permission_{role_id}'
                    )
        return StoredComputer(
            id=computer_id,
            edit_properties=edit_properties,
            edit_permissions=edit_permissions,
            active=active,
            ip=ip,
            permissions=permissions,
            errors=errors,
        )

    @classmethod
    def _admin_event_computers_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        modal: str | None = None,
        action: str | None = None,
        computer_id: int | None = None,
        data: dict[str, str] | None = None,  # type: ignore
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: ComputerAdminWebContext = ComputerAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            computer_id=computer_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        client_can_manage_computers: dict[int, bool] = {
            computer.id: web_context.client.can_manage_computer(computer)
            for computer in web_context.admin_event.computers_by_id.values()
        }
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context,
        ) | {
            'admin_event_tab': 'admin-event-computers-tab',
            'client_can_manage_computers': client_can_manage_computers,
        }

        match modal:
            case None:
                pass
            case 'computer':
                if data is None:
                    ip: str | None = None
                    active: bool | None = None
                    match action:
                        case 'update':
                            assert web_context.admin_computer is not None
                            ip = web_context.admin_computer.stored_computer.ip
                        case 'create' | 'clone' | 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update' | 'clone':
                            assert web_context.admin_computer is not None
                            active = web_context.admin_computer.stored_computer.active
                        case 'create':
                            active = True
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    data = (
                        {
                            'ip': WebContext.value_to_form_data(ip),
                            'active': WebContext.value_to_form_data(active),
                        }
                        | {
                            f'role_{role_value}': WebContext.value_to_form_data(False)
                            for role_value in Role.values()
                        }
                        | {
                            f'permission_{role_value}': WebContext.value_to_form_data(
                                None
                            )
                            for role_value in Role.values()
                        }
                    )
                    match action:
                        case 'update' | 'clone':
                            assert web_context.admin_computer is not None
                            for (
                                role,
                                permission,
                            ) in web_context.admin_computer.permissions_by_role.items():
                                data[f'role_{role.value}'] = (
                                    WebContext.value_to_form_data(True)
                                )
                                data[f'permission_{role.value}'] = (
                                    WebContext.value_to_form_data(permission)
                                )
                        case 'create' | 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    stored_computer: StoredComputer = (
                        cls._admin_validate_computer_update_data(
                            action, web_context, data
                        )
                    )
                    errors = stored_computer.errors
                if errors is None:
                    errors = {}
                template_context |= {
                    'previous_computer': (
                        web_context.admin_computer if action == 'create' else None
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
        path='/admin/event/{event_uniq_id:str}/computers',
        name='admin-event-computers-tab',
        cache=1,
    )
    async def htmx_admin_event_computers_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_computers_render(
            request,
            event_uniq_id=event_uniq_id,
        )

    @get(
        path='/admin/computer-modal/create/{event_uniq_id:str}',
        name='admin-computer-create-modal',
        cache=1,
    )
    async def htmx_admin_computer_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_computers_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='computer',
            action='create',
            computer_id=None,
        )

    @get(
        path='/admin/computer-modal/{action:str}/{event_uniq_id:str}/{computer_id:int}',
        name='admin-computer-modal',
        cache=1,
    )
    async def htmx_admin_computer_modal(
        self,
        request: HTMXRequest,
        action: str,
        event_uniq_id: str,
        computer_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_computers_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='computer',
            action=action,
            computer_id=computer_id,
        )

    def _admin_computer_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        action: str,
        event_uniq_id: str,
        computer_id: int | None,
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'delete' | 'create':
                web_context: ComputerAdminWebContext = ComputerAdminWebContext(
                    request,
                    event_uniq_id=event_uniq_id,
                    computer_id=computer_id,
                    data=data,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        stored_computer: StoredComputer = self._admin_validate_computer_update_data(
            action, web_context, data
        )
        if stored_computer.errors:
            return self._admin_event_computers_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='computer',
                action=action,
                computer_id=computer_id,
                data=data,
                errors=stored_computer.errors,
            )
        event_loader: EventLoader = EventLoader.get(request=request)
        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            match action:
                case 'create':
                    stored_computer = event_database.add_stored_computer(
                        stored_computer
                    )
                    event_database.commit()
                    Message.success(
                        request,
                        _('Computer [{ip}] has been created.').format(
                            ip=stored_computer.ip
                        ),
                    )
                case 'update':
                    if (
                        web_context.admin_computer is None
                        or web_context.admin_computer.localhost
                    ):
                        raise RuntimeError(
                            f'{web_context.admin_computer=} for [{action=}]'
                        )
                    stored_computer = event_database.update_stored_computer(
                        stored_computer
                    )
                    event_database.commit()
                    Message.success(
                        request,
                        _("Unknown computers' access has been updated.")
                        if web_context.admin_computer.unknown
                        else _('Computer [{ip}] has been updated.').format(
                            ip=stored_computer.ip
                        ),
                    )
                case 'delete':
                    if (
                        web_context.admin_computer is None
                        or web_context.admin_computer.localhost
                        or web_context.admin_computer.unknown
                    ):
                        raise RuntimeError(
                            f'{web_context.admin_computer=} for [{action=}]'
                        )
                    event_database.delete_stored_computer(web_context.admin_computer.id)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Computer [{ip}] has been deleted.').format(
                            ip=web_context.admin_computer.ip
                        ),
                    )
                case _:
                    raise ValueError(f'action=[{action}]')
        event_loader.clear_cache(event_uniq_id)
        return self._admin_event_computers_render(request, event_uniq_id=event_uniq_id)

    @post(
        path='/admin/computer-create/{event_uniq_id:str}', name='admin-computer-create'
    )
    async def htmx_admin_computer_create(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_computer_update(
            request,
            event_uniq_id=event_uniq_id,
            action='create',
            computer_id=None,
            data=data,
        )

    @patch(
        path='/admin/computer-update/{event_uniq_id:str}/{computer_id:int}',
        name='admin-computer-update',
    )
    async def htmx_admin_computer_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        computer_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_computer_update(
            request,
            event_uniq_id=event_uniq_id,
            action='update',
            computer_id=computer_id,
            data=data,
        )

    @delete(
        path='/admin/computer-delete/{event_uniq_id:str}/{computer_id:int}',
        name='admin-computer-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_computer_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        computer_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_computer_update(
            request,
            event_uniq_id=event_uniq_id,
            action='delete',
            computer_id=computer_id,
            data=data,
        )
