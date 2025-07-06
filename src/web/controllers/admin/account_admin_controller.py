import re
from typing import Annotated, Any

from argon2 import PasswordHasher
from litestar import post, get, delete, patch
from litestar.plugins.htmx import HTMXRequest, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from data.auth.entities import Account
from data.auth.roles import Role
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredAccount
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.messages import Message


class AccountAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        account_id: int | None,
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
        self.admin_account: Account | None = None
        if self.error:
            return
        if account_id:
            try:
                self.admin_account = self.admin_event.accounts_by_id[account_id]
            except KeyError:
                self._redirect_error(f'Account [{account_id}] not found.')
                return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_account': self.admin_account,
            'roles': Role.roles(),
        }


class AccountAdminController(BaseEventAdminController):
    @staticmethod
    def _admin_validate_account_update_data(
        action: str,
        web_context: AccountAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> StoredAccount:
        assert web_context.admin_event is not None
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        account_id: int | None = None
        username: str | None = None
        password: str | None = None
        edit_properties: bool = True
        edit_permissions: bool = True
        active: bool = False
        permissions: dict[int, str | None] = {}
        if web_context.admin_account and action in [
            'update',
            'delete',
        ]:
            account_id = web_context.admin_account.id
            edit_properties = web_context.admin_account.edit_properties
            edit_permissions = web_context.admin_account.edit_permissions
        if action in [
            'delete',
        ]:
            pass
        else:
            if web_context.admin_account and web_context.admin_account.anonymous:
                username = web_context.admin_account.username
                password_hash = web_context.admin_account.password_hash
                active = web_context.admin_account.active
            else:
                username = WebContext.form_data_to_str(data, field := 'username')
                if not username:
                    errors[field] = _('Please enter the username.')
                # NOTE(Amaras): this prevents usernames starting with -
                elif not re.match(r'^[a-zA-Z0-9_][a-zA-Z0-9_\-]*$', username):
                    errors[field] = _(
                        'Accepted characters are letters, numbers, underscore (_) and minus (-).'
                    )
                else:
                    match action:
                        case 'create' | 'clone':
                            if username in web_context.admin_event.accounts_by_username:
                                errors[field] = _(
                                    'Account [{username}] already exists.'
                                ).format(username=username)
                        case 'update':
                            assert web_context.admin_account is not None
                            if (
                                username != web_context.admin_account.username
                                and username
                                in web_context.admin_event.accounts_by_username
                            ):
                                errors[field] = _(
                                    'Account [{username}] already exists.'
                                ).format(username=username)
                        case _:
                            raise ValueError(f'action=[{action}]')
                password = WebContext.form_data_to_str(data, field := 'password')
                if password is None and action not in ['create', 'clone']:
                    password_hash = web_context.admin_account.password_hash
                elif password is not None:
                    ph = PasswordHasher()
                    password_hash = ph.hash(password)
                else:
                    password_hash = None
                active = WebContext.form_data_to_bool(data, 'active')
            for role_id in Role.values():
                if WebContext.form_data_to_bool(data, f'role_{role_id}'):
                    permissions[role_id] = WebContext.form_data_to_str(
                        data, f'permission_{role_id}'
                    )
        return StoredAccount(
            id=account_id,
            edit_properties=edit_properties,
            edit_permissions=edit_permissions,
            active=active,
            username=username,
            password_hash=password_hash,
            permissions=permissions,
            errors=errors,
        )

    @classmethod
    def _admin_event_accounts_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        modal: str | None = None,
        action: str | None = None,
        account_id: int | None = None,
        data: dict[str, str] | None = None,  # type: ignore
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: AccountAdminWebContext = AccountAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            account_id=account_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context,
        ) | {
            'admin_event_tab': 'admin-event-accounts-tab',
        }

        match modal:
            case None:
                pass
            case 'account':
                if data is None:
                    username: str | None = None
                    active: bool | None = None
                    match action:
                        case 'update':
                            assert web_context.admin_account is not None
                            username = web_context.admin_account.stored_account.username
                        case 'create' | 'clone' | 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update' | 'clone':
                            assert web_context.admin_account is not None
                            active = web_context.admin_account.stored_account.active
                        case 'create':
                            active = True
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    data = (
                        {
                            'username': WebContext.value_to_form_data(username),
                            'active': WebContext.value_to_form_data(active),
                            'password': '',
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
                            assert web_context.admin_account is not None
                            for (
                                role,
                                permission,
                            ) in web_context.admin_account.permissions_by_role.items():
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
                    stored_account: StoredAccount = (
                        cls._admin_validate_account_update_data(
                            action, web_context, data
                        )
                    )
                    errors = stored_account.errors
                if errors is None:
                    errors = {}
                template_context |= {
                    'previous_account': (
                        web_context.admin_account if action == 'create' else None
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
        path='/admin/event/{event_uniq_id:str}/accounts',
        name='admin-event-accounts-tab',
        cache=1,
    )
    async def htmx_admin_event_accounts_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_accounts_render(
            request,
            event_uniq_id=event_uniq_id,
        )

    @get(
        path='/admin/account-modal/create/{event_uniq_id:str}',
        name='admin-account-create-modal',
        cache=1,
    )
    async def htmx_admin_account_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_accounts_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='account',
            action='create',
            account_id=None,
        )

    @get(
        path='/admin/account-modal/{action:str}/{event_uniq_id:str}/{account_id:int}',
        name='admin-account-modal',
        cache=1,
    )
    async def htmx_admin_account_modal(
        self,
        request: HTMXRequest,
        action: str,
        event_uniq_id: str,
        account_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_accounts_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='account',
            action=action,
            account_id=account_id,
        )

    def _admin_account_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        action: str,
        event_uniq_id: str,
        account_id: int | None,
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'delete' | 'create':
                web_context: AccountAdminWebContext = AccountAdminWebContext(
                    request,
                    event_uniq_id=event_uniq_id,
                    account_id=account_id,
                    data=data,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        stored_account: StoredAccount = self._admin_validate_account_update_data(
            action, web_context, data
        )
        if stored_account.errors:
            return self._admin_event_accounts_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='account',
                action=action,
                account_id=account_id,
                data=data,
                errors=stored_account.errors,
            )
        event_loader: EventLoader = EventLoader.get(request=request)
        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            if web_context.admin_event.default_custom_mode_objects:
                event_database.create_custom_exec_mode_objects()
            match action:
                case 'create':
                    stored_account = event_database.add_stored_account(stored_account)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Account [{username}] has been created.').format(
                            username=stored_account.username
                        ),
                    )
                case 'update':
                    assert web_context.admin_account is not None
                    stored_account = event_database.update_stored_account(
                        stored_account
                    )
                    event_database.commit()
                    Message.success(
                        request,
                        _('Unauthenticated access has been updated.')
                        if web_context.admin_account.anonymous
                        else _('Account [{username}] has been updated.').format(
                            username=stored_account.username
                        ),
                    )
                case 'delete':
                    if web_context.admin_account is None:
                        raise RuntimeError(
                            f'{web_context.admin_account=} for [{action=}]'
                        )
                    if web_context.admin_account.anonymous:
                        raise RuntimeError('Can not delete the anonymous account')
                    event_database.delete_stored_account(web_context.admin_account.id)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Account [{username}] has been deleted.').format(
                            username=web_context.admin_account.username
                        ),
                    )
                case _:
                    raise ValueError(f'action=[{action}]')
        event_loader.clear_cache(event_uniq_id)
        return self._admin_event_accounts_render(request, event_uniq_id=event_uniq_id)

    @post(path='/admin/account-create/{event_uniq_id:str}', name='admin-account-create')
    async def htmx_admin_account_create(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_account_update(
            request,
            event_uniq_id=event_uniq_id,
            action='create',
            account_id=None,
            data=data,
        )

    @patch(
        path='/admin/account-update/{event_uniq_id:str}/{account_id:int}',
        name='admin-account-update',
    )
    async def htmx_admin_account_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        account_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_account_update(
            request,
            event_uniq_id=event_uniq_id,
            action='update',
            account_id=account_id,
            data=data,
        )

    @delete(
        path='/admin/account-delete/{event_uniq_id:str}/{account_id:int}',
        name='admin-account-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_account_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        account_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_account_update(
            request,
            event_uniq_id=event_uniq_id,
            action='delete',
            account_id=account_id,
            data=data,
        )
