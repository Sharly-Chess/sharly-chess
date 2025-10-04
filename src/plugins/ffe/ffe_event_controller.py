from functools import partial
from typing import Annotated, Any
from litestar import get, post
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body

from common import format_timestamp_date_time
from common.i18n import _
from common.network import NetworkMonitor
from data.access_levels.actions import AuthAction
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_background_uploader import FfeBackgroundUploader, FfeUploadStatus
from plugins.ffe.ffe_session import FFESession
from plugins.ffe.ffe_session_handler import FFESessionHandler
from plugins.ffe.utils import FFEUtils, PlayerFFELicence
from plugins.utils import PluginUtils
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.admin.player_admin_controller import PlayerAdminController
from web.controllers.admin.tournament_admin_controller import TournamentAdminWebContext
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard, TournamentActionGuard

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FfeAdminEventController(BaseEventAdminController):
    guards = []

    @get(
        path='/ffe/event/{event_uniq_id:str}/players',
        name='ffe-admin-event-players-tab',
        guards=[EventGuard(), ActionGuard(AuthAction.VIEW_PLAYERS_TAB)],
    )
    async def htmx_ffe_event_tab(
        self,
        request: HTMXRequest,
        admin_players_filter_leagues: list[str] | None = None,
        admin_players_filter_licences: list[int] | None = None,
    ) -> Template:
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
        PlayerAdminController.set_players_search_results(request)
        return PlayerAdminController._admin_event_players_render(
            request, reload_event=True
        )

    @post(
        path='/ffe/test-auth',
        name='ffe-test-auth',
    )
    async def htmx_ffe_test_auth(
        self,
        data: Annotated[
            dict[str, Any],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        ffe_auth_valid: bool | None = None

        if NetworkMonitor.connected():
            ffe_id: int = 0
            try:
                ffe_id = WebContext.form_data_to_int(data, 'ffe_id') or 0
            except ValueError:
                pass
            ffe_password: str = WebContext.form_data_to_str(data, 'ffe_password') or ''

            if ffe_id and ffe_password:
                ffe_auth_valid = FFESession(tournament=None).test_auth(
                    ffe_id=ffe_id, ffe_password=ffe_password
                )

        errors = {}
        # Compare to False, None means 'unable to check'
        if ffe_auth_valid is False:
            errors['ffe_id'] = _('Invalid FFE certification number or password.')
            errors['ffe_password'] = _('Invalid FFE certification number or password.')

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

    @get(
        path='/ffe/ffe-upload-modal/{event_uniq_id:str}',
        name='ffe-upload-modal',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_ffe_upload_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)

        FfeBackgroundUploader.update_eligible_tournaments(web_context.get_admin_event())

        return HTMXTemplate(
            template_name='/ffe_upload_modal.html',
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
            context=web_context.template_context
            | {
                'format_timestamp_date_time': format_timestamp_date_time,
                'result_id': FfeBackgroundUploader.result_id,
                'upload_status_messages': FfeBackgroundUploader.upload_status_messages,
                'ffe_utils': FFEUtils,
            },
        )

    @staticmethod
    def _render_upload_results(
        web_context: BaseEventAdminWebContext,
    ) -> Template:
        return HTMXTemplate(
            template_name='/ffe_upload_results.html',
            context=web_context.template_context
            | {
                'format_timestamp_date_time': format_timestamp_date_time,
                'result_id': FfeBackgroundUploader.result_id,
                'upload_status_messages': FfeBackgroundUploader.upload_status_messages,
                'ffe_utils': FFEUtils,
            },
        )

    @get(
        path='/ffe/ffe-upload-results/{event_uniq_id:str}',
        name='ffe-upload-results',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_ffe_upload_results(self, request: HTMXRequest) -> Template:
        web_context = BaseEventAdminWebContext(request)
        return self._render_upload_results(web_context)

    @post(
        path='/ffe/ffe-upload/{event_uniq_id:str}',
        name='ffe-upload',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_ffe_upload(self, request: HTMXRequest) -> Template:
        web_context = BaseEventAdminWebContext(request)
        FfeBackgroundUploader.upload_event(web_context.get_admin_event())
        return self._render_upload_results(web_context)

    @post(
        path='/ffe/ffe-upload-tournament/{event_uniq_id:str}/{tournament_id:int}',
        name='ffe-upload-tournament',
        guards=[EventGuard(), TournamentActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_ffe_upload_tournament(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()

        FfeBackgroundUploader.schedule_upload(tournament, True)

        return self._render_upload_results(web_context)

    @get(
        path='/ffe/nav-upload-button/{event_uniq_id:str}',
        name='ffe-nav-upload-button',
        guards=[EventGuard()],
    )
    async def htmx_admin_ffe_nav_upload_button(self, request: HTMXRequest) -> Template:
        web_context = BaseEventAdminWebContext(request)
        admin_event = web_context.admin_event
        assert admin_event is not None

        has_upload_error = False
        statuses = FfeBackgroundUploader.upload_status_messages
        tournaments = admin_event.tournaments
        for tournament in tournaments:
            result = statuses.get(
                FfeBackgroundUploader.result_id(admin_event.uniq_id, tournament.id),
                None,
            )
            if result and result.status == FfeUploadStatus.ERROR:
                has_upload_error = True
                break

        return HTMXTemplate(
            template_name='/ffe_upload_button.html',
            context=web_context.template_context
            | {
                'has_upload_error': has_upload_error,
            },
        )
