from typing import Annotated, Any
from litestar import get, post
from litestar.response import Template
from litestar_htmx import HTMXRequest, ClientRedirect, HTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body

from common.i18n import _
from common.network import NetworkMonitor
from plugins.ffe.engine.ffe_session import FFESession
from plugins.ffe.ffe_session_handler import FFESessionHandler
from plugins.ffe.util import PlayerFFELicence
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.admin.player_admin_controller import PlayerAdminController


class FfeAdminEventController(BaseEventAdminController):
    @get(
        path='/ffe/event/{event_uniq_id:str}/players',
        name='ffe-admin-event-players-tab',
        cache=1,
    )
    async def htmx_ffe_event_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        admin_players_filter_leagues: list[str] | None = None,
        admin_players_filter_licences: list[int] | None = None,
    ) -> Template | ClientRedirect:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=None,
        )
        if web_context.error:
            return web_context.error

        if admin_players_filter_leagues is not None:
            FFESessionHandler.set_session_admin_players_filter_leagues(
                request,
                [
                    league
                    for league in admin_players_filter_leagues
                    if league  # '' must be ignored
                ],
            )
        elif admin_players_filter_licences is not None:
            FFESessionHandler.set_session_admin_players_filter_licences(
                request,
                [
                    PlayerFFELicence(query_param)
                    for query_param in admin_players_filter_licences
                    if query_param >= 0  # -1 must be ignored
                ],
            )

        return PlayerAdminController._admin_event_players_render(
            request,
            event_uniq_id=event_uniq_id,
        )

    @post(
        path='/ffe/test-auth',
        name='ffe-test-auth',
    )
    async def htmx_ffe_test_auth(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, Any],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        ffe_auth_valid: bool | None = None

        if NetworkMonitor.connected():
            ffe_id = data['ffe_id']
            ffe_password = data['ffe_password']

            if ffe_id and ffe_password:
                ffe_auth_valid = FFESession(tournament=None, debug=False).test_auth(
                    ffe_id=ffe_id, ffe_password=ffe_password
                )

        errors = {}
        # Compare to False, None means 'unable to check'
        if ffe_auth_valid is False:
            errors['ffe_id'] = _('Invalid FFE ID or password.')
            errors['ffe_password'] = _('Invalid FFE ID or password.')

        return HTMXTemplate(
            template_name='ffe_tournament_ffe_auth_fields.html',
            context={
                'data': {
                    'ffe_id': data['ffe_id'],
                    'ffe_password': data['ffe_password'],
                },
                'ffe_auth_valid': ffe_auth_valid is True,
                'ffe_password_visible': data['ffe_password_visible'] == 'true',
                'errors': errors,
            },
        )
