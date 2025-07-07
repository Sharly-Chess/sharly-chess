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
from data.auth.managers import RoleManager
from database.sqlite.event.event_store import StoredDevice
from utils.enum import FormAction
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
        device_id: int | None = None,
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

    def get_admin_device(self) -> Device:
        assert self.admin_device is not None
        return self.admin_device

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_event_tab': 'admin-event-devices-tab',
            'admin_device': self.admin_device,
            'roles': RoleManager.objects(),
        }


class DeviceAdminController(BaseEventAdminController):
    @classmethod
    def _admin_event_devices_render(
        cls,
        web_context: DeviceAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template | ClientRedirect:
        if web_context.error:
            return web_context.error
        return cls._admin_event_render(
            cls._get_admin_event_render_context(web_context) | (template_context or {})
        )

    @classmethod
    def _device_form_modal_context(
        cls,
        web_context: DeviceAdminWebContext,
        action: FormAction,
        data: dict[str, str],
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        default_data = WebContext.values_dict_to_form_data(
            {
                'ip': '',
                'active': True,
                'roles': [],
                'tournament_ids': [],
            }
        )
        return {
            'modal': 'device',
            'action': action,
            'role_options': {
                role.id: role.name
                for role, is_manageable in web_context.client.role_management.items()
                if is_manageable
            },
            'tournament_options': web_context.get_tournament_options(),
            'data': default_data | data,
            'errors': errors or {},
        }

    @staticmethod
    def _device_form_data_from_device(device: Device) -> dict[str, str]:
        stored_device = device.stored_device
        return WebContext.values_dict_to_form_data(
            {
                'ip': stored_device.ip,
                'active': stored_device.active,
                'roles': stored_device.roles,
                'tournament_ids': stored_device.tournament_ids,
            }
        )

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
            DeviceAdminWebContext(request, event_uniq_id)
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
        web_context = DeviceAdminWebContext(request, event_uniq_id)
        if web_context.error:
            return web_context.error
        template_context = self._device_form_modal_context(
            web_context, FormAction.CREATE, {}
        )
        return self._admin_event_devices_render(web_context, template_context)

    @get(
        path='/admin/device-modal/update/{event_uniq_id:str}/{device_id:int}',
        name='admin-device-update-modal',
        cache=1,
    )
    async def htmx_admin_device_update_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        device_id: int,
    ) -> Template | ClientRedirect:
        web_context = DeviceAdminWebContext(request, event_uniq_id, device_id)
        if web_context.error:
            return web_context.error
        template_context = self._device_form_modal_context(
            web_context,
            FormAction.UPDATE,
            self._device_form_data_from_device(web_context.get_admin_device()),
        )
        return self._admin_event_devices_render(web_context, template_context)

    @get(
        path='/admin/device-modal/clone/{event_uniq_id:str}/{device_id:int}',
        name='admin-device-clone-modal',
        cache=1,
    )
    async def htmx_admin_device_clone_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        device_id: int,
    ) -> Template | ClientRedirect:
        web_context = DeviceAdminWebContext(request, event_uniq_id, device_id)
        if web_context.error:
            return web_context.error
        device = web_context.get_admin_device()
        template_context = self._device_form_modal_context(
            web_context,
            FormAction.CLONE,
            self._device_form_data_from_device(device),
        )
        return self._admin_event_devices_render(web_context, template_context)

    @get(
        path='/admin/device-modal/delete/{event_uniq_id:str}/{device_id:int}',
        name='admin-device-delete-modal',
        cache=1,
    )
    async def htmx_admin_device_delete_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        device_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_devices_render(
            DeviceAdminWebContext(request, event_uniq_id, device_id),
            {'modal': 'device_delete'},
        )

    @staticmethod
    def _validate_device_form_data(
        data: dict[str, str],
        web_context: DeviceAdminWebContext,
        action: FormAction,
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        event = web_context.get_admin_event()
        device = web_context.admin_device
        if not device or not (device.unknown or device.localhost):
            ip = WebContext.form_data_to_str(data, field := 'ip')
            if not ip:
                errors[field] = _('Please enter the IP address.')
            elif matches := re.match(
                r'^(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|0?[1-9][0-9]|0?0?[1-9])\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|0?[1-9][0-9]|0?0?[1-9])\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|0?[1-9][0-9]|0?0?[1-9])\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|0?[1-9][0-9]|0?0?[1-9])$',
                ip,
            ):
                ip = f'{int(matches.group(1))}.{int(matches.group(2))}.{int(matches.group(3))}.{int(matches.group(4))}'
                data[field] = ip
                if ip in event.devices_by_ip and (
                    action != FormAction.UPDATE or (device and device.ip == ip)
                ):
                    errors[field] = _('Device [{ip}] already set.').format(ip=ip)
            else:
                errors[field] = _('The IP address [{ip}] is not valid.').format(ip=ip)
        roles = WebContext.form_data_to_list_str(data, field := 'roles') or []
        if not roles:
            errors[field] = _('At least one role is expected.')
        return errors

    @post(path='/admin/device-create/{event_uniq_id:str}', name='admin-device-create')
    async def htmx_admin_device_create(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        web_context = DeviceAdminWebContext(request, event_uniq_id)
        if web_context.error:
            return web_context.error
        flat_data = WebContext.flatten_list_data(data)
        if errors := self._validate_device_form_data(
            flat_data, web_context, FormAction.CREATE
        ):
            return self._admin_event_devices_render(
                web_context,
                self._device_form_modal_context(
                    web_context, FormAction.CREATE, flat_data, errors
                ),
            )
        event = web_context.get_admin_event()
        # TODO (Molrn) Add a specific endpoint for creating the default Accounts / Devices
        event.create_custom_exec_mode_objects()
        device = event.create_device(
            StoredDevice(
                id=None,
                active=WebContext.form_data_to_bool(flat_data, 'active'),
                roles=WebContext.form_data_to_list_str(flat_data, 'roles'),
                tournament_ids=WebContext.form_data_to_list_int(
                    flat_data, 'tournament_ids'
                )
                or None,
                ip=WebContext.form_data_to_str(flat_data, 'ip'),
            )
        )
        Message.success(
            request, _('Device [{ip}] has been created.').format(ip=device.ip)
        )
        return self._admin_event_devices_render(web_context)

    @patch(
        path='/admin/device-update/{event_uniq_id:str}/{device_id:int}',
        name='admin-device-update',
    )
    async def htmx_admin_device_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        device_id: int,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        web_context = DeviceAdminWebContext(request, event_uniq_id, device_id)
        if web_context.error:
            return web_context.error
        flat_data = WebContext.flatten_list_data(data)
        if errors := self._validate_device_form_data(
            flat_data, web_context, FormAction.UPDATE
        ):
            return self._admin_event_devices_render(
                web_context,
                self._device_form_modal_context(
                    web_context, FormAction.UPDATE, flat_data, errors
                ),
            )
        event = web_context.get_admin_event()
        # TODO (Molrn) Add a specific endpoint for creating the default Accounts / Devices
        event.create_custom_exec_mode_objects()
        device = web_context.get_admin_device()
        stored_device = device.stored_device
        if not device.unknown:
            stored_device.active = WebContext.form_data_to_bool(flat_data, 'active')
            stored_device.ip = WebContext.form_data_to_str(flat_data, 'ip')
        stored_device.roles = WebContext.form_data_to_list_str(flat_data, 'roles')
        stored_device.tournament_ids = (
            WebContext.form_data_to_list_int(flat_data, 'tournament_ids') or None
        )
        event.update_device(stored_device)
        Message.success(
            request,
            _("Unknown devices' access has been updated.")
            if device.unknown
            else _('Device [{ip}] has been updated.').format(ip=stored_device.ip),
        )
        return self._admin_event_devices_render(web_context)

    @delete(
        path='/admin/device-delete/{event_uniq_id:str}/{device_id:int}',
        name='admin-device-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_device_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        device_id: int,
    ) -> Template | ClientRedirect:
        web_context = DeviceAdminWebContext(request, event_uniq_id, device_id)
        if web_context.error:
            return web_context.error
        event = web_context.get_admin_event()
        device = web_context.get_admin_device()
        event.delete_device(device)
        Message.success(
            request, _('Device [{ip}] has been deleted.').format(ip=device.ip)
        )
        return self._admin_event_devices_render(web_context)
