from typing import Annotated, Any

from litestar import post, get, delete, patch
from litestar.plugins.htmx import HTMXRequest, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from data.rotator import Rotator
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredRotator
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.messages import Message
from web.session import SessionHandler


class RotatorAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        rotator_id: int | None,
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
        self.admin_rotator: Rotator | None = None
        if self.error:
            return
        if rotator_id:
            try:
                self.admin_rotator = self.admin_event.rotators_by_id[rotator_id]
            except KeyError:
                self._redirect_error(f'Rotator [{rotator_id}] not found.')
                return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_rotator': self.admin_rotator,
        }


class RotatorAdminController(BaseEventAdminController):
    @staticmethod
    def _admin_validate_rotator_update_data(
        action: str,
        web_context: RotatorAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> StoredRotator:
        assert web_context.admin_event is not None
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        field = 'uniq_id'
        uniq_id: str | None = WebContext.form_data_to_str(data, field)
        public: bool | None = None
        delay: int | None = None
        message_default: bool | None = True
        message_text: str | None = None
        screen_ids: list[int] | None = None
        family_ids: list[int] | None = None
        if action in [
            'delete',
        ]:
            pass
        else:
            if not uniq_id:
                errors[field] = _('Please enter the rotator ID.')
            else:
                match action:
                    case 'create' | 'clone':
                        if uniq_id in web_context.admin_event.rotators_by_uniq_id:
                            errors[field] = _(
                                'Rotator [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
                    case 'update':
                        assert web_context.admin_rotator is not None
                        if (
                            uniq_id != web_context.admin_rotator.uniq_id
                            and uniq_id in web_context.admin_event.rotators_by_uniq_id
                        ):
                            errors[field] = _(
                                'Rotator [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
                    case _:
                        raise ValueError(f'action=[{action}]')
            public = WebContext.form_data_to_bool(data, 'public')
        match action:
            case 'create' | 'update' | 'clone':
                public = WebContext.form_data_to_bool(data, 'public')
                field = 'delay'
                try:
                    delay = WebContext.form_data_to_int(data, field, minimum=1)
                except ValueError:
                    errors[field] = _('A positive integer is expected.')
                screen_ids = []
                for screen_id in web_context.admin_event.basic_screens_by_id:
                    field = f'screen_{screen_id}'
                    if WebContext.form_data_to_bool(data, field):
                        screen_ids.append(screen_id)
                family_ids = []
                for family_id in web_context.admin_event.families_by_id:
                    field = f'family_{family_id}'
                    if WebContext.form_data_to_bool(data, field):
                        family_ids.append(family_id)
                field = 'message_text'
                message_default = WebContext.form_data_to_bool(
                    data, field + '_checkbox'
                )
                if message_default and web_context.admin_rotator:
                    # do not change the original value when the default message is used
                    # (needed since disabled fields are not submitted)
                    message_text = web_context.admin_rotator.stored_rotator.message_text
                else:
                    message_text = WebContext.form_data_to_str(data, field)
            case 'delete':
                uniq_id = uniq_id or ''
            case _:
                raise ValueError(f'action=[{action}]')

        assert uniq_id is not None

        rotator_id: int | None = None
        if web_context.admin_rotator and action not in [
            'create',
            'clone',
        ]:
            rotator_id = web_context.admin_rotator.id

        return StoredRotator(
            id=rotator_id,
            uniq_id=uniq_id,
            public=bool(public),
            delay=delay,
            screen_ids=screen_ids,
            family_ids=family_ids,
            message_default=bool(message_default),
            message_text=message_text,
            errors=errors,
        )

    @classmethod
    def _admin_event_rotators_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        modal: str | None = None,
        action: str | None = None,
        rotator_id: int | None = None,
        data: dict[str, str] | None = None,  # type: ignore
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: RotatorAdminWebContext = RotatorAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            rotator_id=rotator_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')

        admin_rotators_sorted_by_uniq_id: list[Rotator]
        if web_context.client.can_view_private_screens:
            admin_rotators_sorted_by_uniq_id = (
                web_context.admin_event.rotators_sorted_by_uniq_id
            )
        elif web_context.client.can_view_public_screens:
            admin_rotators_sorted_by_uniq_id = (
                web_context.admin_event.public_rotators_sorted_by_uniq_id
            )
        else:
            admin_rotators_sorted_by_uniq_id = []
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context,
        ) | {
            'admin_event_tab': 'admin-event-rotators-tab',
            'admin_rotators_show_details': SessionHandler.get_session_admin_rotators_show_details(
                web_context.request
            ),
            'admin_rotators': admin_rotators_sorted_by_uniq_id,
        }

        match modal:
            case None:
                pass
            case 'rotator':
                if data is None:
                    uniq_id: str | None = None
                    public: bool | None = None
                    delay: int | None = None
                    message_default: bool = True
                    message_text: str | None = None
                    screen_ids: list[int] | None = None
                    family_ids: list[int] | None = None
                    match action:
                        case 'update':
                            assert web_context.admin_rotator is not None
                            uniq_id = web_context.admin_rotator.stored_rotator.uniq_id
                        case 'create':
                            uniq_id = (
                                web_context.admin_event.get_unused_rotator_uniq_id()
                            )
                        case 'clone':
                            assert web_context.admin_rotator is not None
                            uniq_id = (
                                web_context.admin_event.get_unused_rotator_uniq_id(
                                    web_context.admin_rotator.stored_rotator.uniq_id
                                )
                            )
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update' | 'clone':
                            assert web_context.admin_rotator is not None
                            public = web_context.admin_rotator.stored_rotator.public
                            delay = web_context.admin_rotator.stored_rotator.delay
                            message_default = (
                                web_context.admin_rotator.stored_rotator.message_default
                            )
                            message_text = (
                                web_context.admin_rotator.stored_rotator.message_text
                            )
                            screen_ids = (
                                web_context.admin_rotator.stored_rotator.screen_ids
                            )
                            family_ids = (
                                web_context.admin_rotator.stored_rotator.family_ids
                            )
                        case 'create':
                            public = True
                            message_default = True
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    data = {
                        'uniq_id': WebContext.value_to_form_data(uniq_id),
                        'public': WebContext.value_to_form_data(public),
                        'delay': WebContext.value_to_form_data(delay),
                        'message_text_checkbox': WebContext.value_to_form_data(
                            message_default
                        ),
                        'message_text': WebContext.value_to_form_data(message_text),
                    }
                    if screen_ids:
                        data |= {
                            f'screen_{screen_id}': WebContext.value_to_form_data(
                                screen_id in screen_ids
                            )
                            for screen_id in web_context.admin_event.basic_screens_by_id
                        }
                    if family_ids:
                        data |= {
                            f'family_{family_id}': WebContext.value_to_form_data(
                                family_id in family_ids
                            )
                            for family_id in web_context.admin_event.families_by_id
                        }
                    stored_rotator: StoredRotator = (
                        cls._admin_validate_rotator_update_data(
                            action, web_context, data
                        )
                    )
                    errors = stored_rotator.errors
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
        path='/admin/event/{event_uniq_id:str}/rotators',
        name='admin-event-rotators-tab',
    )
    async def htmx_admin_event_rotators_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        admin_rotators_show_details: bool | None,
    ) -> Template | ClientRedirect:
        if admin_rotators_show_details is not None:
            SessionHandler.set_session_admin_rotators_show_details(
                request, admin_rotators_show_details
            )
        return self._admin_event_rotators_render(
            request,
            event_uniq_id=event_uniq_id,
        )

    @get(
        path='/admin/rotator-modal/create/{event_uniq_id:str}',
        name='admin-rotator-create-modal',
    )
    async def htmx_admin_rotator_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_rotators_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='rotator',
            action='create',
            rotator_id=None,
        )

    @get(
        path='/admin/rotator-modal/{action:str}/{event_uniq_id:str}/{rotator_id:int}',
        name='admin-rotator-modal',
    )
    async def htmx_admin_rotator_modal(
        self,
        request: HTMXRequest,
        action: str,
        event_uniq_id: str,
        rotator_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_rotators_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='rotator',
            action=action,
            rotator_id=rotator_id,
        )

    def _admin_rotator_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        action: str,
        event_uniq_id: str,
        rotator_id: int | None,
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'delete' | 'create':
                web_context: RotatorAdminWebContext = RotatorAdminWebContext(
                    request,
                    event_uniq_id=event_uniq_id,
                    rotator_id=rotator_id,
                    data=data,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        stored_rotator: StoredRotator = self._admin_validate_rotator_update_data(
            action, web_context, data
        )
        if stored_rotator.errors:
            return self._admin_event_rotators_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='rotator',
                action=action,
                rotator_id=rotator_id,
                data=data,
                errors=stored_rotator.errors,
            )
        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            match action:
                case 'create':
                    stored_rotator = event_database.add_stored_rotator(stored_rotator)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Rotator [{rotator_uniq_id}] has been created.').format(
                            rotator_uniq_id=stored_rotator.uniq_id
                        ),
                    )
                case 'update':
                    stored_rotator = event_database.update_stored_rotator(
                        stored_rotator
                    )
                    event_database.commit()
                    Message.success(
                        request,
                        _('Rotator [{rotator_uniq_id}] has been updated.').format(
                            rotator_uniq_id=stored_rotator.uniq_id
                        ),
                    )
                case 'delete':
                    if web_context.admin_rotator is None:
                        raise RuntimeError(
                            f'{web_context.admin_rotator=} for [{action=}]'
                        )
                    event_database.delete_stored_rotator(web_context.admin_rotator.id)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Rotator [{rotator_uniq_id}] has been deleted.').format(
                            rotator_uniq_id=web_context.admin_rotator.uniq_id
                        ),
                    )
                case _:
                    raise ValueError(f'action=[{action}]')

        return self._admin_event_rotators_render(request, event_uniq_id=event_uniq_id)

    @post(path='/admin/rotator-create/{event_uniq_id:str}', name='admin-rotator-create')
    async def htmx_admin_rotator_create(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_rotator_update(
            request,
            event_uniq_id=event_uniq_id,
            action='create',
            rotator_id=None,
            data=data,
        )

    @patch(
        path='/admin/rotator-update/{event_uniq_id:str}/{rotator_id:int}',
        name='admin-rotator-update',
    )
    async def htmx_admin_rotator_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        rotator_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_rotator_update(
            request,
            event_uniq_id=event_uniq_id,
            action='update',
            rotator_id=rotator_id,
            data=data,
        )

    @delete(
        path='/admin/rotator-delete/{event_uniq_id:str}/{rotator_id:int}',
        name='admin-rotator-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_rotator_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        rotator_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_rotator_update(
            request,
            event_uniq_id=event_uniq_id,
            action='delete',
            rotator_id=rotator_id,
            data=data,
        )
