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
from data.auth.managers import RoleManager
from database.sqlite.event.event_store import StoredAccount
from utils.enum import FormAction
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
        account_id: int | None = None,
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
        self.admin_account: Account | None = None
        if self.error:
            return
        if account_id:
            try:
                self.admin_account = self.admin_event.accounts_by_id[account_id]
            except KeyError:
                self._redirect_error(f'Account [{account_id}] not found.')
                return

    def get_admin_account(self) -> Account:
        assert self.admin_account is not None
        return self.admin_account

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_event_tab': 'admin-event-accounts-tab',
            'admin_account': self.admin_account,
            'roles': RoleManager.objects(),
        }


class AccountAdminController(BaseEventAdminController):
    @classmethod
    def _admin_event_accounts_render(
        cls,
        web_context: AccountAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template | ClientRedirect:
        if web_context.error:
            return web_context.error
        return cls._admin_event_render(
            cls._get_admin_event_render_context(web_context) | (template_context or {})
        )

    @classmethod
    def _account_form_modal_context(
        cls,
        web_context: AccountAdminWebContext,
        action: FormAction,
        data: dict[str, str],
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        default_data = WebContext.values_dict_to_form_data(
            {
                'username': '',
                'password': '',
                'active': True,
                'roles': [],
                'tournament_ids': [],
            }
        )
        return {
            'modal': 'account',
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
    def _account_form_data_from_account(account: Account) -> dict[str, str]:
        stored_account = account.stored_account
        return WebContext.values_dict_to_form_data(
            {
                'username': stored_account.username,
                'active': stored_account.active,
                'roles': stored_account.roles,
                'tournament_ids': stored_account.tournament_ids,
            }
        )

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
            AccountAdminWebContext(request, event_uniq_id)
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
        web_context = AccountAdminWebContext(request, event_uniq_id)
        if web_context.error:
            return web_context.error
        template_context = self._account_form_modal_context(
            web_context, FormAction.CREATE, {}
        )
        return self._admin_event_accounts_render(web_context, template_context)

    @get(
        path='/admin/account-modal/update/{event_uniq_id:str}/{account_id:int}',
        name='admin-account-update-modal',
        cache=1,
    )
    async def htmx_admin_account_update_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        account_id: int,
    ) -> Template | ClientRedirect:
        web_context = AccountAdminWebContext(request, event_uniq_id, account_id)
        if web_context.error:
            return web_context.error
        template_context = self._account_form_modal_context(
            web_context,
            FormAction.UPDATE,
            self._account_form_data_from_account(web_context.get_admin_account()),
        )
        return self._admin_event_accounts_render(web_context, template_context)

    @get(
        path='/admin/account-modal/clone/{event_uniq_id:str}/{account_id:int}',
        name='admin-account-clone-modal',
        cache=1,
    )
    async def htmx_admin_account_clone_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        account_id: int,
    ) -> Template | ClientRedirect:
        web_context = AccountAdminWebContext(request, event_uniq_id, account_id)
        if web_context.error:
            return web_context.error
        account = web_context.get_admin_account()
        template_context = self._account_form_modal_context(
            web_context,
            FormAction.CLONE,
            self._account_form_data_from_account(account),
        )
        return self._admin_event_accounts_render(web_context, template_context)

    @get(
        path='/admin/account-modal/delete/{event_uniq_id:str}/{account_id:int}',
        name='admin-account-delete-modal',
        cache=1,
    )
    async def htmx_admin_account_delete_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        account_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_accounts_render(
            AccountAdminWebContext(request, event_uniq_id, account_id),
            {'modal': 'account_delete'},
        )

    @staticmethod
    def _validate_account_form_data(
        data: dict[str, str],
        web_context: AccountAdminWebContext,
        action: FormAction,
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        event = web_context.get_admin_event()
        account = web_context.admin_account
        if not (account and account.anonymous):
            username = WebContext.form_data_to_str(data, field := 'username')
            if not username:
                errors[field] = _('Please enter the username.')
            elif not re.match(r'^[a-zA-Z0-9_\-]+$', username):
                errors[field] = _(
                    'Accepted characters are letters, numbers, underscore (_) and minus (-).'
                )
            elif username in event.accounts_by_username and (
                action != FormAction.UPDATE
                or (account and account.username == username)
            ):
                errors[field] = _('Account [{username}] already exists.').format(
                    username=username
                )
        roles = WebContext.form_data_to_list_str(data, field := 'roles') or []
        if not roles:
            errors[field] = _('At least one role is expected.')
        return errors

    @post(path='/admin/account-create/{event_uniq_id:str}', name='admin-account-create')
    async def htmx_admin_account_create(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        web_context = AccountAdminWebContext(request, event_uniq_id)
        if web_context.error:
            return web_context.error
        flat_data = WebContext.flatten_list_data(data)
        if errors := self._validate_account_form_data(
            flat_data, web_context, FormAction.CREATE
        ):
            return self._admin_event_accounts_render(
                web_context,
                self._account_form_modal_context(
                    web_context, FormAction.CREATE, flat_data, errors
                ),
            )
        event = web_context.get_admin_event()
        # TODO (Molrn) Add a specific endpoint for creating the default Accounts / Devices
        event.create_custom_exec_mode_objects()
        password = WebContext.form_data_to_str(flat_data, 'password')
        password_hash = PasswordHasher().hash(password) if password else None
        account = event.create_account(
            StoredAccount(
                id=None,
                active=WebContext.form_data_to_bool(flat_data, 'active'),
                roles=WebContext.form_data_to_list_str(flat_data, 'roles'),
                tournament_ids=WebContext.form_data_to_list_int(
                    flat_data, 'tournament_ids'
                )
                or None,
                username=WebContext.form_data_to_str(flat_data, 'username'),
                password_hash=password_hash,
            )
        )
        Message.success(
            request,
            _('Account [{username}] has been created.').format(
                username=account.username
            ),
        )
        return self._admin_event_accounts_render(web_context)

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
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        web_context = AccountAdminWebContext(request, event_uniq_id, account_id)
        if web_context.error:
            return web_context.error
        flat_data = WebContext.flatten_list_data(data)
        if errors := self._validate_account_form_data(
            flat_data, web_context, FormAction.UPDATE
        ):
            return self._admin_event_accounts_render(
                web_context,
                self._account_form_modal_context(
                    web_context, FormAction.UPDATE, flat_data, errors
                ),
            )
        event = web_context.get_admin_event()
        # TODO (Molrn) Add a specific endpoint for creating the default Accounts / Devices
        event.create_custom_exec_mode_objects()
        account = web_context.get_admin_account()
        stored_account = account.stored_account
        if not account.anonymous:
            stored_account.active = WebContext.form_data_to_bool(flat_data, 'active')
            stored_account.username = WebContext.form_data_to_str(flat_data, 'username')
            password = WebContext.form_data_to_str(flat_data, 'password')
            if password:
                stored_account.password_hash = PasswordHasher().hash(password)
        stored_account.roles = WebContext.form_data_to_list_str(flat_data, 'roles')
        stored_account.tournament_ids = (
            WebContext.form_data_to_list_int(flat_data, 'tournament_ids') or None
        )
        event.update_account(stored_account)
        Message.success(
            request,
            _('Unauthenticated access has been updated.')
            if account.anonymous
            else _('Account [{username}] has been updated.').format(
                username=account.username
            ),
        )
        return self._admin_event_accounts_render(web_context)

    @delete(
        path='/admin/account-delete/{event_uniq_id:str}/{account_id:int}',
        name='admin-account-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_account_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        account_id: int,
    ) -> Template | ClientRedirect:
        web_context = AccountAdminWebContext(request, event_uniq_id, account_id)
        if web_context.error:
            return web_context.error
        event = web_context.get_admin_event()
        account = web_context.get_admin_account()
        event.delete_account(account)
        Message.success(
            request,
            _('Account [{username}] has been deleted.').format(
                username=account.username
            ),
        )
        return self._admin_event_accounts_render(web_context)
