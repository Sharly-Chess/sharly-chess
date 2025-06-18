from typing import Annotated, Any

from litestar import post, get, delete, patch
from litestar.plugins.htmx import HTMXRequest, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from data.auth.entities import User
from data.auth.roles import Role
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredUser
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.messages import Message


class UserAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        user_id: int | None,
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
        self.admin_user: User | None = None
        if self.error:
            return
        if user_id:
            try:
                self.admin_user = self.admin_event.users_by_id[user_id]
            except KeyError:
                self._redirect_error(f'User [{user_id}] not found.')
                return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_user': self.admin_user,
        }


class UserAdminController(BaseEventAdminController):
    @staticmethod
    def _admin_validate_user_update_data(
        action: str,
        web_context: UserAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> StoredUser:
        assert web_context.admin_event is not None
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        user_id: int = 0
        username: str = ''
        password: str = ''
        active: bool = False
        tournament_uniq_ids_by_role_id: dict[int, str] = {}
        if web_context.admin_user and action not in [
            'create',
            'clone',
        ]:
            user_id = web_context.admin_user.id
        if action in [
            'delete',
        ]:
            pass
        else:
            username = WebContext.form_data_to_str(data, field := 'username')
            if not username:
                errors[field] = _('Please enter the username.')
            else:
                match action:
                    case 'create' | 'clone':
                        if username in web_context.admin_event.users_by_username:
                            errors[field] = _(
                                'User [{username}] already exists.'
                            ).format(username=username)
                    case 'update':
                        assert web_context.admin_user is not None
                        if (
                            username != web_context.admin_user.username
                            and username in web_context.admin_event.users_by_username
                        ):
                            errors[field] = _(
                                'User [{username}] already exists.'
                            ).format(username=username)
                    case _:
                        raise ValueError(f'action=[{action}]')
            password = WebContext.form_data_to_str(data, 'password')
            active = WebContext.form_data_to_bool(data, 'active')
            for role_id in Role.values():
                if WebContext.form_data_to_bool(data, f'role_{role_id}'):
                    tournament_uniq_ids_by_role_id[role_id] = (
                        WebContext.form_data_to_str(
                            data, f'tournament_uniq_ids_{role_id}'
                        )
                    )

        return StoredUser(
            id=user_id,
            active=active,
            username=username,
            password=password,
            tournaments_uniq_ids_by_role_id=tournament_uniq_ids_by_role_id,
            errors=errors,
        )

    @classmethod
    def _admin_event_users_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        modal: str | None = None,
        action: str | None = None,
        user_id: int | None = None,
        data: dict[str, str] | None = None,  # type: ignore
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: UserAdminWebContext = UserAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            user_id=user_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context,
        ) | {
            'admin_event_tab': 'admin-event-users-tab',
        }

        match modal:
            case None:
                pass
            case 'user':
                if data is None:
                    username: str | None = None
                    active: bool | None = None
                    password: str | None = None
                    match action:
                        case 'update':
                            assert web_context.admin_user is not None
                            username = web_context.admin_user.stored_user.username
                        case 'create' | 'clone' | 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update' | 'clone':
                            assert web_context.admin_user is not None
                            active = web_context.admin_user.stored_user.active
                            password = web_context.admin_user.stored_user.password
                        case 'create':
                            active = True
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    data = {
                        'username': WebContext.value_to_form_data(username),
                        'active': WebContext.value_to_form_data(active),
                        'password': WebContext.value_to_form_data(password),
                    }
                    match action:
                        case 'update' | 'clone':
                            assert web_context.admin_user is not None
                            for (
                                permission
                            ) in web_context.admin_user.permissions_by_id.values():
                                data[f'role_{permission.role.value}'] = (
                                    WebContext.value_to_form_data(True)
                                )
                                data[f'tournament_uniq_ids_{permission.role.value}'] = (
                                    WebContext.value_to_form_data(
                                        permission.tournament_uniq_ids
                                    )
                                )
                        case 'create' | 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    stored_user: StoredUser = cls._admin_validate_user_update_data(
                        action, web_context, data
                    )
                    errors = stored_user.errors
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
        path='/admin/event/{event_uniq_id:str}/users',
        name='admin-event-users-tab',
        cache=1,
    )
    async def htmx_admin_event_users_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_users_render(
            request,
            event_uniq_id=event_uniq_id,
        )

    @get(
        path='/admin/user-modal/create/{event_uniq_id:str}',
        name='admin-user-create-modal',
        cache=1,
    )
    async def htmx_admin_user_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_users_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='user',
            action='create',
            user_id=None,
        )

    @get(
        path='/admin/user-modal/{action:str}/{event_uniq_id:str}/{user_id:int}',
        name='admin-user-modal',
        cache=1,
    )
    async def htmx_admin_user_modal(
        self,
        request: HTMXRequest,
        action: str,
        event_uniq_id: str,
        user_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_users_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='user',
            action=action,
            user_id=user_id,
        )

    def _admin_user_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        action: str,
        event_uniq_id: str,
        user_id: int | None,
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'delete' | 'create':
                web_context: UserAdminWebContext = UserAdminWebContext(
                    request,
                    event_uniq_id=event_uniq_id,
                    user_id=user_id,
                    data=data,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        stored_user: StoredUser = self._admin_validate_user_update_data(
            action, web_context, data
        )
        if stored_user.errors:
            return self._admin_event_users_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='user',
                action=action,
                user_id=user_id,
                data=data,
                errors=stored_user.errors,
            )
        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            match action:
                case 'create':
                    stored_user = event_database.add_stored_user(stored_user)
                    event_database.commit()
                    Message.success(
                        request,
                        _('User [{username}] has been created.').format(
                            username=stored_user.username
                        ),
                    )
                case 'update':
                    stored_user = event_database.update_stored_user(stored_user)
                    event_database.commit()
                    Message.success(
                        request,
                        _('User [{username}] has been updated.').format(
                            username=stored_user.username
                        ),
                    )
                case 'delete':
                    if web_context.admin_user is None:
                        raise RuntimeError(f'{web_context.admin_user=} for [{action=}]')
                    event_database.delete_stored_user(web_context.admin_user.id)
                    event_database.commit()
                    Message.success(
                        request,
                        _('User [{username}] has been deleted.').format(
                            username=web_context.admin_user.username
                        ),
                    )
                case _:
                    raise ValueError(f'action=[{action}]')
        web_context.admin_event.clear_user_cache()
        return self._admin_event_users_render(request, event_uniq_id=event_uniq_id)

    @post(path='/admin/user-create/{event_uniq_id:str}', name='admin-user-create')
    async def htmx_admin_user_create(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_user_update(
            request,
            event_uniq_id=event_uniq_id,
            action='create',
            user_id=None,
            data=data,
        )

    @patch(
        path='/admin/user-update/{event_uniq_id:str}/{user_id:int}',
        name='admin-user-update',
    )
    async def htmx_admin_user_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        user_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_user_update(
            request,
            event_uniq_id=event_uniq_id,
            action='update',
            user_id=user_id,
            data=data,
        )

    @delete(
        path='/admin/user-delete/{event_uniq_id:str}/{user_id:int}',
        name='admin-user-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_user_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        user_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_user_update(
            request,
            event_uniq_id=event_uniq_id,
            action='delete',
            user_id=user_id,
            data=data,
        )
