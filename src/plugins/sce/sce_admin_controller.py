import copy
from datetime import datetime, timedelta
from functools import cached_property
from typing import Annotated, Any

from litestar import get, post, patch
from litestar.enums import RequestEncodingType
from litestar.exceptions import ClientException, NotFoundException
from litestar.params import Parameter, Body
from litestar.response import Redirect
from litestar_htmx import HTMXRequest, ClientRedirect, HTMXTemplate

from common import SharlyChessException
from common.i18n import _
from common.logger import get_logger
from data.access_levels.actions import AuthAction
from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_session import (
    SCESession,
    SCE_BASE_URL,
    SCE_SYNC_DELAY,
    SCE_UPLOAD_DELAY,
)
from plugins.sce.sce_background_uploader import (
    schedule_upload,
    upload_event_tournaments,
)
from plugins.sce.utils import SCETokens, SCEEventPluginData, SCEUtils
from utils.date_time import format_datetime
from web.controllers.admin.base_admin_controller import (
    BaseAdminController,
    AdminWebContext,
)
from web.controllers.base_controller import WebContext
from web.messages import Message
from web.urls import build_internal_get_url, index_url, admin_event_url
from web.utils import PKCEUtils

logger = get_logger()


CODE_VERIFIER_EXPIRATION_DELAY = 5


class SCEWebContext(AdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        tournament_id: int | None = None,
        reload_event: bool = False,
    ):
        super().__init__(request, reload_event=reload_event)
        event = self.get_admin_event()
        self.tournament: Tournament | None = None
        if tournament_id:
            try:
                self.tournament = event.tournaments_by_id[tournament_id]
            except KeyError:
                raise NotFoundException(f'Tournament [{tournament_id}] not found.')

    def get_tournament(self) -> Tournament:
        assert self.tournament is not None
        return self.tournament

    @property
    def sync_modal_context(self) -> dict[str, Any]:
        event = self.get_admin_event()

        plugin_data = SCEUtils.get_event_plugin_data(event)
        new_sce_tournament_options = copy.copy(plugin_data.tournament_names_by_id)
        new_local_tournament_options: dict[str, str] = {}
        for tournament in event.tournaments:
            sce_id = SCEUtils.get_tournament_plugin_data(tournament).id
            if sce_id and sce_id in new_sce_tournament_options:
                del new_sce_tournament_options[sce_id]
            elif tournament in self.allowed_tournaments:
                new_local_tournament_options[str(tournament.id)] = tournament.name

        return self.table_context | {
            'new_sce_tournament_options': new_sce_tournament_options,
            'new_local_tournament_options': new_local_tournament_options,
        }

    @property
    def table_context(self) -> dict[str, Any]:
        return self.template_context | {
            'sce_allowed_tournaments': self.sce_allowed_tournaments,
            'sce_event_status': SCEUtils.resolve_event_status(self.get_admin_event()),
        }

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'tournament': self.tournament,
            'SCE_BASE_URL': SCE_BASE_URL,
            'SCE_SYNC_DELAY': SCE_SYNC_DELAY,
            'SCE_UPLOAD_DELAY': SCE_UPLOAD_DELAY,
            'sce_utils': SCEUtils,
            'format_datetime': format_datetime,
        }

    @cached_property
    def sce_tournaments(self) -> list[Tournament]:
        return [
            tournament
            for tournament in self.get_admin_event().tournaments
            if SCEUtils.get_tournament_plugin_data(tournament).id
        ]

    @cached_property
    def allowed_tournaments(self) -> list[Tournament]:
        return self.client.allowed_tournaments_for_action(AuthAction.PUBLISH_RESULTS)

    @cached_property
    def sce_allowed_tournaments(self) -> list[Tournament]:
        return [
            tournament
            for tournament in self.sce_tournaments
            if tournament in self.allowed_tournaments
        ]


