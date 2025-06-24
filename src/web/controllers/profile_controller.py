from typing import Annotated

from litestar import post, get
from litestar.plugins.htmx import HTMXRequest, ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, Redirect
from litestar_htmx import HTMXTemplate

from common.i18n import _
from data.auth.entities import Account
from web.controllers.admin.base_event_admin_controller import BaseEventAdminWebContext
from web.controllers.base_controller import WebContext, BaseController
from web.session import SessionHandler
from web.urls import admin_event_url


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
            trigger_event='modal_opened',
            after='settle',
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
    ) -> Template | ClientRedirect:
        web_context: ProfileWebContext = ProfileWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=None,
        )
        if web_context.error:
            return web_context.error
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
    ) -> Template | ClientRedirect | Redirect:
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
                if account.password == password:
                    SessionHandler.store_account(
                        request,
                        web_context.admin_event,
                        account,
                    )
                else:
                    errors[field] = _('Password does not match.')
                    data[field] = ''
            except KeyError:
                errors['username'] = _('Invalid username.')
        if errors:
            return self._render_profile_modal(
                web_context,
                data=data,
                errors=errors,
            )
        return Redirect(
            admin_event_url(request, event_uniq_id=web_context.admin_event.uniq_id)
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
    ) -> Template | ClientRedirect | Redirect:
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
        return Redirect(
            admin_event_url(request, event_uniq_id=web_context.admin_event.uniq_id)
        )
