from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash
from litestar import post, get
from litestar.plugins.htmx import HTMXRequest, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar_htmx import HTMXTemplate

from common.i18n import _
from data.auth.entities import Account
from database.sqlite.event.event_database import EventDatabase
from web.controllers.admin.base_event_admin_controller import BaseEventAdminWebContext
from web.controllers.base_controller import WebContext, BaseController
from web.session import SessionHandler


class ProfileWebContext(BaseEventAdminWebContext):
    pass


class ProfileController(BaseController):
    @staticmethod
    def _render_profile_modal(
        web_context: ProfileWebContext,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        return HTMXTemplate(
            template_name='common/profile/profile_modal.html',
            context=web_context.template_context
            | {
                'data': data or {},
                'errors': errors or {},
            },
            re_target='#modal-wrapper',
        )

    @get(
        path=[
            '/profile-modal/{event_uniq_id:str}',
            '/profile-modal',
        ],
        name='profile-modal',
        cache=1,
    )
    async def htmx_profile_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str | None,
        locale: str | None = None,
    ) -> Template | ClientRedirect:
        web_context: ProfileWebContext = ProfileWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=None,
        )
        if web_context.error:
            return web_context.error

        self.set_locale(request, locale)

        return self._render_profile_modal(web_context)

    @post(
        path='/profile-login/{event_uniq_id:str}',
        name='profile-login',
    )
    async def htmx_profile_login(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        web_context: ProfileWebContext = ProfileWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        field: str
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        username: str | None = WebContext.form_data_to_str(data, field := 'username')
        if not username:
            errors[field] = _('Please enter the username.')
        else:
            password: str | None = WebContext.form_data_to_str(
                data, field := 'password'
            )
            try:
                account: Account = web_context.admin_event.accounts_by_username[
                    username
                ]
                ph = PasswordHasher()
                try:
                    pw_hash = account.password_hash
                    # NOTE(Amaras): because of a peculiar design decision from
                    # the author of argon2-cffi, the only return value is True,
                    # all other outcomes result in an exception, and it is dangerous
                    # to change that design decision now.
                    # Therefore, if the verification does not error, then it has
                    # succeded.
                    ph.verify(pw_hash, password)
                    # NOTE(Amaras): hashing parameters might change, either through
                    # our own choice, or when the default parameters are improved.
                    # It is thus necessary to check if a re-hashing is needed as soon
                    # as possible, and rehash the password (which we verified is correct)
                    # if parameters changed.
                    if ph.check_needs_rehash(pw_hash):
                        account.update_password(ph.hash(password))
                        # FIXME(Amaras): because there is no reference to a
                        # database inside both Account and StoredAccount,
                        # this is pretty much the only place to update it.
                        # This lack of abstraction is alright for a POC, but
                        # bad practice otherwise.
                        with EventDatabase(event_uniq_id) as event_database:
                            account.stored_account = (
                                event_database.update_stored_account(
                                    account.stored_account
                                )
                            )
                except (VerifyMismatchError, VerificationError):
                    errors['field'] = _('Invalid username or password.')
                    data[field] = ''
                except InvalidHash:
                    errors['field'] = _(
                        'Something went wrong. Please ask your administrator to recreate your account.'
                    )
                else:
                    SessionHandler.store_account(
                        request,
                        web_context.admin_event,
                        account,
                    )

                    # Update the web context to reflect the login
                    web_context: ProfileWebContext = ProfileWebContext(
                        request,
                        event_uniq_id=event_uniq_id,
                        data=data,
                    )
            except KeyError:
                errors['username'] = _('Invalid username or password.')

        return self._render_profile_modal(
            web_context,
            data=data,
            errors=errors,
        )

    @post(
        path='/profile-logout/{event_uniq_id:str}',
        name='profile-logout',
    )
    async def htmx_profile_logout(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        web_context: ProfileWebContext = ProfileWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        assert web_context.admin_event is not None
        SessionHandler.store_account(
            request,
            web_context.admin_event,
            None,
        )

        # Update the web context to reflect the login
        web_context: ProfileWebContext = ProfileWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=data,
        )

        return self._render_profile_modal(
            web_context,
            data=data,
        )