class SCEAdminController(BaseAdminController):
    OAUTH_CODE_VERIFIER_BY_STATE: dict[str, tuple[str, datetime]] = {}

    @classmethod
    def trigger_oauth(
        cls,
        request: HTMXRequest,
        redirect_action: str,
        sce_event_id: str | None = None,
        event_uniq_id: str | None = None,
    ):
        state = PKCEUtils.generate_state()
        code_verifier = PKCEUtils.generate_code_verifier()
        code_expires_at = datetime.now() + timedelta(
            minutes=CODE_VERIFIER_EXPIRATION_DELAY
        )
        cls.OAUTH_CODE_VERIFIER_BY_STATE[state] = code_verifier, code_expires_at
        route_params = {'action': redirect_action}
        if event_uniq_id:
            route_params['event_uniq_id'] = event_uniq_id
        redirect_uri = build_internal_get_url(
            request, 'sce-oauth-callback', route_params=route_params
        )
        oauth_url = SCESession.build_oauth_url(
            redirect_uri=redirect_uri,
            code_challenge=PKCEUtils.generate_code_challenge(code_verifier),
            state=state,
            event_id=sce_event_id,
        )
        logger.info('Sharly-Chess.com OAuth ongoing')
        logger.debug(
            'Sharly-Chess.com OAuth - code verifier: %s, expires at: %s, url: %s',
            code_verifier,
            code_expires_at.isoformat(),
            oauth_url,
        )
        return ClientRedirect(oauth_url)

    @get(
        path='/sce/oauth/event-import',
        name='sce-oauth-event-import',
    )
    async def htmx_sce_oauth_event_import(self, request: HTMXRequest) -> ClientRedirect:
        return self.trigger_oauth(request, redirect_action='import-event')

    @get(
        path='/sce/oauth/event-connect/{event_uniq_id:str}',
        name='sce-oauth-event-connect',
    )
    async def htmx_sce_oauth_event_connect(
        self, request: HTMXRequest
    ) -> ClientRedirect:
        event = SCEWebContext(request).get_admin_event()
        return self.trigger_oauth(
            request,
            redirect_action='connect-event',
            sce_event_id=SCEUtils.get_event_plugin_data(event).id,
            event_uniq_id=event.uniq_id,
        )

    @classmethod
    def _import_event(cls, sce_event_id: str, tokens: SCETokens) -> Event:
        uniq_id = EventLoader().get_unused_event_uniq_id(sce_event_id)
        EventDatabase(uniq_id).create()
        try:
            event = EventLoader().load_event(uniq_id)
            plugin_data = SCEEventPluginData(
                id=sce_event_id, tokens=tokens, last_sync_at=datetime.now()
            )
            event.plugin_data[PLUGIN_NAME] = plugin_data
            event.stored_event.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
            session = SCESession(event)
            session.update_event_from_sce_event(is_create=True)
            return session.event
        finally:
            EventDatabase(uniq_id).file.unlink(missing_ok=True)

    @get(
        path=[
            '/sce/oauth/callback/{action:str}',
            '/sce/oauth/callback/{action:str}/{event_uniq_id:str}',
        ],
        name='sce-oauth-callback',
    )
    async def htmx_sce_oauth_callback(
        self,
        request: HTMXRequest,
        action: str,
        event_uniq_id: str | None,
        state_param: Annotated[str, Parameter(query='state')],
        sce_event_id: Annotated[str, Parameter(query='event_id')] = '',
        code: str = '',
        error: str = '',
    ) -> Redirect:
        error_message: str | None = None
        tokens: SCETokens | None = None
        if not sce_event_id:
            error_message = _('Sharly-Chess.com authorization canceled.')
        elif error:
            logger.error(error)
            error_message = _(
                'Authorization failed, consult the logs for more details.'
            )
        elif state_param not in self.OAUTH_CODE_VERIFIER_BY_STATE:
            error_message = _('Authorization failed, possible CSRF attack!')
        elif not code:
            raise ClientException('Missing parameter: code')
        else:
            code_verifier, expires_at = self.OAUTH_CODE_VERIFIER_BY_STATE[state_param]
            if expires_at < datetime.now():
                error_message = _('Authorization expired, please try again.')
            try:
                tokens = SCESession.get_tokens_from_code(
                    code, code_verifier, str(request.url).split('?')[0]
                )
            except SharlyChessException:
                error_message = _(
                    'Authorization failed, consult the logs for more details.'
                )
        if not tokens:
            Message.error(request, error_message or '')
        else:
            logger.info('Sharly-Chess.com OAuth successful')
            match action:
                case 'import-event':
                    try:
                        event = self._import_event(sce_event_id, tokens)
                        Message.success(
                            request,
                            _('Event [{event}] successfully imported!').format(
                                event=event.name
                            ),
                        )
                        event_uniq_id = event.uniq_id
                    except SharlyChessException as e:
                        logger.error(str(e))
                        Message.error(
                            request,
                            _('An error occurred, consult the logs for more details.'),
                        )
                case 'connect-event':
                    web_context = SCEWebContext(request)
                    event = web_context.get_admin_event()
                    plugin_data = SCEUtils.get_event_plugin_data(event)
                    plugin_data.id = sce_event_id
                    plugin_data.tokens = tokens
                    SCEUtils.update_event_plugin_data(event, plugin_data, write=False)
                    try:
                        SCESession(event).update_event_from_sce_event()
                        Message.success(
                            request,
                            _(
                                'Event [{event}] successfully connected to Sharly-Chess.com!'
                            ).format(event=event.name),
                        )
                    except SharlyChessException as e:
                        logger.error(str(e))
                        Message.error(
                            request,
                            _('An error occurred, consult the logs for more details.'),
                        )
                case _:
                    raise NotFoundException(f'Unknown action [{action}]')
        return Redirect(
            admin_event_url(request, event_uniq_id)
            if event_uniq_id
            else index_url(request)
        )

    @classmethod
    def _render_sync_modal(
        cls, web_context: SCEWebContext, succes_message: str | None = None
    ) -> HTMXTemplate:
        return cls._render_modal(
            template_name='/sce_sync_modal.html',
            template_context=web_context.sync_modal_context
            | {'success_message': succes_message},
        )

    @get(
        path='/sce/sync-modal/{event_uniq_id:str}',
        name='sce-sync-modal',
    )
    async def htmx_sce_sync_modal(
        self,
        request: HTMXRequest,
    ) -> HTMXTemplate:
        web_context = SCEWebContext(request)
        event = web_context.get_admin_event()
        try:
            # Update the event status / ensure all links will work in case slugs have changed
            SCESession(event).update_event_from_sce_event()
        except SharlyChessException as e:
            logger.error(str(e))
        return self._render_sync_modal(web_context)

    @staticmethod
    def _render_upload_table(web_context: SCEWebContext) -> HTMXTemplate:
        return HTMXTemplate(
            template_name='/sce_upload_table.html',
            context=web_context.table_context,
            re_target='#sce-upload-table',
            re_swap='outerHTML',
        )

    @get(
        path='/sce/sync-modal/upload-table/{event_uniq_id:str}',
        name='sce-sync-modal-upload-table',
    )
    async def htmx_sce_sync_modal_upload_table(
        self, request: HTMXRequest
    ) -> HTMXTemplate:
        return self._render_upload_table(SCEWebContext(request))

    @get(
        path='/sce/event-status-section/{event_uniq_id:str}',
        name='sce-event-status-section',
    )
    async def htmx_sce_event_status_section(self, request: HTMXRequest) -> HTMXTemplate:
        web_context = SCEWebContext(request)
        return HTMXTemplate(
            template_name='/sce_event_status_section.html',
            context=web_context.table_context,
            re_target='#sce-event-status-section',
            re_swap='outerHTML',
        )

    @patch(
        path='/sce/update-event-auto-player-sync/{event_uniq_id:str}',
        name='sce-update-event-auto-player-sync',
    )
    async def htmx_sce_update_event_auto_player_sync(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> HTMXTemplate:
        web_context = SCEWebContext(request)
        event = web_context.get_admin_event()
        plugin_data = SCEUtils.get_event_plugin_data(event)
        plugin_data.auto_player_sync = WebContext.form_data_to_bool(
            data, 'auto_player_sync'
        )
        SCEUtils.update_event_plugin_data(event, plugin_data)
        return HTMXTemplate(template_name='/common/empty.html')

    @patch(
        path='/sce/update-event-auto-upload/{event_uniq_id:str}',
        name='sce-update-event-auto-upload',
    )
    async def htmx_sce_update_event_auto_upload(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> HTMXTemplate:
        web_context = SCEWebContext(request)
        event = web_context.get_admin_event()
        plugin_data = SCEUtils.get_event_plugin_data(event)
        plugin_data.auto_upload = WebContext.form_data_to_bool(data, 'auto_upload')
        SCEUtils.update_event_plugin_data(event, plugin_data)
        return self._render_upload_table(web_context)

    @patch(
        path='/sce/update-tournament-auto-upload/{event_uniq_id:str}/{tournament_id:int}',
        name='sce-update-tournament-auto-upload',
    )
    async def htmx_sce_update_tournament_auto_upload(
        self,
        request: HTMXRequest,
        tournament_id: int,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> HTMXTemplate:
        web_context = SCEWebContext(request, tournament_id)
        tournament = web_context.get_tournament()

        plugin_data = SCEUtils.get_tournament_plugin_data(tournament)
        plugin_data.auto_upload = WebContext.form_data_to_bool(
            data, f'tournament_auto_upload_{tournament.id}'
        )
        SCEUtils.update_tournament_plugin_data(tournament, plugin_data)
        return HTMXTemplate(
            template_name='/sce_tournament_statuses.html',
            context=web_context.table_context,
            re_target=f'#tournament-upload-statuses-{tournament.id}',
            re_swap='innerHTML',
        )

    @post(
        path='/sce/upload-tournament-results/{event_uniq_id:str}/{tournament_id:int}',
        name='sce-upload-tournament-results',
    )
    async def htmx_sce_upload_tournament_results(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> HTMXTemplate:
        web_context = SCEWebContext(request, tournament_id)
        tournament = web_context.get_tournament()
        schedule_upload(tournament)
        return self._render_upload_table(web_context)

    @post(
        path='/sce/upload-all-tournament-results/{event_uniq_id:str}',
        name='sce-upload-all-tournament-results',
    )
    async def htmx_sce_upload_all_tournament_results(
        self, request: HTMXRequest
    ) -> HTMXTemplate:
        web_context = SCEWebContext(request)
        upload_event_tournaments(web_context.sce_allowed_tournaments)
        message = _('Upload started for all tournaments.')
        return self._render_sync_modal(web_context, message)

    @post(
        path='/sce/sync-players/{event_uniq_id:str}',
        name='sce-sync-players',
    )
    async def htmx_sce_sync_players(self, request: HTMXRequest) -> HTMXTemplate:
        web_context = SCEWebContext(request)
        # TODO (Molrn) Implement player sync
        message = 'Players synchronized.'
        return self._render_sync_modal(web_context, message)

    @post(
        path='/sce/import-tournaments/{event_uniq_id:str}',
        name='sce-import-tournaments',
    )
    async def htmx_sce_import_tournaments(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> HTMXTemplate:
        web_context = SCEWebContext(request)
        flat_data = WebContext.flatten_list_data(data)
        sce_tournament_ids = WebContext.form_data_to_list_str(
            flat_data, 'sce_tournament_ids'
        )
        # TODO (Molrn) Implement tournaments import
        message = f'Tournaments [{", ".join(sce_tournament_ids)}] imported.'
        return self._render_sync_modal(web_context, message)

    @post(
        path='/sce/upload-local-tournaments/{event_uniq_id:str}',
        name='sce-upload-local-tournaments',
    )
    async def htmx_sce_upload_local_tournaments(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> HTMXTemplate:
        web_context = SCEWebContext(request)
        flat_data = WebContext.flatten_list_data(data)
        tournament_ids = WebContext.form_data_to_list_int(flat_data, 'tournament_ids')
        # TODO (Molrn) Implement local tournaments upload
        message = f'Tournaments {tournament_ids} uploaded.'
        return self._render_sync_modal(web_context, message)
