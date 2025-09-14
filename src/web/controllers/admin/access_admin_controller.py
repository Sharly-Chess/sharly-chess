import re
from typing import Annotated, Any

from argon2 import PasswordHasher
from litestar import post, get, delete, patch
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.plugins.htmx import HTMXRequest, ClientRedirect
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXTemplate

from common.i18n import _
from data.account import Account
from data.access_levels.manager import AccessLevelManager
from data.access_levels.access_levels import AccessLevel, AccessLevelScope
from data.player import Player
from database.sqlite.event.event_store import StoredAccount
from utils.enum import FormAction
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import Redirect, WebContext
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
            'access_levels': AccessLevelManager.objects(),
        }


class AccessAdminController(BaseEventAdminController):
    @classmethod
    def _admin_event_access_render(
        cls,
        web_context: AccountAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template | ClientRedirect | Redirect:
        if web_context.error:
            return web_context.error
        return cls._admin_event_render(
            web_context.template_context | (template_context or {})
        )

    @staticmethod
    def _permission_form_context(
        web_context: AccountAdminWebContext,
        data: dict[str, str],
    ) -> dict[str, Any]:
        access_levels = [
            AccessLevelManager.get_object(access_level_id)
            for access_level_id in WebContext.form_data_to_list_str(
                data, 'access_levels'
            )
        ]
        inherited_access_levels: set[AccessLevel] = set()
        for access_level in access_levels:
            inherited_access_levels |= access_level.sub_access_levels()
        selected_access_levels = [
            access_level
            for access_level in access_levels
            if access_level not in inherited_access_levels
        ]
        return {
            'manageable_access_levels': web_context.client.manageable_access_levels,
            'selected_access_levels': selected_access_levels,
            'inherited_access_levels': inherited_access_levels,
            'tournament_access_level_selected': any(
                access_level.scope == AccessLevelScope.TOURNAMENT
                for access_level in selected_access_levels
            ),
            'tournament_options': web_context.get_tournament_options(),
            'data': data,
            'errors': {},
        }

    @get(
        path='/admin/access/permissions-form/{event_uniq_id: str}',
        name='admin-access-permissions-form',
    )
    async def admin_access_permission_form(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        access_levels: list[str] | None,
        tournament_ids: list[str] | None,
    ) -> Template | ClientRedirect | Redirect:
        web_context = AccountAdminWebContext(request, event_uniq_id)
        if web_context.error:
            return web_context.error
        data = WebContext.flatten_list_data(
            {
                'access_levels': access_levels or '',
                'tournament_ids': tournament_ids or '',
            }
        )
        return HTMXTemplate(
            template_name='admin/accounts/permissions_form.html',
            context=web_context.template_context
            | self._permission_form_context(web_context, data),
        )

    # --------------------------------------------------------------------------
    # Accounts
    # --------------------------------------------------------------------------

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
                'first_name': '',
                'last_name': '',
                'password': '',
                'active': True,
                'access_levels': [],
                'tournament_ids': [],
            }
        )
        data = default_data | data
        return cls._permission_form_context(web_context, data) | {
            'modal': 'account',
            'action': action,
            'data': data,
            'errors': errors or {},
        }

    @staticmethod
    def _account_form_data_from_account(account: Account) -> dict[str, str]:
        stored_account = account.stored_account
        return WebContext.values_dict_to_form_data(
            {
                'first_name': stored_account.first_name,
                'last_name': stored_account.last_name,
                'active': stored_account.active,
                'access_levels': stored_account.access_levels,
                'tournament_ids': stored_account.tournament_ids,
            }
        )

    @get(
        path='/admin/event/{event_uniq_id:str}/accounts',
        name='admin-event-accounts-tab',
    )
    async def htmx_admin_event_accounts_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect | Redirect:
        return self._admin_event_access_render(
            AccountAdminWebContext(request, event_uniq_id)
        )

    @get(
        path='/admin/account-modal/create/{event_uniq_id:str}',
        name='admin-account-create-modal',
    )
    async def htmx_admin_account_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect | Redirect:
        web_context = AccountAdminWebContext(request, event_uniq_id)
        if web_context.error:
            return web_context.error
        template_context = self._account_form_modal_context(
            web_context, FormAction.CREATE, {}
        )
        return self._admin_event_access_render(web_context, template_context)

    @get(
        path='/admin/account-modal/update/{event_uniq_id:str}/{account_id:int}',
        name='admin-account-update-modal',
    )
    async def htmx_admin_account_update_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        account_id: int,
    ) -> Template | ClientRedirect | Redirect:
        web_context = AccountAdminWebContext(request, event_uniq_id, account_id)
        if web_context.error:
            return web_context.error
        template_context = self._account_form_modal_context(
            web_context,
            FormAction.UPDATE,
            self._account_form_data_from_account(web_context.get_admin_account()),
        )
        return self._admin_event_access_render(web_context, template_context)

    @get(
        path='/admin/account-modal/clone/{event_uniq_id:str}/{account_id:int}',
        name='admin-account-clone-modal',
    )
    async def htmx_admin_account_clone_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        account_id: int,
    ) -> Template | ClientRedirect | Redirect:
        web_context = AccountAdminWebContext(request, event_uniq_id, account_id)
        if web_context.error:
            return web_context.error
        account = web_context.get_admin_account()
        template_context = self._account_form_modal_context(
            web_context,
            FormAction.CLONE,
            self._account_form_data_from_account(account),
        )
        return self._admin_event_access_render(web_context, template_context)

    @get(
        path='/admin/account-modal/delete/{event_uniq_id:str}/{account_id:int}',
        name='admin-account-delete-modal',
    )
    async def htmx_admin_account_delete_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        account_id: int,
    ) -> Template | ClientRedirect | Redirect:
        return self._admin_event_access_render(
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
        if not account or account.user_account:
            first_name: str = (
                WebContext.form_data_to_str(data, field := 'first_name') or ''
            )
            if first_name and not re.match(r"^[a-zA-Z0-9'\-]*$", first_name):
                errors[field] = _(
                    "Accepted characters are letters, numbers, single quote (') and minus (-)."
                )
            last_name: str = (
                WebContext.form_data_to_str(data, field := 'last_name') or ''
            )
            if not last_name:
                errors[field] = _('This field is required.')
            elif not re.match(r"^[a-zA-Z0-9'\-]*$", last_name):
                errors[field] = _(
                    "Accepted characters are letters, numbers, single quote (') and minus (-)."
                )
            if 'first_name' not in errors and 'last_name' not in errors:
                full_name: str = Player.player_full_name(first_name, last_name)
                check_full_name_not_used: bool
                if account and action == FormAction.UPDATE:
                    check_full_name_not_used = (
                        account.full_name
                        != Player.player_full_name(first_name, last_name)
                    )
                else:
                    check_full_name_not_used = True
                if (
                    check_full_name_not_used
                    and full_name in event.user_accounts_sorted_by_name
                ):
                    errors[field] = _(
                        'Account [{account_name}] already exists.'
                    ).format(account_name=full_name)
            if action == FormAction.CREATE:
                password = WebContext.form_data_to_str(data, field := 'password')
                if not password:
                    errors[field] = _('This field is required.')
        # no validation on the access levels, an empty list is accepted.
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
    ) -> Template | ClientRedirect | Redirect:
        web_context = AccountAdminWebContext(request, event_uniq_id)
        if web_context.error:
            return web_context.error
        flat_data = WebContext.flatten_list_data(data)
        if errors := self._validate_account_form_data(
            flat_data, web_context, FormAction.CREATE
        ):
            return self._admin_event_access_render(
                web_context,
                self._account_form_modal_context(
                    web_context, FormAction.CREATE, flat_data, errors
                ),
            )
        event = web_context.get_admin_event()
        password = WebContext.form_data_to_str(flat_data, 'password')
        password_hash = PasswordHasher().hash(password) if password else None
        account = event.create_account(
            StoredAccount(
                id=None,
                active=WebContext.form_data_to_bool(flat_data, 'active'),
                access_levels=WebContext.form_data_to_list_str(
                    flat_data, 'access_levels'
                ),
                tournament_ids=WebContext.form_data_to_list_int(
                    flat_data, 'tournament_ids'
                )
                or None,
                first_name=WebContext.form_data_to_str(flat_data, 'first_name'),
                last_name=WebContext.form_data_to_str(flat_data, 'last_name'),
                password_hash=password_hash,
            )
        )
        Message.success(
            request,
            _('Account [{account_name}] has been created.').format(
                account_name=account.full_name
            ),
        )
        return self._admin_event_access_render(web_context)

    @patch(
        path='/admin/account-update/{event_uniq_id:str}/{account_id:int}',
        name='admin-account-update',
    )
    async def htmx_admin_account_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        account_id: int,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect | Redirect:
        web_context = AccountAdminWebContext(request, event_uniq_id, account_id)
        if web_context.error:
            return web_context.error
        flat_data = WebContext.flatten_list_data(data)
        if errors := self._validate_account_form_data(
            flat_data, web_context, FormAction.UPDATE
        ):
            return self._admin_event_access_render(
                web_context,
                self._account_form_modal_context(
                    web_context, FormAction.UPDATE, flat_data, errors
                ),
            )
        event = web_context.get_admin_event()
        account = web_context.get_admin_account()
        stored_account = account.stored_account
        if not account.anonymous:
            stored_account.active = WebContext.form_data_to_bool(flat_data, 'active')
            stored_account.first_name = WebContext.form_data_to_str(
                flat_data, 'first_name'
            )
            stored_account.last_name = WebContext.form_data_to_str(
                flat_data, 'last_name'
            )
            password = WebContext.form_data_to_str(flat_data, 'password')
            if password:
                stored_account.password_hash = PasswordHasher().hash(password)
        stored_account.access_levels = WebContext.form_data_to_list_str(
            flat_data, 'access_levels'
        )
        stored_account.tournament_ids = (
            WebContext.form_data_to_list_int(flat_data, 'tournament_ids') or None
        )
        event.update_account(stored_account)
        Message.success(
            request,
            _('Unauthenticated access has been updated.')
            if account.anonymous
            else _('Account [{account_name}] has been updated.').format(
                account_name=account.full_name
            ),
        )
        return self._admin_event_access_render(web_context)

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
    ) -> Template | ClientRedirect | Redirect:
        web_context = AccountAdminWebContext(request, event_uniq_id, account_id)
        if web_context.error:
            return web_context.error
        event = web_context.get_admin_event()
        account = web_context.get_admin_account()
        event.delete_account(account)
        Message.success(
            request,
            _('Account [{account_name}] has been deleted.').format(
                account_name=account.full_name
            ),
        )
        return self._admin_event_access_render(web_context)
