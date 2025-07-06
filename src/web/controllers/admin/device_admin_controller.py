import re
from typing import Annotated, Any

from litestar import post, get, delete, patch
from litestar.plugins.htmx import HTMXRequest, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from data.auth.entities import Device
from data.auth.roles import Role
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredDevice
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.messages import Message


class DeviceAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        device_id: int | None,
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
        self.admin_device: Device | None = None
        if self.error:
            return
        if device_id:
            try:
                self.admin_device = self.admin_event.devices_by_id[device_id]
            except KeyError:
                self._redirect_error(f'Device [{device_id}] not found.')
                return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_device': self.admin_device,
            'roles': Role.roles(),
        }


class DeviceAdminController(BaseEventAdminController):
    @staticmethod
    def _admin_validate_device_update_data(
        action: str,
        web_context: DeviceAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> StoredDevice:
        assert web_context.admin_event is not None
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        device_id: int | None = None
        ip: str | None = None
        edit_properties: bool = True
        edit_permissions: bool = True
        active: bool = False
        permissions: dict[int, str | None] = {}
        if web_context.admin_device and action in [
            'update',
            'delete',
        ]:
            device_id = web_context.admin_device.id
            edit_properties = web_context.admin_device.edit_properties
            edit_permissions = web_context.admin_device.edit_permissions
        if action in [
            'delete',
        ]:
            pass
        else:
            if web_context.admin_device and (
                web_context.admin_device.unknown or web_context.admin_device.localhost
            ):
                ip = web_context.admin_device.ip
                active = web_context.admin_device.active
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
                            if ip in web_context.admin_event.devices_by_ip:
                                errors[field] = _('Device [{ip}] already set.').format(
                                    ip=ip
                                )
                        case 'update':
                            assert web_context.admin_device is not None
                            if (
                                ip != web_context.admin_device.ip
                                and ip in web_context.admin_event.devices_by_ip
                            ):
                                errors[field] = _('Device [{ip}] already set.').format(
                                    ip=ip
                                )
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
        return StoredDevice(
            id=device_id,
            edit_properties=edit_properties,
            edit_permissions=edit_permissions,
            active=active,
            ip=ip,
            permissions=permissions,
            errors=errors,
        )

    @classmethod
    def _admin_event_devices_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        modal: str | None = None,
        action: str | None = None,
        device_id: int | None = None,
        data: dict[str, str] | None = None,  # type: ignore
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: DeviceAdminWebContext = DeviceAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            device_id=device_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context,
        ) | {
            'admin_event_tab': 'admin-event-devices-tab',
        }

        match modal:
            case None:
                pass
            case 'device':
                if data is None:
                    ip: str | None = None
                    active: bool | None = None
                    match action:
                        case 'update':
                            assert web_context.admin_device is not None
                            ip = web_context.admin_device.stored_device.ip
                        case 'create' | 'clone' | 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update' | 'clone':
                            assert web_context.admin_device is not None
                            active = web_context.admin_device.stored_device.active
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
                            assert web_context.admin_device is not None
                            for (
                                role,
                                permission,
                            ) in web_context.admin_device.permissions_by_role.items():
                                data[f'role_{role.id}'] = WebContext.value_to_form_data(
                                    True
                                )
                                data[f'permission_{role.id}'] = (
                                    WebContext.value_to_form_data(permission)
                                )
                        case 'create' | 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    stored_device: StoredDevice = (
                        cls._admin_validate_device_update_data(
                            action, web_context, data
                        )
                    )
                    errors = stored_device.errors
                if errors is None:
                    errors = {}
                template_context |= {
                    'previous_device': (
                        web_context.admin_device if action == 'create' else None
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
        path='/admin/event/{event_uniq_id:str}/devices',
        name='admin-event-devices-tab',
        cache=1,
    )
    async def htmx_admin_event_devices_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_devices_render(
            request,
            event_uniq_id=event_uniq_id,
        )

    @get(
        path='/admin/device-modal/create/{event_uniq_id:str}',
        name='admin-device-create-modal',
        cache=1,
    )
    async def htmx_admin_device_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_devices_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='device',
            action='create',
            device_id=None,
        )

    @get(
        path='/admin/device-modal/{action:str}/{event_uniq_id:str}/{device_id:int}',
        name='admin-device-modal',
        cache=1,
    )
    async def htmx_admin_device_modal(
        self,
        request: HTMXRequest,
        action: str,
        event_uniq_id: str,
        device_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_devices_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='device',
            action=action,
            device_id=device_id,
        )

    def _admin_device_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        action: str,
        event_uniq_id: str,
        device_id: int | None,
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'delete' | 'create':
                web_context: DeviceAdminWebContext = DeviceAdminWebContext(
                    request,
                    event_uniq_id=event_uniq_id,
                    device_id=device_id,
                    data=data,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        stored_device: StoredDevice = self._admin_validate_device_update_data(
            action, web_context, data
        )
        if stored_device.errors:
            return self._admin_event_devices_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='device',
                action=action,
                device_id=device_id,
                data=data,
                errors=stored_device.errors,
            )
        event_loader: EventLoader = EventLoader.get(request=request)
        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            if web_context.admin_event.default_custom_mode_objects:
                event_database.create_custom_exec_mode_objects()
            match action:
                case 'create':
                    stored_device = event_database.add_stored_device(stored_device)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Device [{ip}] has been created.').format(
                            ip=stored_device.ip
                        ),
                    )
                case 'update':
                    if (
                        web_context.admin_device is None
                        or web_context.admin_device.localhost
                    ):
                        raise RuntimeError(
                            f'{web_context.admin_device=} for [{action=}]'
                        )
                    stored_device = event_database.update_stored_device(stored_device)
                    event_database.commit()
                    Message.success(
                        request,
                        _("Unknown devices' access has been updated.")
                        if web_context.admin_device.unknown
                        else _('Device [{ip}] has been updated.').format(
                            ip=stored_device.ip
                        ),
                    )
                case 'delete':
                    if (
                        web_context.admin_device is None
                        or web_context.admin_device.localhost
                        or web_context.admin_device.unknown
                    ):
                        raise RuntimeError(
                            f'{web_context.admin_device=} for [{action=}]'
                        )
                    event_database.delete_stored_device(web_context.admin_device.id)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Device [{ip}] has been deleted.').format(
                            ip=web_context.admin_device.ip
                        ),
                    )
                case _:
                    raise ValueError(f'action=[{action}]')
        event_loader.clear_cache(event_uniq_id)
        return self._admin_event_devices_render(request, event_uniq_id=event_uniq_id)

    @post(path='/admin/device-create/{event_uniq_id:str}', name='admin-device-create')
    async def htmx_admin_device_create(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_device_update(
            request,
            event_uniq_id=event_uniq_id,
            action='create',
            device_id=None,
            data=data,
        )

    @patch(
        path='/admin/device-update/{event_uniq_id:str}/{device_id:int}',
        name='admin-device-update',
    )
    async def htmx_admin_device_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        device_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_device_update(
            request,
            event_uniq_id=event_uniq_id,
            action='update',
            device_id=device_id,
            data=data,
        )

    @delete(
        path='/admin/device-delete/{event_uniq_id:str}/{device_id:int}',
        name='admin-device-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_device_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        device_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_device_update(
            request,
            event_uniq_id=event_uniq_id,
            action='delete',
            device_id=device_id,
            data=data,
        )
