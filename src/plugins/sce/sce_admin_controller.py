from datetime import datetime, timedelta
from typing import Annotated

from litestar import get
from litestar.exceptions import ClientException, NotFoundException
from litestar.params import Parameter
from litestar.response import Redirect
from litestar_htmx import HTMXRequest, ClientRedirect

from common import SharlyChessException
from common.i18n import _
from common.logger import get_logger
from data.event import Event
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from plugins.sce import PLUGIN_NAME
from plugins.sce.sce_session import SCESession
from plugins.sce.utils import SCETokens, SCEEventPluginData
from web.controllers.admin.base_admin_controller import (
    BaseAdminController,
)
from web.messages import Message
from web.urls import build_internal_get_url, index_url, admin_event_url
from web.utils import PKCEUtils

logger = get_logger()


CODE_VERIFIER_EXPIRATION_DELAY = 5


class SCEAdminController(BaseAdminController):
    OAUTH_CODE_VERIFIER_BY_STATE: dict[str, tuple[str, datetime]] = {}

    @get(
        path='/sce/oauth/event-import',
        name='sce-oauth-event-import',
    )
    async def htmx_sce_oauth_event_import(
        self,
        request: HTMXRequest,
    ) -> ClientRedirect:
        state = PKCEUtils.generate_state()
        code_verifier = PKCEUtils.generate_code_verifier()
        self.__class__.OAUTH_CODE_VERIFIER_BY_STATE[state] = (
            code_verifier,
            datetime.now() + timedelta(minutes=CODE_VERIFIER_EXPIRATION_DELAY),
        )
        oauth_url = SCESession.build_oauth_url(
            redirect_uri=build_internal_get_url(
                request,
                'sce-oauth-callback',
                route_params={'action': 'import-event'},
            ),
            code_challenge=PKCEUtils.generate_code_challenge(code_verifier),
            state=state,
        )
        logger.info('Sharly-Chess.com OAuth ongoing at %s', oauth_url)
        return ClientRedirect(oauth_url)

    @classmethod
    def _import_event(cls, sce_event_id: str, tokens: SCETokens) -> Event:
        uniq_id = EventLoader().get_unused_event_uniq_id(sce_event_id)
        EventDatabase(uniq_id).create()
        try:
            event = EventLoader().load_event(uniq_id)
            plugin_data = SCEEventPluginData(id=sce_event_id, tokens=tokens)
            event.plugin_data[PLUGIN_NAME] = plugin_data
            event.stored_event.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
            session = SCESession(event)
            session.update_event_from_sce_event(is_create=True)
            return session.event
        finally:
            EventDatabase(uniq_id).file.unlink(missing_ok=True)

    @get(
        path='/sce/oauth/callback/{action:str}',
        name='sce-oauth-callback',
    )
    async def htmx_sce_oauth_callback(
        self,
        request: HTMXRequest,
        action: str,
        state_param: Annotated[str, Parameter(query='state')],
        sce_event_id: Annotated[str, Parameter(query='event_id')],
        code: str = '',
        error: str = '',
        event_uniq_id: str | None = None,
    ) -> Redirect:
        error_message: str | None = None
        tokens: SCETokens | None = None
        if error:
            logger.error(error)
            error_message = _(
                'Authorization failed, consult the logs for more details.'
            )
        elif state_param not in self.OAUTH_CODE_VERIFIER_BY_STATE:
            error_message = _('Authorization failed, possible CSRF attack!')
        elif not code or not sce_event_id:
            raise ClientException('Missing parameters.')
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
                case _:
                    raise NotFoundException(f'Unknown action [{action}]')
        return Redirect(
            admin_event_url(request, event_uniq_id)
            if event_uniq_id
            else index_url(request)
        )
