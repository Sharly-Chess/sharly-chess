from typing import Any
from litestar import get
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate, ClientRedirect

from web.controllers.admin.base_event_admin_controller import BaseEventAdminController, BaseEventAdminWebContext

from .util import PlayerFFELicence
from .ffe_session_handler import FFESessionHandler

class FfeAdminEventController(BaseEventAdminController):

    @get(
        path='/ffe/event/{event_uniq_id:str}/{admin_event_tab:str}',
        name='ffe-admin-event-tab',
        cache=1,
    )
    async def htmx_ffe_event_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        admin_event_tab: str,
        admin_players_filter_leagues: list[str] | None = None,
        admin_players_filter_licences: list[int] | None = None,
    ) -> Template | ClientRedirect:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            admin_event_tab=admin_event_tab,
            data=None,
        )
        if web_context.error:
            return web_context.error
        
        match admin_event_tab:
            case 'players':
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
            case _:
                pass

        template_context: dict[str, Any] = self._get_admin_event_render_context(
            web_context
        )
        
        return HTMXTemplate(
            template_name='admin/event_layout.html',
            context=template_context
        )
